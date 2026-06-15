# Error-Handling & Structured-Logging Evaluation

Scope: the tool-error path (`log_tool_error`, per-handler try/except, `tool_executor.execute_tool`, the MCP SDK wire boundary), the OpenSearch connection/auth error+logging path (`src/opensearch/connection.py`, `src/opensearch/client.py`), and the logging infrastructure (`logging_config.py`, the structured-event vocabulary). Verdicts below are grounded in the surface map and an adversarial verification pass; claims that were refuted or narrowed in that pass are flagged inline.

---

## 1. Executive Summary

**Verdict: functional but messy.** The error/logging design *works* — the integration oracle passes and the wire bytes are stable — but it carries two competing "error" representations and two competing "log" representations, so a single failure can emit 2-4 log lines across mismatched schemas, and structured fields are invisible in the default log format. The infrastructure (JsonFormatter, `extra=` events, stderr handler, structured exception extraction) is sound; the problems are *consolidation and discipline*, not architecture.

**Headline problems:**

1. **Double-handling / double-logging of every soft error (HIGH).** A caught error flows through `log_tool_error` (emits `event_type=tool_error`) *and then* `tool_executor.execute_tool` re-detects the `is_error` dict key and emits a *second* event (`event_type=tool_execution`, `status=error`). Two events, different field sets, different `tool_name` conventions (registry key vs display name) — a metrics pipeline must JOIN two schemas to reconstruct one failure.
2. **Two incompatible wire contracts for "the call failed" (HIGH, but contract-locked).** Business/runtime errors ride the wire as `CallToolResult.isError=false` with a private `is_error:true` key; pre-invocation errors (unknown tool, arg validation) raise and surface as `isError=true`. Spec-compliant MCP clients keying on `isError` treat every OpenSearch error as success. (Tests lock both — see §5/§6.)
3. **Duplicated / asymmetric OpenSearch request logging (MEDIUM).** Streaming path logs a non-2xx at WARNING (parent `log_request_fail`) + ERROR (`_log_request_event`) + tool-boundary; streaming error events carry `response_size` but no `error`, fallback error events carry `error` but no `response_size`. Two ResponseSizeExceededError messages for one logical error.
4. **Structured fields invisible by default + secret-leak risk + stdio hazard (MEDIUM/HIGH).** The default `text` log format drops every `extra=` field, so structured data is observable only when `--log-format json`. `str(exception)` and `opensearch_url` flow into both logs and client-visible text with no redaction layer; the `tool_params.py` `Provided: {...}` echo can include `opensearch_password`. `tool_generator.py:315` `print()` writes to stdout, which corrupts JSON-RPC framing on stdio transport.

**Severity counts:** 2 HIGH (double-event, wire-contract split), 1 HIGH/MEDIUM (secret leak), 3 MEDIUM (request-log duplication, text-mode invisibility, stdio print), plus several LOW cleanups (dead code, free-form operation strings, inconsistent context kwargs).

---

## 2. Current-State Map

### 2a. Error paths (where → mechanism → what the client gets)

