# Rebuild Decision Log

A running, append-only record of what was built, the design/code decisions made, and
*why* — so the rebuild is auditable and the eventual HTML report can be assembled from
a factual trail. Newest entries at the bottom.

**Standing constraints (apply to every decision):**
1. **Correctness first**, then maintainability, then latency/memory/efficiency.
2. **Minimal diff / reviewer-friendliness** — do NOT heavily rewrite working code; prefer
   surgical in-place edits over new abstractions unless a cited defect justifies it. A
   reviewer must understand each change against the old code in <30s. Middle ground, not
   a ground-up rewrite. (An adversarial `lens:minimal-diff` enforces this every checkpoint.)
3. **No observable behavior drift** without a documented reason logged here.
4. Each change is gated by the test suite (525-baseline unit + integration oracle) and ruff.

---

## D0 — Framework: stay on low-level `mcp.server.Server` (not high-level FastMCP)
**Why:** the server does per-mode schema mutation the decorator API can't express; the
official SDK v2 renames `FastMCP`→`MCPServer` (alpha; staying low-level immunizes us);
zero new framework dependency on an official OpenSearch repo. Get the "clean" win from
*modularization*, not framework swap. **Diff impact:** minimal — keeps the existing server
shape. (See REBUILD_MASTER_PLAN.md §1, FASTMCP_REBUILD_DESIGN.md.)

## D1 — Pin `mcp>=1.25,<2`; add `pydantic-settings`
**Why:** avoid auto-upgrading into the breaking v2 alpha. **Commit:** 17e2d73.

## D2 — Capture golden snapshot of the 4 generated tools before deleting the generator
**Why:** the generator's schemas must be reproduced byte-for-byte; freeze them first as the
fidelity oracle. **Artifact:** tests/fixtures/generated_tools_golden.json. **Commit:** 17e2d73.

## D3 — Typed `ToolSpec` + `ToolRegistry` (additive, dict-compatible)
**Why:** replace the implicit shape of the 344-line dict literal with a documented, typed,
fail-loud (duplicate-key) registry — WITHOUT changing runtime shape (it still behaves as
`dict[str, ToolSpec]`, so consumers are untouched). **Minimal-diff note:** read API mirrors
dict so zero consumer changes. **Commit:** 027b495.

## D4 — Extract `check_tool_compatibility` to leaf `compat.py`; `tools.py` delegates
**Why:** breaks the real import cycle (tools→generic_api_tool→tool_filter→tools) that forced
lazy in-function imports. Error message + bare-Exception behavior byte-identical. **Commit:** a56326b.

## D5 — `compose_registry`/`modules.py` manifest + immutable `ServerContext` (additive)
**Why:** make the legacy `**`-spread order explicit/testable; begin replacing global mutable
state. **Minimal-diff note:** introduced additively; `global_state` stays source of truth
until later phases migrate readers (no big-bang). **Commit:** a56326b.

## D6 — version_cache / auth_strategy / settings modules (additive, UNWIRED)
**Why:** prepared fixes for audit defects (per-call version round-trip, duplicated auth
ladder, scattered config). Built + tested in isolation first; wired in later phases so each
integration is independently gated. **Risk flagged for minimal-diff lens:** these are new
modules not yet earning their place until wired — must verify they replace (not add to)
existing code when integrated. **Commit:** 2f1d69d.

## D7 — Static replacement of the 4 OpenAPI-generated tools + DELETE the generator
**Why (cited defect, audit P0-1):** the runtime generator fetched the OpenAPI spec from an
unpinned GitHub branch at boot — no timeout, 30s+ hang offline, `print()` to stdout
corrupting the stdio JSON-RPC stream, swallowed errors silently dropping tools. The 4 tools
are now static, registered at import in the generator's exact order, schemas byte-locked to
the golden snapshot. **Proven:** registry builds with 48 tools and ZERO outbound network.
**Behavior preserved:** tool names, order, schemas, GET-with-body, NDJSON, version gating.
**Diff impact:** -317 (generator) / -7 generator tests; +~400 static tools+tests. Net removes
a network dependency and a whole non-deterministic code path. **Commits:** 704b52d, f5b8719.

