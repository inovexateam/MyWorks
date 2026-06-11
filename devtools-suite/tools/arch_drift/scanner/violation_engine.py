"""
Violation engine.
Evaluates every compiled rule against the import graph and returns violations.
Each checker is independent — add new ones at the bottom.
"""

from pathlib import Path
from rules.loader import CompiledArchRules, _glob_match
from scanner.import_graph import ImportGraph, ImportEdge, FileNode
from core.models import Violation, RuleKind, Severity


def evaluate_all(rules: CompiledArchRules, graph: ImportGraph) -> list[Violation]:
    """Run all checkers and return combined violation list."""
    violations = []
    violations += check_layer_dependencies(rules, graph)
    violations += check_no_dependency(rules, graph)
    violations += check_naming(rules, graph)
    violations += check_max_coupling(rules, graph)
    violations += check_domain_isolation(rules, graph)
    if rules.no_circular:
        violations += check_circular(graph)
    return violations


# ── Layer dependency checker ──────────────────────────────────────────────────

def check_layer_dependencies(rules: CompiledArchRules, graph: ImportGraph) -> list[Violation]:
    violations = []
    for node in graph.nodes.values():
        from_layer = rules.assign_layer(node.path)
        if from_layer == 'unknown':
            continue

        allowed = rules.get_allowed_layers(from_layer)
        # Always allow imports within the same layer or from 'shared'
        always_ok = {from_layer, 'shared', 'unknown'}

        for edge in node.imports:
            to_layer = _resolve_to_layer(rules, edge.target_ns, edge.source_file)
            if to_layer == 'unknown' or to_layer in always_ok or to_layer in allowed:
                continue

            violations.append(Violation(
                rule_kind=RuleKind.LAYER_DEPENDENCY,
                severity=Severity.ERROR,
                message=(
                    f"Layer violation: '{from_layer}' imports from '{to_layer}' "
                    f"— not in allowed list {allowed}"
                ),
                file=node.path,
                line=edge.line,
                from_layer=from_layer,
                to_layer=to_layer,
                import_path=edge.target_ns,
                rule_name="layer_dependency",
            ))
    return violations


def _resolve_to_layer(rules: CompiledArchRules, target_ns: str, source_file: str) -> str:
    """Try to determine which layer a target namespace/path belongs to."""
    # For relative TS imports — match against path
    if target_ns.startswith('.') or '/' in target_ns:
        return rules.assign_layer(target_ns)
    # For namespace-based (C#/Java) — match namespace against layer patterns
    target_as_path = target_ns.replace('.', '/').lower()
    return rules.assign_layer(target_as_path)


# ── No-dependency checker ─────────────────────────────────────────────────────

def check_no_dependency(rules: CompiledArchRules, graph: ImportGraph) -> list[Violation]:
    violations = []
    for node in graph.nodes.values():
        for edge in node.imports:
            for rule in rules.no_dep_rules:
                from_matches = _glob_match(rule.from_pattern, node.path) or \
                               _glob_match(rule.from_pattern, node.namespace)
                to_matches   = _glob_match(rule.to_pattern, edge.target_ns) or \
                               _glob_match(rule.to_pattern, edge.source_file)
                if from_matches and to_matches:
                    from_layer = rules.assign_layer(node.path)
                    to_layer   = _resolve_to_layer(rules, edge.target_ns, node.path)
                    violations.append(Violation(
                        rule_kind=RuleKind.NO_DEPENDENCY,
                        severity=Severity.ERROR,
                        message=rule.message or f"Forbidden dependency: {node.path} → {edge.target_ns}",
                        file=node.path,
                        line=edge.line,
                        from_layer=from_layer,
                        to_layer=to_layer,
                        import_path=edge.target_ns,
                        rule_name="no_dependency",
                    ))
    return violations


# ── Naming convention checker ─────────────────────────────────────────────────