| Where | Mechanism | Wire result to client |
|---|---|---|
| `tool_logging.py:91` (single soft-error builder, ~70 callers) | `log_tool_error()` returns `[{'type':'text','text':'Error <op>: <exc>','is_error':True}]` | `CallToolResult.isError=false`; `content[0]` is a `TextContent` with the non-standard `is_error:true` extra surviving verbatim |
| `tools.py` ~40 handlers (e.g. `:155,:195`) | `try/except Exception → log_tool_error(<Name>, e, '<gerund>', index=…)` | soft-error dict (`isError=false`) |
| `tools.py:204,272,326,467,510,546` (6 of ~48 handlers) | manual `if isinstance(result,dict) and 'error' in result:` → wrap in synthetic `Exception` → `log_tool_error` | soft-error dict. Other 42 handlers format an `{'error':…}` body as **success** (rarely reached — see §6) |
| `tools.py:99-121` `check_tool_compatibility` | `raise Exception(msg)` inside handler `try` | swallowed → soft-error dict `Error <op>: Tool '…' is not supported…`; logged `exception_type='Exception'` (indistinguishable from a crash) |
| `generic_api_tool.py:107` write-gate | `return log_tool_error(... PermissionError('Write operations are disabled. Method "X" is not allowed.'))` | soft-error dict; message deliberately omits the env-var name |
| `tool_generator.py:315` | `except Exception: print('Error generating tools: …')` | **no MCP response**; tool never registered; stdout write (stdio hazard) |
| `tool_executor.py:59-62` unknown tool | `raise ValueError('Unknown or disabled tool: <name>')` | propagates to SDK outer except → `_make_error_result` → `CallToolResult.isError=true` |
| `tool_executor.py:67 → tool_params.py:55` arg validation | `validate_args_for_mode` raises `ValueError('Missing required field(s): …\n\nProvided: {…}')` | `isError=true`, text = the ValueError message (can echo args) |
| MCP SDK `server.py:528-532` | jsonschema input validation | `isError=true`, `'Input validation error: …'` (a 3rd validation shape) |
| `connection.py:187-208 / 298-306` | `raise ResponseSizeExceededError` | soft-error dict via tool boundary; two divergent messages |
| `connection.py:229-247` | non-2xx → `_raise_error` → opensearchpy `TransportError` subclass | soft-error dict; `log_tool_error` extracts `status_code`+`root_cause` |
| `connection.py:266-273` | broad `except → fallback`; original streaming error swallowed (WARNING only) | no error surfaced if fallback succeeds |
| `client.py:611-716` auth | per-method `except → AuthenticationError(... {e})`; outer double-wrap; `:716` dead code | soft-error dict via tool boundary |

### 2b. Structured log events (event_type → fields → where)

| event_type | Level | Fields | Emitted at |
|---|---|---|---|
| `tool_error` | ERROR | `tool_name` (**registry key**), `exception_type`, `status='error'`, `status_code` (int only), `root_cause`, `**context` | `tool_logging.py:86-89` |
| `tool_execution` | INFO/ERROR | `tool_name` (**display name**), `status`, `duration_ms`, `tool_key`, `error_type` (set for raised errors; **absent for soft errors**) | `tool_executor.py:106-114` |
| `opensearch_request` | INFO/ERROR | `http_method`, `endpoint`, `status`, `duration_ms`, `status_code?`, `response_size?`, `error?` | `connection.py:44-68` (streaming `:239/:253`, fallback `:309/:326`) |
| `datasource_connection` | ERROR | `auth_method`, `datasource_type`, `status='error'`, `opensearch_url` (**raw**), `error` | `client.py:182-192` (failure only) |
| `memory_snapshot` | INFO | `memory_rss_mb` (`-1.0` sentinel when unavailable), `pid` | `logging_config.py:126-133` |

Plus **~80 plain `logging.*` calls** with **no `event_type`** (client auth/init, tool_filter, config, memory_tools, connection debug, `skills_tools.py:64` full-response INFO, `generic_api_tool.py:149` URL INFO). In `text` mode all `extra=` fields are dropped, so structured and plain logs look identical.

---

## 3. Problems & Modern Standard

### P1 — Double-event per failure (HIGH)
**Evidence:** `tool_logging.py:86-89` emits `tool_error`; `tool_executor.py:73-76` re-detects `result[0].get('is_error')` and `:111-114` emits `tool_execution` `status=error`. One failure → two ERROR events.
**Bad outcome:** error counts double if a pipeline naively sums across event types; neither event alone has {name + duration + exception_type + status_code + root_cause}; the two can't even join because `tool_name` differs (registry key vs display name); `error_type` is absent on the soft-error `tool_execution` (so "error rate by error_type" has a blind spot for the *majority* of errors).
**Modern standard:** one canonical event per logical outcome; log once at the point it's handled (Twelve-Factor logs as event streams; structlog/python-json-logger guidance).
**Recommendation:** Merge into a single `tool_execution(status=error)` event carrying the merged fields. Make `log_tool_error` stop emitting its own `logger.error`; have it *return* the classification metadata so `execute_tool` folds it into the one event (see §4). **Severity: HIGH.**