## D8 — Standing adversarial review at every checkpoint (user-requested)
**Why:** keep a zoomed-out, skeptical view of architecture/code/fidelity/simplicity AND
minimal-diff/reviewer-friendliness. 5-lens workflow → ADVERSARIAL_REVIEW_LOG.md. Fix BLOCKERs
before proceeding. **Artifact:** .claude/workflows/adversarial-arch-review.js.

## D9 — Final deliverable: HTML report via frontend-design skill (user-requested)
**When:** after the rebuild is complete. Summarizes every change + rationale for fast review,
assembled from this log + ADVERSARIAL_REVIEW_LOG.md + the commit trail.

## D10 — Adversarial review #1 fixes (PROCEED-WITH-FIXES, 0 blockers, 8 majors)
The first adversarial-review checkpoint (ADVERSARIAL_REVIEW_LOG.md, P0-P3) flagged 8 majors;
fixed the correctness/fidelity ones immediately:
- **#1 tool ordering (single source of truth):** `register.py` now builds the 4 tools keyed in
  the TRUE generator order via `GENERATED_TOOL_ORDER = (ClusterHealth, Count, Msearch, Explain)`;
  `tools.py` iterates that result (deleted the duplicate hard-coded tuple). Added a registry
  tail-order test pinning `list(TOOL_REGISTRY.keys())[-4:]` — the actual tools/list wire contract.
  Fixed the golden test that pinned the WRONG order.
- **#2 settings truthy-union (fidelity/security):** `parse_bool_string` widened the truthy set to
  `{true,1,yes}` for 5 flags that live code parses as exactly `lower()=='true'` — a typo'd
  `OPENSEARCH_NO_AUTH=1` would have disabled auth. Reverted to exact `== 'true'`; fixed the false
  docstring; updated tests to PIN `1`/`yes` → False as a regression guard.
- **#3 version_cache global lock (concurrency):** one module-global asyncio.Lock held across the
  awaited fetch caused cross-key head-of-line blocking (slow GET / for cluster A blocked B).
  Switched to PER-KEY locks (dict of locks under a short meta-lock + double-checked locking + a
  lock-free fast path). Added a real cross-key non-blocking test (awaitable parked fetch via Event)
  replacing the tautological synchronous-counter one.
- **#5 register.py unwired fallback (cycle risk):** made `version_check` a REQUIRED param (dropped
  the `if None: from tools.tools import ...` fallback) — removes a dormant import-cycle footgun and
  an untested branch. Sole caller + test already inject it.
Gate: 687 passed, ruff clean, registry still 48 tools / correct tail / zero network.

