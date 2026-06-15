# OpenSearch MCP Server — Architecture & Behavior Audit

**Scope:** Static subsystem review + dynamic runtime probes + adversarial verification of the sharpest findings, feeding the rebuild ("Phase B") and a deep-research shortlist ("Phase C").
**Guiding rule (restated):** *No drift without a concrete, documented reason.* Every behavior we change in the rebuild must be tied to an explicit defect or a deliberate, signed-off modernization — and every behavior we keep must be reproduced faithfully (golden snapshots where the wire contract matters).

---

## 1. Executive Summary

**Verdict: the architecture is mostly sound and worth a faithful rebuild, but it carries a handful of real, load-bearing defects that must be fixed — not preserved.** The tool I/O contracts, auth/connection-override matrix, tool-filtering category semantics, and structured error logging are solid and well-tested; those should be reproduced 1:1. The defects cluster in four areas the user already flagged: (1) a per-call cluster version round-trip that doubles network traffic, (2) a half-working response-size limiter whose protection is *off by default* while docs claim it is on, (3) a boot-time GitHub fetch for runtime OpenAPI tool generation that makes startup non-deterministic, offline-fragile, and can hang for 30s, and (4) tool-group organization implemented as hard-coded lists that have already drifted out of sync with the registry. A fifth cross-cutting bug: **tool failures are never surfaced via the MCP protocol `isError` flag**, so every call looks like a success to clients.

### Findings by severity

| Severity | Count | Notes |
|---|---|---|
| **P0** | 3 | Boot-time GitHub fetch (no timeout, swallowed, drops 4 core tools); golden-snapshot capture required before removing the generator; the generated tools' global-registry coupling must be preserved during removal. |
| **P1** | ~22 | Per-call version round-trip; soft-error/`isError` contract; response-size default-off + buffering + download-then-check fallback; `connection.py` re-implements parent request flow; god-modules; duplicated boot pipeline; category lists drift; fail-open security filter; global-state mutation. |
| **P2** | ~20 | Typed-exception gaps; duplicated config parsing; precedence asymmetries; auth precedence/partial-cred fallthrough; structural cohesion (helper.py, tool_params.py, get_tools). |
| **P3** | ~12 | Mutable default arg; dead/unreachable code; naming inconsistencies; UA header clobber on bearer path; URL userinfo in logs. |

**Adversarial verification tempered three claims** (reflected honestly below): the per-call check is **not** redundant (it is the *only* version gate in multi mode); the buffered connection is **not "worse than the parent"** (both peak at ~3x); and the custom `is_error` key is **not dropped** on serialization (it survives inside `content`, just not as the protocol-level `isError`).

---

## 2. Prioritized Findings Table

> `Verdict` = adversarial verification result where one exists (CONFIRMED / REFUTED / NUANCED / —). `Action` = KEEP / CHANGE / INVESTIGATE.

