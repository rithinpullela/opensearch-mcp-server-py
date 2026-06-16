# Design Decisions — High-Uncertainty Subsystems (OpenSearch MCP Server Rebuild)

**Status:** Decision-grade. Each subsystem records ONE chosen design, the rationale (with rejected
alternatives), the contract we preserve (and pinning tests), any deliberate observable change, and
the honestly-verified risks from the adversarial pass.

**Verification note (read first):** Before writing, the actual source tree was re-inspected. Two
claims in the upstream design inputs and the adversarial pass were found to be **wrong about the
current code** and are corrected throughout:

1. **There IS a per-call version check in BOTH modes.** Every tool's `_run` calls
   `check_tool_compatibility(...)` → `get_opensearch_version(args)` (`src/tools/tools.py:99-102`,
   invoked at `:127, :163, :175, ...` for every tool). This runs in single *and* multi mode. There
   is *also* a startup-time filter (`src/tools/tool_filter.py:455` fetches version, `:494` gates via
   `is_tool_compatible`). So the system has **two** gates, not one. The adversarial verdict that
   "version gating happens ONCE at startup" is incorrect; its corollary findings (no cache exists,
   `version=None` enables incompatible tools, no TTL env var exists) are correct and are honored.
2. `DEFAULT_MAX_RESPONSE_SIZE = None` is confirmed (`src/opensearch/connection.py:19`,
   comment: "No limit by default"). `max_response_size` is confirmed **absent** from
   `CONNECTION_OVERRIDE_FIELDS` (grep in `src/tools/tool_filter.py` / `server_instructions.py`).
3. `pydantic>=2.11.3` is a dependency; `pydantic-settings` is **not** yet — adding it is part of the
   config decision.

---

## 1. Version-Gate Caching Layer

### Problem
Every tool invocation calls `check_tool_compatibility()` (`src/tools/tools.py:99-102`) →
`get_opensearch_version(args)` (`src/opensearch/helper.py:752-768`), which opens a fresh
`AsyncOpenSearch` client, issues `GET /`, parses `version.number`, and closes the client — **per
call**. On a busy server this creates tens of clients/minute against the same static cluster
identity. There is no caching anywhere (`grep` for `version.*cache` returns zero hits).
`get_opensearch_version()` returns `None` on any exception (`helper.py:767`), and
`is_tool_compatible(None, …)` returns `True` unconditionally (`src/tools/utils.py:30-31`), so a
transient `/` failure silently *enables* version-gated tools.

### Decision
Add a small **per-connection-target, TTL-bounded, async-safe version cache** that wraps
`get_opensearch_version()`. The per-call gate stays (it is real and load-bearing in both modes); we
make it cheap.

- **New file:** `src/opensearch/version_cache.py`
  ```python
  # Module-level dict is GIL-safe for get/set of whole entries; the lock guards
  # the check-fetch-store critical section so concurrent calls don't stampede /info.
  _CACHE: dict[str, tuple[Version | None, float]] = {}   # key -> (version, expiry_epoch)
  _LOCK = asyncio.Lock()                                  # async, NOT threading.RLock

  def make_cache_key(args: baseToolArgs) -> str: ...      # normalized; see risks
  async def get_cached_version(args, fetch: Callable[[], Awaitable[Version | None]]) -> Version | None
  def clear_cache() -> None                               # test hook + future SIGHUP refresh
  ```
- **Integration:** `get_opensearch_version()` becomes a thin wrapper:
  `return await get_cached_version(args, fetch=_fetch_version_uncached)`. `tools.py:101` and
  `tool_filter.py:455` are unchanged — caching is transparent.
- **Cache key (normalized):** multi mode → `args.opensearch_cluster_name`; single mode → a
  **normalized** connection URL (lowercase host, explicit default port, no trailing slash, userinfo
  stripped). Normalization lives in `make_cache_key` and is pure/deterministic.
- **TTL:** default 600s (10 min), override via new env var `OPENSEARCH_VERSION_CACHE_TTL_SECS`.
- **Concurrency primitive:** `asyncio.Lock`, **not** `threading.RLock`. The server is async
  (`StreamableHTTPSessionManager`, MCP SDK uses `anyio.Lock`); injecting an OS-blocking lock into
  async paths is wrong.
