# OpenSearch MCP Server — Phased Rebuild Plan

> Companion to `FASTMCP_REBUILD_DESIGN.md`. This is the sequenced, gated execution plan. The goal is a clean, modular reorg on the **official MCP SDK** (`mcp>=1.25,<2`) that preserves the black-box contract **1:1**.

---

## 1. Guiding Principles

1. **The integration suite is the oracle.** ~40 black-box tests (subprocess CLI + `/health` + `/mcp` wire + verbatim text markers) define "1:1." They must stay green at every phase boundary. Only *internal organization* changes — never observable bytes.
2. **Move, don't rewrite.** `opensearch/` (auth/client/helper), all tool handlers, `tool_filter.py`, `config.py`, `tool_executor.py`, installer/hooks are relocated **verbatim**. Reviewers should see file moves, not behavior diffs.
3. **Stay on the low-level `mcp.server.Server`.** It is the cleanest 1:1 match for raw-schema dicts + per-mode mutation, and it is what the repo already runs. Zero new top-level dependencies.
4. **Golden-snapshot before deleting.** Capture the 4 generated tools' exact schemas from the live generator before `tool_generator.py` is removed.
5. **Shims keep unit tests green.** Lazy `TOOL_REGISTRY` re-export, `global_state` delegation, and retained `streaming_server` patch symbols are intentional, documented debt with a removal path in a later major.
6. **One change-set per phase, each independently green.** Land phases as reviewable PRs; never break `main`.
7. **Sign every commit `-s`** (DCO) and run the formatter before each commit.

---

## 2. Phase-by-Phase Plan

> Effort is rough, for one engineer familiar with the repo. "Gate" = the tests that must pass before the phase merges.

### Phase 0 — Golden snapshot + pin (do this FIRST)
**Deliverables**
- A throwaway script runs `generate_tools_from_openapi()` against the pinned spec and serializes the 4 tools' `input_schema`, `min_version`, `max_version`, `http_methods` to a fixture (`tests/fixtures/generated_tools_golden.json`).
- A regression test `test_generated_tools_golden` that will later assert the static dicts byte-match the fixture.
- Bump `pyproject.toml`: `mcp[cli]>=1.9.4` → `mcp>=1.25,<2`; refresh `uv.lock`.

**Gate:** full existing suite green on the new pin (unit + integration where env available).
**Effort:** 0.5 day.

---

### Phase 1 — Scaffold (settings / bootstrap / serve / registry)
**Deliverables**
- `mcp_server_opensearch/settings.py`: `ServerSettings`/`AppContext` frozen dataclass.
- `mcp_server_opensearch/bootstrap.py`: `build_app_context()` + `build_registry(ctx)` — the single owner of the 5-step boot, lifted from the duplicated stdio/streaming startup.
- `mcp_server_opensearch/serve.py`: `serve_pipeline(ctx)` + `register_mcp_handlers(server, enabled_tools)` building `Server('opensearch-mcp-server', …)`, wiring `@list_tools()` (`Tool(name, description, inputSchema=dict)`) + `@call_tool() → execute_tool`.
- `tools/registry.py`: `ToolRegistry` (insertion-ordered) + `ToolSpec` TypedDict + `add()` validating required keys, `display_name` regex `^[a-zA-Z0-9_-]+$`, and **no-duplicate-keys**.
- `tools/modules.py`: `MODULES` manifest in exact legacy order.
- `tools/compat.py`: `check_tool_compatibility` moved here (breaks the circular import).

At this phase the registry is still populated from the legacy `tools.py` (adapter), so nothing observable changes yet.

**Gate:** all unit tests green (via shims); `test_streaming_server` route-table test green; a new `test_composition_order` asserting `list(registry.keys()) == legacy_order` for memory on/off.
**Effort:** 1.5 days.

---