def check_naming(rules: CompiledArchRules, graph: ImportGraph) -> list[Violation]:
    violations = []
    for node in graph.nodes.values():
        file_layer = rules.assign_layer(node.path)
        if file_layer == 'unknown':
            continue
        fname = Path(node.path).name
        stem  = Path(node.path).stem
        ext   = Path(node.path).suffix.lower()

        for rule in rules.naming_rules:
            if rule.layer != file_layer:
                continue

            # Check extension match
            if rule.applies_to_exts and ext not in rule.applies_to_exts:
                continue

            # Check exclusions
            skip = any(_glob_match(exc, node.path) for exc in rule.exclude_patterns)
            if skip:
                continue

            # suffix rule: file must end with this suffix
            if rule.suffix:
                if not stem.endswith(rule.suffix):
                    violations.append(Violation(
                        rule_kind=RuleKind.NAMING,
                        severity=Severity.WARNING,
                        message=(
                            f"Naming: '{fname}' in '{file_layer}' layer "
                            f"should end with '{rule.suffix}'"
                        ),
                        file=node.path, line=0,
                        from_layer=file_layer, to_layer="",
                        import_path="", rule_name="naming",
                    ))

            # suffix_one_of rule
            if rule.suffix_one_of:
                if not any(stem.endswith(s) for s in rule.suffix_one_of):
                    violations.append(Violation(
                        rule_kind=RuleKind.NAMING,
                        severity=Severity.WARNING,
                        message=(
                            f"Naming: '{fname}' in '{file_layer}' layer "
                            f"should end with one of {rule.suffix_one_of}"
                        ),
                        file=node.path, line=0,
                        from_layer=file_layer, to_layer="",
                        import_path="", rule_name="naming",
                    ))

            # no_suffix rule: file must NOT end with any of these
            if rule.no_suffix:
                bad = [s for s in rule.no_suffix if stem.endswith(s)]
                if bad:
                    msg = rule.message or f"'{fname}' in '{file_layer}' should not end with {bad}"
                    violations.append(Violation(
                        rule_kind=RuleKind.NAMING,
                        severity=Severity.WARNING,
                        message=msg,
                        file=node.path, line=0,
                        from_layer=file_layer, to_layer="",
                        import_path="", rule_name="naming",
                    ))

    return violations


# ── Max coupling checker ──────────────────────────────────────────────────────

def check_max_coupling(rules: CompiledArchRules, graph: ImportGraph) -> list[Violation]:
    violations = []
    for node in graph.nodes.values():
        file_layer = rules.assign_layer(node.path)
        for rule in rules.coupling_rules:
            if rule.layer != file_layer:
                continue
            # Count unique external namespaces imported
            external = {
                e.target_ns for e in node.imports
                if not e.target_ns.startswith('.')
                and not e.target_ns.startswith(node.namespace)
            }
            if len(external) > rule.max_external_imports:
                violations.append(Violation(
                    rule_kind=RuleKind.MAX_COUPLING,
                    severity=Severity.WARNING,
                    message=(
                        f"Coupling: '{node.path}' imports from {len(external)} external namespaces "
                        f"(max {rule.max_external_imports}). "
                        + (rule.message or "")
                    ),
                    file=node.path, line=0,
                    from_layer=file_layer, to_layer="multiple",
                    import_path=", ".join(sorted(external)[:5]),
                    rule_name="max_coupling",
                ))
    return violations


# ── Domain isolation checker ──────────────────────────────────────────────────

def _find_context(rules: CompiledArchRules, path: str) -> str:
    for ctx in rules.domain_contexts:
        for pat in ctx.patterns:
            if _glob_match(pat, path):
                return ctx.name
    return "none"


def _is_allowed_crossing(rules: CompiledArchRules, from_ctx: str, to_ctx: str, via_path: str) -> bool:
    for crossing in rules.allowed_crossings:
        if crossing['from'] == from_ctx and crossing['to'] == to_ctx:
            via_pattern = crossing.get('via', '')
            if not via_pattern or _glob_match(via_pattern, via_path):
                return True
    return False


def check_domain_isolation(rules: CompiledArchRules, graph: ImportGraph) -> list[Violation]:
    if not rules.domain_contexts:
        return []
    violations = []
    for node in graph.nodes.values():
        from_ctx = _find_context(rules, node.path)
        if from_ctx == 'none':
            continue
        for edge in node.imports:
            to_ctx = _find_context(rules, edge.target_ns)
            if to_ctx == 'none' or to_ctx == from_ctx:
                continue
            if _is_allowed_crossing(rules, from_ctx, to_ctx, node.path):
                continue
            violations.append(Violation(
                rule_kind=RuleKind.DOMAIN_ISOLATION,
                severity=Severity.ERROR,
                message=(
                    f"Bounded context violation: '{from_ctx}' context imports from '{to_ctx}' context "
                    f"without going through a declared integration point"
                ),
                file=node.path, line=edge.line,
                from_layer=from_ctx, to_layer=to_ctx,
                import_path=edge.target_ns,
                rule_name="domain_isolation",
            ))
    return violations


# ── Circular dependency checker ───────────────────────────────────────────────

def check_circular(graph: ImportGraph) -> list[Violation]:
    chains = graph.detect_circular_chains()
    violations = []
    for chain in chains:
        chain_str = " → ".join(chain)
        violations.append(Violation(
            rule_kind=RuleKind.NO_CIRCULAR,
            severity=Severity.ERROR,
            message=f"Circular dependency: {chain_str}",
            file=chain[0].replace('.', '/') + '.cs',
            line=0,
            from_layer=chain[0],
            to_layer=chain[-1],
            import_path=chain_str,
            rule_name="no_circular",
        ))
    return violations
