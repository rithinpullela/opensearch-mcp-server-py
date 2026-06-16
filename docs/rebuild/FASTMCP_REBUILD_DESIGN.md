# OpenSearch MCP Server — Rebuild Architecture Design

> Status: design proposal. Scope: rebuild `opensearch-mcp-server-py` on the **official MCP Python SDK** with a clean, modular, contribute-friendly structure while preserving the **observable behavior 1:1**.

---

## 1. Executive Summary

**Is a clean 1:1 rebuild feasible? — Yes, with one honest caveat.**

A clean, modular rebuild that preserves the entire black-box contract (CLI flags, endpoints, tool names, schema fields, output/error text, auth modes, transports) is **feasible and low-risk**, because the load-bearing pieces (the low-level `mcp.server.Server`, the raw-dict tool registry, the connection/auth layer, the handler text) are **moved, not rewritten**. The rebuild is primarily a **reorganization** — splitting the 1,297-line `tools.py` and 687-line `tool_params.py` into ~150-line per-domain modules — plus **deleting the runtime OpenAPI generator** in favor of 4 hand-written static tools.

The one caveat: the 4 generator-produced tools (`MsearchTool`, `ExplainTool`, `CountTool`, `ClusterHealthTool`) have **hand-built `input_schema` dicts that do NOT equal any Pydantic `model_json_schema()`**. They must be reconstructed by hand and locked with a **golden-snapshot test captured from the live generator before deletion**. This is the single sharpest fidelity risk and is fully mitigable.

**Headline:** *Keep the low-level `mcp.server.Server` + the raw-dict tool registry that the repo already runs on; reorganize the monolith into per-domain `register(registry, ctx)` modules; delete the OpenAPI generator in favor of 4 golden-snapshot-locked static tools. Zero new top-level dependencies.*

---

## 2. Why the Current Code Is Messy

The current server already works and is on the right framework — but its organization fights contributors:

| Problem | Where | Pain |
|---|---|---|
| **Monolithic registry** | `src/tools/tools.py` (1,297 lines) | A single literal `TOOL_REGISTRY = {**SKILLS, **AGENTIC, **MEMORY, ...35 inline}`. Adding a tool means editing a giant file and a giant dict spread. |
| **Monolithic params** | `src/tools/tool_params.py` (687 lines) | Every Pydantic args model in one file; unrelated tools collide in diffs. |
| **Runtime OpenAPI generator** | `src/tools/tool_generator.py` | 4 tools are synthesized **at server boot by fetching the OpenSearch OpenAPI spec from GitHub over the network**. A boot-time network dependency, non-deterministic schema, and hard-to-test code path. |
| **Duplicated startup** | `stdio_server.py` + `streaming_server.py` | The 5-step boot pipeline (`set_mode` → `load_clusters` → generate → `apply_custom_tool_config` → `get_tools`) is copy-pasted across both transports. |
| **Circular-import dance** | `tools.py` ↔ `check_tool_compatibility` | Lazy imports inside functions to dodge cycles. |
| **Process-global mutable state** | `global_state.py`, `_resolved_allow_write_setting`, `cluster_registry` | Set-once-then-read globals threaded implicitly through the call graph rather than an explicit context object. |

**Important:** the repo is **not** on FastMCP today. It uses the low-level `mcp.server.Server` with an explicit `@server.list_tools()` that emits `Tool(inputSchema=<raw dict>)`. That low-level API is actually the *cleanest* match for the repo's raw-schema + per-mode-mutation contract — so the rebuild keeps it.

---

## 3. Framework Decision

**Recommendation: the official MCP Python SDK (`modelcontextprotocol/python-sdk`), pinned `mcp>=1.25,<2`. Confidence: high.**

The pragmatic reading of "FastMCP": **keep the low-level `mcp.server.Server`** where the raw-schema / per-mode-mutation / route-table / dual-write-protection contract lives, and adopt the high-level `FastMCP` API *only* where it adds clarity. The repo already runs entirely on the first-party `mcp` package (1.23.0 in the lock; pyproject pins `mcp[cli]>=1.9.4`), with **zero `jlowin/fastmcp` references**.

### Scorecard (official SDK vs third-party `jlowin/fastmcp`)