**Deferred majors (tracked, not yet actioned):** #4 (~1100 LOC unwired modules — addressed by
WIRING them in their phase so they replace live code, the minimal-diff mandate; next up) and the
MINORs (#6 import-time mutation doc, #7 tautological compose_registry test until domains land,
#8 auth_strategy dead branch, modules.py indirection, 6-file generated package). The version_cache
proportionality QUESTION + auth fail-secure CHANGELOG note are flagged for the maintainer.

## D11 — Auth: SURGICAL in-place fix, DELETE unwired auth_strategy module (workflow-decided)
**Fork:** wire in the 280-line auth_strategy.py vs surgical in-place fixes. Resolved by an
adversarial decision workflow (2 analysts + judge). **Decision: SURGICAL-IN-PLACE.** Even the
analyst assigned to argue FOR wiring concluded against it.
**Why:** the audit's premise (a "duplicated 6-level auth ladder") is FALSE — the ladder exists
exactly once in `_create_opensearch_client` and both single/multi mode funnel through it. With no
duplication, the typed resolver earns nothing DRY-wise (YAGNI: one call site). resolve_auth_strategy
is PURE (no I/O, no logging) so it could NOT delete the ~101-line apply ladder — wiring it would ADD
a ~50-line dispatch layer on top (+~320 lines code+tests net) AND still need separate client.py edits
for 2 of 3 log-hygiene fixes. Surgical path fixes the SAME defects for ~30x less diff.
**Done (client.py +53/-9):**
- O4 fail-secure guard: if explicit AWS key material (access_key or secret_key) is present without
  the full {access_key, secret_key, region} triple → raise AuthenticationError (no silent fallthrough
  to ambient identity). aws_region ALONE does NOT trigger it (it's the legit IAM/ambient path).
- Bearer path MERGES the Authorization header into base headers (preserves custom User-Agent) instead
  of replacing them.
- IAM ARN log: INFO → DEBUG (account/role identifier kept out of INFO).
- New `_scrub_url_userinfo()` applied at all URL log sinks (`_log_connection_event` + the 2 init INFO
  lines) — strips `user:pass@` (CWE-532).
- **Deleted** src/opensearch/auth_strategy.py (280) + tests/opensearch/test_auth_strategy.py (317) —
  the unwired module that never earned its place (recoverable from git if a 2nd ladder ever appears).
- Added 10 unit tests (5 fail-secure guard via _create_opensearch_client directly, 5 URL-scrub);
  updated the bearer test to assert User-Agent is now preserved (it encoded the old clobber bug).
**Observable changes (flag for maintainer, O4 + log hygiene):** partial AWS header creds now RAISE
(CHANGELOG breaking note for partial-cred configs); IAM ARN no longer at INFO; bearer UA preserved.
Gate: 660 passed, ruff clean. Net: ~600 fewer lines than wiring, same correctness.

## D12 — Response-size limiting redesign (connection.py) [OBSERVABLE: O2/O3]
Audit P1-5/6/7/9 + DESIGN_DECISIONS §2. connection.py net -16 lines (deleted the post-hoc fallback).
- **DEFAULT_MAX_RESPONSE_SIZE: None → 10 MiB.** Protection ON by default, ending the code/docs
  divergence (USER_GUIDE claimed 10MB in 3 places; code was None). **OBSERVABLE (O2):** large
  `_search`/`_cat` responses >10MB now raise ResponseSizeExceededError; opt out via
  OPENSEARCH_MAX_RESPONSE_SIZE or per-call override. Flag for maintainer + CHANGELOG.
- **Short-circuit when limit is None:** `perform_request` delegates fully to `super()` (inherits
  parent auth/TLS/gzip/exception-translation verbatim, no second buffering pass).
- **Decode → `('utf-8','surrogatepass')`** matching the parent (the old strict utf-8 + str(bytes)
  fallback corrupted valid responses with surrogate code points).
- **Deleted `_fallback_perform_request`** (P1-7/P1-10): it downloaded the whole body then measured
  (defeating memory safety) AND the broad `except` re-issued every 4xx/5xx as a 2nd HTTP request
  (single 404 = 2 requests; dangerous for non-idempotent writes). **OBSERVABLE (O3):** transport
  errors now propagate (translated to ConnectionTimeout/SSLError/ConnectionError exactly as the
  parent does — reproduced via reraise_exceptions + the aiohttp->opensearch mapping); HTTP-status
  errors (TransportError subclasses from _raise_error) propagate unchanged; NO re-issue.
- Tests: updated test_init_default (10MB), replaced fallback test with short-circuit-when-None test,
  added a real streaming early-abort test (proves abort at chunk 3 of 10 BEFORE buffering the whole
  body — the memory-safety guarantee the audit said was untested), fixed 4 client tests asserting the
  old None default. Gate: 661 passed, ruff clean.

## D13 — Adversarial review #2 fixes (STOP-AND-FIX: 1 BLOCKER + 2 MAJORs)
Review #2 verdict was STOP-AND-FIX. Fixed the correctness issues before proceeding:
- **BLOCKER (connection.py UnboundLocalError):** the `except Exception` handler referenced
  `start`/`url_path`/`orig_body` assigned INSIDE the try AFTER the failure points, so a
  session/SSL setup failure (exactly what the handler translates) raised UnboundLocalError and
  MASKED the real error. The early-abort test missed it (mocked a never-throwing session). Fix:
  hoisted orig_body/url_path above the try; `start = time.monotonic()` (not self.loop.time — loop
  is only set once the session exists, inside the try); switched the 3 duration clocks to
  time.monotonic for consistency. Added test_session_creation_failure_raises_connection_error
  (proves ConnectionError propagates, not UnboundLocalError).
- **MAJOR (params.py validation drift):** my `Optional[str]=None` ACCEPTED explicit `index=None`
  where the generator's `(str,None)` REJECTED it. Restored exact fidelity by rebuilding the 4 arg
  models with `create_model(..., index=(str,None), body=(Any,None))` — index/id reject explicit
  null, body accepts it, matching the generator byte-for-byte. Fixed the false "mirror" docstring.
  Added test_generated_params.py (7 tests pinning the validation). No new observable change.
- **MAJOR (version_cache header-auth key bleed):** when OPENSEARCH_HEADER_AUTH=true the real URL
  comes from the per-request opensearch-url header, invisible to make_cache_key → cross-cluster
  version bleed. Fix: get_opensearch_version BYPASSES the cache when header-auth is active (fetches
  per request). Added 2 tests (header-auth → 2 fetches; non-header → 1 cached fetch).
Deferred (sequencing, not correctness): the ~600 LOC unwired scaffold (registry/modules/context/
settings) — to be wired-or-deleted in the domain-split phase, with UNWIRED banners meanwhile.
MINORs (docstring wording, cache eviction, doc clutter) tracked for cleanup.
Gate: 671 passed, ruff clean.

## D14 — Monolith split (MIDDLE-PATH) + delete unwired scaffold (workflow-decided)
**Fork:** how to handle the 1311-line tools.py monolith + the ~600 LOC unwired scaffold
(registry/modules/context/settings). Resolved by a 3-analyst decision workflow → **MIDDLE-PATH**.
- **WIRE registry.py + modules.py** (they finally earn their place): replaced the 343-line inline
  TOOL_REGISTRY literal in tools.py with `compose_registry(...).as_dict()`. The inline tool METADATA
  moved verbatim into `tools/domains/core.py` (CORE_TOOLS, 35 tools, exact legacy order); **handlers
  did NOT move** (they stay in tools.py; core.py imports them) — so no git-blame reset and the review
  surface is ~30 lines of wiring, not 1000 lines of relocated logic. tools.py: 1311→982 lines.
- **CRITICAL constraint (caught by the workflow):** TOOL_REGISTRY MUST stay a plain dict —
  config.py calls `.update()` and tool_filter.py calls `.pop()` on it (ToolRegistry lacks `.pop` and
  would reject re-adds). So compose ends in `.as_dict()`; ZERO consumers changed.
- **DELETE context.py + settings.py** (+ their tests): unwired, zero prod importers, and wiring them
  would be hundreds of out-of-scope lines (replace global_state / ~30 env reads) — betraying the
  minimal-diff mandate. Removed `pydantic-settings` dep (only settings.py used it) + refreshed lock.
- **Strengthened test_modules.py:** was a tautology (sourced `core` from TOOL_REGISTRY itself); now
  sources `core` from domains/core.py + pins a hand-FROZEN 47/48-tool key-order literal as a real
  regression oracle (memory on/off), plus an independent-composition check and a core-objects-are-live
  identity check.
- **Why not FULL-SPLIT:** moving 35 handler bodies (~900 LOC) resets blame + balloons review to ~1270
  lines for no cited defect (audit named the 343-line literal, not handler layout). **Why not
  DELETE-ALL:** registry/modules wiring is cheap move-only work that kills the real P1 defect.
Net ≈ -624 LOC overall. Gate: 617 passed (674 − 57 deleted settings/context tests), ruff clean,
registry byte-identical (48 tools, exact order, plain dict, zero network).

## D15 — Adversarial review #3 fixes (PROCEED-WITH-FIXES: 0 blockers, 3 majors)
Review #3 confirmed the two prior debts (connection BLOCKER, ~600 LOC unwired scaffold) are
genuinely resolved. Fixed its 3 MAJORs + 2 cheap MINORs:
- **MAJOR tools.py↔core.py circular import:** core.py top-imported 35 handlers from tools.py while
  tools.py imported CORE_TOOLS from core.py — core.py couldn't import standalone. Fixed by converting
  CORE_TOOLS (module-level dict) into `build_core_tools()` with the handler/arg imports moved LAZILY
  inside it (mirrors the generated/ pattern) + a module-level cache so it returns the same objects.
  tools.py calls build_core_tools() at its bottom. Added test_core_importable.py (subprocess imports
  core.py FIRST in a fresh interpreter → must not raise). Cycle verified broken.
- **MAJOR params.py base-arg validation drift [OBSERVABLE O10]:** the deleted generator coerced ALL
  base args to str; the static models inherit baseToolArgs' real types (bool/int/etc). This is MORE
  correct (matches every other tool) but is an observable change for the 4 ex-generated tools — they
  now type-validate base args instead of accepting only strings. Fixed the false "match EXACTLY"
  docstring (now distinguishes tool-specific exact-match from base-arg deliberate-stricter), added
  3 base-arg typing tests.
- **MAJOR version_cache multi-mode header-auth bleed:** D13's bypass only checked the single-mode
  OPENSEARCH_HEADER_AUTH env flag; multi mode enables header auth per-cluster via
  cluster_info.opensearch_header_auth. Extracted `_header_auth_active(args, mode)` that checks the env
  flag (single) or the target cluster's config flag (multi) and bypasses the cache either way. Added
  2 multi-mode tests (header-auth cluster → bypass; fixed cluster → cached).
- **MINOR http_methods now in _REQUIRED_KEYS** (write-protection filter substring-matches 'GET' on it
  — a tool missing it would be silently treated as a write tool).
- **MINOR ExplainTool input_schema property order** restored to generator insertion order
  (index,id,body) so the schema is byte-faithful, not just dict-equal.
- **Test isolation:** added a conftest autouse fixture resetting global_state mode after each test
  (other files call set_mode('multi') and leak it; the new bypass branches on get_mode()).
Gate: 623 passed, ruff clean, registry byte-identical (48, plain dict), core.py cycle-free.

## O-list update
O10 (NEW): the 4 ex-generated tools (Msearch/Explain/Count/ClusterHealth) now validate base
connection args with their real baseToolArgs types instead of coercing all to str (more correct;
aligns with every other tool). CHANGELOG-worthy, low risk.

## D16 — FIX the MCP isError contract [OBSERVABLE O1] (workflow-decided FIX-NOW/minimal)
**Fork:** fix vs defer the audit's #1 correctness finding (P1-3) — tool-execution failures were
returned to MCP clients as SUCCESS (CallToolResult isError=false), the failure smuggled only into a
private is_error key. Decision workflow (3 analysts + judge) → **FIX-NOW via the minimal mechanism.**
The judge empirically falsified the "defer/huge-churn" fear: execute_tool is imported by exactly ONE
test file, only ONE assertion sits on its boundary, and mcp 1.26/1.27 low-level call_tool passes a
returned CallToolResult(isError=...) through verbatim (verified in both venvs + a live serialization
check showing wire isError=True with text preserved byte-for-byte).
**Mechanism (chokepoint, ~6 prod lines):** in tool_executor.execute_tool, the soft-error branch now
`return CallToolResult(content=result, isError=True)` instead of the bare list; success still returns
the bare list. Did NOT use `raise` (that routes through _make_error_result which would drop the
structured content + reformat the message). Widened 3 return annotations to
`list[TextContent] | CallToolResult` (execute_tool + both call_tool wrappers; wrapper bodies unchanged).
Pre-invocation errors (unknown tool, arg/jsonschema validation) already raise→isError=true, untouched.
**Oracle-first sequencing (false-green prevention):** reworked integration_tests/framework/assertions.py
to read `result.isError` as PRIMARY (text-prefix kept as secondary belt-and-suspenders) — transparently
re-points all 127 integration call sites with zero per-test edits. Migrated the single execute_tool
boundary assertion in test_tool_executor.py to assert CallToolResult/isError; the 12 other is_error
assertions test log_tool_error/tool functions directly (the tool→executor soft-dict contract is
preserved) and are untouched.
Gate: 623 passed, ruff clean; live check confirms wire isError=True + exact text preserved.
