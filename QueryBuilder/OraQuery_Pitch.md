# Problem Statement

Writing and reviewing Oracle SQL is slow and error-prone. Developers either hand-write complex multi-table queries (easy to get joins, NULL handling, or aggregation wrong) or use Copilot/AI to generate SQL (fast, but unvalidated — Oracle-specific bugs like `ROWNUM` misuse, `NULL = NULL`, or missing `GROUP BY` columns ship silently). Existing tools (SQL Developer, generic DB GUIs) either require a live connection and don't catch Oracle-specific anti-patterns, or are generic SQL builders with no Oracle awareness. Teams have no fast, in-editor way to build, validate, and trust a query before running it against production.

# Proposed Idea

OraQuery: a VS Code extension that puts a visual Oracle SQL query builder directly in the editor, integrated with Copilot Chat. Tables and joins are built visually on a canvas; the tool generates production-ready Oracle SQL and runs it through a 22-rule Oracle-specific validator automatically — catching mistakes before they reach a database session, not after.

# Differentiation

- **Oracle-specific, not generic SQL.** Native support for `CONNECT BY`, `PIVOT`/`UNPIVOT`, `NVL`/`DECODE`, `FETCH FIRST`, Oracle hints (`/*+ ... */`), and 22 validation rules tied to real `ORA-XXXXX` errors — not a generic ANSI SQL tool with Oracle bolted on.
- **Lives where developers already work.** No separate app, no new login — it's a VS Code panel, alongside the code and Copilot Chat developers already use daily.
- **Validates instead of trusting.** Copilot and most AI tools generate SQL with no safety net. OraQuery closes that loop: generate → validate → auto-fix the deterministic mistakes → surface only the judgment calls that need a human.
- **Visual-first for complex joins.** Multi-table joins, self-joins, and multi-hop FK chains are built by dragging tables, not by hand-writing nested `ON` clauses — the highest-friction part of SQL authoring for both humans and AI-generated queries.

# Capabilities

- **Visual query canvas** — drag-and-drop tables, auto-detected FK joins, self-joins, multi-hop joins, non-equi joins, full WHERE/GROUP BY/HAVING/ORDER BY/window function builders, CTEs, subqueries, CASE/NVL/DECODE expressions, UNION/PIVOT/UNPIVOT, and CONNECT BY hierarchical queries — all without hand-writing SQL.
- **22-rule Oracle validation engine** — catches real `ORA-XXXXX` errors, silent-failure traps (`NULL = NULL`), anti-patterns (`ROWNUM` instead of `FETCH FIRST`), and structural issues (circular CTEs, cartesian products, non-deterministic window functions) before the query ever runs.
- **Copilot Chat integration (`@oraquery`)** — generate SQL from natural language inside the editor, with the validator running automatically on the output; deterministic mistakes are auto-fixed, judgment-call issues are surfaced inline instead of shipping silently.

# Solution Value

OraQuery turns SQL authoring from "write it, run it, hope it's right" into a validated, visual, in-editor workflow. It reduces time spent debugging join logic and Oracle-specific runtime errors, makes AI-generated SQL trustworthy instead of just fast, and gives teams a shared, consistent way to build and review complex Oracle queries without leaving VS Code.