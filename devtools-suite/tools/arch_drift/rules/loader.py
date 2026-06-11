"""
Loads and compiles arch-rules.yml into evaluable rule objects.
Supports layer_dependency, naming, no_dependency, no_circular,
max_coupling, and domain_isolation rule kinds.
"""

import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from fnmatch import fnmatch
from core.models import RuleKind, Severity


@dataclass
class CompiledLayerRule:
    from_layer: str
    allowed_to: list[str]   # layers this layer may import


@dataclass
class CompiledNamingRule:
    layer: str
    suffix: str = ""
    suffix_one_of: list[str] = field(default_factory=list)
    no_suffix: list[str] = field(default_factory=list)
    applies_to_exts: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class CompiledNoDependencyRule:
    from_pattern: str
    to_pattern: str
    message: str = ""


@dataclass
class CompiledCouplingRule:
    layer: str
    max_external_imports: int
    message: str = ""


@dataclass
class CompiledDomainContext:
    name: str
    patterns: list[str]


@dataclass
class CompiledArchRules:
    # namespace prefix → layer name
    layer_map: list[tuple[str, str]]          # (glob_pattern, layer_name)

    layer_rules: list[CompiledLayerRule]
    naming_rules: list[CompiledNamingRule]
    no_dep_rules: list[CompiledNoDependencyRule]
    coupling_rules: list[CompiledCouplingRule]
    no_circular: bool
    domain_contexts: list[CompiledDomainContext]
    allowed_crossings: list[dict]              # [{from, to, via}]

    def assign_layer(self, filepath: str) -> str:
        """Return the layer name for a file path, or 'unknown'."""
        norm = filepath.replace('\\', '/').lower()
        for pattern, layer in self.layer_map:
            if _glob_match(pattern, norm):
                return layer
        return "unknown"

    def get_allowed_layers(self, from_layer: str) -> list[str]:
        """Return the list of layers a given layer may import from."""
        for rule in self.layer_rules:
            if rule.from_layer == from_layer:
                return rule.allowed_to
        return []


def _glob_match(pattern: str, path: str) -> bool:
    """Match glob patterns like **.Controllers.** against a file path."""
    # Convert ** glob to regex
    # **.Controllers.** → anything containing /Controllers/ or .Controllers.
    pat = pattern.lower().replace('\\', '/')
    # Replace ** with a regex wildcard that matches across slashes
    regex = re.escape(pat).replace(r'\*\*', '.*').replace(r'\*', '[^/]*')
    return bool(re.search(regex, path))


def load_rules(rules_path: str) -> CompiledArchRules:
    """Load and compile arch-rules.yml from disk."""
    path = Path(rules_path)
    if not path.exists():
        raise FileNotFoundError(f"arch-rules.yml not found at: {rules_path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    # ── Layer map ──────────────────────────────────────────────────────────────
    layer_map = []
    for layer_def in raw.get('layers', []):
        layer_name = layer_def['name']
        for ns in layer_def.get('namespaces', []):
            layer_map.append((ns, layer_name))

    # ── Layer dependency rules ─────────────────────────────────────────────────
    layer_rules = []
    for ld in raw.get('layer_dependencies', []):
        layer_rules.append(CompiledLayerRule(
            from_layer=ld['from'],
            allowed_to=ld.get('may_import', [])
        ))

    # ── Naming rules ───────────────────────────────────────────────────────────
    naming_rules = []
    for nr in raw.get('naming_rules', []):
        layer = nr['layer']
        for pat in nr.get('patterns', []):
            exts = []
            for ext_str in pat.get('applies_to', '').split(','):
                ext_str = ext_str.strip()
                if ext_str.startswith('**'):
                    exts.append(ext_str[2:])
                elif ext_str:
                    exts.append(ext_str)

            excludes = []
            for exc in pat.get('exclude', '').split(','):
                exc = exc.strip()
                if exc:
                    excludes.append(exc)

            naming_rules.append(CompiledNamingRule(
                layer=layer,
                suffix=pat.get('suffix', ''),
                suffix_one_of=pat.get('suffix_one_of', []),
                no_suffix=pat.get('no_suffix', []),
                applies_to_exts=exts,
                exclude_patterns=excludes,
                message=pat.get('message', ''),
            ))

    # ── No-dependency rules ────────────────────────────────────────────────────
    no_dep_rules = []
    for nd in raw.get('no_dependency', []):
        no_dep_rules.append(CompiledNoDependencyRule(
            from_pattern=nd['from'],
            to_pattern=nd['to'],
            message=nd.get('message', ''),
        ))

    # ── Coupling rules ─────────────────────────────────────────────────────────
    coupling_rules = []
    for cr in raw.get('max_coupling', []):
        coupling_rules.append(CompiledCouplingRule(
            layer=cr['layer'],
            max_external_imports=cr['max_external_imports'],
            message=cr.get('message', ''),
        ))

    # ── Domain isolation ───────────────────────────────────────────────────────
    domain_raw = raw.get('domain_isolation', {})
    domain_contexts = []
    for ctx in domain_raw.get('contexts', []):
        domain_contexts.append(CompiledDomainContext(
            name=ctx['name'],
            patterns=ctx.get('namespaces', [])
        ))

    allowed_crossings = domain_raw.get('allowed_crossings', [])

    return CompiledArchRules(
        layer_map=layer_map,
        layer_rules=layer_rules,
        naming_rules=naming_rules,
        no_dep_rules=no_dep_rules,
        coupling_rules=coupling_rules,
        no_circular=raw.get('no_circular', False),
        domain_contexts=domain_contexts,
        allowed_crossings=allowed_crossings,
    )


def find_rules_file(repo_path: str) -> str:
    """Search for arch-rules.yml in repo root and common locations."""
    candidates = [
        'arch-rules.yml',
        'architecture.yml',
        '.arch-rules.yml',
        'docs/arch-rules.yml',
        'tools/arch-rules.yml',
    ]
    for candidate in candidates:
        full = Path(repo_path) / candidate
        if full.exists():
            return str(full)
    return str(Path(repo_path) / 'arch-rules.yml')  # default (may not exist)