### P2 — Wire-contract split (HIGH; contract-locked)
**Evidence:** ~70 soft-error sites → `isError=false` + private `is_error` key; raised errors (`tool_executor.py:62`, `tool_params.py:55`, SDK `server.py:532`) → `isError=true`.
**Bad outcome:** a spec-compliant client distinguishes success/failure on `CallToolResult.isError`, so it silently treats every business/OpenSearch error as a successful result. The only error signal is the literal `Error ` text prefix and a non-standard extra field most clients ignore.
**Modern standard (MCP spec):** tool-execution failures should set `CallToolResult.isError=true` with the message in `content`; `is_error` is not part of the `TextContent` schema.
**Recommendation:** This is the single biggest *correctness* gap, **but the integration oracle and ~30 unit asserts lock the current bytes** (see §5). Do **not** flip `isError` as part of a faithful rebuild; flag it as a deliberate, separately-tested future migration. **Severity: HIGH (deferred).**

### P3 — Duplicated / asymmetric request logging (MEDIUM)
**Evidence:** streaming non-2xx logs at `connection.py:230` (parent `log_request_fail`, WARNING) + `:239` (`_log_request_event`, ERROR) + tool boundary; streaming error event omits `error=`, fallback error event (`:326-333`) omits `response_size=`. Two ResponseSizeExceededError messages (`:204-208` "Stopped reading at N" vs `:302-306` "Received N"). Two duration clocks (`self.loop.time()` vs `time.monotonic()`).
**Bad outcome:** 3-4 log lines per failure; a query on `opensearch_request status=error` gets inconsistent fields by path.
**Modern standard:** one emitter, one stable field set, lazy/lightweight fields in hot paths.
**Recommendation:** Single `_log_request_event` call with the full field set (always consider `status_code|None`, `response_size|None`, `error|None`); remove the explicit streaming `log_request_fail/success` (opensearchpy already logs internally); unify the two size-exceeded messages and the duration clock to `time.monotonic()`. **Severity: MEDIUM.**

### P4 — Structured fields invisible in default format (MEDIUM)
**Evidence:** `logging_config.py:77-80` text formatter is `'%(asctime)s - %(name)s - %(levelname)s - %(message)s'` — drops all `extra=`. JSON only on `--log-format json`.
**Bad outcome:** in the default config none of `event_type/duration_ms/status_code/...` are observable; metric filters on `$.event_type` ignore ~80 plain calls.
**Recommendation:** Render a compact `key=value` tail in text mode; document the event enum in one constants module; give error/hot-path plain calls an `event_type`. **Severity: MEDIUM.**

### P5 — Secret leak + no redaction layer (HIGH/MEDIUM)
**Evidence:** `tool_logging.py:41` stringifies the whole exception into both log and client text; `tool_params.py:51-53` echoes `Provided: {user_input}` which can contain `opensearch_password`/`aws_secret`; `client.py:189/329/378` log `opensearch_url` (runtime-confirmed to retain `user:pass@host` userinfo); `skills_tools.py:64` logs full ML response at INFO; no `logging.Filter`/scrubber anywhere.
**Note (verified, narrowed):** the opensearchpy *parent* `log_request_success/fail` URL output does **not** leak userinfo — `_normalize_hosts` strips it before connection construction. The real leak is the repo's *own* logging of the `opensearch_url` variable. (See §6.)
**Modern standard (OWASP):** allowlist redaction filter; never `str(exception)` into client text; designate never-log fields.
**Recommendation:** add one `logging.Filter` on the root handler scrubbing `password/secret/token/bearer/authorization/api_key/credential` keys and URL userinfo; add `baseToolArgs.redacted_dict()` for the `Provided:` echo; redact the `str(exception)` text in `log_tool_error` before it becomes client-visible; demote `skills_tools.py:64` to DEBUG. **Severity: HIGH for the `Provided:`/url paths, MEDIUM elsewhere.**

