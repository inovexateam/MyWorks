"""
Confidence scorer — the core decision engine.

Takes raw reference counts + reachability data and assigns:
  - A dead reason (why we think it's dead)
  - A confidence percentage (how sure we are)
  - A list of suppressions (reasons it might still be live)

The key insight: false positives are MUCH worse than false negatives.
Better to miss 20 dead symbols than to accidentally tell someone to
delete a symbol called via reflection or dependency injection.

Scoring algorithm:
  Start at 100% confidence.
  Subtract for every reason it might actually be live.
  Final score maps to HIGH/MEDIUM/LOW confidence tiers.
"""

import re
import subprocess
from pathlib import Path
from core.models import (
    SymbolDef, SymbolKind, DeadSymbol, DeadReason, Confidence, ScanResult
)


# ── Suppression rules (things that reduce confidence) ─────────────────────────

REFLECTION_PATTERNS = re.compile(
    r'Activator\.Create|GetType\(\)|typeof\s*\(.*\)|'
    r'Assembly\.GetTypes|MethodInfo|PropertyInfo|FieldInfo|'
    r'Invoke\(|DynamicInvoke|Expression\.Call|'
    r'JsonProperty|JsonIgnore|XmlElement|DataMember|'
    r'Column\(|Table\(|Key\b',
    re.IGNORECASE
)

DI_PATTERNS = re.compile(
    r'services\.(AddScoped|AddSingleton|AddTransient|AddHostedService)|'
    r'@Injectable|@Autowired|@Bean|@Component\b|@Service\b|@Repository\b|'
    r'container\.Register|container\.Bind|Bind<|To<',
    re.IGNORECASE
)

INTERFACE_IMPL_PATTERN = re.compile(
    r':\s*(I[A-Z]\w+)|implements\s+(\w+)|'
    r'class\s+\w+\s*<[^>]+>',
    re.MULTILINE
)

SERIALIZATION_PATTERNS = re.compile(
    r'\[Serializable\]|\[JsonObject\]|\[DataContract\]|'
    r'@JsonProperty|@XmlRoot|@Entity\b|'
    r'ISerializable|XmlSerializer|JsonSerializer|DataContractSerializer',
    re.IGNORECASE
)

EVENT_HANDLER_PATTERNS = re.compile(
    r'EventHandler|delegate\s+\w+|\.Subscribe\(|AddEventListener|'
    r'@HostListener|@Output\(\)|EventEmitter',
    re.IGNORECASE
)

# Names that are almost certainly live regardless of reference count
ALWAYS_LIVE_NAMES = {
    'main', 'Main', 'toString', 'ToString', 'equals', 'Equals',
    'hashCode', 'GetHashCode', 'dispose', 'Dispose', 'finalize',
    'ngOnInit', 'ngOnDestroy', 'ngOnChanges', 'ngAfterViewInit',
    'OnGet', 'OnPost', 'OnPut', 'OnDelete', 'OnPatch',
    'Configure', 'ConfigureServices', 'CreateHostBuilder',
    'setUp', 'tearDown',
}

# Patterns that make a method likely live even with zero direct refs
FRAMEWORK_METHOD_PATTERNS = re.compile(
    r'^(On|Handle|Process|Execute|Run|Start|Stop|'
    r'Get|Post|Put|Delete|Patch|Head|Options|'
    r'ng|can|is|has|should)[A-Z]',
)


def compute_confidence(
    sym: SymbolDef,
    ref_count: int,
    is_reachable: bool,
    file_content: str = "",
) -> tuple[int, list[str]]:
    """
    Returns (confidence_pct 0-100, list_of_suppressions).
    Higher confidence = more sure it's dead.
    """
    score = 100
    suppressions = []

    # ── Always-live names ──────────────────────────────────────────────────────
    if sym.name in ALWAYS_LIVE_NAMES:
        return 10, [f"`{sym.name}` is a framework/convention method — almost certainly live"]

    # ── Override methods — called by base class ────────────────────────────────
    if sym.is_override:
        score -= 40
        suppressions.append("Marked `override` — called by base class or framework")

    # ── Abstract members — implemented by subclasses ───────────────────────────
    if sym.is_abstract:
        score -= 50
        suppressions.append("Abstract member — implementations may be called externally")

    # ── Interface implementations ──────────────────────────────────────────────
    if sym.kind == SymbolKind.INTERFACE:
        score -= 60
        suppressions.append("Interface definition — implementations may be injected")

    # ── Attributes / annotations indicate framework usage ─────────────────────
    if sym.has_attribute:
        score -= 25
        suppressions.append("Has attributes/annotations — may be called by framework via reflection")

    # ── Reflection patterns in the same file ──────────────────────────────────
    if file_content and REFLECTION_PATTERNS.search(file_content):
        score -= 20
        suppressions.append("File uses reflection patterns — symbol may be dynamically invoked")

    # ── Dependency injection registration ─────────────────────────────────────
    if file_content and DI_PATTERNS.search(file_content):
        score -= 20
        suppressions.append("DI registration detected — may be resolved at runtime")

    # ── Serialization ─────────────────────────────────────────────────────────
    if file_content and SERIALIZATION_PATTERNS.search(file_content):
        score -= 15
        suppressions.append("Serialization attributes present — properties may be set via deserialization")

    # ── Event handlers ────────────────────────────────────────────────────────
    if file_content and EVENT_HANDLER_PATTERNS.search(file_content):
        score -= 15
        suppressions.append("Event handler patterns detected")

    # ── Framework-named method ────────────────────────────────────────────────
    if FRAMEWORK_METHOD_PATTERNS.match(sym.name):
        score -= 15
        suppressions.append(f"`{sym.name}` matches framework naming convention")

    # ── Angular components/services — always live ──────────────────────────────
    if sym.kind in (SymbolKind.COMPONENT, SymbolKind.SERVICE):
        score -= 35
        suppressions.append(f"Angular {sym.kind.value} — declared in module, live by framework")

    # ── Public API — may be called by external consumers ──────────────────────
    if sym.is_public and ref_count == 0:
        score -= 10
        suppressions.append("Public symbol — may be part of a library API consumed externally")

    # ── Reachability bonus ────────────────────────────────────────────────────
    if is_reachable:
        score -= 30
        suppressions.append("Reachable from entry points via call graph analysis")

    # ── Reference count bonus ─────────────────────────────────────────────────
    if ref_count > 0:
        # Non-zero refs substantially reduce confidence
        penalty = min(ref_count * 15, 60)
        score -= penalty
        suppressions.append(f"Referenced {ref_count} time(s) in codebase")

    return max(0, min(100, score)), suppressions


