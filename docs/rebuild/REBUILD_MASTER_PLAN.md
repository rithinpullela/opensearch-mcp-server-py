# OpenSearch MCP Server — Rebuild Master Plan (North Star)

> **This is the authoritative plan.** It reconciles the four research deliverables into one
> sequenced, test-gated build with every behavior change justified. When any other doc conflicts
> with this one, this one wins.
>
> Companion docs (inputs, kept for detail):
> `FASTMCP_REBUILD_DESIGN.md` · `FASTMCP_REBUILD_PLAN.md` · `AUDIT_FINDINGS.md` ·
> `ERROR_LOGGING_EVALUATION.md` · `DESIGN_DECISIONS.md` · `MCP_V2_EXPLAINER.md`
>
> Branch: `rebuild/fastmcp-modular` · Baseline: **525 unit tests** collect/pass (excl. `eval` marker)
> · ~30 integration test files are the **black-box 1:1 oracle**.

---

## 1. Goal

Rebuild `opensearch-mcp-server-py` so it is **easy to understand, contribute to, and maintain**, with
**strong backward compatibility** — by reorganizing the working code into a clean modular shape, fixing
a bounded set of real defects the audit confirmed, and deleting the runtime OpenAPI generator. This is
**a reorganization + targeted fixes, not a behavioral rewrite.**

**The framework question, settled:** "Port to FastMCP" resolves to **stay on the low-level
`mcp.server.Server`** and earn the "clean" win through *modularization*, not high-level `FastMCP`
decorators. Reasons (verified): (a) the server does per-mode schema mutation that the decorator API
can't express; (b) the official SDK v2 renames `FastMCP`→`MCPServer` (alpha now, stable ~mid-2026) —
staying low-level means the rename can't touch us; (c) zero new framework dependency on an official
OpenSearch repo. Pin **`mcp>=1.25,<2`**.

---

## 2. The Prime Directive

**No drift from current observable behavior without a concrete, documented reason.**

- **Reproduce faithfully** (the external contract): the 48 tool names + I/O text, the 4 generated
  tools (golden-snapshot-locked), the auth/connection-override matrix, tool-filtering + write-protection
  semantics, CLI flags + subcommands, env var names, YAML keys, HTTP endpoints, structured-log fields.
- **Change deliberately, each tied to a cited defect** — the list in §5. Every item there has a
  justification, the tests it touches, and whether it needs the maintainer's ratification on return.
