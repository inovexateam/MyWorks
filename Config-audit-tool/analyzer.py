"""
Main analyzer / orchestrator.

Flow:
  1. Fetch file trees for code repo, component-cd repo, app-cd repo.
  2. Identify env-specific values files in component-cd and app-cd
     (by folder convention: env/<name>/values.yaml, or filename
     convention: values-<name>.yaml — both are checked since the user
     said the cd repo has "file structures for env wise").
  3. For each environment, deep-merge app-cd base values under
     component-cd override values (Helm semantics: component overrides
     app defaults) -> the EFFECTIVE key set for that env.
  4. Build a usage index from: component-cd templates, app-cd templates,
     and the full code repo (Java/C#).
  5. Classify every effective key:
       - DEAD_HELM: never referenced in any chart template
       - DEAD_CODE: referenced in templates (so it reaches a container
         as an env var) but never read by application code
       - FULLY_DEAD: neither templated nor read in code
       - LIVE: referenced in both layers
  6. Run drift detection across the per-env effective key sets.
  7. Attach evidence trace (define -> template -> code) to every key.
"""

from dataclasses import dataclass, field, asdict
import re

from .github_client import session, RepoRef, filter_relevant_files, RepoNotFoundError
from .yaml_merge import load_yaml_with_lines, flatten_to_keymap, deep_merge, LeafInfo
from .usage_scanner import build_usage_index, find_matches_for_key, UsageHit
from .diff_engine import find_env_drift, DriftFinding

ENV_FOLDER_PATTERNS = ["dev", "qa", "stage", "staging", "uat", "prod", "production", "perf", "sit"]

# Top-level / leaf naming conventions that mark a key as infrastructure
# config (consumed by the orchestrator/deployment layer, never expected
# to be read by application code). This is heuristic, not exhaustive —
# the goal is to label, not to hide or silently exclude anything, per
# the requirement that ALL keys be shown with their nature called out.
INFRA_KEY_MARKERS = (
    "image", "imagepullpolicy", "imagepullsecrets", "replicacount", "replicas",
    "resources", "limits", "requests", "livenessprobe", "readinessprobe",
    "startupprobe", "serviceaccount", "nodeselector", "tolerations", "affinity",
    "podsecuritycontext", "securitycontext", "hpa", "autoscaling", "strategy",
    "rollingupdate", "terminationgraceperiodseconds", "labels", "annotations",
    "podannotations", "podlabels", "volumes", "volumemounts", "ports",
    "containerport", "targetport", "servicetype", "ingress", "route",
    "host", "tls", "priorityclassname", "revisionhistorylimit", "namespace",
)


def classify_key_role(dotted_path: str) -> str:
    """
    Returns 'INFRA' if the key's path matches deployment/orchestration
    conventions (consumed by Helm/K8s only — correctly never read by
    app code), otherwise 'APP_CONFIG' (expected to be readable by the
    application — a DEAD_CODE hit here is a more meaningful signal
    than the same hit on an infra key).

    Note: 'host' alone is ambiguous (could be ingress host or a DB
    host app code reads) — we check the fuller path context first
    before falling back to the bare marker.
    """
    lower = dotted_path.lower()
    parts = re.split(r"[.\[\]]+", lower)
    parts = [p for p in parts if p]

    # specific disambiguation: database/db/connection-ish paths that
    # happen to end in 'host' or 'port' are APP_CONFIG, not INFRA,
    # even though 'host'/'port' alone would otherwise look infra-ish
    # via ingress/route conventions.
    app_context_markers = ("database", "db", "connection", "datasource", "redis", "queue", "broker", "api", "endpoint", "secret", "credential", "auth", "feature", "flag")
    if any(m in parts for m in app_context_markers) or any(
        any(m in p for m in app_context_markers) for p in parts
    ):
        return "APP_CONFIG"

    if any(p in INFRA_KEY_MARKERS for p in parts):
        return "INFRA"

    return "APP_CONFIG"


@dataclass
class KeyFinding:
    dotted_path: str
    classification: str  # LIVE | DEAD_HELM | DEAD_CODE | FULLY_DEAD
    key_role: str          # INFRA | APP_CONFIG
    defined_in: dict      # {file_path, line, value, repo}
    template_hits: list   # list of {file_path, line, repo}
    code_hits: list       # list of {file_path, line, repo, layer}
    env: str = ""


@dataclass
class AnalysisResult:
    findings: list = field(default_factory=list)       # KeyFinding (as dicts)
    drift: list = field(default_factory=list)           # DriftFinding (as dicts)
    envs_detected: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    repo_meta: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


def _detect_env_files(file_paths: list[str]) -> dict[str, list[str]]:
    """Maps env-name -> list of values file paths, using two conventions:
    folder-based (env/dev/values.yaml, dev/values.yaml) and
    filename-based (values-dev.yaml, values.dev.yaml)."""
    env_files: dict[str, list[str]] = {}
    for p in file_paths:
        lower = p.lower()
        if "values" not in lower or not lower.endswith((".yaml", ".yml")):
            continue
        parts = lower.replace("\\", "/").split("/")
        matched_env = None
        for part in parts[:-1]:
            for env_name in ENV_FOLDER_PATTERNS:
                if part == env_name or part == f"env-{env_name}" or part == f"{env_name}-env":
                    matched_env = env_name
        filename = parts[-1]
        if not matched_env:
            for env_name in ENV_FOLDER_PATTERNS:
                if f"-{env_name}." in filename or f".{env_name}." in filename or f"_{env_name}." in filename:
                    matched_env = env_name
        if matched_env:
            env_files.setdefault(matched_env, []).append(p)
        elif filename in ("values.yaml", "values.yml") and matched_env is None:
            env_files.setdefault("default", []).append(p)
    return env_files