### P6 — stdio stdout hazard + swallowed startup failure (MEDIUM)
**Evidence:** `tool_generator.py:314-315` `except Exception: print('Error generating tools: …')` — stdout write + silent tool-drop, no structured event.
**Recommendation:** replace with `logger.error(..., extra={'event_type':'tool_generation_error'})`; StreamHandler stays on stderr. **Severity: MEDIUM.**

### P7 — Low-severity cleanups (LOW)
- Bare `Exception` from `check_tool_compatibility` (`tools.py:121`) → introduce typed `ToolVersionIncompatibleError(Exception)` so a version gate is distinguishable from a crash in metrics (metrics-only; wire text unchanged — see §6).
- Dead code: unreachable `raise AuthenticationError('No valid authentication method provided')` (`client.py:716`) + redundant double-wrap (`:709-716`).
- Free-form `operation` gerunds with no schema; same tool uses `'getting shards'` (`:209`) vs `'getting shards information'` (`:227`).
- Inconsistent `context` kwargs: `index` passed by ~8 handlers, omitted by the rest; agentic_memory/memory tools never pass `id`/`index`.
- Hand-typed tool-name literals duplicated at each call site and the registry key (drift risk); generator/skills derive names a third way.

---

## 4. Target Design (neater, simpler — wire bytes preserved)

**Thesis:** keep the exact wire bytes the tests assert, but route every error through one funnel and every diagnostic through one structured emitter with one redaction layer.

**Error model — single chokepoint, two outcomes (both already locked by tests):**
- Small exception hierarchy rooted at the existing `OpenSearchClientError`: `ResponseSizeExceededError`, `ConfigurationError`, `AuthenticationError`, plus a new `ToolVersionIncompatibleError(Exception)` to replace the bare `raise Exception` (metrics-only).
- (A) **Tool-execution/business errors** keep surfacing as the soft-dict via the *one* unchanged `log_tool_error` (signature, return shape, text format all identical) — the single soft-error builder for all ~70 sites.
- (B) **Pre-invocation errors** (unknown/disabled tool, arg validation) keep RAISING out of `execute_tool` → SDK `_make_error_result` → `isError=true`.
- **Centralize `{'error':…}` body re-detection** in the helper/transport layer so all ~48 cat-style handlers treat an error body identically, and replace the synthetic `Exception(result['error'])` (no `status_code/info`) with the real structured error. Delete the 6 copy-pasted branches in `tools.py`.

**Logging model — one schema, one emitter, one formatter, stderr-only, redacted once:**
- One event vocabulary in a constants module: `tool_execution`, `opensearch_request`, `datasource_connection`, `memory_snapshot`, `tool_generation_error`. **Eliminate the `tool_error` vs `tool_execution` split** — one `tool_execution(status=error)` event carries `tool_name`(registry key)+`display_name`+`duration_ms`+unified `error_type`+`status_code`+`root_cause`+context.
- One `_log_request_event` call per request with the full field set; remove the redundant streaming `log_request_fail/success`; unify size-exceeded messages and the duration clock.
- Text mode renders `extra=` as a compact `key=value` tail (no more invisible structured data); DEBUG entry/exit, INFO semantic, ERROR failures; quiet noisy third-party loggers (opensearchpy/aiohttp/botocore/urllib3); one stderr handler.
- One `logging.Filter` on the root handler scrubs sensitive keys + URL userinfo; `log_tool_error` redacts `str(exception)` before it becomes client text; `baseToolArgs.redacted_dict()` sanitizes the `Provided:` echo.

**Mechanism to merge the two events without double-logging (verified):** `log_tool_error` stops calling `logger.error` and instead returns the classification fields alongside the dict (e.g. an internal `_error_meta` key on the returned dict, stripped before the MCP client sees it); `execute_tool`'s soft-error branch reads it and folds `exception_type/status_code/root_cause` into the single `tool_execution` event. (The contextvar handshake also works but is more fragile under async; the synchronous return path is sufficient.)

**Deleted / collapsed:** `tool_executor.py:73-76` second-event emission; the separate `tool_error` event; the 6 duplicated `{'error':…}` branches; redundant streaming `log_request_fail/success`; the duplicate size-exceeded logging + divergent messages; `tool_generator.py:315` `print()`; the `client.py:716` dead code + `:709-716` double-wrap.