- **Negative-result handling:** a fetch that returns `None` (error path) is cached **only briefly**
  (hard-coded 5s floor) so a flaky `/` does not pin "unknown" for the full TTL window, while still
  collapsing a thundering herd.

### Why
- opensearch-py best practice is to reuse a client/connection pool per cluster; creating a client
  per tool call violates that. The cluster identity is static within a session, so caching is safe.
- `asyncio.Lock` chosen over `threading.RLock` per the adversarial finding (NUANCED→corrected):
  concurrency here is async, and the MCP SDK already serializes with `anyio` primitives. An async
  lock prevents the concurrent-`/info` stampede (10 clients → 1 fetch + 9 cache hits).
- **Rejected — Option A (no cache, status quo):** wasteful client churn, stampede under load,
  silent `None` enable-bug stays. **Rejected — Option C (two-tier startup+runtime):** marginal gain;
  the startup filter already exists, so a second tier adds code for ~5-10ms/100 calls.
  **Rejected — Option D (Redis/shared cache):** external dependency breaks the in-process,
  single-replica statelessness guarantee; overkill.

### Contract preserved (+ pinning tests)
- `get_opensearch_version()` signature/return type unchanged; `is_tool_compatible()` logic
  unchanged. Env var, YAML, CLI, tool I/O all unchanged.
- **Pinning tests:** `tests/tools/test_tool_filters.py::TestIsToolCompatible` (unchanged),
  `tests/opensearch/test_helper.py::test_get_opensearch_version*` (must still pass; add a
  cache-bypass fixture that calls `clear_cache()` in setup so each test sees a fresh fetch).
- **New tests (`tests/opensearch/test_version_cache.py`):** (a) hit within TTL → one fetch;
  (b) expiry → refetch; (c) concurrent `asyncio.gather` of N calls → exactly one underlying fetch;
  (d) `None` result cached only for the short floor; (e) key normalization equivalence classes.

### Deliberate observable changes
- **None functional.** Internal-only. The only behavioral difference is *staleness*: after a cluster
  upgrade/downgrade, the per-call gate may use a stale version for up to the TTL. This is bounded and
  configurable.

### Verified risks (honest)
- **BREAKS — URL key stability (single-mode dynamic overrides).** No URL normalization exists today
  (`_parsed_with_default_ports` only adds ports). `localhost:9200` vs `127.0.0.1:9200`, trailing
  slash, and omitted `:443` produce *different* keys for the *same* cluster. **Mitigation is
  mandatory, not optional:** `make_cache_key` must lowercase host, add explicit default port, strip
  trailing slash, and strip userinfo. Unit tests must cover all four equivalence classes. We accept
  that `localhost`↔`127.0.0.1` are NOT unified (a true cache miss, harmless: just an extra fetch).
- **BREAKS — `version=None` (serverless / fetch error) enables incompatible tools.** Confirmed:
  `is_tool_compatible(None, {min_version:'3.3.0'})` returns `True` (`utils.py:30-31`); 41 tools carry
  `min_version` with no `max_version` (e.g., `DataDistributionTool` 3.3.0+). The cache faithfully
  passes `None` through — so caching does **not** fix this, and must not be claimed to. **Decision:
  the cache is necessary but not sufficient.** A separate fix (tracked in the change table) is
  required: short-TTL negative caching (above) limits the *duration* of the wrong-enable on transient
  errors, and a follow-up adds an explicit `serverless_incompatible` flag honored by
  `is_tool_compatible`. Without that flag, true serverless still enables 3.3.0+ tools that then fail
  at runtime.
