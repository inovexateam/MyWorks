"""
Line-number-aware YAML loading.

Standard PyYAML loses line numbers once parsed into plain dicts. We need
line numbers for every leaf key (for the "reference with line number"
requirement), so we use a custom Loader that attaches (line, col) to
every mapping/scalar node via a SafeLoader subclass.

Output shape: a "KeyMap" — flat dict of dotted-path -> LeafInfo, where
LeafInfo carries the value, line number, and column. Nested dicts are
walked recursively so `image.tag` becomes a single addressable key,
matching how Helm templates reference `.Values.image.tag`.
"""

from dataclasses import dataclass
from typing import Any, Optional

import yaml


@dataclass
class LeafInfo:
    dotted_path: str
    value: Any
    line: int  # 1-indexed
    file_path: str = ""  # filled in by caller (repo-relative path)


class _LineLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    """
    Builds the mapping but tags EACH VALUE NODE with its own start
    line via a side-table keyed by id(value), since plain scalars
    (str/int/bool) can't carry attributes directly. We also keep
    '__line__' for the mapping's own start (used when a dict itself
    has no scalar children, e.g. an empty section).
    """
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        value = loader.construct_object(value_node, deep=deep)
        mapping[key] = value
        # Record the line for this specific key's value, 1-indexed.
        loader.line_table[(id(mapping), key)] = value_node.start_mark.line + 1
    mapping["__line__"] = node.start_mark.line + 1
    mapping["__line_table_ref__"] = id(mapping)
    return mapping


_LineLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)

_original_init = _LineLoader.__init__


def _patched_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.line_table = {}


_LineLoader.__init__ = _patched_init


def load_yaml_with_lines(text: str):
    """
    Parses YAML text, returning (parsed_tree, line_table) where
    line_table maps (id(parent_dict), key) -> 1-indexed line number
    for that key's value. Nested dicts still carry '__line__' for
    their own start, used as a fallback for empty sections.
    """
    if not text or not text.strip():
        return {}, {}
    try:
        loader = _LineLoader(text)
        try:
            data = loader.get_single_data()
        finally:
            loader.dispose()
        return data, loader.line_table
    except yaml.YAMLError:
        return None, {}  # caller should report as a parse error, not crash


def flatten_to_keymap(node: Any, file_path: str, line_table: Optional[dict] = None, prefix: str = "") -> dict[str, LeafInfo]:
    """
    Walks a parsed (line-annotated) YAML structure and returns a flat
    dict: dotted.path -> LeafInfo, with each leaf's LINE being its own
    line in the source file (via line_table), not its parent's line.
    Lists are indexed numerically (e.g. env[0].name) so array-based
    k8s manifests (env vars, etc.) are still individually addressable.
    """
    line_table = line_table or {}
    out: dict[str, LeafInfo] = {}
    if isinstance(node, dict):
        own_line = node.get("__line__", 0)
        parent_id = node.get("__line_table_ref__")
        had_children = False
        for k, v in node.items():
            if k in ("__line__", "__line_table_ref__"):
                continue
            had_children = True
            child_path = f"{prefix}.{k}" if prefix else str(k)
            child_line = line_table.get((parent_id, k), own_line)
            if isinstance(v, (dict, list)):
                out.update(flatten_to_keymap(v, file_path, line_table, child_path))
            else:
                out[child_path] = LeafInfo(
                    dotted_path=child_path, value=v, line=child_line, file_path=file_path
                )
        if not had_children and prefix:
            out[prefix] = LeafInfo(dotted_path=prefix, value=None, line=own_line, file_path=file_path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            child_path = f"{prefix}[{i}]"
            if isinstance(item, (dict, list)):
                out.update(flatten_to_keymap(item, file_path, line_table, child_path))
            else:
                out[child_path] = LeafInfo(
                    dotted_path=child_path, value=item, line=0, file_path=file_path
                )
    return out


def deep_merge(base: dict, override: dict) -> dict:
    """
    Helm-semantics deep merge: override wins on scalar conflicts,
    dicts merge key-by-key recursively, lists in override fully
    replace lists in base (this matches Helm's values.yaml merge
    behavior — lists are not concatenated).

    Bookkeeping keys (__line__, __line_table_ref__) are dropped here:
    once two files are merged, a single "source line" no longer makes
    sense for a key that may exist in both, so line attribution should
    be read from the original per-file keymaps before merging, not
    from this merged structure.
    """
    if not isinstance(base, dict):
        return override
    if not isinstance(override, dict):
        return override if override is not None else base

    result = {k: v for k, v in base.items() if k not in ("__line__", "__line_table_ref__")}
    for k, v in override.items():
        if k in ("__line__", "__line_table_ref__"):
            continue
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result