def classify_dead_symbols(
    symbols: list[SymbolDef],
    ref_counts: dict[str, int],
    reachable_ids: set[str],
    repo_path: str,
    min_confidence: int = 60,
) -> list[DeadSymbol]:
    """
    For every symbol with low/zero refs, compute confidence and classify.
    Returns only symbols above min_confidence threshold.
    """
    dead: list[DeadSymbol] = []

    # Cache file content to avoid re-reading
    file_cache: dict[str, str] = {}

    for sym in symbols:
        ref_count   = ref_counts.get(sym.id, 0)
        is_reachable = sym.id in reachable_ids

        # Skip clearly live symbols early
        if ref_count > 5 and is_reachable:
            continue
        if sym.is_test:
            continue

        # Load file content for suppression checks
        if sym.file not in file_cache:
            try:
                full = Path(repo_path) / sym.file
                file_cache[sym.file] = full.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                file_cache[sym.file] = ""

        file_content = file_cache[sym.file]

        conf_pct, suppressions = compute_confidence(
            sym, ref_count, is_reachable, file_content
        )

        if conf_pct < min_confidence:
            continue

        # Determine dead reason
        if not is_reachable and ref_count == 0:
            reason = DeadReason.NO_REFERENCES
        elif not is_reachable:
            reason = DeadReason.UNREACHABLE
        elif ref_count == 0 and not sym.is_public:
            reason = DeadReason.PRIVATE_NO_CALL
        elif ref_count == 0 and sym.is_public:
            reason = DeadReason.UNUSED_EXPORT
        else:
            reason = DeadReason.OBSOLETE_BRANCH

        confidence = (
            Confidence.HIGH   if conf_pct >= 85 else
            Confidence.MEDIUM if conf_pct >= 60 else
            Confidence.LOW
        )

        # Estimate git age
        git_age = _get_git_age(sym.file, sym.line, repo_path)

        explanation = _build_explanation(sym, ref_count, is_reachable, reason)

        dead.append(DeadSymbol(
            symbol=sym,
            reason=reason,
            confidence=confidence,
            confidence_pct=conf_pct,
            explanation=explanation,
            safe_to_delete=confidence == Confidence.HIGH and not suppressions,
            git_age_days=git_age,
            suppressions=suppressions,
        ))

    dead.sort(key=lambda d: -d.confidence_pct)
    return dead


def _build_explanation(sym: SymbolDef, ref_count: int, is_reachable: bool, reason: DeadReason) -> str:
    parts = []
    if ref_count == 0:
        parts.append("No references found anywhere in the codebase")
    else:
        parts.append(f"Only {ref_count} reference(s) found")
    if not is_reachable:
        parts.append("not reachable from any entry point")
    if sym.lines_of_code > 0:
        parts.append(f"~{sym.lines_of_code} lines could be removed")
    return ". ".join(parts) + "."


def _get_git_age(filepath: str, line: int, repo_path: str) -> int:
    """Return days since this line was last meaningfully changed. 0 if git unavailable."""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%cr', '--', filepath],
            cwd=repo_path, capture_output=True, text=True, timeout=5
        )
        age_str = result.stdout.strip()
        if 'year' in age_str:
            n = int(re.search(r'(\d+)', age_str).group(1))
            return n * 365
        if 'month' in age_str:
            n = int(re.search(r'(\d+)', age_str).group(1))
            return n * 30
        if 'week' in age_str:
            n = int(re.search(r'(\d+)', age_str).group(1))
            return n * 7
        if 'day' in age_str:
            n = int(re.search(r'(\d+)', age_str).group(1))
            return n
        return 1
    except Exception:
        return 0


def build_scan_result(
    dead: list[DeadSymbol],
    files_scanned: int,
    symbols_found: int,
) -> ScanResult:
    by_kind = {}
    by_conf = {'high': 0, 'medium': 0, 'low': 0}
    by_lang = {}
    total_loc = 0

    for d in dead:
        by_kind[d.symbol.kind.value] = by_kind.get(d.symbol.kind.value, 0) + 1
        by_conf[d.confidence.value]  = by_conf.get(d.confidence.value, 0) + 1
        by_lang[d.symbol.language]   = by_lang.get(d.symbol.language, 0) + 1
        total_loc += d.symbol.lines_of_code

    return ScanResult(
        dead_symbols=dead,
        files_scanned=files_scanned,
        symbols_found=symbols_found,
        dead_count=len(dead),
        safe_to_delete=by_conf.get('high', 0),
        lines_recoverable=total_loc,
        by_kind=by_kind,
        by_confidence=by_conf,
        by_language=by_lang,
    )