---

## 5. Preserved Contract (must stay byte-identical for the oracle)

- **`log_tool_error` return shape EXACTLY:** `[{'type':'text','text':<error_text>,'is_error':True}]`; `error_text = f'Error {operation}: {exception}'` when `operation` truthy else `f'Error: {exception}'`. Must return a **plain dict list** (not pre-built `TextContent`) — `tests/tools/test_tool_logging.py:9-22` and the `result[0]['is_error']` unit asserts depend on it.
- **Soft errors ride the wire as `isError=false`** with `is_error:true` preserved in `content[0]`. Do NOT flip to `isError=true` without migrating the (currently passing) tests and flagging the change.
- **`execute_tool` metric classification stays on the `is_error` dict key only** — `tests/mcp_server_opensearch/test_tool_executor.py:74-92` locks that `'Error codes explained: 404 …'` *without* the key is `status='success'`. Do NOT switch to text-prefix detection.
- **Exact error-text substrings** asserted in `test_tools.py` / `test_srw_search_tools.py` / `test_skills_tools.py:108` (`'Error executing DataDistributionTool: Test error'`) / `test_agentic_memory_tools.py:426` (`'Error searching memory: Container not found'`): e.g. `Error listing indices:`, `Error getting mapping:`, `Error searching index:`, `Error getting shards information:`, `Error getting cluster state:`, `Error getting segment information:`, `Error getting node information:`, `Error getting index information:`, `Error getting index statistics:`, `Error getting query insights:`, `Error getting hot threads information:`, `Error getting allocation information:`, `Error getting long-running tasks information:`, `Error getting nodes information:`, plus `Error searching query sets/search configurations/judgments/experiments`. Gerunds + `Error <op>: <exc>` format must stay identical.
- **Raised pre-invocation errors keep `isError=true`:** `ValueError('Unknown or disabled tool: <name>')` (`test_tool_executor.py:95-98`) and `validate_args_for_mode` `'Missing required field(s): …'` (`:131-147`).
- **`tool_error` structured-log fields** asserted by `test_tool_logging.py`: `event_type`, `tool_name`, `exception_type` (`:36`), `status='error'`, `status_code` only when int=404 (`:49`), `root_cause` from `info`/JSON-string/`error` (`:66,:79`), absent for non-JSON info (`:93`), context kwargs only when non-None. **If merged into `tool_execution`, this file must be migrated in lockstep.**
- **`tool_execution` fields** asserted by `test_tool_executor.py`: `event_type`, `status`, `duration_ms>=0`, `tool_key` when resolved, `error_type` ∈ {`UnknownToolError`,`ValidationError`,`type(e).__name__`} for raised errors. Any field rename requires migrating these asserts.
- **Write-gate message EXACTLY** `Write operations are disabled. Method "X" is not allowed.` and must NOT contain `OPENSEARCH_SETTINGS_ALLOW_WRITE`/`allow_write` (`test_generic_tool.py:90,121-129`).
- **JsonFormatter:** one JSON object per line on stderr, `extra=` merged to top level, `default=str`, includes timestamp/level/logger/message (`tests/mcp_server_opensearch/test_logging_config.py`).

---

## 6. Verified Risks & Mitigations (adversarial pass — honest)