- **Honor the adversarial corrections** (things the research disproved): the per-call version check is
  NOT redundant (it's per-call in *both* modes — `tools.py:99-102`); the buffered connection is NOT
  "worse than the parent" (both peak ~3×); the `is_error` dict key is NOT dropped on serialization
  (survives via `extra='allow'`). Build to the corrected reality.

---

## 3. Verified Ground Truth (re-checked against live code 2026-06-14)

| Fact | Verified |
|---|---|
| Static tool registry | **44 tools** (`TOOL_REGISTRY`), +4 generated = 48; memory tools (3) conditional on `MEMORY_TOOLS_ENABLED=true` (default false) |
| Generated tools | `ClusterHealthTool` (GET), `CountTool` (GET,POST), `ExplainTool` (GET,POST; req body,id,index), `MsearchTool` (GET,POST; req body); `min='1.0'` `max='99.99.99'` |
| Golden snapshot | ✅ **captured** at `tests/fixtures/generated_tools_golden.json`; proven deterministic across 2 fetches (normalize `required` as set) |
| Integration oracle failure-detection | `integration_tests/framework/assertions.py:13,27,48` — **text-prefix only** (`'Error'`,`'Input validation error'`); **never reads `isError`** |
| Per-call version gate | Real in **both** modes (`tools.py:99-102` → `helper.py:752-768`); no cache anywhere; `is_tool_compatible(None,…)=True` (fail-open) |
| Response-size default | `DEFAULT_MAX_RESPONSE_SIZE=None` (`connection.py:19`) — OFF, contradicts USER_GUIDE's 10MB |
| `mcp` installed | 1.26.0; pyproject pins `mcp[cli]>=1.9.4` (no upper bound) |
| `pydantic-settings` | NOT a dependency yet (`pydantic>=2.11.3` is) |

---

## 4. Target Architecture (the modular shape)

Keep package roots `mcp_server_opensearch`, `tools`, `opensearch` (import-path compat). Decompose the
monoliths; thread one immutable `ServerContext`; delete the generator.

```
src/
  settings.py            [NEW] Settings(BaseSettings): every env var, one place, typed + aliased
  config_loader.py       [NEW] load_config() -> (Settings, AppConfig); one yaml parse; extra='forbid'
  mcp_server_opensearch/
    __init__.py                main(): argv dispatch + argparse  (IDENTICAL flag/subcommand surface)
    __main__.py                python -m … entry (unchanged)
    context.py           [NEW] ServerContext frozen dataclass (mode/profile/config/allow_write/…)
    bootstrap.py         [NEW] build_context() + build_registry(ctx) — single owner of the boot pipeline
    serve.py             [NEW] serve_pipeline(ctx) + register_mcp_handlers(server, enabled_tools)
    stdio_server.py            thin wrapper → serve_pipeline (keeps unit-test patch symbols)
    streaming_server.py        thin wrapper → serve_pipeline (keeps create_mcp_server/get_tools symbols)
    transport/
      starlette_app.py   [MOVED] MCPStarletteApp verbatim (5-route table, #271 no-307, stateless HTTP)
    tool_executor.py           dispatcher: O(1) lookup by display_name; the ONE error/metric funnel
    logging_config.py          text+json formatters (text renders extra=), stderr-only, redaction filter
    server_instructions.py     CONNECTION_OVERRIDE_FIELDS (importable — integration tests use it)
    clusters_information.py     multi-cluster registry (reads via config_loader)
    installer.py / install_hooks.py   CLI-only subcommands (moved verbatim)
  tools/
    registry.py          [NEW] typed ToolSpec + ToolRegistry (insertion-ordered, no-duplicate-keys)
    modules.py           [NEW] MODULES manifest in EXACT legacy spread order
    compat.py            [NEW] check_tool_compatibility (breaks the import cycle)
    tool_filter.py             write-filter + per-mode schema mutation  ← THE CONTRACT (kept)
    config.py                  apply_custom_tool_config (deepcopy boundary kept; global write removed)
    tool_params.py             baseToolArgs + validate_args_for_mode + redacted_dict()
    tool_logging.py            log_tool_error (returns classification meta; no own logger.error)
    utils.py                   format_json, is_tool_compatible (+ serverless_incompatible follow-up)
    domains/             [NEW] per-domain register(registry, ctx) — ~150 lines each:
      core.py  cat.py  search_relevance.py  agentic_memory.py  skills.py  memory.py
      generated/               the 4 ex-OpenAPI tools, STATIC:
        schema.py              hand-built input_schema dicts (golden-snapshot locked)
        params.py              MsearchArgs/ExplainArgs/CountArgs/ClusterHealthArgs (validation)
        handlers.py            select_endpoint + process_body NDJSON ported verbatim
  opensearch/
    client.py                  uses resolve_auth_strategy(); per-call overrides; version cache wired
    auth_strategy.py     [NEW] resolve_auth_strategy() -> typed AuthStrategy (shared single+multi)
    version_cache.py     [NEW] per-target TTL version cache (asyncio.Lock)
    connection.py              BufferedAsyncHttpConnection: streaming-only, selective except, surrogatepass
    helper.py                  REST calls (split candidate; centralizes {'error':…} re-detection)
# DELETED: tools/tool_generator.py + the boot-time generate_tools_from_openapi() network fetch
```

---

## 5. Decisions Ledger — every change, with justification

### 5A. KEEP (reproduce 1:1 — the contract)
Tool names/count, all tool I/O text + `format_json` compactness + the 4 tools' plain `json.dumps`,
auth precedence order (no_auth>bearer>headerAWS>iam>basic>ambient), connection-override matrix,
tool-filtering category + write-protection semantics, per-mode schema mutation, CLI flags +
`memory install`/`install-hooks`, env var names, YAML keys, `/mcp` `/sse` `/messages/` `/health`
endpoints + #271 no-307, structured-log field names (until 5C migrates them in lockstep).

### 5B. CHANGE — internal only, no observable behavior delta (do freely)
| Item | Defect | 
|---|---|
| Delete runtime OpenAPI generator; 4 tools become static (golden-locked) | P0-1: boot-time unpinned-GitHub fetch, no timeout, stdout print, swallows error, drops tools |
| Split `tools.py`/`tool_params.py`/`helper.py` monoliths into per-domain modules | P1-17/P2-12: god-modules |
| Typed `ToolSpec` + `ToolRegistry` (no-dup-keys, O(1) dispatch); add `category` field | P1-11/P1-18/P3-11 |
| One `ServerContext`; drop process-global mutable state; remove `apply_custom_tool_config` global write | P1-16/P1-20 |
| Single `create_mcp_server`/`serve_pipeline` factory (de-dup boot pipeline) | P1-19 |
| Version cache (`version_cache.py`, asyncio.Lock, TTL 600s, short-floor negative cache) | P1-1: per-call client churn + `/info` stampede |
| `resolve_auth_strategy()` typed resolver (shared single+multi) | P2-3: duplicated 6-level ladder |
| Acyclic layering (move registry+compat to leaf); remove lazy-import dodges; dead-code pass | P2-14/P3-10 |
| Logging: one event schema, text renders `extra=`, stderr-only, quiet 3rd-party loggers, redaction filter, replace generator `print()` | EL P1/P3/P4/P6 |
| Merge `tool_error`→single `tool_execution(status=error)` event (return-meta mechanism) | EL P1: double-event |
| Centralize `{'error':…}` re-detection in helper; delete 6 copy-pasted branches | EL §6 (verified: no test breaks) |
| Config: `Settings(BaseSettings)` + `AppConfig`, one parse, one `env_bool()`, threaded via context | P1-21 |

### 5C. CHANGE — OBSERVABLE behavior; flagged for maintainer ratification on return
| # | Change | Justification | Tests | Ratify? |
|---|---|---|---|---|
| O1 | **`isError` contract fix**: tool failures set `CallToolResult.isError=true` (today errors ride `isError=false`; clients see success) | Audit P1-3 — the #1 correctness gap; MCP spec compliance; user explicitly wants stale test behavior modernized | Rework `assertions.py` to read `isError` **FIRST**, migrate `test_tool_executor.py`+`test_tool_logging.py` in lockstep, then flip | **YES** |
| O2 | **10MB response-size default enforced** (was unlimited) | Match USER_GUIDE; prevent OOM | update `test_init_default_max_response_size`; per-call override escape hatch | **YES** (regresses large `_search`/`_cat`) |
| O3 | Mid-stream/transport errors propagate raw; delete post-hoc fallback | P1-10: single 404 = 2 HTTP requests (non-idempotent hazard) | delete `test_perform_request_fallback_to_parent`; add `test_non_idempotent_404_not_reissued` | **YES** |
| O4 | Partial AWS header creds → raise `AuthenticationError` (no ambient fallthrough) | P2/§4: privilege-confusion fix; verified non-breaking | `test_auth_strategy.py` (new) | No |
| O5 | Multi mode rejects per-call `aws_profile`/`opensearch_no_auth` | Multi-tenant identity hardening; single/zero-config unaffected | `test_auth_strategy.py`, multi-mode override case | **YES** |
| O6 | `version=None` (serverless/error) — add `serverless_incompatible` flag + fail-safe; cache alone doesn't fix | Cache passes None through; `is_tool_compatible(None)=True` enables 3.3.0+ tools that fail at runtime | `test_tool_filters.py` (add None case) | **YES** |
| O7 | YAML typos fail fast (`extra='forbid'`); config precedence per-field (env>file>default) vs today's whole-file shadow | Single source of truth; catch latent errors | new Settings tests; `test_config.py` holds | **YES** |
| O8 | `max_response_size` per-call overridable | Lets agents raise cap when 10MB too small | add to `test_connection_overrides.py` matrix | rec. |
| O9 | Decode → `('utf-8','surrogatepass')`; URL userinfo scrubbed from logs; IAM ARN INFO→DEBUG; UA preserved on bearer | Match opensearch-py; CWE-532 log hygiene | adjust log-assertion tests; decode happy-path holds | No |

**Rejected from research (do NOT implement):** global `ALLOW_PER_CALL_HOST_IDENTITY_SELECTION` flag
(breaks zero-config → replaced by O5 mode-specific gate); `threading.RLock` for the cache (use
`asyncio.Lock`); flipping `isError` without first reworking `assertions.py` (false-green trap).

---

## 6. Build Sequence (phases; each = reviewable, gated green)

> Gate = stated tests pass + `ruff format`/`ruff check` clean + commit signed `-s`. Never break a phase boundary.

- **P0 — Snapshot & pin.** ✅ golden snapshot captured. Pin `mcp>=1.25,<2`; add `pydantic-settings`; refresh lock. Gate: 525 unit green on new pin.
- **P1 — Scaffold.** `settings.py`, `config_loader.py`, `context.py`, `bootstrap.py`, `serve.py`, `registry.py`, `modules.py`, `compat.py`. Registry still fed from legacy `tools.py` adapter (nothing observable changes). Gate: unit green via shims + composition-order test (legacy key order, memory on/off).
- **P2 — Client/auth/version-cache/connection.** `auth_strategy.py`, `version_cache.py`, `connection.py` refactor (streaming-only, surrogatepass, selective except, 10MB default), per-call `max_response_size`. Gate: `integration_tests/auth/*` + `test_connection_overrides` + new `test_auth_strategy`/`test_version_cache` + connection tests.
- **P3 — Static tools by domain** (incl. the 4 generated; flip registry source legacy→MODULES). Gate: `test_generated_tools_golden` byte-matches fixture; `integration_tests/tools/*`; composition-order holds.
- **P4 — Config/filtering/write-protection** on the new settings model; declarative `category` field; fail-closed filter. Gate: `tool_filtering/*` + `write_protection/*` + `test_tool_filters` + `test_config`.
- **P5 — Transports.** Move `MCPStarletteApp` verbatim into `transport/`; thin server wrappers. Gate: route-table + no-307 test; live `/health`+`/mcp` smoke single+multi.
- **P6 — Error/logging funnel.** One `tool_execution` event, centralized `{'error':…}` re-detection, redaction filter, text-renders-extra, stderr-only. **O1 isError**: rework `assertions.py` first → migrate unit tests → flip. Gate: `test_tool_logging`+`test_tool_executor` (migrated) + full integration suite green on `isError`.
- **P7 — Memory/skills/installer** moved verbatim; memory env-gate via `ctx`. Gate: memory/installer tests (skip when AWS env absent).
- **P8 — Test migration + cutover.** Delete `test_tool_generator.py`; gate `test_judgment_tool_evals.py` behind marker; dead-code pass; full suite + live smoke (stdio+stream × single+multi). Write handoff (Phase E).

---

## 7. Open Questions for the Maintainer (answer on return)
1. **O1 isError flip** — ratify the contract fix + `assertions.py` rework? (I'm proceeding; it's reversible.)
2. **O2 10MB default** — confirm the cap value; any known large-response workloads to size for?
3. **O5/O6** — any multi-mode deployment relying on per-call `aws_profile`/`no_auth`? Confirm serverless fail-safe policy (fail-open vs fail-closed when version unknown).
4. **O7** — accept per-field config precedence replacing whole-file shadowing? (One-release diff-logging shim available.)
5. **Spec-drift CI** — want a periodic job diffing the live OpenAPI spec against the 4 static generated-tool schemas?