| Criterion | Official | 3rd-party | Verdict / Why |
|---|:--:|:--:|---|
| 1:1 contract fidelity (raw `model_json_schema()` dicts, per-mode mutation, exact text markers, dual write-protection) | 3 | 4 | Neither maps cleanly. 3rd-party scores higher on the *public* raw-schema path, but the repo already hand-builds `Tool(inputSchema=<raw dict>)` on the low-level Server — the cleanest 1:1 match — so official wins pragmatically. |
| **Governance / dependency acceptability (weighted heavily)** | **5** | **2** | **Decisive.** Official SDK = the same first-party package already vendored → **zero new top-level deps**. 3rd-party adds a large NEW transitive surface (authlib, cyclopts, openapi-pydantic, jsonschema-path, websockets, …), raises the mcp floor to ≥1.17, single-maintainer bus-factor. For an official OpenSearch repo, first-party is the only governable default. |
| Ease of contribution & readability | 4 | 4 | Tie. 3rd-party has nicer decorators; official keeps a small mental model with no exotic concepts and preserves the dict registry the team knows. |
| Auth coverage (7 OpenSearch client auth modes) | 4 | 4 | Orthogonal. All 7 modes live in the connection layer and port verbatim regardless of framework. |
| Transport coverage (incl. stateless streamable-http) | 5 | 5 | Both support stdio + SSE + streamable-http. Repo already runs `StreamableHTTPSessionManager(stateless=True)`; survives unchanged. |
| Tool filtering + per-category write protection | 4 | 4 | Both reduce to "decide which tools to register at startup + keep the runtime gate." Existing custom code is preserved either way. |
| Multi-cluster + per-call dynamic connection / per-mode schema toggling | 4 | 3 | Neither supports per-request schema *views* natively. The repo's raw-dict mutation in `get_tools()` ports directly onto the low-level Server; it fights 3rd-party's signature-first decorators. |
| Maturity / forward-compat with v2 | 4 | 3 | Official 1.x is GA/maintenance, semver-bounded; pin `<2` to avoid the imminent v2 `FastMCP`→`MCPServer` rename. 3rd-party churns fast (3.x re-arch, ~262 open issues). |
| Testing story (white-box + black-box) | 4 | 4 | Black-box integration tests are framework-agnostic. White-box unit tests patch concrete symbols + the dict registry — **least** rewriting if we stay on the current low-level Server + dict registry. |

**Net:** governance + the verified architectural fact (already on the low-level Server) point the same way. Adopting the official SDK adds **zero new dependencies** and keeps the entire tree first-party and already-audited.

---

## 4. The External Contract (preserve 1:1)

This is the black-box feature inventory. Every box below is an observable behavior the integration suite pins. **If a box changes, we broke compatibility.**