- **PARTIAL — "SDK passes the soft-dict through as-is; `cast()` avoids coercion."** *Outcome confirmed, mechanism wrong.* The dict **is** coerced into a real `TextContent`; `is_error` survives only because every MCP model uses `model_config=ConfigDict(extra='allow')`. **Mitigation:** do not justify the contract on "no coercion"; **pin the `mcp` version** and add a regression test that serializes a `CallToolResult` from the soft-dict and asserts `is_error` survives — a future SDK flip to `extra='forbid'/'ignore'` would silently drop it. Also: the ~30 `result[0]['is_error']` asserts are **unit** tests against the pre-SDK return value; the integration oracle classifies purely on the `Error`/`Input validation error` **text prefix** (`integration_tests/framework/assertions.py:13`), so preserve the text format independent of serialization.
- **CONFIRMED — metric classification must stay on the `is_error` key, not text prefix.** `test_tool_executor.py:74-92` proves `'Error codes explained…'` without the key is `success`. Keep production detection on `result[0].get('is_error')` only.
- **CONFIRMED — typed `ToolVersionIncompatibleError` is metrics-only and safe.** Empirically byte-identical wire text/`is_error` when swapped for the bare `Exception`. Constraints: must subclass `builtins.Exception` (so existing `except Exception` catches it), keep raising it *inside* `check_tool_compatibility`, and do NOT add type-branching to `log_tool_error`'s returned dict. No test covers this path today — **add a regression test** (assert text startswith `Error `, contains `is not supported`, `is_error=True`, and logged `exception_type=='ToolVersionIncompatibleError'`).
- **PARTIAL — centralizing `{'error':…}` re-detection "flips ~34 handlers and is intentional drift that breaks tests."** *Corrected:* **6** handlers re-detect (`tools.py:204,272,326,467,510,546`); **42** do not (not "~34"). The flip affects **only** the narrow HTTP-200-with-error-body case (some `_cat` endpoints) — all real non-2xx already RAISE at `connection.py:247` and are uniformly handled today. **NO existing test breaks** (no test mocks a helper *returning* `{'error':…}` and asserts success). Safe intentional drift; centralize in `helper.py`, delete the 6 branches, add the missing regression test, and normalize the `'getting shards'` vs `'getting shards information'` operation divergence.
- **REFUTED — "opensearchpy parent `log_request_fail/success` leak `user:pass@host`."** `_normalize_hosts` strips userinfo into `http_auth` before connection construction; runtime capture showed neither username nor password in parent log output. **Mitigation:** point redaction at the repo's **own** `opensearch_url` logging — `client.py:189` (`datasource_connection` extra), `:329/:378-379/:479/:482` (INFO/ERROR init lines), which were runtime-confirmed to retain `user:pass`. Removing the explicit streaming `log_request_fail/success` is still safe (no test covers them) but is not what fixes the leak.
- **CONFIRMED — merging into one event requires the soft-error classification to reach `tool_executor`.** Today the handler consumes the exception in place; only the dict reaches the executor (verified: soft-error `tool_execution` has `status=error` but no `error_type/exception_type/status_code/root_cause`). **Mitigation:** return the metadata from `log_tool_error` (sidecar key stripped before the client), fold it into the one event; migrate `test_tool_logging.py` and `test_tool_executor.py` together (19 passing tests pin the two-event shape). Integration tests need no change.

---

## 7. How This Folds Into the Rebuild Phases

- **Logging-infrastructure phase (owns P3, P4, P6, P5-redaction):** single `_log_request_event` field set + remove redundant streaming logs + unify clocks/messages; text-mode `key=value` rendering; event-enum constants module; quiet third-party loggers; replace `tool_generator.py:315` `print()` with a structured `tool_generation_error`; install the one redaction `logging.Filter` on the root handler; demote `skills_tools.py:64` to DEBUG; strip userinfo from app-logged `opensearch_url`.
- **Tool-execution / error-funnel phase (owns P1, P7, P5-`Provided:`):** merge `tool_error` into one `tool_execution(status=error)` event (return-metadata mechanism), delete `tool_executor.py:73-76` second emission; centralize `{'error':…}` re-detection in `helper.py` and delete the 6 `tools.py` branches; introduce `ToolVersionIncompatibleError`; `baseToolArgs.redacted_dict()` for the validation echo; delete `client.py:716` dead code + double-wrap. Migrate `test_tool_logging.py` + `test_tool_executor.py` in lockstep.
- **Deferred / separately-tested (P2):** the `isError` wire-contract correction is *not* part of the faithful rebuild — schedule it as its own migration with test updates and a client-compat note.
- **Cross-cutting guard:** pin the `mcp` SDK version and add the `is_error`-survival serialization regression test before relying on the preserved contract.

---
EOF marker: end of evaluation.
