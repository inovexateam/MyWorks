"""
Environment drift detection.

Given multiple environment-specific values files (e.g. values-dev.yaml,
values-qa.yaml, values-prod.yaml — or env-named folders containing
values.yaml), this finds keys present in some environments but missing
in others. This is distinct from "dead config": a drifted key is very
much alive, just inconsistently defined, which is its own bug class
worth surfacing separately in the UI.
"""

from dataclasses import dataclass, field


@dataclass
class DriftFinding:
    dotted_path: str
    present_in: list[str]  # env names where key exists
    missing_in: list[str]  # env names where key is absent
    sample_line: int = 0
    sample_file: str = ""
    sample_value: str = ""


def find_env_drift(env_keymaps: dict[str, dict]) -> list[DriftFinding]:
    """
    env_keymaps: { "dev": {dotted_path: LeafInfo, ...}, "qa": {...}, "prod": {...} }
    Returns one DriftFinding per key that doesn't appear in all envs.
    """
    all_envs = list(env_keymaps.keys())
    all_keys: set[str] = set()
    for km in env_keymaps.values():
        all_keys.update(km.keys())

    findings = []
    for key in sorted(all_keys):
        present = [env for env in all_envs if key in env_keymaps[env]]
        missing = [env for env in all_envs if env not in present]
        if missing:
            # pick a sample from whichever env has it, for line/file reference
            sample_env = present[0]
            leaf = env_keymaps[sample_env][key]
            findings.append(DriftFinding(
                dotted_path=key,
                present_in=present,
                missing_in=missing,
                sample_line=leaf.line,
                sample_file=leaf.file_path,
                sample_value=str(leaf.value),
            ))
    return findings