### Phase 2 — Client / Auth layer (move, don't modify)
**Deliverables**
- Confirm `opensearch/client.py`, `connection.py`, `helper.py` are byte-identical post-move (no edits). If the import paths are unchanged (they are — package roots kept), this is a **no-op verification phase**.
- Add a focused unit test matrix asserting the 7-mode priority order + the preserved quirks (Bearer drops user-agent; password not stripped; URL port injection; `aoss` vs `es`) if not already covered.

**Gate:** `integration_tests/auth/*` (the 6 server-side auth configs + header-auth priority) green where `IT_*` env present; otherwise skip cleanly.
**Effort:** 0.5 day (verification-heavy, not code-heavy).

---

### Phase 3 — Static tools by domain
**Deliverables (one sub-PR per domain to keep reviews small)**
- `tools/domains/core.py` — ListIndex, IndexMapping, SearchIndex, GetIndexInfo, GetIndexStats, Generic, ListClusters(`multi_only`).
- `tools/domains/cat.py` — GetShards, GetClusterState, GetSegments, CatNodes, GetAllocation, GetLongRunningTasks, GetNodes, GetQueryInsights, GetNodesHotThreads.
- `tools/domains/search_relevance.py` — the 19 SRW tools.
- `tools/domains/agentic_memory.py` — `register()` the 7 ML-Commons tools (handlers stay in `agentic_memory/actions.py`).
- `tools/domains/skills.py` — DataDistribution, LogPatternAnalysis.
- `tools/domains/memory.py` — `register()` NO-OP unless `ctx.memory_tools_enabled`; preserves `bypass_write_filter`/`memory_tool` flags.
- `tools/domains/generated/{schema,params,handlers}.py` — the 4 hand-written tools (the hard part). `schema.py` builds the dicts explicitly; `handlers.py` ports `select_endpoint` + `process_body` NDJSON verbatim; plain `json.dumps` + `TextContent`.
- Flip the registry source from the legacy `tools.py` adapter to `MODULES`.

**Gate:**
- `test_generated_tools_golden` byte-matches the Phase-0 fixture.
- `integration_tests/tools/*` (≈20 files) all marker assertions green.
- `test_composition_order` still green after the source flip.
**Effort:** 3–4 days (generated tools ≈1.5 of those).

---

### Phase 4 — Config / Filtering / Write protection
**Deliverables**
- `tool_filter.py`, `config.py`, `utils.py` moved verbatim; `apply_custom_tool_config` keeps its `copy.deepcopy` boundary.
- Wire `allow_write` resolution + `allow_write_categories` exempt-set + the dual write-protection through `AppContext` (single-init-then-read; safe under stateless HTTP).
- Reproduce the asymmetric precedence in `AppContext` (non-empty `tools` section disables CLI overrides; config-file path disables env filtering) with a dedicated unit test.

**Gate:**
- `integration_tests/tool_filtering/*` (env/CLI/YAML) green.
- `integration_tests/write_protection/*` (disabled/enabled/categories) green — especially `ALLOW_WRITE=false + ALLOW_WRITE_CATEGORIES=search_relevance` lists SRW write tools **but** Generic POST still blocked.
- `tests/tools/test_tool_filters.py` + per-mode schema-stripping tests green.
**Effort:** 2 days.

---

