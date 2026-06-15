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
