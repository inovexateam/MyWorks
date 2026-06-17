"""
Usage scanner — answers "is this values.yaml key referenced anywhere?"
across three layers:

  1. Helm/K8s templates (component-cd + app-cd):  {{ .Values.foo.bar }}
  2. Java source: @Value("${foo.bar}"), System.getenv("FOO_BAR"),
     env.getProperty("foo.bar"), ConfigurationProperties bindings
  3. C# source: IConfiguration["Foo:Bar"], Environment.GetEnvironmentVariable,
     [FromServices]/options pattern via Configure<T>, appsettings binding

Because key naming conventions differ across these three worlds
(dotted vs colon vs UPPER_SNAKE env var), we generate a set of
"reasonable name variants" for each dotted key and check all of them.
This is intentionally permissive (favors false-"alive" over false-"dead")
since flagging something as dead is the expensive mistake to make.
"""

import re
from dataclasses import dataclass, field


@dataclass
class UsageHit:
    file_path: str
    line: int
    snippet: str
    layer: str  # "helm" | "java" | "csharp"


def key_name_variants(dotted_path: str) -> set[str]:
    """
    'app.database.connectionString' ->
      {'app.database.connectionString', 'app:database:connectionString',
       'APP_DATABASE_CONNECTIONSTRING', 'connectionString', 'connectionstring', ...}
    """
    # strip array indices like image[0].tag -> image.tag for matching purposes
    clean = re.sub(r"\[\d+\]", "", dotted_path)
    parts = clean.split(".")
    last = parts[-1]

    variants = {clean}
    variants.add(":".join(parts))  # C# IConfiguration style
    variants.add("_".join(p.upper() for p in parts))  # ENV VAR style, full path
    variants.add(re.sub(r"(?<!^)(?=[A-Z])", "_", last).upper())  # camelCase -> ENV_VAR for leaf
    variants.add(last)  # bare leaf name, last resort
    variants.add(last.lower())
    return {v for v in variants if v}


HELM_REF_RE = re.compile(
    r"\.Values\.([A-Za-z0-9_\.\[\]\"\'-]+)"
)

JAVA_VALUE_ANNOTATION_RE = re.compile(
    r'@Value\s*\(\s*"\$\{([^:}\s]+)'
)
JAVA_GETENV_RE = re.compile(
    r'(?:System\.getenv|getenv)\s*\(\s*"([^"]+)"'
)
JAVA_PROPERTY_RE = re.compile(
    r'\.getProperty\s*\(\s*"([^"]+)"'
)

CSHARP_INDEXER_RE = re.compile(
    r'(?:Configuration|_config|config)\s*\[\s*"([^"]+)"\s*\]'
)
CSHARP_ENV_RE = re.compile(
    r'Environment\.GetEnvironmentVariable\s*\(\s*"([^"]+)"'
)
CSHARP_GETVALUE_RE = re.compile(
    r'GetValue\s*<[^>]+>\s*\(\s*"([^"]+)"'
)
CSHARP_GETSECTION_RE = re.compile(
    r'GetSection\s*\(\s*"([^"]+)"'
)


def extract_helm_refs(text: str, file_path: str) -> list[UsageHit]:
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in HELM_REF_RE.finditer(line):
            ref = m.group(1).strip("\"'")
            ref = ref.replace('"', "").replace("'", "")
            hits.append(UsageHit(file_path, lineno, line.strip(), "helm"))
            hits[-1].snippet = f"{ref}::{line.strip()}"
    return hits


def _scan_with_patterns(text: str, file_path: str, patterns: list[re.Pattern], layer: str) -> list[UsageHit]:
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            for m in pat.finditer(line):
                key_found = m.group(1)
                hits.append(UsageHit(file_path, lineno, f"{key_found}::{line.strip()}", layer))
    return hits


def extract_java_refs(text: str, file_path: str) -> list[UsageHit]:
    return _scan_with_patterns(
        text, file_path,
        [JAVA_VALUE_ANNOTATION_RE, JAVA_GETENV_RE, JAVA_PROPERTY_RE],
        "java",
    )


def extract_csharp_refs(text: str, file_path: str) -> list[UsageHit]:
    return _scan_with_patterns(
        text, file_path,
        [CSHARP_INDEXER_RE, CSHARP_ENV_RE, CSHARP_GETVALUE_RE, CSHARP_GETSECTION_RE],
        "csharp",
    )


def scan_file_for_refs(text: str, file_path: str) -> list[UsageHit]:
    """Dispatch by extension, but run Helm-ref scan on any yaml/template
    file and run BOTH Java and C# scanners on ambiguous source files —
    mixed-language repos mean we don't trust the extension alone for
    config-read patterns that could appear in either."""
    lower = file_path.lower()
    hits: list[UsageHit] = []

    if lower.endswith((".yaml", ".yml", ".tpl", ".gotmpl")):
        hits += extract_helm_refs(text, file_path)

    if lower.endswith((".java",)):
        hits += extract_java_refs(text, file_path)
    elif lower.endswith((".cs", ".cshtml")):
        hits += extract_csharp_refs(text, file_path)
    elif lower.endswith((".properties", ".json", ".config")):
        # property/config files can hold either-style references in
        # templated/interpolated form; check both cheaply.
        hits += extract_java_refs(text, file_path)
        hits += extract_csharp_refs(text, file_path)

    return hits


def build_usage_index(files: dict[str, str]) -> list[UsageHit]:
    """files: {repo_relative_path: file_text}. Returns every usage hit
    found across all files, tagged with its source layer."""
    all_hits: list[UsageHit] = []
    for path, text in files.items():
        if text is None:
            continue
        all_hits.extend(scan_file_for_refs(text, path))
    return all_hits


def find_matches_for_key(dotted_path: str, usage_hits: list[UsageHit]) -> list[UsageHit]:
    """Given a values.yaml dotted key, return all usage hits whose
    extracted reference matches any reasonable name variant of that key."""
    variants_lower = {v.lower() for v in key_name_variants(dotted_path)}
    matches = []
    for hit in usage_hits:
        extracted = hit.snippet.split("::", 1)[0].lower()
        # match if extracted ref equals a variant, OR ends with the
        # dotted leaf (handles partial paths like 'Values.image.tag'
        # appearing as just 'image.tag' after the .Values. prefix is
        # stripped, vs our key being 'component.image.tag')
        if extracted in variants_lower or any(
            extracted.endswith(v) or v.endswith(extracted) for v in variants_lower if len(v) > 2
        ):
            matches.append(hit)
    return matches