- **NUANCED — TTL semantics.** A 10-min default means a freshly-upgraded cluster keeps the old gate
  briefly. Acceptable for the common case; `OPENSEARCH_VERSION_CACHE_TTL_SECS=0` disables caching for
  fast-upgrade environments. (Corrected from the input's "15 min".)
- **HOLDS — async model.** Verified `asyncio.Lock` is the correct primitive; `threading.RLock` from
  the input is rejected.

---

## 2. Response-Size Limiting & Streaming Memory Safety

### Problem (audit P1-6, P1-7, P1-9)
`src/opensearch/connection.py`:
- **`:19`** `DEFAULT_MAX_RESPONSE_SIZE = None` (protection OFF by default) contradicts
  `USER_GUIDE.md` (10MB documented default) — code/docs divergence.
- **`:275-322`** `_fallback_perform_request` calls `super().perform_request()` which downloads the
  *entire* body, then measures — defeating the "before data is fetched into memory" guarantee.
- **`:216`** strict `decode('utf-8')` with a `str(bytes)` fallback diverges from opensearch-py's
  `decode('utf-8','surrogatepass')`, corrupting JSON with valid surrogate code points.
- **`:266`** broad `except Exception` re-issues *all* errors through the fallback, double-issuing on
  404/409 (non-idempotent hazard).

### Decision
Set the default to 10MB, stream into a pre-sized buffer with incremental abort, fix the decode,
delete the post-hoc fallback, short-circuit to the parent when disabled, **and make
`max_response_size` per-call overridable** (the mitigation the adversarial pass requires).

- **`connection.py:19`** → `DEFAULT_MAX_RESPONSE_SIZE = 10 * 1024 * 1024`.
- **`perform_request()` refactor:**
  - If `self.max_response_size is None`: `return await super().perform_request(...)` immediately
    (verified HOLDS — auth/TLS/compression/header/timeout handling is byte-for-byte identical to the
    parent, so no state is lost).
  - Best-effort Content-Length pre-check: read `response.content_length`; raise immediately if it
    exceeds the limit, **but skip the pre-check when `Content-Encoding` indicates compression**
    (compressed length is not predictive of decompressed length — gzip-bomb caveat).
  - Stream `response.content.iter_chunked(8192)` into a `bytearray`, tracking offset; abort the moment
    `offset + len(chunk) > limit`. (Size is measured on *decompressed* bytes — verified HOLDS: aiohttp
    auto-decompresses before chunks reach us.)
  - Decode with `decode('utf-8', 'surrogatepass')`; delete the `str(bytes)` branch.
  - **Delete `_fallback_perform_request` (`:275-322`).** Replace the broad `except` with **selective**
    handling (per the adversarial refinement): re-raise `ResponseSizeExceededError`; re-raise
    `aiohttp.ClientSSLError`, `ClientConnectorError`, `ClientPayloadError`, `asyncio.CancelledError`
    (fail fast — these are not transient mid-stream conditions); let `asyncio.TimeoutError` /
    `ClientConnectionError` propagate as the parent's translated `ConnectionTimeout`/`ConnectionError`
    (no silent re-issue); log+raise anything unknown.
- **`client.py`:** add `max_response_size` to `CONNECTION_OVERRIDE_FIELDS`
  (`src/mcp_server_opensearch/server_instructions.py`) so an agent can raise/lower the cap per call.
  Single/multi parsing (`:243-255`, `:403-417`) keep falling back to the 10MB default.

### Why
- **B over A (keep None, fix docs):** the docs describe the limit as a *feature*, not opt-in; "fix
  docs to say no limit" enshrines a broken promise and keeps the post-hoc fallback and 3x peak.
- **B over C (enforce above the connection):** post-body enforcement means the parent's
  `response.text()` already buffered everything — no early abort, no Content-Length fast path.
- **Decode:** `surrogatepass` matches opensearch-py's own `OpenSearchClientResponse.text()`; security
  posture equals the parent (it only round-trips surrogate escapes; `b'\xff\xfe'` still raises).

### Contract preserved (+ pinning tests)
- `ResponseSizeExceededError` type, message format, and `DEFAULT_MAX_RESPONSE_SIZE` symbol/import
  chain unchanged. Env var `OPENSEARCH_MAX_RESPONSE_SIZE` and YAML `max_response_size` parsing
  unchanged (invalid → default).
- **Keep:** `test_response_size_exceeded_error_creation`, SSL/attribute tests,
  `test_url_construction_with_params`, `test_response_decoding_logic` (happy path).
- **New:** `test_short_circuit_when_limit_is_none`, `test_content_length_pre_check`,
  `test_streaming_aborts_before_full_buffer`, `test_non_idempotent_404_not_reissued`.

### Deliberate observable changes
1. **10MB default now enforced** (was effectively unlimited). Large `_search`/`_cat` responses that
   work today will start returning `ResponseSizeExceededError`. Opt out by raising the env var or the
   new per-call `max_response_size`.
2. **Mid-stream / transport errors now surface raw** (translated by parent) instead of silently
   re-issuing — safer for non-idempotent writes; delete `test_perform_request_fallback_to_parent`.
3. **`max_response_size` becomes per-call overridable** — update `test_connection_overrides.py` to
   include it in the override matrix.

### Verified risks (honest)
- **BREAKS — 10MB regression needs maintainer sign-off.** The audit explicitly says "pick the cap with
  that regression in mind." This design picks 10MB to match docs, but the regression on large
  workloads is real and requires ratification. Mitigated by per-call override + clear release note.
- **NUANCED — Content-Length pre-check.** No race (it reads the raw header), but it is **unreliable
  for compressed responses** (gzip bomb). Pre-check is a fast-path *only*; the incremental stream
  check is the mandatory defense. Skip pre-check when `Content-Encoding` is present.
- **NUANCED — error-precedence on large error bodies.** If a 404's body exceeds the (small) limit
  mid-stream, the caller sees `ResponseSizeExceededError`, not `NotFoundError`. Edge case (OpenSearch
  errors are small JSON, < 10MB). Document; do not special-case.
- **NUANCED — removing fallback affects non-idempotent ops.** For idempotent GET/HEAD the propagated
  error is safely retryable; for POST/PUT/DELETE the caller must verify cluster state before retry.
  CHANGELOG must state this.
- **NUANCED — decode currently strict, not surrogatepass.** Confirmed mismatch; the change to
  `surrogatepass` is required to match the parent (not a regression).
- **HOLDS — short-circuit safety, `surrogatepass` safety, decompressed-size measurement,
  `connection_class_kwargs` delivery of `max_response_size`.** All verified against the venv source.

---

## 3. Connection-Layer Seam (BufferedAsyncHttpConnection)

> This subsystem overlaps §2 by design; §2 owns the size/decode/streaming mechanics, **§3 owns the
> seam decision**: how much of the parent we re-implement and how errors propagate.

### Problem (audit P1-8, P1-10)
`BufferedAsyncHttpConnection.perform_request` (`connection.py:97-322`) re-implements the parent
nearly whole (URL build, auth headers, gzip, timeout, session). The broad `except Exception` at
`:266` catches normal HTTP status errors and re-issues via the fallback (single 404 → 2 requests).
Full re-implementation is a drift surface (SigV4 bug class).

### Decision
**Keep the custom connection, but shrink the seam to the minimum that streaming requires, and remove
the fallback** (Option v).

- Short-circuit to `super().perform_request()` whenever `max_response_size is None` (verified the
  custom path and parent are otherwise byte-for-byte identical, so nothing is lost when disabled).
- Extract `_stream_bounded_response(response, max_size) -> bytes` so the size+decode logic lives in
  one helper, used only on the size-enforced path.
- Replace the broad `except`/fallback with the **selective** handler from §2 (fail-fast on
  SSL/DNS/payload/cancel; propagate transient connection/timeout as the parent's translated
  exceptions; never re-issue).

### Why
- The parent (`opensearchpy/_async/http_async.py`) buffers the whole body in `response.text()`; it
  exposes no hook to stop early. Streaming therefore *requires* a custom `perform_request` — this is
  deliberate extension, not accidental duplication.
- **Rejected — (i) subclass only `response.text()`:** still duplicates session/URL build; brittle to
  aiohttp internals. **Rejected — (ii) wrap at transport level:** `AsyncTransport` has no clean hook.
  **Rejected — (iv) enforce in serializer:** body already fully downloaded; defeats early abort.
- Removing the fallback fixes the double-issue and the exception-translation violation in one move.

### Contract preserved (+ pinning tests)
- `perform_request(method, url, params, body, ...) -> (status, headers, data)` signature and exception
  translation (auth/timeout/SSL) preserved via the parent on both the short-circuit and propagation
  paths. `BufferedAsyncHttpConnection.__init__(max_response_size=...)` signature preserved.
- **Pinning:** `tests/opensearch/test_connection_overrides.py` (client init + override matrix);
  `connection_class_kwargs` delivery is **HOLDS-verified** (Transport `**kwargs` →
  `connection_class(metrics=..., **kwargs)`).

### Deliberate observable changes
- Same as §2 items 2 & 3 (raw error propagation; per-call `max_response_size`). No additional drift.

### Verified risks (honest)
- **NUANCED — `iter_chunked` stability vs exception scope.** Streaming itself is stable under
  cancellation (verified). The hazard was the *broad except* masking SSL/DNS/payload errors as
  "streaming failed." The selective handler (above) is mandatory, not optional.
- **HOLDS — short-circuit loses no auth/TLS/compression state** (static diff vs parent confirmed).

---

## 4. Authentication & Connection Resolution

### Problem (audit P2-3, P3-4/3-5, P3-6, P1-10)
The 6-level auth ladder is duplicated verbatim across single/multi mode and lives inline in
`_create_opensearch_client` (`src/opensearch/client.py:486-716`). Confirmed branch order:
1. `opensearch_no_auth` (`:607`) → 2. `bearer_auth_header` (`:616`) →
3. header AWS creds `if aws_access_key_id and aws_secret_access_key and aws_region` (`:630`) →
4. `iam_arn` (`:652`) → 5. basic `opensearch_username/password` (`:679`) → 6. ambient AWS (fallthrough).
Defects: partial AWS header creds silently fall through to ambient identity (privilege confusion);
`opensearch_no_auth` and `aws_profile` are per-call-settable (`:268-273`); bearer path can clobber
User-Agent; URL userinfo can leak into logs.

### Decision
**Extract a typed resolver, preserve the precedence order exactly, add fail-secure validation, and
fix log leakage** — i.e., Option B with Option C groundwork. **Do not add a global
`ALLOW_PER_CALL_HOST_IDENTITY_SELECTION` flag** (the adversarial pass shows it BREAKS zero-config
deployments and duplicates the existing visibility gate).

- **New file:** `src/opensearch/auth_strategy.py`
  ```python
  AuthStrategy = NoAuth | BasicAuth | BearerToken | HeaderAWSCreds | IAMRoleAssumed | ProfileAWSCreds
  def resolve_auth_strategy(...) -> AuthStrategy   # raises AuthenticationError on partial creds
  ```
  One resolver, called by both single and multi mode; the inline if/elif ladder in
  `_create_opensearch_client` collapses to "apply the resolved strategy."
- **Fail-secure validation:** if *any* of {access_key, secret_key, region} is present but not *all
  three*, raise `AuthenticationError` (no silent fallthrough to ambient).
- **Per-call identity gating — use the EXISTING mechanism, not a new flag.** Multi mode is the
  multi-tenant surface: reject per-call `aws_profile` / `opensearch_no_auth` overrides **only when
  `mode == 'multi'`**. Single/zero-config mode keeps them (zero-config *requires* per-call params —
  `CONNECTION_OVERRIDE_FIELDS` are already stripped from schemas when a connection is preconfigured,
  via `tool_filter.py:508` + `is_dynamic_mode_enabled()`).
- **Log fixes:** scrub URL userinfo before logging; lift URL credentials into `http_auth`; drop IAM
  ARN to DEBUG; merge `Authorization` into existing headers (preserve User-Agent).

### Why
- The precedence order is **load-bearing and verified correct** (HOLDS): `test_header_auth.py`
  proves header-AWS overrides server-side basic (level 3 > 5). The audit labels it *undocumented*,
  not *wrong*. So we reproduce it faithfully and document it.
- Partial-cred rejection is a **fix, not a breaking change** (HOLDS-verified): zero tests, zero docs,
  zero config depend on the silent-fallthrough; only a 2-of-3 caller relying on a bug is affected,
  and failing secure is correct.
- **Rejected — global `ALLOW_PER_CALL_HOST_IDENTITY_SELECTION` flag (input's recommendation):**
  BREAKS zero-config deployments that legitimately pass per-call `aws_profile`/`opensearch_no_auth`
  (a documented CHANGELOG feature, exercised by `test_dynamic_connection.py`). Preconfigured
  deployments already gate these by *hiding the fields* from the schema. Mode-specific enforcement in
  multi mode achieves the multi-tenant goal without the operational burden or the regression.
- **Rejected — Option A (validate only):** leaves duplication and identity-selection exposure.

### Contract preserved (+ pinning tests)
- Precedence order identical: no_auth > bearer > header-AWS > iam > basic > ambient. Per-call override
  fields stay in `baseToolArgs` (`tool_params.py:60-92`). Single/multi dispatch identical for the same
  inputs.
- **Pinning:** all `integration_tests/auth/*.py` (basic, no_auth, bearer, header, iam, profile) pass
  unchanged in **single mode**; `tests/opensearch/test_connection_overrides.py` unchanged in single
  mode.
- **New (`tests/opensearch/test_auth_strategy.py`):** partial-header-creds raises; full
  6-level precedence order; URL userinfo scrubbed in logs; multi-mode rejects per-call
  `aws_profile`/`no_auth`.

### Deliberate observable changes
1. **Partial AWS header creds now raise `AuthenticationError`** instead of silently using ambient
   identity. (Security fix; no legitimate caller affected.)
2. **Multi mode rejects per-call `aws_profile` / `opensearch_no_auth` overrides.** Multi-tenant
   isolation. Single/zero-config unaffected. (Diverges from the input's global-flag proposal —
   intentional correction.)
3. **URL userinfo scrubbed from logs; IAM ARN moved INFO→DEBUG; User-Agent preserved on bearer.**

### Verified risks (honest)
- **HOLDS — precedence order correct** (with the constraint that the partial-cred guard and the
  no-re-issue behavior from §2/§3 must land together).
- **HOLDS — partial-cred rejection is non-breaking.**
- **BREAKS — the global identity-selection flag.** Explicitly **not adopted**; replaced by
  mode-specific multi-mode enforcement, which preserves the zero-config feature.

---

## 5. Config / Settings Single-Source-of-Truth

### Problem (audit P1-21)
~30 env vars scattered across 7 files with inconsistent truthy parsing (`allow_write` uses
`"true"`, dynamic-connection uses `"1"`/`"0"`); ~5 `yaml.safe_load` calls per boot; YAML config
silently disables all 9 tool-filter env vars with a one-line warning
(`tool_filter.py` "Both config file and environment variables are set. Using config file."); no
canonical precedence ladder; no typo detection on YAML keys.

### Decision
Adopt **Pydantic `BaseSettings`** with a typed `Settings` (env) model and a typed `AppConfig` (YAML)
model, loaded **once** through a single `load_config()`, threaded via a `ServerContext`.

- **Add dependency:** `pydantic-settings` (note: not yet present; `pydantic>=2.11.3` is). Pin in
  `pyproject.toml`.
- **New files:** `src/settings.py` (`Settings(BaseSettings)` enumerating every env var exactly once,
  with `alias=` matching today's names and a shared `parse_bool_string` validator accepting
  `true/1/yes`); `src/config_loader.py` (`load_config(path) -> (Settings, AppConfig)`, one
  `yaml.safe_load`, `AppConfig` with `extra='forbid'` on subsections to catch typos).
- **Precedence (documented, per-field):** env var > YAML value > default.
- **Migration is phased:** Phase 1 introduces the models + `ServerContext` without removing the
  existing `os.getenv` calls; Phase 2 migrates call sites subsystem-by-subsystem; Phase 3 adds tests.

### Why
- Pydantic `BaseSettings` is the de-facto standard (FastAPI/Uvicorn/botocore patterns); gives a single
  source of truth, type validation at parse time, one parse pass, and typo detection — directly
  retiring every P1-21 defect (inconsistent truthy parsing, scattered getenv, undefined precedence).
- **Rejected — Option 2 (helper + cached YAML only):** leaves 30+ `os.getenv` calls and the
  config-disables-env quirk; future vars added ad hoc. **Rejected — Option 3 (global dict, defer):**
  no type validation, precedence still implicit.

### Contract preserved (+ pinning tests)
- All CLI flags, env var names, and YAML keys unchanged (the `Settings` aliases reproduce them
  exactly). Tool I/O unchanged.
- **Pinning:** `tests/tools/test_config.py` passes unchanged;
  `integration_tests/tool_filtering/test_filtering_yaml_config.py` unchanged.
- **New:** Settings field/alias/type coverage; precedence (env overrides YAML when YAML absent);
  bool parsing of `false`/`0`; typo rejection via `extra='forbid'`.

### Deliberate observable changes
1. **YAML typos now fail fast** (`ValidationError`) instead of being silently ignored. Intended;
   surfaces latent config errors.
2. **Precedence becomes uniform per-field (env > file > default).** Today, a config file disables
   tool-filter env vars wholesale. The new model overrides per field. This is a behavior change for
   anyone relying on "config file fully shadows env" — must be called out in the migration guide.
3. **`pydantic-settings` added as a dependency.**

### Verified risks (honest)
- **Per-field precedence vs. today's whole-file shadowing** is a real semantic change (input
  Assumption 2). It is a fix, but operators using both env + file together will see different
  effective config. Document prominently; consider a one-release compatibility shim that logs the
  diff between old (file-wins) and new (per-field) resolution.
- `extra='forbid'` must be on subsections only (not the root) to leave room for future top-level keys.
- Bool parsing must cover all current truthy spellings (`true`, `1`, `yes`) to avoid silently
  flipping a flag during migration.

---

## Decisions that change observable behavior

| # | Change | Justification | Tests affected | Needs maintainer ratification? |
|---|--------|---------------|----------------|-------------------------------|
| 1 | Version gate may use a cached version (≤TTL) after cluster up/downgrade | Eliminate per-call client churn + `/info` stampede; cluster identity is static | `test_version_cache.py` (new); `test_helper.py` (add `clear_cache` fixture) | No — internal, bounded, env-configurable |
| 2 | `version=None` (serverless/error) still enables version-gated tools; needs explicit `serverless_incompatible` flag follow-up | Cache cannot fix the `is_tool_compatible(None)=True` bug; must be fixed separately | `test_tool_filters.py` (add `is_tool_compatible(None,{min_version:'3.3.0'})` case) | **Yes** — confirm the follow-up flag + fail-safe-on-None policy |
| 3 | **10MB response-size default now enforced** (was unlimited) | Match `USER_GUIDE.md`; prevent OOM | `test_init_default_max_response_size` (update to 10MB) | **Yes** — regression on large `_search`/`_cat` |
| 4 | `max_response_size` becomes per-call overridable | Lets agents raise the cap when 10MB is too small | `test_connection_overrides.py` (add to matrix) | Recommended — small surface expansion |
| 5 | Mid-stream/transport errors propagate raw (no silent re-issue); fallback deleted | Fixes 404/409 double-issue; safe for non-idempotent writes | Delete `test_perform_request_fallback_to_parent`; add `test_non_idempotent_404_not_reissued` | **Yes** — confirm callers tolerate explicit errors |
| 6 | Partial AWS header creds raise `AuthenticationError` (no ambient fallthrough) | Fail-secure; closes privilege-confusion | `test_auth_strategy.py` (new) | No — verified non-breaking |
| 7 | Multi mode rejects per-call `aws_profile` / `opensearch_no_auth` overrides | Multi-tenant identity-selection hardening; single/zero-config unaffected | `test_auth_strategy.py`, `test_connection_overrides.py` (multi-mode case) | **Yes** — confirm no multi-mode deployment relies on per-call profile/no_auth |
| 8 | URL userinfo scrubbed from logs; IAM ARN INFO→DEBUG; User-Agent preserved on bearer | CWE-532 log hygiene; fix header clobber | log-assertion tests (adjust) | No |
| 9 | YAML typos fail fast (`extra='forbid'`); config precedence becomes per-field (env>file>default) | Single source of truth; catch latent errors | new Settings tests; `test_config.py` unchanged | **Yes** — per-field precedence differs from today's whole-file shadowing |
| 10 | Decode switches to `('utf-8','surrogatepass')` | Match opensearch-py; stop corrupting surrogate JSON | `test_response_decoding_logic` (happy path holds) | No — matches parent |

**Rejected from the inputs (do NOT implement):** the global `ALLOW_PER_CALL_HOST_IDENTITY_SELECTION`
flag (BREAKS zero-config; replaced by mode-specific multi-mode enforcement, row 7); `threading.RLock`
for the version cache (wrong concurrency model; use `asyncio.Lock`); the input's claim that the
per-call version check is redundant or startup-only (it is real and per-call in both modes).
