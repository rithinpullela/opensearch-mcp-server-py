# Rebuild process documentation

These are **internal process artifacts** from the modular-rebuild effort (the work that
split the monolithic tool registry, removed the runtime OpenAPI generator, added the
version cache, and hardened auth / response-size handling). They are kept for
auditability and to explain *why* the current architecture looks the way it does — they
are **not** contributor onboarding docs. For that, see the repo root: `README.md`,
`DEVELOPER_GUIDE.md`, `AGENTS.md`, `USER_GUIDE.md`, `CONTRIBUTING.md`.

## What's authoritative

| Doc | Status | Read it for |
|---|---|---|
| **`DECISION_LOG.md`** | ✅ **Authoritative** — the running record (D0–D15+) | What changed, and the *why* behind every design/code decision, in order. **Start here.** |
| **`ADVERSARIAL_REVIEW_LOG.md`** | ✅ Authoritative — append-only review trail | The adversarial critiques at each checkpoint and how findings were resolved. |
| `AUDIT_FINDINGS.md` | ✅ Historical-but-accurate | The original architecture/behavior audit (P0–P3 findings) that scoped the work. |
| `ERROR_LOGGING_EVALUATION.md` | ✅ Historical-but-accurate | The error-handling / structured-logging evaluation. |
| `MCP_V2_EXPLAINER.md` | ✅ Reference | What MCP SDK/protocol "v2" changes and why we pinned `mcp>=1.25,<2`. |

## ⚠️ Superseded — do NOT treat as the shipped design

| Doc | Status | Why |
|---|---|---|
| `REBUILD_MASTER_PLAN.md` (§4 Target Architecture) | ⚠️ **Partially superseded by DECISION_LOG D11/D14** | Describes an immutable `ServerContext`, a single `serve_pipeline`, a typed `Settings` model, and an `auth_strategy.py` module as the target. Those were **built then deleted** once adversarial review showed they did not earn their place under the minimal-diff mandate (their premises — e.g. a "duplicated auth ladder" — proved false). The shipped design stays on the low-level `mcp.server.Server`, keeps `global_state` for mode, and fixed auth/config **in place**. |
| `FASTMCP_REBUILD_DESIGN.md`, `FASTMCP_REBUILD_PLAN.md` | ⚠️ **Superseded / exploratory** | Early framework-direction exploration. The rebuild deliberately did **not** adopt a separate "FastMCP" framework; it modularized on the existing low-level SDK. Kept only as a record of the path considered and rejected. |
| `DESIGN_DECISIONS.md` (§4 auth resolver, §5 Settings) | ⚠️ **Partially superseded** | The typed `resolve_auth_strategy()` and `pydantic-settings` model described here were not shipped (see D11/D15); the equivalent fixes were made surgically in `client.py`. The version-cache and response-size sections (§1–§3) *were* shipped and remain accurate. |

When the process docs disagree with the **shipped code** or with **`DECISION_LOG.md`**,
the code and the decision log win.