| ID | Subsystem | Finding | Verdict | Action | One-line recommendation |
|---|---|---|---|---|---|
| **P0-1** | openapi-gen | Boot fetches OpenAPI spec from `raw.githubusercontent.com/.../refs/heads/main` on every start (no timeout, `print()` to stdout, swallows error, silently drops Msearch/Explain/Count/ClusterHealth) | CONFIRMED | CHANGE (remove) | Delete the generator + both call sites; ship the 4 tools as static `ToolSpec`s. |
| **P0-2** | openapi-gen | Golden snapshot of the 4 generated tools must be captured before deletion (input_schema, http_methods string, versions, required sets, body descriptions) | CONFIRMED | KEEP (reproduce) | Capture `tests/fixtures/generated_tools_golden.json` + a lock test *before* removing the generator. |
| **P0-3** | openapi-gen | Generated `tool_func` self-gates via the **global** `TOOL_REGISTRY[name]` lookup; static tools must register under exact canonical keys in the same dict | CONFIRMED | KEEP (preserve) | Register the 4 static tools in the canonical `TOOL_REGISTRY` under their exact names. |
| **P1-1** | request-path | Every tool call fetches cluster version (`client.info()`) via a fresh, uncached client before the real op — doubles round-trips & client builds | CONFIRMED | CHANGE | Cache version per connection target; remove the per-call probe from the hot path. |
| **P1-2** | request-path | Per-call `check_tool_compatibility` claimed "almost entirely redundant" with registration-time gating | **REFUTED** | INVESTIGATE | Keep it — it is the **only** version gate in multi mode; cache it instead of removing it. |
| **P1-3** | request-path | Soft errors (`is_error=True`) never reach the MCP protocol `isError` flag; clients see every call as success | CONFIRMED (one sub-claim corrected) | CHANGE | Return `CallToolResult(isError=True)` (or raise) for failures. |
| **P1-4** | request-path | `execute_tool` error detection only matches dict-shaped manual tools, misses `TextContent` generated tools | — | CHANGE | Standardize one return contract; detect failure via `isError`. |
| **P1-5** | connection-buffer | Response-size limiter buffers all chunks in a list, then joins, then decodes (~3x), and only checks size when limit is set | NUANCED (not "worse than parent") | CHANGE | Stream into one pre-sized bytearray with early abort; short-circuit to `super()` when limit is None. |
| **P1-6** | connection-buffer | `DEFAULT_MAX_RESPONSE_SIZE=None` contradicts USER_GUIDE's documented 10MB default — protection OFF by default | CONFIRMED | CHANGE | Make code+docs agree; recommend a finite default (10MB) with explicit opt-out. |
| **P1-7** | connection-buffer | Fallback path downloads the entire response, *then* measures size — defeats "before data is fetched into memory" | CONFIRMED | CHANGE | Enforce size incrementally on the fallback too, or via Content-Length pre-check; no post-hoc check. |
| **P1-8** | connection-buffer / auth | Custom `perform_request` re-implements the parent request flow (drift risk; SigV4 bug #237 is direct evidence) | NUANCED (P2; exceptions not mistyped, but duplicate request fired on errors) | CHANGE | Extend, don't fork: enforce size at the body-read step or above the connection; reuse upstream auth/TLS/exception translation. |
| **P1-9** | connection-buffer | Strict UTF-8 decode with `str(bytes)` fallback diverges from parent's `surrogatepass`; corrupts valid responses with surrogate code points | CONFIRMED | CHANGE | Decode with `('utf-8','surrogatepass')`; delete the `str(bytes)` branch. |
| **P1-10** | connection-buffer / auth | Broad `except Exception` re-issues every error response (incl. 404/409) as a second full HTTP request; catches `RecursionError` | CONFIRMED (P0 in auth view) | CHANGE | Catch only transport errors; let HTTP-status errors propagate; never re-issue the request. |
| **P1-11** | tool-groups | Categories are hard-coded external lists, not a per-tool property (zero `category` field in the registry) | — | CHANGE | Add `category` to each `ToolSpec`; derive `category_to_tools` from one registry pass. |
| **P1-12** | tool-groups | `core_tools` list drifted: 4 of 9 names (ClusterHealth/Count/Explain/Msearch) aren't in the static registry, silently skipped | CONFIRMED (they come only from the generator) | CHANGE | Derive core membership from the registry; validate curated sets at startup. |
| **P1-13** | tool-groups | `enabled_category_list` always seeded with `['core_tools']`, so the "enabled" filter always runs (not opt-in) | — | CHANGE | Give each category `enabled_by_default`; don't pre-seed the user-enable list. |
| **P1-14** | tool-groups | A config file silently disables ALL env-var filtering (incl. unrelated disable/allow_write rules) | — | INVESTIGATE | Define one uniform per-field precedence; stop blanket-suppressing env when `--config` present. |
| **P1-15** | tool-groups | `process_tool_filter` swallows all exceptions and returns nothing — malformed filter silently exposes full toolset (fail-open security gate) | — | CHANGE | Validate up front, apply atomically, fail closed/loud on config errors. |
| **P1-16** | config-env / structure | `apply_custom_tool_config` mutates the module-global `default_tool_registry` as a hidden side effect (non-idempotent) | — | CHANGE | Remove the global write; thread the returned registry (callers already capture it). |
| **P1-17** | structure | `tools.py` is a 1297-line god-module mixing 30+ wrappers, the 344-line registry literal, and the version-gate orchestrator | — | CHANGE | Split into `registry.py` + per-domain modules + dispatcher; collapse boilerplate wrappers. |
| **P1-18** | structure | `ToolSpec` is an untyped dict repeated ~50x across 5 files; optional keys present/absent inconsistently; `http_methods` substring-matched | — | CHANGE | Define a typed `ToolSpec` model; `http_methods: frozenset[str]`. |
| **P1-19** | structure | Boot pipeline duplicated verbatim between `stdio_server.py` and `streaming_server.py` | — | CHANGE | Extract a shared `create_mcp_server()` factory; transports differ only in binding. |
| **P1-20** | structure / config | Four+ process-global mutable stores (mode/profile/config_path/allow_write/cluster_registry/TOOL_REGISTRY) mutated at boot, read per request | — | CHANGE | Thread one immutable `ServerContext`; drop module globals. |
| **P1-21** | config-env | No single source of truth: ~30 env vars, 9 CLI flags, ~12 YAML keys across 7 files; YAML re-parsed 5x per boot | — | CHANGE | One `settings.py` (pydantic-settings) + one typed `AppConfig` parsed once. |
| **P1-22** | auth-client | Partial AWS header credentials silently fall through to the server's ambient creds (privilege confusion) | — | CHANGE | Require the full header cred set; raise on partial; never downgrade to ambient. |
| **P2-1** | request-path | `check_tool_compatibility` raises bare `Exception`, funneled through generic catch — can't distinguish incompatible from transient | — | CHANGE | Define a typed `ToolIncompatibleError`; classify non-retryable. |
| **P2-2** | request-path / structure | Version-gate fails open (`None` → compatible) and is paid per-call even when it provides no guarantee | CONFIRMED | INVESTIGATE | Document fail-open semantics; make gating advisory + startup-only/cached. |
| **P2-3** | auth-client | Undocumented 6-level auth priority ladder, duplicated verbatim between single & multi mode | — | CHANGE | One shared auth resolver returning a typed `AuthStrategy`; document precedence. |
| **P2-4** | auth-client | `verify_certs` split across explicit kwarg + `tls_config`; insecure mTLS allowed with only a warning | — | CHANGE | Centralize TLS kwargs; elevate insecure-mTLS to a loud warning/opt-in. |
| **P2-5** | connection-buffer | `OPENSEARCH_MAX_RESPONSE_SIZE` parsing duplicated single/multi; setting undocumented in README; YAML key scattered | — | CHANGE | One `parse_max_response_size()`; co-locate env/YAML/default; fix docs. |
| **P2-6** | connection-buffer | `max_response_size` not per-call overridable while all other connection params are | — | INVESTIGATE | Decide deliberately: include it in overrides or prune the partial surface; document. |
| **P2-7** | config-env | `max_size_limit` per-tool key undocumented & omitted from the validator's own error message | — | CHANGE | Drive validation + error string from one field set; add to `example_config.yml`. |
| **P2-8** | config-env | Duplicate-key handling inconsistent: CLI warns + last-wins, YAML silently last-wins | — | CHANGE | Add a duplicate-key-detecting YAML loader; keep last-wins, warn. |
| **P2-9** | config-env | `parse_unknown_args_to_dict` relies on fragile argparse fallthrough; drops malformed/positional args silently | — | CHANGE | Parse `--k=v` tokens explicitly; error per-token, not a global empty dict. |
| **P2-10** | config-env / structure | Module-global `global_state` for mode/profile/config with silent `'single'` default | — | CHANGE | Thread settings/context; make `get_mode()` loud on unset. |
| **P2-11** | config-env | `OPENSEARCH_SETTINGS_ALLOW_WRITE` defaults to write-enabled, parsed in 3 places; inconsistent truthy parsing across vars | — | CHANGE | One `env_bool()` helper; resolve allow_write once; keep default value. |
| **P2-12** | structure | `helper.py` is a 1290-line catch-all (REST + agentic-memory CRUD + CSV + numeric utils) | — | CHANGE | Split by bounded context; move pure utils to `util/`. |
| **P2-13** | structure | `get_tools` conflates filtering, version-check, schema-stripping, env-reading in one 130-line function with mode branches | — | CHANGE | Decompose into pure composable steps; mode is a parameter. |
| **P2-14** | structure | `tools.tools` lazily imported from 4+ modules purely to break import cycles | — | CHANGE | Move registry + compat to a leaf module; acyclic layering. |
| **P2-15** | structure | Import-time side effects freeze env state (`MEMORY_TOOLS_REGISTRY`, `CONNECTION_OVERRIDE_FIELDS`) before the server configures itself | — | CHANGE | Assemble registries in the boot factory after config is read. |
| **P3-1** | request-path | `is_tool_compatible(tool_info: dict = {})` uses a mutable default arg | — | CHANGE | Use `None` default, normalize inside. |
| **P3-2** | connection-buffer | Size limit counts decompressed bytes (auto_decompress) — ambiguous vs Content-Length | NUANCED | INVESTIGATE | Document decompressed-size semantics; guard any Content-Length fast-path. |
| **P3-3** | connection-buffer / structure | Dead unreachable code + double/triple request logging | — | CHANGE | One structured event per outcome; remove unreachable raise. |
| **P3-4** | auth-client | Bearer auth path replaces (not merges) headers, dropping the custom User-Agent | — | CHANGE | Merge `Authorization` into the base header set. |
| **P3-5** | auth-client | IAM ARN logged at INFO; URL userinfo (`user:pass@host`) preserved into logged URL | — | CHANGE | Scrub URL userinfo; drop ARN to debug; strip creds from stored URL. |
| **P3-6** | auth-client | Per-call connection overrides expose `aws_profile`/`no_auth` to remote callers (host-identity selection) | — | INVESTIGATE | Gate per-call overrides behind a server flag; exclude host-identity selectors. |
| **P3-7** | config-env | Three names for "serverless" (`is_serverless`/`AWS_OPENSEARCH_SERVERLESS`/`aws_opensearch_serverless`) | — | INVESTIGATE | Canonical name + mechanical alias derivation (keep public names). |
| **P3-8** | config-env | CLI dotted-override coercion via `yaml.safe_load` mis-coerces free text (`description=no` → `False`) | — | CHANGE | Coerce per declared field type, not blanket YAML-load. |
| **P3-9** | config-env | Three TLS path env vars invisible to a plain `os.getenv` grep (read via `_get_env_path`) | — | KEEP | List them in the central settings model for discoverability. |
| **P3-10** | structure | Dead code: `get_config_file_path`, `get_memory_tools_registry` have no readers | — | CHANGE | Remove; run a dead-code pass (vulture). |
| **P3-11** | structure | `tool_executor` resolves tool by O(n) linear scan + re-imports `validate_args_for_mode` per call | — | CHANGE | Key `enabled_tools` by display_name (O(1)); module-top import. |
| **P3-12** | observability | `serverInfo.version` reports the MCP SDK version (1.26.0), not the package version (0.10.0) | CONFIRMED | CHANGE | Pass `version=importlib.metadata.version(...)` into `Server(...)`. |

---

## 3. Deep-Dive: User's Named Concerns

### 3.1 Per-request version gating (the network round-trip per call)

**Evidence (CONFIRMED, statically + dynamically + adversarially):**
- Every handler in `src/tools/tools.py` opens with `await check_tool_compatibility('<Tool>', args)` (`tools.py:99-121`), which calls `await get_opensearch_version(args)` (`tools.py:101`).
- `get_opensearch_version` (`src/opensearch/helper.py:753-767`) opens a **fresh** client via `get_opensearch_client(args)` and issues `client.info()` — a `GET /` to the cluster root — then the real helper opens **another** fresh client for the actual operation.
- `get_opensearch_client` (`client.py:108-143`) is a per-call context manager that builds and `close()`s an `AsyncOpenSearch` each call — **no pooling survives the call**. `grep` confirms **zero caching constructs** anywhere in `src/`.
- **Instrumented run:** 15 tool calls → 15 `get_opensearch_version` invocations → 15 `GET /` shadowing 15 data requests (1.00 version round-trip per call; per-call request count **doubled**). At 50ms simulated RTT, ~50ms of ~118ms/call was pure version overhead. Generated/generic-API tools are worse: they open the work client, then open a **second** client for the version check (2 client builds/call).
- The gate **fails open**: `get_opensearch_version` returns `None` on error and `is_tool_compatible(None, …)` returns `True` (`utils.py:30-31`), so when the probe fails it provides no protection — yet the failing round-trip is still paid.

**Adversarial correction — do NOT simply "rely on the registration-time gate":** The registration-time version filter (`tool_filter.py:455/494`) runs **single mode only**; multi mode returns early at `tool_filter.py:450` *before* the version is ever fetched. So in multi mode the per-call `check_tool_compatibility` is the **sole** compatibility gate (search-relevance tools floor at 3.1.0/3.5.0; skills/agentic-memory at 3.3.0). Removing it would let a 3.5.0-only tool run against a 2.x cluster in the same multi-mode server. The "almost entirely redundant" framing is **REFUTED**.

**Recommended modern behavior:**
- Cache the cluster version per connection target — process-global in single mode, keyed by cluster name in multi mode — with an optional TTL; `check_tool_compatibility` reads from cache instead of issuing `client.info()` every call.
- Reuse a long-lived pooled client per target so the (now-cached) probe and the real op share connections.
- In single, non-dynamic mode the startup gate already filtered the registry against the one fixed cluster, so the per-call check can be skipped there; keep it (cached) for multi mode and dynamic/header-auth/URL-override cases.
- For serverless (version `None` → compatible-by-default), caching `None` is sufficient and safe.

**Deep research needed?** **YES (light).** The caching key strategy and TTL for multi-mode (different clusters, dynamic per-call connection overrides) and the interaction with the version-gate fail-open decision need design sign-off before coding.

---

### 3.2 Response-size limiting / streaming memory safety (the buffered connection)

**Evidence (CONFIRMED with one severity correction):**
- `connection.py:182-214` builds `chunks = []`, iterates `response.content.iter_chunked(8192)` appending every chunk, then `b''.join(chunks)`, then `.decode('utf-8')`. The size guard (`:187-190`) only fires `if self.max_response_size is not None`.
- **Default is off:** `DEFAULT_MAX_RESPONSE_SIZE = None` (`connection.py:19`); `client.py` resolves to `None` when the env var is unset. Runtime boot log confirmed: `Configuring OpenSearch client with no response size limit`.
- **Docs disagree:** USER_GUIDE.md:620/669/868/872-873 and `example_config.yml` all claim a **10MB default** "to prevent memory exhaustion." Code default is `None`. **This is a true code/docs contract divergence.**
- **Fallback defeats the purpose:** `_fallback_perform_request` (`connection.py:275-306`) calls `super().perform_request()` (full `response.text()` download) and only *then* measures size — the OOM has already happened. The fallback is reached via a broad `except Exception` that also re-issues the request (see §3.6).
- **Decode divergence:** strict `utf-8` with `str(bytes)` fallback corrupts valid JSON containing surrogate code points; parent uses `('utf-8','surrogatepass')`. Path-dependent: the same bytes deserialize fine via the fallback (parent decode) but fail via the streaming path.

**Adversarial corrections (temper these):**
- **"3x memory, WORSE than parent" is OVERSTATED.** The parent's `await response.text()` internally also does list-append + join + decode in aiohttp's `StreamReader`, so it *also* peaks at ~3x. The accurate statement is **"no safer than the parent at extra cost,"** not "worse."
- **Size is measured on decompressed bytes** (aiohttp `auto_decompress=True`), so a gzip bomb can still inflate before the cap trips. Document this; any Content-Length fast-path must account for compression.

**Recommended modern behavior (priority order):**
1. **Fix the default/docs divergence** — set `DEFAULT_MAX_RESPONSE_SIZE = 10*1024*1024` so protection is on by default and matches the docs, OR (lower-risk) fix the docs to state "no limit." Code and docs **must** agree. *(Note: a 10MB default will start rejecting large `_search`/`_cat` responses that work today; pick the cap with that regression in mind, and update the two tests asserting the `None` default.)*
2. When the limit is `None`, short-circuit to `return await super().perform_request(...)` so the custom path is never paid for when it does nothing.
3. If enforcement is kept: read into one pre-sized `bytearray`, abort on `len > limit`, optional Content-Length pre-check (best-effort; absent for chunked encoding). Decode with `('utf-8','surrogatepass')`; delete the `str(bytes)` branch. Document that the cap is on decompressed size.
4. Make the fallback protective (incremental read) or remove it (see §3.6).

**Deep research needed?** **YES.** Choosing the default cap value, the Content-Length-vs-decompressed-size semantics, and whether to keep a custom connection at all (vs enforcing at the serializer/response layer) all need design analysis — this is the most-tangled subsystem and the verification showed several intertwined bugs.

---

### 3.3 Removing the OpenAPI / HTTP runtime generation

**Evidence (CONFIRMED, P0):**
- `stdio_server.py:45` and `streaming_server.py:52` call `await generate_tools_from_openapi()` **unconditionally** at boot, before tool filtering.
- `tool_generator.py:18` `BASE_URL` points at `raw.githubusercontent.com/.../refs/heads/main/...` (an **unpinned moving branch**); `fetch_github_spec` (`:28-51`) does 2 HTTPS GETs with **no timeout**.
- **Runtime probes:** offline/unroutable host → `generate_tools_from_openapi()` hung **30.4s** (aiohttp default) before failing; pointing at a black-hole host hung **past 20s indefinitely**. On failure it `print()`s to **stdout** (`:315`) — which is the JSON-RPC channel in stdio mode (latent stream-corruption hazard; note it fires during setup *before* the stream opens) — swallows the exception, and silently ships **5 of 9** advertised core tools.
- The entire network dependency exists to add exactly **4 tools** (Msearch/Explain/Count/ClusterHealth); 44/48 (~92%) are already static. Happy-path cost ~0.45–0.5s per boot.

**Hidden couplings to preserve during removal (P0):**
- The generated `tool_func` self-gates via the **global** `TOOL_REGISTRY[name]` lookup (`tool_generator.py:251` → `tools.py:102`), so the 4 static replacements **must** live in the same canonical `TOOL_REGISTRY` dict keyed exactly `MsearchTool`/`ExplainTool`/`CountTool`/`ClusterHealthTool`.
- `select_endpoint` ignores HTTP method → all body-bearing tools issue **GET-with-body** (CONFIRMED live). `http_methods` is the string `'GET, POST'`, matched by the write filter via substring (`'GET' in 'GET, POST'`). Reproduce GET behavior and the substring-passing methods string verbatim — switching to POST is a behavior change requiring sign-off and would interact with the write filter.
- `process_body` NDJSON conversion for msearch (`tool_generator.py:130-171`) is the one genuinely load-bearing transform — port it verbatim, keyed on the same tool-name strings. (The "float coercion" the tests appear to check is an illusion — `1.0 == 1` — do NOT add coercion logic.)

**Recommended modern behavior:** Capture a golden snapshot (`tests/fixtures/generated_tools_golden.json`) by running the live generator **once** against the pinned spec, lock it with a test, *then* hand-write the 4 `ToolSpec`s and delete `generate_tools_from_openapi`, `fetch_github_spec`, both call sites, and the imports. Update/remove dependent tests (whole `test_tool_generator.py`; the `generate_tools_from_openapi` patches in both server tests; the 4-tool fixtures in `test_tool_filters.py`).

**Golden-snapshot locking refinements (from verification):**
- Compare `required` as a **set**, not byte-equal/ordered JSON — the live generator emits set-iteration order, so a strict byte-diff would be flaky against its own baseline.
- For `min/max_version`, assert **semantic** equality (`is_tool_compatible` parses with `optional_minor_and_patch=True`, so `'1.0'` == `'1.0.0'`); only `http_methods` strings and body descriptions/titles must be byte-exact.
- Don't reproduce an `op_group` key — it is never stored or consumed.

**Deep research needed?** **NO** for the removal mechanics (well-understood; just capture-then-replace). **LIGHT** only to decide the static args-model strictness (faithful loose model vs tightening required-ness — a real correctness improvement that fixes the `/None/_explain/{id}` garbage-path bug).

---

### 3.4 Tool-group organization

**Evidence:**
- Categories are **five hard-coded literal lists** inside the 270-line `process_tool_filter` (`tool_filter.py:179-275`), not a property of tools — `grep` finds **zero** `'category'` fields in the registry.
- **Already drifted:** `core_tools` lists 9 names but ClusterHealth/Count/Explain/Msearch aren't in the static registry (they come only from the generator), and the build loop silently skips unknown names. README advertises 9; only 5 are real without the generator. (CONFIRMED.)
- `enabled_category_list` is always seeded `['core_tools']` (`:172`), so the "enabled" filter is permanently on, not opt-in. Memory is conditionally appended; search_relevance/agentic_memory/skills are special-cased elsewhere — the "default on" set is an emergent seeding side effect, not a declaration.
- Category semantics are scattered: memory auto-enables if its tools register (which only happens if `MEMORY_TOOLS_ENABLED=true`), agentic_memory enables via `memory_container_id`, skills is disabled by the installer default. No single table answers "what categories exist, which are on by default, how do I toggle each, what's the write policy."

**Recommended modern behavior:**
- Add `category` (or `categories: list`) to each `ToolSpec`; derive `category_to_tools` from one registry pass — drift becomes structurally impossible.
- One declarative `CATEGORIES` structure: `name → {enabled_by_default, write_default, description}`. Collapse the memory/agentic/skills special-cases into uniform `enabled_by_default` flags. Keep observable defaults (core + memory-when-registered visible; others opt-in).
- Split `process_tool_filter` into `load_filter_config()` (env+YAML → typed `ToolFilterConfig`) and pure `apply_filter(registry, config)`.
- Make the filter **fail closed/loud** on malformed config (it currently swallows all exceptions → fail-open security gate).

**Deep research needed?** **NO.** This is a well-understood declarative refactor; the only design decision (uniform config precedence) overlaps with §3.5.

---

### 3.5 Config / env / YAML / CLI ergonomics (single source of truth)

**Evidence:**
- No single source of truth: ~30 env vars (7 files), 9 CLI flags, ~12 YAML keys; the config YAML is `yaml.safe_load`'d **5 separate times** per boot (`clusters_information.py:84`, `config.py:304,345`, `tool_filter.py:86,278`).
- Precedence is "all-or-nothing" and inconsistent: a `--config` file silently nukes **all** env filtering (only a one-line warning, and only for the 9 tool-filter vars — not connection vars or CLI tool overrides). `allow_write` is read from the file even in env mode. CLI `--tool.X.description` is silently dropped under `--config` with **no** warning.
- `allow_write` defaults to **write-enabled** and its truthy parse is copy-pasted 3x; truthy parsing is inconsistent across vars (`allow_write` accepts only `'true'`; `dynamic_connection` accepts `'1'/'0'`).
- Three names for "serverless"; `max_size_limit` accepted but omitted from its own validator error and from `example_config.yml`; duplicate YAML keys silently last-win (CLI warns); `parse_unknown_args_to_dict` relies on fragile argparse fallthrough.

**Recommended modern behavior:**
- One `settings.py` (pydantic-settings `Settings`) enumerating every env var with type/default/alias, and a typed `AppConfig` parsed **once** from YAML (`extra='forbid'` to reject typos), threaded via `ServerContext`.
- Two-phase config: a **loader** (env AND/OR file → one validated config, with one documented precedence ladder applied uniformly) and a **pure apply** step that knows nothing about env/YAML.
- One `env_bool()` helper with a consistent truthy set; resolve `allow_write` once; canonical name per concept with mechanical alias derivation (keep public names for back-compat).
- Keep external contract identical (same env names, YAML keys, CLI flags) — this is internal consolidation, **not** a public-surface change.

**Deep research needed?** **LIGHT** — pick the precedence ladder (file vs env vs CLI) and confirm pydantic-settings cleanly models the existing env/YAML/arg three-way naming without breaking public names. Mostly a design decision, not research.

---

### 3.6 Auth & connection quality

**Evidence:**
- **Double-execution on errors (P0/P1, CONFIRMED):** the streaming `try` wraps `_raise_error` (`connection.py:247`), so a normal 404/409/400 is caught by the broad `except Exception` (`:266`) and re-issued via the fallback's `super().perform_request()` — verified live: **a single 404 fires 2 HTTP requests.** Doubles error-path load; dangerous for non-idempotent writes. `RecursionError` (an `Exception` subclass) is also wrongly caught. *(Corrections: `CancelledError` is `BaseException` and propagates fine; the re-raised exception **type** is preserved — the defects are the duplicate request, the reraise-contract violation, and double logging, not mistyped exceptions.)*
- **Partial AWS header creds → ambient fallthrough (P2):** if a caller supplies access-key + secret but omits region, the branch is skipped and execution falls through to the **server's** ambient identity — privilege confusion in a multi-tenant feature.
- **Undocumented 6-level auth ladder**, duplicated verbatim single/multi; `no_auth` silently wins over explicit creds; `aws_profile` is remotely settable (host-identity selection).
- **TLS:** `verify_certs` split across an explicit kwarg + `tls_config`; insecure mTLS allowed with only a warning. **Bearer path clobbers headers**, dropping the custom User-Agent (P3). **URL userinfo** (`user:pass@host`) preserved into logged URLs (P3); IAM ARN logged at INFO. *(Good: passwords/tokens/secret keys are never logged — preserve that.)*

**Recommended modern behavior:**
- Don't re-implement `perform_request`. Enforce size at the body-read step or above the connection; reuse upstream auth/TLS/compression/exception-translation. If a streaming early-abort is kept, narrow the `try` so `_raise_error` is outside it, add `except reraise_exceptions: raise`, and translate aiohttp errors to `ConnectionError/ConnectionTimeout/SSLError` as the parent does.
- One shared auth resolver returning a typed `AuthStrategy`; document the precedence ladder; require full header cred sets (raise on partial, never downgrade to ambient); decide whether `no_auth` should override explicit creds (likely warn).
- Centralize all TLS kwargs; elevate insecure-mTLS to a loud warning/opt-in. Merge `Authorization` into base headers (preserve UA). Scrub URL userinfo from logs; lift URL creds into `http_auth`. Use `raise … from e`; don't silently fall back to a default boto3 session when a named profile fails.
- INVESTIGATE gating per-call connection overrides (esp. `aws_profile`, `no_auth`) behind a server opt-in.

**Deep research needed?** **YES (focused).** The auth precedence semantics (no_auth vs explicit creds), per-call override security posture (multi-tenancy + host-identity selectors), and the safest seam to insert size limiting without re-implementing `perform_request` need explicit design analysis — this is the highest-risk file.

---

### 3.7 Module structure & cohesion

**Evidence:**
- `tools.py` (1297 lines) mixes 30+ near-identical wrappers, the 344-line `TOOL_REGISTRY` literal, and the version-gate orchestrator. `helper.py` (1290 lines) spans REST + agentic-memory CRUD + CSV + numeric utils. `tool_params.py` (687 lines) is a flat dump of 35+ Args models with `validate_args_for_mode` mixed in. Args live in 3 different places.
- Boot pipeline duplicated verbatim between the two servers. `tools.tools` lazily imported from 4+ modules to break real import cycles (`tools → generic_api_tool → tool_filter → tools`; `helper → tools → helper`).
- 4+ process-global mutable stores; `apply_custom_tool_config` mutates the global `default_tool_registry` *and* returns a copy (non-idempotent). Import-time side effects freeze env state before the server configures itself. Dead code (`get_config_file_path`, `get_memory_tools_registry`).

**Recommended modern behavior:** Acyclic layering — leaf `registry.py` (`ToolSpec` model + `register()` decorator) + per-domain tool modules that self-register + a dispatcher (`tool_executor.py`) owning the version gate. One shared `create_mcp_server()` factory. One `ServerContext` dataclass threaded explicitly (drop the globals). Assemble registries in the factory (no import-time env reads). Co-locate Args + helpers with their tool group. Run a dead-code pass.

**Deep research needed?** **NO.** Standard decomposition; the only cross-cutting decision (ServerContext shape) is design, informed by §3.1/§3.5.

---

## 4. Test Suite Verdict

The suite (~626 unit + 30 integration files) splits cleanly into a strong external-contract oracle to **KEEP green** and a band of tests that **pin stale behavior** the rebuild must modernize.

### KEEP — the 1:1 oracle (must stay green; these define the contract to reproduce)
- `tests/tools/test_tools.py::TestTools` — exact OpenSearch client call signatures per manual tool (e.g. `cat.indices(index=None, format='json')`, `search(index=…, body={…,'size':10})`) and result text shapes. **(Drop only the per-call `info()` expectation.)**
- `tests/opensearch/test_connection_overrides.py` — per-call override precedence matrix. High value.
- `tests/tools/test_tool_filters.py` (`TestIsToolCompatible`, `TestProcessToolFilter`, `TestAllowWriteCategories`, `TestMultiOnlyFilter`) — version math, category gating, write/allow_write semantics, multi_only exclusion. Strongest part of the suite.
- `tests/tools/test_tool_logging.py` — structured error logging (message format, status_code/root_cause extraction).
- `tests/tools/test_config.py` — YAML+CLI customization & precedence. (Consolidate the redundant `desc alias` test.)
- Integration: `write_protection/*`, `server_modes/*`, `auth/*`, `errors/*`, `tools/test_dynamic_connection.py`, and the 4 generated-tool behavior tests (`test_{count,msearch,explain,cluster_health}_tool.py`) — **retarget the 4 onto static implementations**, don't delete.

### MODERNIZE — tests that pin behavior we are intentionally changing
- **`integration_tests/framework/assertions.py`** — detects failure purely via `text.startswith(('Error','Input validation error'))`, never reads `result.isError`. **Rework FIRST** (read `result.isError`) or the whole integration suite gives false signal once the error contract is fixed.
- `tests/mcp_server_opensearch/test_tool_executor.py::test_soft_error_detected_via_is_error_flag` and `::test_text_starting_with_error_without_flag_is_success` — pin the dropped `is_error` dict key / string-sniffing. Rewrite to assert protocol-level `isError`.
- `tests/opensearch/test_response_size_limiting.py` — `test_init_default_max_response_size` (pins `None` default), `test_perform_request_fallback_to_parent` (enshrines the broken download-then-check fallback), and the tautological `test_size_limit_calculation` / `test_chunk_processing_logic` / `test_response_decoding_logic` (re-implement the algorithm in the test body — DELETE).
- `tests/tools/test_tool_generator.py` (whole file) + the `generate_tools_from_openapi` patches in `test_stdio_server.py` / `test_streaming_server.py` (`assert_called_once()`) — delete with the generator.
- `tests/tools/test_tools.py` per-call `client.info()` mock — drop the per-call expectation (keep API-shape assertions).

### LOW VALUE / DEAD WEIGHT
- `tests/tools/test_judgment_tool_evals.py` — **fails collection** (`ModuleNotFoundError: anthropic`), errors out `pytest tests/`. Gate behind an optional marker/skip-if-missing or move out of the default path.
- Several over-granular constructor tests and local-mock tests in `test_stdio_server.py`/`test_streaming_server.py` that assert on the test's own stand-in rather than the real handler.

### Coverage gaps (add in the rebuild)
1. **Highest value:** a test that a failing tool returns `CallToolResult.isError == True` (clean message) and a success returns `isError == False`. Nothing asserts the protocol flag today.
2. A test proving the cluster version is fetched **at most once** per server lifetime / **zero** times per call.
3. A test that streaming size-limiting raises **before** the full body is buffered (current tests only check post-hoc arithmetic).
4. An integration test that a real 4xx/5xx surfaces as a protocol error with structured `root_cause`.
5. A "category catalog" test enumerating canonical category → default-on/off.
6. A single source-of-truth test enumerating every recognized config key (env + YAML + CLI).
7. A typed `ToolIncompatibleError` (non-retryable, distinct from transient) test if a runtime gate survives.
8. A test asserting GET-with-body is issued for a body-bearing msearch (no current test pins the method).

---

## 5. Changes That Require Deep Research Before Coding (Phase C shortlist)

These are the items where the right behavior is a genuine design decision, not a mechanical port:

1. **Version-gate caching strategy (§3.1).** Cache key/TTL for single vs multi vs dynamic-override vs serverless; how the cached value interacts with the fail-open decision; whether to keep a runtime gate at all in single non-dynamic mode. *(Verification REFUTED the "just remove it" path — multi mode depends on it.)*
2. **Response-size limiting redesign (§3.2).** Default cap value (and its regression impact on large `_search`/`_cat`), wire-vs-decompressed semantics, Content-Length pre-check viability under gzip/chunked, and whether to keep a custom connection at all vs enforcing above it. Most-tangled subsystem.
3. **Connection-layer architecture / where to insert size limiting without re-implementing `perform_request` (§3.2/§3.6).** The narrowest upstream seam (body-read override vs serializer/response layer) that preserves auth/TLS/compression/exception-translation and fixes the double-request and decode-divergence bugs.
4. **Auth precedence + per-call override security posture (§3.6).** `no_auth` vs explicit creds, partial-cred handling, remote-settable `aws_profile`/`no_auth` in a multi-tenant context. Highest-risk file.
5. **Config precedence ladder & single settings model (§3.5).** Choosing one uniform per-field precedence (file/env/CLI) and confirming pydantic-settings models the existing three-way naming without breaking public env/YAML/arg names.
6. **MCP error-contract migration (§3.3/P1-3).** Whether to raise-and-let-SDK-convert vs return `CallToolResult(isError=True)`, the seam in `execute_tool`, and the ~8 tests + return-type change it triggers.

*(NOT requiring deep research: removing the OpenAPI generator, tool-group declarative refactor, and the structural decompositions — these are well-understood capture-then-replace / refactor work, gated only on the design decisions above.)*

---

## 6. Guiding Rule (Restated)

**No drift without a concrete, documented reason.**
- Reproduce faithfully: tool I/O signatures, the 4 generated tools (golden snapshot), auth/connection-override matrix, category semantics, structured error logging — these are the external contract.
- Change deliberately, with a cited defect: per-call version probe, response-size default/buffering/fallback/decode, the OpenAPI boot fetch, fail-open filter, soft-error/`isError` contract, global-state mutation.
- Where verification tempered a finding (per-call check is **not** redundant; buffered connection is **not** worse than parent; `is_error` key is **not** dropped), the rebuild must honor the corrected reality, not the original overstatement.
