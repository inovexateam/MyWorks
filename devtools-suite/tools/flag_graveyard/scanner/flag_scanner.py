"""
Flag scanner — Layer 1.
Scans the entire repo looking for feature flag definitions and usages.

Supports 6 flag patterns across C#, Java, and Angular/TypeScript:
  1. Hardcoded boolean constants (const bool ENABLE_X = true)
  2. appsettings.json / application.yml / .env config values
  3. Environment variable checks (Environment.GetEnvironmentVariable)
  4. LaunchDarkly / Unleash / Split.io SDK calls
  5. Custom IFeatureService.IsEnabled / FeatureManager.IsEnabled
  6. Inline string/enum comparisons (feature toggle patterns)
"""

import os
import re
import json
from pathlib import Path
from core.models import FlagDefinition, FlagUsage, FlagKind, FlagState

SKIP_DIRS = {
    'node_modules', '.git', 'bin', 'obj', 'dist', '.angular',
    'build', 'out', 'target', '__pycache__', 'migrations', 'coverage'
}

LANG_EXT = {'.cs': 'csharp', '.java': 'java', '.ts': 'angular', '.tsx': 'angular'}

# ── Name normalizer ────────────────────────────────────────────────────────────

def normalize_flag_name(raw: str) -> str:
    """Strip quotes, underscores, and common prefixes → canonical name."""
    name = raw.strip('"\'` ')
    name = re.sub(r'^(FEATURE_|FEAT_|FF_|FLAG_|ENABLE_|feature\.|flag\.)', '', name, flags=re.IGNORECASE)
    return name.lower().replace('-', '_').replace('.', '_')


# ── Ticket reference extractor ────────────────────────────────────────────────

TICKET_PATTERN = re.compile(r'\b([A-Z]{2,8}-\d{1,6}|#\d{3,6})\b')

def extract_ticket_ref(content_around: str) -> str:
    m = TICKET_PATTERN.search(content_around)
    return m.group(1) if m else ""


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CODE SCANNER — finds flag usages in .cs / .java / .ts files
# ═══════════════════════════════════════════════════════════════════════════════