def _fetch_files(ref: RepoRef, paths: list[str]) -> dict[str, str]:
    out = {}
    for p in paths:
        try:
            out[p] = session.get_file_content(ref, p)
        except RepoNotFoundError:
            out[p] = None
    return out


def run_analysis(code_url: str, component_cd_url: str, app_cd_url: str) -> AnalysisResult:
    from .github_client import parse_github_url

    result = AnalysisResult()

    code_ref = parse_github_url(code_url)
    comp_ref = parse_github_url(component_cd_url)
    app_ref = parse_github_url(app_cd_url)

    for label, ref in (("code", code_ref), ("component-cd", comp_ref), ("app-cd", app_ref)):
        try:
            ref.ref = session.get_default_branch(ref)
        except RepoNotFoundError as e:
            result.warnings.append(f"[{label}] {e}")

    result.repo_meta = {
        "code": code_ref.full_name,
        "component_cd": comp_ref.full_name,
        "app_cd": app_ref.full_name,
    }

    code_tree = session.get_tree(code_ref)
    comp_tree = session.get_tree(comp_ref)
    app_tree = session.get_tree(app_ref)

    code_paths = filter_relevant_files(code_tree)
    comp_paths = filter_relevant_files(comp_tree)
    app_paths = filter_relevant_files(app_tree)

    code_files = _fetch_files(code_ref, code_paths)
    comp_files = _fetch_files(comp_ref, comp_paths)
    app_files = _fetch_files(app_ref, app_paths)

    comp_env_files = _detect_env_files(comp_paths)
    app_env_files = _detect_env_files(app_paths)
    all_env_names = sorted(set(comp_env_files.keys()) | set(app_env_files.keys()) - {"default"})
    if not all_env_names:
        all_env_names = ["default"]
    result.envs_detected = all_env_names

    # Build per-env effective key maps (app-cd base, component-cd override)
    env_keymaps: dict[str, dict[str, LeafInfo]] = {}
    for env in all_env_names:
        app_keymap = {}
        for fp in app_env_files.get(env, app_env_files.get("default", [])):
            parsed, line_table = load_yaml_with_lines(app_files.get(fp) or "")
            if parsed:
                app_keymap.update(flatten_to_keymap(parsed, f"app-cd/{fp}", line_table))

        comp_keymap = {}
        for fp in comp_env_files.get(env, comp_env_files.get("default", [])):
            parsed, line_table = load_yaml_with_lines(comp_files.get(fp) or "")
            if parsed:
                comp_keymap.update(flatten_to_keymap(parsed, f"component-cd/{fp}", line_table))

        # effective = app defaults overridden by component-specific values
        merged: dict[str, LeafInfo] = dict(app_keymap)
        merged.update(comp_keymap)  # component-cd wins on key collisions
        env_keymaps[env] = merged

    # Usage index: templates (both cd repos) + application code
    template_files = {f"component-cd/{k}": v for k, v in comp_files.items()}
    template_files.update({f"app-cd/{k}": v for k, v in app_files.items()})
    code_files_tagged = {f"code/{k}": v for k, v in code_files.items()}

    template_usage = build_usage_index(template_files)
    code_usage = build_usage_index(code_files_tagged)
    all_usage = template_usage + code_usage

    # Classify every key, per env (a key might be live in prod templates
    # but not yet wired in dev, which IS meaningful, so we keep env scope)
    for env, keymap in env_keymaps.items():
        for dotted_path, leaf in keymap.items():
            if dotted_path == "__line__":
                continue
            matches = find_matches_for_key(dotted_path, all_usage)
            template_hits = [m for m in matches if m.layer == "helm"]
            code_hits = [m for m in matches if m.layer in ("java", "csharp")]

            if template_hits and code_hits:
                cls = "LIVE"
            elif template_hits and not code_hits:
                cls = "DEAD_CODE"
            elif not template_hits and code_hits:
                cls = "DEAD_HELM"  # reaches code path some other way; flag for review
            else:
                cls = "FULLY_DEAD"

            key_role = classify_key_role(dotted_path)

            finding = KeyFinding(
                dotted_path=dotted_path,
                classification=cls,
                key_role=key_role,
                defined_in={
                    "file_path": leaf.file_path,
                    "line": leaf.line,
                    "value": _safe_str(leaf.value),
                },
                template_hits=[{"file_path": h.file_path, "line": h.line, "layer": h.layer} for h in template_hits[:5]],
                code_hits=[{"file_path": h.file_path, "line": h.line, "layer": h.layer} for h in code_hits[:5]],
                env=env,
            )
            result.findings.append(asdict(finding))

    # Drift detection across envs
    if len(env_keymaps) > 1:
        drift_findings = find_env_drift(env_keymaps)
        result.drift = [asdict(d) for d in drift_findings]

    # Summary counts for the dashboard header
    counts = {"LIVE": 0, "DEAD_HELM": 0, "DEAD_CODE": 0, "FULLY_DEAD": 0}
    role_counts = {"INFRA": 0, "APP_CONFIG": 0}
    for f in result.findings:
        counts[f["classification"]] = counts.get(f["classification"], 0) + 1
        role_counts[f["key_role"]] = role_counts.get(f["key_role"], 0) + 1
    result.summary = {
        "total_keys": len(result.findings),
        "by_classification": counts,
        "by_role": role_counts,
        "drift_count": len(result.drift),
        "envs": all_env_names,
    }

    return result


def _safe_str(v) -> str:
    if v is None:
        return ""
    s = str(v)
    return s if len(s) < 200 else s[:200] + "..."
