# pcos-scanner — project context

Food barcode/scoring Streamlit prototype.

## Read before work

- Read `README.md`.
- Locate relevant work in `core`, `data`, `knowledge`, `migrations`, `tests`, `app.py`.
- Read nested project instructions and the current plan/handoff before changes. Verify commands from the actual README, dependency manifest, or script; setup did not test application behavior.

## Boundaries

- Existing location retained; runtime health not re-tested.
- Keep project-specific instructions in this authoritative file; the other agent filename is an adapter. Do not put personal machine paths or credentials in repository instructions.
- Verify current state rather than treating this inventory snapshot as progress. Preserve unrelated changes; record what was actually tested in the existing handoff.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