### Phase 5 — Transports
**Deliverables**
- `transport/starlette_app.py`: `MCPStarletteApp` moved **verbatim** — `StreamableHTTPSessionManager(stateless=True, json_response=False)`, exact 5-route ordered table, bare `/mcp` as Route + Mount (#271 no-307), `/health`→200, lifespan + uvicorn graceful shutdown.
- `stdio_server.py` / `streaming_server.py` reduced to thin wrappers over `serve_pipeline`, keeping the symbol names unit tests patch (`create_mcp_server`, `MCPStarletteApp`, `get_tools`).

**Gate:**
- `test_streaming_server` route-table + no-redirect test green.
- Integration harness boot (`/health` poll → 200) + a smoke `list_tools`/`call_tool` over `/mcp` green for both single and multi mode.
**Effort:** 1 day.

---

### Phase 6 — Memory / Skills / Installer
**Deliverables**
- `memory_tools.py`, `skills_tools.py`, `installer.py`, `install_hooks.py`, `agentic_memory/*` moved verbatim.
- Move the memory env-gate from import-time to `ctx.memory_tools_enabled` (resolved once in bootstrap), preserving: (a) absence of the 3 tools when disabled (baseline 44 vs 47), (b) the independent multi-mode `memory_tool` exclusion.
- Verify CLI argv pre-dispatch still routes `memory install` and `install-hooks` before argparse, with identical flag semantics (bare `--from-local`⇒cwd, abspath).

**Gate:**
- Memory tool integration/unit tests green (where AWS env present, else skip).
- `requires_ml_tool`-gated agentic/skills tests green or cleanly skipped.
- Installer/hooks unit tests (file targets, base64 Stop-hook, idempotency substrings, apostrophe-free prompts) green.
**Effort:** 1.5 days.

---

### Phase 7 — Test migration
**Deliverables**
- Unit tests pinned to `tool_generator` internals: **deleted**, replaced by direct tests of the 4 static generated tools + the golden snapshot.
- Unit tests patching `mcp_server_opensearch.streaming_server.get_tools` / `set_mode` / `process_tool_filter` / the dict registry: kept green via shims (minimal/no edits).
- New tests added where the reorg enables cleaner coverage (per-domain `register()` smoke tests, no-duplicate-keys assertion).

**Gate:** full `tests/` suite green; `pytest -m <marker>` selection intact for all registered markers.
**Effort:** 1.5 days.

---

### Phase 8 — Compatibility shim cleanup decision + cutover
**Deliverables**
- Document the shims (`tools/tools.py` lazy `TOOL_REGISTRY` re-export + `check_tool_compatibility`; `global_state` delegation; retained `streaming_server` symbols) as known debt with a removal target (next major).
- Final full-suite run (unit + all available integration markers) + a manual smoke against a real cluster in single and multi mode.
- Update `README`/`USER_GUIDE` only where internal module paths are referenced (the external CLI/config docs do not change).

**Gate:** green CI; reviewer sign-off; no observable behavior delta vs `main`.
**Effort:** 1 day.

**Total rough effort:** ~13–15 engineer-days, landable as ~10–12 reviewable PRs.

---

## 3. Test Strategy — reusing ~15k LOC of tests as the 1:1 oracle

| Layer | What it does | Reuse posture |
|---|---|---|
| **Integration (~40 tests, `integration_tests/`)** | Black-box: spawn the real server subprocess, poll `/health`, talk MCP over `/mcp`, assert on text markers, auth precedence, write-blocking, filtering visibility, multi-cluster params, concurrency. Imports nothing from the package **except** `CONNECTION_OVERRIDE_FIELDS` from `server_instructions`. | **Survives essentially unchanged.** This IS the 1:1 oracle. Keep CLI flags, endpoints, env-var names, tool names, schema fields, and `Error`/`Input validation error` prefixes. The only possible edit is the `CONNECTION_OVERRIDE_FIELDS` import path — and we deliberately keep `server_instructions` so even that doesn't move. |
| **Unit (~520 tests, `tests/`)** | White-box: import internal modules, mock the OpenSearch client, assert on `process_tool_filter`/`get_tools`/`execute_tool`/`is_tool_compatible`, the dict-registry shape, and the Starlette route table. Patch concrete symbols. | **Kept green via shims** for the bulk; **rewritten** only for the `tool_generator`-internal tests (replaced by static-tool + golden-snapshot tests) and the #271 route test (re-validated against the verbatim route table). |

**Marker contract preserved exactly:** `eval` (skipped unless `--run-evals` + `ANTHROPIC_API_KEY`), category selectors (`auth`/`tools`/`errors`/`concurrency`/`server_modes`/`dynamic_connection`), env-dependency categories (`basic_auth`/`aws`/`iam_role`/`header_auth`/`no_auth` — skip when `IT_*` missing), `requires_ml_tool` (probes the live cluster). Missing env ⇒ **skip**, never fail.

**Phase-boundary rule:** a phase cannot merge until its gate tests AND the full integration suite (for available markers) are green.

---

## 4. Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Phase |
|---|---|:--:|:--:|---|:--:|
| 1 | Hand-built generated schema diverges from the generator's dict (body `type`, missing `default`, `typed_keys` type, title casing) | Med | High | Golden snapshot **before** deletion + byte-equality regression test; build dict element-by-element | 0, 3 |
| 2 | `min_version` normalized to `1.0.0` instead of `1.0` | Med | Med | Hard-code `'1.0'`; assert via golden snapshot + version-error-text test | 3 |
| 3 | Per-mode schema mutation copy-semantics changed (deep-copy or per-request `get_tools`) corrupts the shared registry | Low | High | Keep once-at-startup snapshot + `apply_custom_tool_config` deepcopy boundary; reproduce 3-condition `opensearch_url`-required logic verbatim | 3, 4 |
| 4 | Write-protection refactor loses the empty/missing-`http_methods`→write-only edge or applies categories to the runtime gate | Med | High | Preserve substring semantics + two separate layers; explicit empty/missing→dropped unit test | 4 |
| 5 | Bootstrap ordering: `set_mode` runs after schema computation → mode silently `single` | Low | High | Set mode/profile/config in `bootstrap` before `build_registry`; assert in a unit test | 1 |
| 6 | Composition order / memory-gate drift; duplicate-key silent drop under FastMCP semantics | Low | Med | Pinned order-equality test + `add()` no-duplicate-keys hard failure | 1, 6 |
| 7 | #271 bare-`/mcp` 307 regression | Low | Med | Move `MCPStarletteApp` verbatim; keep the route-table unit test | 5 |
| 8 | Building on the refuted "header auth needs low-level Server" premise | N/A | — | **Removed from rationale.** We keep the low-level Server for the raw-schema/per-mode contract, not for header auth | Design |
| 9 | Generated tools' plain-`json.dumps` vs `format_json` divergence "cleaned up" | Low | Low | Verified safe against current suite, but preserve plain `json.dumps` for zero drift; keep `process_body` NDJSON spacing | 3 |
| 10 | Future v2 (`FastMCP`→`MCPServer`) lands via routine bump | Low | High | Pin `mcp>=1.25,<2`; isolate transport wiring so a budgeted v2 migration is confined to `serve.py` + `transport/` | 0 |

---

## 5. Open Questions for the Maintainer

1. **Spec pinning for generated tools.** After deleting the live OpenAPI fetch, the 4 tools' schemas become hard-coded constants that no longer track upstream `opensearch-api-specification`. Acceptable? Should we add a periodic CI job that re-fetches the spec and diffs against the static dicts to catch upstream drift?
2. **`tool_params.py` split.** Keep the single `tool_params.py` in the first cut (lower risk), or split per-domain into `tools/args/` immediately for the contribution-ergonomics win? (Design defers this as optional.)
3. **Shim lifetime.** The `tools/tools.py` `TOOL_REGISTRY` re-export + `global_state` delegation shims keep ~520 unit tests green. Do you want a tracking issue to remove them (and rewrite those tests against the new structure) in the next major, or keep them indefinitely?
4. **Generated-tool output serialization.** Verified safe to standardize the 4 tools on compact `format_json` (current integration assertions pass either way). Preserve the existing spaced `json.dumps` for zero drift (recommended), or unify on `format_json` for consistency?
5. **v2 migration timing.** v2 brings native middleware (the natural home for `tool_execution` logging + list-time write filter). Do you want the rebuild to leave explicit seams for that, or stay strictly minimal on the 1.x line until v2 stabilizes?
6. **`max_size_limit` wiring.** `SearchIndexTool`'s clamp reads `max_size_limit` from its registry entry (default 100), set via config. Confirm the rebuild should continue to inject this from config into the `ToolSpec` rather than hard-coding.