### 4.1 CLI / Entry Point
- [ ] `[project.scripts] opensearch-mcp-server-py = "mcp_server_opensearch:main"` — unchanged.
- [ ] Flags: `--transport {stdio,stream}` (default stdio), `--host` (127.0.0.1), `--port` (9900), `--mode {single,multi}` (single), `--profile` (''), `--config` (''), `--debug`, `--log-format {text,json}`.
- [ ] Pre-argparse argv dispatch: `memory install [--from-git URL | --from-local [PATH]]` (bare `--from-local` ⇒ cwd; paths abspath'd) and `install-hooks --client {kiro,claude-code,cursor} [--scope {workspace,user}]`.
- [ ] Dotted overrides: `--tool.<Tool>.<field>=<value>` (field ∈ {display_name, description, args, max_size_limit}); values coerced via `yaml.safe_load` with raw-string fallback; duplicate keys → last wins + warning.

### 4.2 MCP Wire / Transport
- [ ] `python -m mcp_server_opensearch --transport stream ...` boots; `GET /health` → 200; MCP streamable-http at `/mcp`.
- [ ] Starlette route table (ordered): `/sse` (GET), `/health` (GET→200 'OK'), `/messages/` (Mount), `/mcp` (Route), `/mcp` (Mount). Bare `/mcp` must **NOT** 307-redirect (issue #271).
- [ ] `StreamableHTTPSessionManager(stateless=True, json_response=False)` — stateless horizontal scaling preserved.
- [ ] Graceful SIGTERM shutdown within 5s; stdio transport uses `raise_exceptions=True`.

### 4.3 Tool Catalog (≈44 static; +3 if `MEMORY_TOOLS_ENABLED`)
- [ ] **Core/cat (16):** ListIndexTool, IndexMappingTool, SearchIndexTool, GetShardsTool, GetClusterStateTool, GetSegmentsTool, CatNodesTool, GetIndexInfoTool, GetIndexStatsTool, GetQueryInsightsTool, GetNodesHotThreadsTool, GetAllocationTool, GetLongRunningTasksTool, GetNodesTool, GenericOpenSearchApiTool, ListClustersTool (`multi_only`).
- [ ] **Search relevance (19):** Get/Create/Sample/Delete QuerySet; Get/Create/Delete Experiment; Create/Get/Delete SearchConfiguration; Get/Create/CreateUBI/Delete/CreateLLM JudgmentList; Search QuerySets/SearchConfigurations/Judgments/Experiments.
- [ ] **Agentic memory (7):** Create Session, Add Memories, Get, Update, DeleteByID, DeleteByQuery, Search. Always registered; min_version 3.3.0.
- [ ] **Skills (2):** DataDistributionTool, LogPatternAnalysisTool. min_version 3.3.0.
- [ ] **Generated (4, now static):** MsearchTool, ExplainTool, CountTool, ClusterHealthTool.
- [ ] **Memory (3, conditional):** SaveMemoryTool, SearchMemoryTool, DeleteMemoryTool — only when `MEMORY_TOOLS_ENABLED=true`.
- [ ] Display names byte-identical; registry key order matches legacy `**`-spread order.

### 4.4 Per-tool output markers (asserted verbatim by integration tests)
- [ ] `All indices information:` / `Indices:` / `Mapping for` / `Search results from … (JSON|CSV format)` / `OpenSearch API Response` / `Cluster state information` / `Detailed information for index` / `Statistics for index` / `Node information` / `Detailed node information` / `Allocation information` / `Segment information` / `shard|prirep|state` headers / `Hot threads information` / `DataDistributionTool result` / `LogPatternAnalysisTool result`.
- [ ] JSON via `format_json` = `json.dumps(data, separators=(',',':'), ensure_ascii=False)` (compact) for **most** tools.
- [ ] The 4 generated tools use **plain `json.dumps(response)`** (default spaced separators) via `TextContent` — divergence preserved (see §11).
- [ ] CSV via DictWriter (dot-flattened); raw text passthrough for hot-threads.

### 4.5 Errors & version gating
- [ ] Tool errors return text content beginning with `Error <op>: <exc>` / `Error: <exc>` and carry `is_error: True`. Successful responses never begin with `Error`/`Input validation error`.
- [ ] `check_tool_compatibility` raises `Tool '<name>' is not supported for this OpenSearch version (current version: <v>). Supported version: <min> to <max>.`
- [ ] Version-gated: all inline + agentic + the 4 generated tools. **NOT** gated: ListClustersTool, GenericOpenSearchApiTool, skills, memory tools.
- [ ] `is_tool_compatible`: `None` version ⇒ always compatible; else `min <= current <= max` (inclusive).
- [ ] Structured log per execution: `event_type='tool_execution'`, fields status/duration_ms/tool_key/error_type.

### 4.6 Connection & Auth (7 modes, all in `opensearch/client.py`)
- [ ] Priority order: `no_auth` > Bearer header > header-AWS-creds (needs region) > IAM role (STS) > basic (both user+pass; **password NOT stripped**) > fallback session SigV4.
- [ ] Single mode = env + 10 per-call `baseToolArgs` overrides + optional headers; multi mode = `ClusterInfo` from YAML + optional headers (no per-call overrides).
- [ ] Header auth (lowercased): `opensearch-url`, `aws-region`, `aws-access-key-id`, `aws-secret-access-key`, `aws-session-token`, `aws-service-name`, `authorization`. Headers override server creds.
- [ ] Quirks preserved: Bearer branch **replaces** headers dict (drops user-agent); URL default-port injection (http→80, https→443) preserving userinfo + IPv6; service `aoss` vs `es`; mTLS both-or-error.
- [ ] `BufferedAsyncHttpConnection` (chunked size-limit streaming) + `USER_AGENT` retained.

### 4.7 Config / Filtering / Write Protection
- [ ] 5 YAML sections: `clusters`, `agentic_memory`, `tools`, `tool_category`, `tool_filters`. Env vars mirror controls (used only when no `--config`).
- [ ] **Asymmetric precedence:** a non-empty `tools` section silently disables CLI `--tool.*` overrides; a config-file path silently disables env-var filtering.
- [ ] `core_tools` always force-enabled (seeded). Enabled allowlist is additive with core.
- [ ] **Dual write protection:** (1) list-time `apply_write_filter` drops tools where `'GET' not in http_methods` (substring on the **comma-joined string**; missing ⇒ `[]` ⇒ write-only ⇒ dropped) unless `bypass_write_filter` or in `allow_write_categories`; (2) call-time `GenericOpenSearchApiTool` blocks POST/PUT/DELETE/PATCH with `Write operations are disabled. Method "<M>" is not allowed.` — **categories exempt (1) only, never (2).**
- [ ] allow_write precedence: YAML `tool_filters.settings.allow_write` > env `OPENSEARCH_SETTINGS_ALLOW_WRITE` > default True.

### 4.8 Per-mode schema views (the contract's subtlest part)
- [ ] **single:** strip `opensearch_cluster_name` always; strip `CONNECTION_OVERRIDE_FIELDS` unless dynamic; append `opensearch_url` to `required` **only** when dynamic AND no header-auth AND no `OPENSEARCH_URL` env.
- [ ] **multi:** strip `CONNECTION_OVERRIDE_FIELDS`; **keep** `opensearch_cluster_name`; **exclude** `memory_tool` entries.
- [ ] `CONNECTION_OVERRIDE_FIELDS` stays importable from `mcp_server_opensearch.server_instructions` (the one symbol integration tests import).

### 4.9 Memory / Agentic / Skills / Installer
- [ ] Memory tools auto-create the index via boto3 (managed + AOSS + data-access-policy), recency-decay search (`exp(-0.693 * max(0, age-offset)/half_life)`, defaults offset 24h / half-life 168h), size cap min(size,100).
- [ ] Agentic memory: ML-Commons `memory_containers` REST; `type`→`memory_type` alias; container_id injection (schema default + drop from required + before-validator) for the exact 7 tools; GET-with-body for search.
- [ ] Installer + install-hooks: CLI-only argv subcommands; apostrophe-free `SEARCH_PROMPT`/`SAVE_PROMPT`; base64 Stop-hook loop guard; idempotency by tool-name substring.

---

## 5. Target Architecture

Keep the three existing top-level package roots (`mcp_server_opensearch`, `tools`, `opensearch`) for **1:1 import-path compat**. Delete `tool_generator.py` and the `tools.py` registry literal; everything else is **moved, not modified**.

### 5.1 Layering (text diagram)

```
CLI entry (main)                       mcp_server_opensearch/__init__.py
  └─ pre-argparse argv dispatch        memory install / install-hooks
  └─ argparse → ServerSettings         settings.py (frozen dataclass)
        │
        ▼
build_app_context(settings)            bootstrap.py   ← SINGLE owner of the 5-step boot
  set_mode/profile/config              (mode set BEFORE any tool registration!)
  (+multi) load_clusters_from_yaml
        │
        ▼
build_registry(ctx)                    tools/registry.py + tools/modules.py
  compose MODULES via register()       skills→agentic→memory→core→cat→srw→generated
  apply_custom_tool_config             tools/config.py
  get_tools (per-mode schema mutation) tools/tool_filter.py   ← THE CONTRACT
        │
        ▼
serve_pipeline(ctx, enabled_tools)     serve.py
  Server('opensearch-mcp-server')      low-level mcp.server.Server
  @list_tools → Tool(inputSchema=dict) (raw dict, verbatim)
  @call_tool  → execute_tool           tool_executor.py (structured logging)
        │
   ┌────┴─────────────┐
   ▼                  ▼
stdio_server.py   streaming_server.py + transport/starlette_app.py
                  (5-route table, no-307, stateless HTTP)
        │
        ▼
get_opensearch_client(args)            opensearch/client.py  (7 auth modes, MOVED-NOT-MODIFIED)
  BufferedAsyncHttpConnection          opensearch/connection.py
  helper API calls                     opensearch/helper.py
```

### 5.2 File tree

```
src/
  mcp_server_opensearch/            # SERVER / TRANSPORT / COMPOSITION
    __init__.py                     # main(): argv dispatch + argparse (IDENTICAL flag surface)
    __main__.py                     # python -m … → main()  (unchanged)
    settings.py          [NEW]      # ServerSettings/AppContext frozen dataclass
    bootstrap.py         [NEW]      # build_app_context() + build_registry(ctx)  (single boot owner)
    serve.py             [NEW]      # serve_pipeline(ctx) + register_mcp_handlers(server, enabled)
    stdio_server.py                 # serve() → serve_pipeline → stdio_server() + memory monitor
    streaming_server.py             # create_mcp_server()/serve(); keeps unit-test patch symbols
    transport/
      starlette_app.py   [MOVED]    # MCPStarletteApp VERBATIM (5-route table, #271 no-307)
    global_state.py                 # RETAINED compat shim → delegates to AppContext
    clusters_information.py         # UNCHANGED
    server_instructions.py          # UNCHANGED (CONNECTION_OVERRIDE_FIELDS lives here)
    tool_executor.py                # UNCHANGED (event_type='tool_execution' logging)
    logging_config.py               # UNCHANGED
    installer.py                    # UNCHANGED (CLI-only)
    install_hooks.py                # UNCHANGED (load-bearing prompt strings)
  tools/                            # REGISTRY + DOMAIN MODULES
    registry.py          [NEW]      # ToolRegistry (ordered) + ToolSpec TypedDict + add() validation
    modules.py           [NEW]      # MODULES manifest in EXACT legacy spread order
    compat.py            [NEW]      # check_tool_compatibility (moved out to break cycle) + lazy TOOL_REGISTRY shim
    tool_params.py                  # baseToolArgs + validate_args_for_mode + inline *Args (UNCHANGED behavior)
    tool_logging.py                 # UNCHANGED (log_tool_error)
    tool_filter.py                  # UNCHANGED PIPELINE (write filter + per-mode raw-dict mutation) ← CONTRACT
    config.py                       # UNCHANGED (apply_custom_tool_config, deepcopy boundary)
    utils.py                        # UNCHANGED (format_json, is_tool_compatible)
    generic_api_tool.py             # UNCHANGED (runtime PermissionError write gate)
    memory_tools.py                 # UNCHANGED handlers
    skills_tools.py                 # UNCHANGED handlers
    agentic_memory/{actions,params}.py  # UNCHANGED
    domains/             [NEW]      # self-contained register(registry, ctx) per domain
      core.py  cat.py  search_relevance.py  agentic_memory.py  skills.py  memory.py
      generated/                    # the 4 ex-OpenAPI tools, STATIC
        params.py                   # MsearchArgs/ExplainArgs/CountArgs/ClusterHealthArgs (validation only)
        handlers.py                 # select_endpoint + process_body NDJSON ported VERBATIM
        schema.py                   # HAND-BUILT input_schema dicts (golden-snapshot locked)
  opensearch/                       # CLIENT + AUTH (moved-not-modified)
    client.py  connection.py  helper.py
# DELETED: src/tools/tool_generator.py (+ boot-time generate_tools_from_openapi network fetch)
```

### 5.3 The `ToolSpec` shape (unchanged keys)

```python
class ToolSpec(TypedDict):
    display_name: str
    description: str
    input_schema: dict          # raw model_json_schema() OR hand-built dict
    function: Callable          # async handler
    args_model: type[BaseModel]
    # optional flags:
    min_version: NotRequired[str]
    max_version: NotRequired[str]
    http_methods: NotRequired[str]   # comma-joined STRING, e.g. 'GET, POST'
    multi_only: NotRequired[bool]
    bypass_write_filter: NotRequired[bool]
    memory_tool: NotRequired[bool]
    max_size_limit: NotRequired[int]
```

---

## 6. The Tool Pattern

**Canonical pattern:** a tool is a `ToolSpec` dict registered by a domain module's `register(registry, ctx)` function. **No decorators. No FastMCP `Tool` objects.** This is the only structure that natively supports per-mode raw-schema mutation, the comma-joined `http_methods` substring write-filter, and the custom flags.

### 6.1 A normal tool (schema derived from the args model)

```python
# tools/domains/core.py
async def list_indices_tool(args: ListIndicesArgs) -> list[dict]:
    await check_tool_compatibility('ListIndexTool', args)
    try:
        async with get_opensearch_client(args) as client:
            data = await list_indices(client, args)   # opensearch/helper.py
        return [{'type': 'text', 'text': f'All indices information:\n{format_json(data)}'}]
    except Exception as e:
        return log_tool_error('ListIndexTool', e, 'listing indices', index=args.index)

def register(registry: ToolRegistry, ctx: AppContext) -> None:
    registry.add('ListIndexTool', ToolSpec(
        display_name='ListIndexTool',
        description='Lists indices …',
        input_schema=ListIndicesArgs.model_json_schema(),   # raw flat dict
        function=list_indices_tool,
        args_model=ListIndicesArgs,
        min_version='1.0.0', http_methods='GET'))
```

### 6.2 The hardest case end-to-end — `MsearchTool`

The generated schema is a **hand-built dict, NOT** `model_json_schema()`. Pydantic emits `$defs`/`anyOf`/`default:null`/Title-Case-with-spaces wrappers that **will not byte-match**. So the static rewrite builds the dict explicitly and validates with a separate Pydantic model.

```python
# tools/domains/generated/schema.py
def _base_props():                       # 11 baseToolArgs props, verbatim from the model
    return dict(baseToolArgs.model_json_schema()['properties'])

MSEARCH_SCHEMA = {
    'type': 'object', 'title': 'msearchArgs',
    'properties': {
        **_base_props(),
        'index': {'title': 'Index', 'type': 'string'},          # path param, no default
        'body':  {'title': 'Body', 'description': BODY_DESCRIPTIONS['msearch']},  # NO 'type' key
        'allow_partial_results':       {'title': 'Allow Partial Results', 'type': 'string', 'description': '…'},
        'ccs_minimize_roundtrips':     {'title': 'Ccs Minimize Roundtrips', 'type': 'string', 'description': '…'},
        # … all query params as str (typed_keys keeps its OpenAPI type, e.g. 'boolean')
    },
    'required': ['body'],                # index optional (2/4 endpoints); body force-required for msearch
}

# tools/domains/generated/params.py  — validation only, NOT the schema source
class MsearchArgs(baseToolArgs):
    index: Optional[str] = None
    body: Optional[Any] = None
    allow_partial_results: Optional[str] = None
    # … all query params Optional[str] = None

# tools/domains/generated/handlers.py
ENDPOINTS_MSEARCH = [
    {'path': '/_msearch', 'method': 'GET'}, {'path': '/_msearch', 'method': 'POST'},
    {'path': '/{index}/_msearch', 'method': 'GET'}, {'path': '/{index}/_msearch', 'method': 'POST'}]

async def msearch_tool(args: MsearchArgs) -> list:
    await check_tool_compatibility('MsearchTool', args)         # generated tools DO version-gate
    try:
        p = args.model_dump(exclude_none=True)
        body = process_body(p.pop('body', None), 'MsearchTool')  # NDJSON conversion, verbatim
        ep = select_endpoint(ENDPOINTS_MSEARCH, p)
        path = ep['path']
        if p.get('index'):
            path = path.replace('{index}', str(p.pop('index')))
        query = {k: v for k, v in p.items() if k not in BASE_FIELDS}
        async with get_opensearch_client(args) as client:
            resp = await client.transport.perform_request(ep['method'], path, params=query, body=body)
        text = resp if isinstance(resp, str) else json.dumps(resp)   # PLAIN json.dumps — NOT format_json
        return [TextContent(type='text', text=text)]
    except Exception as e:
        return log_tool_error('MsearchTool', e, 'executing MsearchTool')

def register(registry, ctx):
    registry.add('MsearchTool', ToolSpec(
        display_name='MsearchTool', description='…',
        input_schema=MSEARCH_SCHEMA, function=msearch_tool, args_model=MsearchArgs,
        min_version='1.0', max_version='99.99.99', http_methods='GET, POST'))
```

**Locked version/method metadata (verified from the live spec via golden snapshot):**

| Tool | min | max | http_methods | required |
|---|---|---|---|---|
| MsearchTool | `1.0` | `99.99.99` | `GET, POST` | `[body]` (index optional) |
| ExplainTool | `1.0` | `99.99.99` | `GET, POST` | `[index, id, body]` |
| CountTool | `1.0` | `99.99.99` | `GET, POST` | `[]` (index + body optional) |
| ClusterHealthTool | `1.0` | `99.99.99` | `GET` | `[]` (index optional, no body field) |

> Note: it is `1.0`, **not** `1.0.0`. The raw string surfaces in the `Supported version: 1.0 to 99.99.99` error text and in registry-shape unit tests. Do not "normalize" it.

---

## 7. Config / Auth / Transport Design

### 7.1 Config — one immutable `AppContext`
Built once by `build_app_context(cli_args, cli_tool_overrides)` in `bootstrap.py`. Holds mode/profile/config_path, a lazy `ServerConfig` view of the 5 YAML sections (or env-derived equivalents when no `--config`), and resolved `allow_write` + `dynamic_connection`. The asymmetric precedence (non-empty `tools` section silently disables CLI overrides; config-file path silently disables env filtering) is reproduced verbatim and made testable in one place. `apply_custom_tool_config` and `process_tool_filter` are reused **unchanged**, including the upstream `copy.deepcopy(tool_registry)` boundary that shields the global registry.

### 7.2 Auth — 100% in `opensearch/client.py` (moved, not modified)
The framework swap touches **none** of the auth code. All 7 modes, the priority short-circuits, region resolution, URL/port injection, mTLS, and `_get_auth_from_headers` (via `mcp.server.lowlevel.server.request_ctx` + Starlette `Request`) port verbatim. Single vs multi is dispatched on `get_mode()`, which **must** be set process-wide in `bootstrap` **before** any tool registration — otherwise mode silently defaults to `single` and multi-mode schema views compute wrong.

### 7.3 Transport — two thin transports, one pipeline
Both `stdio_server` and `streaming_server` call `serve_pipeline(ctx)`. Streaming keeps the hand-built `MCPStarletteApp`: `StreamableHTTPSessionManager(stateless=True, json_response=False)`, the exact 5-route ordered table with bare `/mcp` as **both** Route and Mount (#271 no-307 fix), `/health`→200, uvicorn graceful shutdown. Transport wiring is isolated in `transport/` so a future v2 migration is confined to `serve.py` + `transport/` + `tool_executor.py`.

### 7.4 Dependency pin
Move `mcp` from 1.23.0 → **`mcp>=1.25,<2`** in the same change so the v2 `FastMCP`→`MCPServer` rename + lowlevel return-type changes cannot arrive via a routine bump.

---

## 8. What We Are Deleting — and Why

**Deleted:** `src/tools/tool_generator.py` and the boot-time `generate_tools_from_openapi()` GitHub network fetch.

| Why | Benefit |
|---|---|
| Boot-time network call to fetch the OpenAPI spec | Removes a startup reliability/latency dependency; deterministic boot |
| Non-deterministic, hard-to-test generated schemas | 4 tools become plain static code with a golden-snapshot regression test |
| Complex extract/build machinery for 4 tools | ~4 small `schema.py`/`params.py`/`handlers.py` files a contributor can read |

**Trade-off (accepted):** the 4 endpoints' params no longer auto-track upstream spec changes; future OpenSearch param additions become a manual edit to `generated/schema.py` + `params.py`. Given there are only 4 tools and the endpoints are stable, determinism + no-network-boot + 1:1 stability win.

**Mandatory safety net:** capture a golden snapshot of each tool's `input_schema` / `min_version` / `max_version` / `http_methods` from the **live generator before deleting it**, and add a regression test asserting byte-equality of the static dicts against that snapshot.

---

## 9. Backward-Compatibility Guarantees

| Surface | Guarantee |
|---|---|
| CLI entry + flags | Identical script name, identical flag surface, identical argv pre-dispatch subcommands |
| Tool names / count | ≈44 static (+3 memory) display names byte-identical; legacy registry key order preserved (pinned by an equality test) |
| Schemas | Raw `model_json_schema()` dicts + 4 hand-built generated dicts; identical per-mode mutation; `CONNECTION_OVERRIDE_FIELDS` importable from `server_instructions` |
| Output / error text | All markers, compact-`format_json` vs the 4 tools' plain `json.dumps`, pipe tables, CSV, raw hot-threads, `Error <op>: <exc>` prefixes + `is_error:True` — unchanged (handlers moved, not modified) |
| Env vars / endpoints | Every `OPENSEARCH_*`/`AWS_*`/`MEMORY_*` read identically; `/health`, `/mcp`, `/sse`, `/messages/` identical; no-307 on bare `/mcp` |
| Version gating | Same tools gate (inline + agentic + 4 generated); ListClustersTool/Generic/skills/memory do NOT |
| Unit tests | Kept green via shims: `tools/tools.py` lazy-composed `TOOL_REGISTRY` re-export; `global_state` delegation; `streaming_server` keeps `create_mcp_server`/`MCPStarletteApp`/`get_tools` patch symbols |

---

## 10. Composition Order & Override Semantics (verified)

The `MODULES` manifest must reproduce the legacy `**`-spread order **key-for-key**: `skills → agentic_memory → memory → core → cat → search_relevance → generated`. A pinned test asserts `list(composed.keys()) == legacy_expected_order` for `MEMORY_TOOLS_ENABLED ∈ {false, true}`.

**Honest correction (adversarial pass):** the synthesized claim that "register() risks last-writer-wins override drift" is **inverted**. Legacy dict-spread is **last-writer-wins**; the high-level FastMCP `add_tool` is **first-writer-wins** (it logs "Tool already exists" and keeps the first). Our `ToolRegistry.add()` must therefore **assert no duplicate keys before registration** so any future collision is a *hard failure*, not a silent override or silent drop. Verified: the current catalog has **zero duplicate keys** across all four sources, so neither override path is exercised today — but the guard prevents future drift.

---

## 11. Verified Risks & Mitigations

Each risk below was run through an adversarial verification pass. **Verdicts are honest — refuted claims are marked.**

| # | Risk | Verdict | Mitigation |
|---|---|:--:|---|
| R1 | The 4 generated tools' `input_schema` is a hand-built dict that does NOT byte-match any Pydantic `model_json_schema()` (body has no `type`; path params have no `default`; `typed_keys` keeps `boolean`; titles are `name.title()`). | **CONFIRMED** | Build the dict by hand element-by-element; **never** register via `@tool`/`add_tool` (no schema-override hook). Capture golden snapshot from the live generator **before** deletion; byte-equality regression test. Pin/vendor the spec-derived strings. |
| R2 | `min_version` must be `'1.0'` (not `'1.0.0'`), `max_version` `'99.99.99'`; the raw string is observable in the `Supported version:` error text. | **CONFIRMED** | Hand-write the exact strings. Do NOT normalize to `'1.0.0'`. Becomes a hard-coded constant (no longer tracks upstream — accepted). |
| R3 | `get_tools` mutates schemas differently per mode: multi mutates `properties` **in place** on the shared entry + drops memory tools (keeps `opensearch_cluster_name`); single does shallow `.copy()` that **shares nested** `properties`/`required`, strips cluster_name always + override fields unless dynamic, conditionally appends `opensearch_url` to required (3 ANDed conditions). | **CONFIRMED** (with caveat) | Preserve the exact copy semantics + 3-condition logic. **Caveat:** the cross-call "registry corruption" is NOT a live bug today because (a) `get_tools` runs once at startup and (b) `apply_custom_tool_config` returns a `copy.deepcopy`. Keep both the once-at-startup snapshot and the deepcopy boundary, OR deep-copy each returned schema. Do NOT call `get_tools` per-request or drop the deepcopy. |
| R4 | Dual write-protection: substring `'GET' not in http_methods`; missing ⇒ `[]` ⇒ write-only ⇒ dropped; `allow_write_categories` exempts list-time only, never the runtime `GenericOpenSearchApiTool` gate. | **CONFIRMED** | Preserve "keep-if-contains-GET-else-drop" + the empty/missing-as-write-only edge. Keep the two layers fully separate; if methods are refactored to a list/enum, add an explicit empty/missing→dropped unit test. |
| R5 | "Header auth ONLY works on the low-level Server; FastMCP's app builder would break it." | **REFUTED** | FastMCP wraps the **same** low-level Server + `StreamableHTTPServerTransport`; `request_ctx.get().request` resolves identically. Header auth would NOT break under FastMCP. **Drop this false justification.** The *real* load-bearing constraint is bootstrap ordering: `set_mode` MUST run before schema computation, regardless of framework. (We stay on the low-level Server for the raw-schema/per-mode-mutation contract, not for header auth.) Header auth remains HTTP-only (no request on stdio) — already true today. |
| R6 | MODULES composition order + memory env-gate must reproduce legacy spread exactly; "register risks override drift." | **PARTIAL (drift claim inverted)** | Order + import-gate halves confirmed. Override claim is **backwards** (see §10): FastMCP `add_tool` is first-writer-wins (silent drop), not last-writer-wins. Add a no-duplicate-keys assertion + the pinned order-equality test. Move the memory gate from import-time to `ctx.memory_tools_enabled` while keeping the independent multi-mode `memory_tool` exclusion. |
| R7 | The 4 generated tools serialize with plain `json.dumps` (spaced), not compact `format_json`; "standardizing breaks tests." | **PARTIAL (why-it-matters refuted)** | The 4 named integration assertions are substring checks on key+quote tokens or JSON re-parse (whitespace-insensitive) — they pass under **both** serializations. So switching to `format_json` is verifiably safe against the current suite. **Recommendation:** preserve plain `json.dumps` anyway for zero behavioral drift. The genuine verbatim dependency is `process_body`'s NDJSON spacing for msearch — keep that untouched regardless. |

**Net:** R1 and R3 are the two sharpest risks and are fully mitigated by the golden snapshot + preserving the deepcopy/once-at-startup boundary. R5 is a *refuted* premise we explicitly remove from the rationale to avoid building on a false foundation.