# C# patterns
CS_FLAG_PATTERNS = [
    # IFeatureManager / FeatureManager
    re.compile(r'(?:_featureManager|featureManager|FeatureManager)\s*\.\s*IsEnabled(?:Async)?\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    # FeatureFlag.IsEnabled("name")
    re.compile(r'(?:FeatureFlag|Feature|FeatureToggle)\s*\.\s*IsEnabled\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    # hardcoded bool: const bool EnableNewCheckout = true;
    re.compile(r'(?:private|public|internal|protected)?\s*(?:static\s+)?(?:readonly\s+)?const\s+bool\s+(\w*[Ff]eature\w*|\w*[Ff]lag\w*|\w*[Ee]nable\w*)\s*=\s*(true|false)', re.IGNORECASE),
    # _configuration["FeatureFlags:EnableX"]
    re.compile(r'_configuration\s*\[\s*["\']([^"\']*(?:feature|flag|enable)[^"\']*)["\']', re.IGNORECASE),
    # Environment.GetEnvironmentVariable("FEATURE_X")
    re.compile(r'Environment\.GetEnvironmentVariable\s*\(\s*["\']([^"\']*(?:FEATURE|FLAG|ENABLE)[^"\']*)["\']', re.IGNORECASE),
]

# Java patterns
JAVA_FLAG_PATTERNS = [
    re.compile(r'(?:featureManager|flipper|unleash|ldClient)\s*\.\s*(?:isEnabled|getValue|variation)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'@ConditionalOnProperty\s*\([^)]*name\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'static\s+final\s+boolean\s+(\w*(?:FEATURE|FLAG|ENABLE)\w*)\s*=\s*(true|false)', re.IGNORECASE),
    re.compile(r'System\.getenv\s*\(\s*["\']([^"\']*(?:FEATURE|FLAG|ENABLE)[^"\']*)["\']', re.IGNORECASE),
    re.compile(r'environment\.getProperty\s*\(\s*["\']([^"\']*(?:feature|flag)[^"\']*)["\']', re.IGNORECASE),
]

# TypeScript / Angular patterns
TS_FLAG_PATTERNS = [
    re.compile(r'(?:featureService|featureFlags|featureManager|ldClient)\s*\.\s*(?:isEnabled|isOn|variation)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'environment\s*\.\s*(\w*(?:feature|flag|enable)\w*)\b', re.IGNORECASE),
    re.compile(r'(?:const|let|var)\s+(\w*(?:Feature|Flag|Enable)\w*)\s*=\s*(true|false)', re.IGNORECASE),
    re.compile(r'process\.env\.([A-Z_]*(?:FEATURE|FLAG|ENABLE)[A-Z_]*)', re.IGNORECASE),
    re.compile(r'FEATURE_FLAGS\s*\[\s*["\']([^"\']+)["\']', re.IGNORECASE),
]

LANG_PATTERNS = {'csharp': CS_FLAG_PATTERNS, 'java': JAVA_FLAG_PATTERNS, 'angular': TS_FLAG_PATTERNS}

# Detect if a flag usage is inside an if/else and which branch
IF_FLAG_PATTERN = re.compile(
    r'if\s*\([^)]*(?:IsEnabled|isEnabled|isOn|\.enabled|==\s*true|==\s*false)[^)]*\)',
    re.IGNORECASE
)


def scan_code_file(filepath: str, rel_path: str, language: str) -> list[tuple[str, int, str, str]]:
    """
    Returns list of (flag_name, line_number, raw_snippet, hardcoded_value_or_empty).
    hardcoded_value_or_empty is 'true'/'false' if the flag is a const, else ''.
    """
    try:
        content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return []

    patterns = LANG_PATTERNS.get(language, [])
    results = []
    lines = content.split('\n')

    for i, line in enumerate(lines, 1):
        for pat in patterns:
            m = pat.search(line)
            if m:
                name = normalize_flag_name(m.group(1))
                # If second group exists, it's a hardcoded value
                hardcoded = m.group(2).lower() if m.lastindex and m.lastindex >= 2 else ''
                if len(name) < 2 or len(name) > 80:
                    continue
                results.append((name, i, line.strip(), hardcoded))
                break  # one match per line

    return results


def detect_branch_context(lines: list[str], flag_line_idx: int) -> tuple[str, bool, int, int]:
    """
    Look at the lines around the flag usage to determine branch structure.
    Returns (branch_kind, has_else, true_branch_lines, false_branch_lines).
    """
    context_start = max(0, flag_line_idx - 2)
    context = '\n'.join(lines[context_start:flag_line_idx + 10])

    has_else = bool(re.search(r'\}\s*else\s*\{', context))
    branch_kind = 'if_check' if re.search(r'\bif\s*\(', context) else 'direct'

    # Rough estimate: count lines until matching close brace
    true_lines = 0
    false_lines = 0
    depth = 0
    in_true = False
    in_false = False

    for line in lines[flag_line_idx:flag_line_idx + 50]:
        depth += line.count('{') - line.count('}')
        if '{' in line and not in_true:
            in_true = True
            continue
        if in_true and not in_false:
            if depth <= 0 and '}' in line:
                in_false = bool(re.search(r'else', line))
            else:
                true_lines += 1
        elif in_false:
            if depth < 0:
                break
            false_lines += 1

    return branch_kind, has_else, true_lines, false_lines


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONFIG SCANNER — finds flags in appsettings.json / application.yml / .env
# ═══════════════════════════════════════════════════════════════════════════════

def scan_json_config(filepath: str, rel_path: str) -> list[FlagDefinition]:
    """Scan appsettings.json / launchSettings.json for feature flag sections."""
    try:
        data = json.loads(Path(filepath).read_text(encoding='utf-8', errors='ignore'))
    except Exception:
        return []

    flags = []
    _extract_json_flags(data, rel_path, flags, prefix="")
    return flags


def _extract_json_flags(obj, filepath: str, flags: list, prefix: str):
    if isinstance(obj, dict):
        for key, val in obj.items():
            full_key = f"{prefix}.{key}" if prefix else key
            lower_key = key.lower()
            # Keys that look like feature flag sections or individual flags
            if any(x in lower_key for x in ['feature', 'flag', 'toggle', 'enable', 'rollout']):
                if isinstance(val, bool):
                    name = normalize_flag_name(full_key)
                    state = FlagState.ALWAYS_ON if val else FlagState.ALWAYS_OFF
                    flags.append(FlagDefinition(
                        name=name, kind=FlagKind.CONFIG_VALUE,
                        state=state, source_file=filepath, source_line=0, language='config',
                    ))
                elif isinstance(val, (int, float)) and val in (0, 1, 100, 0.0, 1.0):
                    name = normalize_flag_name(full_key)
                    state = FlagState.ALWAYS_ON if val in (1, 100, 1.0) else FlagState.ALWAYS_OFF
                    flags.append(FlagDefinition(
                        name=name, kind=FlagKind.CONFIG_VALUE,
                        state=state, source_file=filepath, source_line=0, language='config',
                    ))
                elif isinstance(val, str) and val.lower() in ('true', 'false', '1', '0', 'on', 'off', 'enabled', 'disabled'):
                    name = normalize_flag_name(full_key)
                    state = FlagState.ALWAYS_ON if val.lower() in ('true', '1', 'on', 'enabled') else FlagState.ALWAYS_OFF
                    flags.append(FlagDefinition(
                        name=name, kind=FlagKind.CONFIG_VALUE,
                        state=state, source_file=filepath, source_line=0, language='config',
                    ))
            _extract_json_flags(val, filepath, flags, full_key)


YAML_FLAG_LINE = re.compile(
    r'^(\s*)([\w\.\-]+):\s*(true|false|yes|no|1|0|enabled|disabled|on|off)\s*$',
    re.IGNORECASE
)

def scan_yaml_config(filepath: str, rel_path: str) -> list[FlagDefinition]:
    """Scan application.yml / application.properties for flag-like keys."""
    try:
        lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    except Exception:
        return []

    flags = []
    for i, line in enumerate(lines, 1):
        m = YAML_FLAG_LINE.match(line)
        if not m:
            continue
        key = m.group(2).lower()
        val = m.group(3).lower()
        if not any(x in key for x in ['feature', 'flag', 'toggle', 'enable', 'rollout']):
            continue
        name = normalize_flag_name(m.group(2))
        state = FlagState.ALWAYS_ON if val in ('true', 'yes', '1', 'enabled', 'on') else FlagState.ALWAYS_OFF
        flags.append(FlagDefinition(
            name=name, kind=FlagKind.CONFIG_VALUE,
            state=state, source_file=rel_path, source_line=i, language='config',
        ))
    return flags


ENV_FLAG_LINE = re.compile(
    r'^([A-Z_]*(?:FEATURE|FLAG|ENABLE|TOGGLE)[A-Z_0-9]*)\s*=\s*(.+)$',
    re.IGNORECASE
)

def scan_env_file(filepath: str, rel_path: str) -> list[FlagDefinition]:
    """Scan .env files for FEATURE_X=true/false patterns."""
    try:
        lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    except Exception:
        return []

    flags = []
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if line.startswith('#') or '=' not in line:
            continue
        m = ENV_FLAG_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip('"\'').lower()
        state = FlagState.ALWAYS_ON if val in ('true', '1', 'yes', 'on', 'enabled') \
           else FlagState.ALWAYS_OFF if val in ('false', '0', 'no', 'off', 'disabled') \
           else FlagState.UNKNOWN
        flags.append(FlagDefinition(
            name=normalize_flag_name(key), kind=FlagKind.ENV_VAR,
            state=state, source_file=rel_path, source_line=i, language='config',
        ))
    return flags


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SCAN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG_EXT = {'.json', '.yml', '.yaml', '.properties'}
ENV_FILES  = {'.env', '.env.production', '.env.local', '.env.staging'}


def scan_all_flags(repo_path: str, verbose: bool = False) -> tuple[list[FlagDefinition], dict[str, list[FlagUsage]], int]:
    """
    Full repo scan. Returns:
      (flag_definitions, usages_by_name, file_count)

    Strategy:
      1. Find all flag definitions from config files and env files
      2. Find all flag usages in source code
      3. Merge: usages enrich definitions
    """
    definitions: dict[str, FlagDefinition] = {}
    all_usages:  dict[str, list[FlagUsage]] = {}
    file_count   = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in files:
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, repo_path).replace('\\', '/')
            ext  = Path(fname).suffix.lower()
            name_lower = fname.lower()

            # Config files
            if ext in CONFIG_EXT:
                if ext == '.json' and any(x in name_lower for x in ['settings', 'config', 'launch']):
                    for flag in scan_json_config(full, rel):
                        definitions[flag.name] = flag
                elif ext in ('.yml', '.yaml'):
                    for flag in scan_yaml_config(full, rel):
                        definitions[flag.name] = flag
                elif ext == '.properties':
                    for flag in scan_yaml_config(full, rel):
                        definitions[flag.name] = flag
                file_count += 1
                continue

            # .env files
            if name_lower in ENV_FILES or name_lower.startswith('.env'):
                for flag in scan_env_file(full, rel):
                    definitions[flag.name] = flag
                file_count += 1
                continue

            # Source code
            lang = LANG_EXT.get(ext)
            if not lang:
                continue

            raw_matches = scan_code_file(full, rel, lang)
            lines = Path(full).read_text(encoding='utf-8', errors='ignore').split('\n')
            file_count += 1

            for flag_name, lineno, snippet, hardcoded in raw_matches:
                # If hardcoded value found, register as a definition
                if hardcoded:
                    state = FlagState.ALWAYS_ON if hardcoded == 'true' else FlagState.ALWAYS_OFF
                    existing = definitions.get(flag_name)
                    if not existing or existing.state == FlagState.UNKNOWN:
                        definitions[flag_name] = FlagDefinition(
                            name=flag_name, kind=FlagKind.CODE_CONSTANT,
                            state=state, source_file=rel, source_line=lineno, language=lang,
                        )

                # Register as a usage
                branch_kind, has_else, true_lines, false_lines = detect_branch_context(lines, lineno - 1)
                usage = FlagUsage(
                    flag_name=flag_name, file=rel, line=lineno, language=lang,
                    usage_pattern=snippet[:120], branch_kind=branch_kind,
                    has_else=has_else,
                    true_branch_lines=true_lines, false_branch_lines=false_lines,
                )
                all_usages.setdefault(flag_name, []).append(usage)

                # Auto-create definition if not seen in config
                if flag_name not in definitions:
                    definitions[flag_name] = FlagDefinition(
                        name=flag_name, kind=FlagKind.CUSTOM_SERVICE,
                        state=FlagState.UNKNOWN, source_file=rel, source_line=lineno, language=lang,
                    )

            if verbose and file_count % 20 == 0:
                print(f"\r  {file_count} files, {len(definitions)} flags...", end='', flush=True)

    if verbose:
        print(f"\r  {file_count} files, {len(definitions)} flags total.        ")

    # Attach usages to definitions
    for name, flag in definitions.items():
        flag.usages = all_usages.get(name, [])

    return list(definitions.values()), all_usages, file_count
