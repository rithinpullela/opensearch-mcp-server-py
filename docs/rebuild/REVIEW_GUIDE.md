# How to review this rebuild

You don't need to read 1,800 lines. ~80% of the diff is **mechanical relocation** (moving a
343-line dict + porting verbatim code) that a golden-snapshot test already proves is faithful.
The *real* code to review — the part with new logic — is about **6 files / ~400 lines**.

Review in this order. For each file: `git diff 1a8b316..HEAD -- <path>`

---

## TIER 1 — Read these carefully (new logic, behavior changes) — ~400 lines

### 1. `src/mcp_server_opensearch/tool_executor.py`  (+20 lines) ⭐ START HERE
The single most important behavior change. Failed tool calls now return
`CallToolResult(isError=True)` instead of a bare list. ~6 lines of real change.
**Look at:** the soft-error branch that wraps `result` in `CallToolResult`.
**Ask:** is the success path still a bare list? Is the error text preserved?

### 2. `src/opensearch/version_cache.py`  (new, 225 lines)
New module: caches the cluster version so the gate doesn't hit the network on every call.
**Look at:** `get_cached_version` (the per-key lock + double-checked locking + fast path) and
`make_cache_key` (URL normalization).
**Ask:** is the async locking correct? Could two different clusters collide on one key?
(There's a dedicated test, `tests/opensearch/test_version_cache.py`, that parks a slow fetch to
prove cluster A doesn't block cluster B.)

### 3. `src/opensearch/connection.py`  (~162 lines changed) ⚠️ the trickiest one
The response-size / streaming rewrite. **Look at:** `perform_request` — the `None` short-circuit
to `super()`, the streaming loop with early abort, the `surrogatepass` decode, and the
`except` block that translates aiohttp errors (this is where the review-#2 crash bug was — the
hoisted `orig_body`/`url_path`/`start` above the `try`).
**Ask:** does every failure path return a real opensearch-py exception (not UnboundLocalError)?
Is the 10MB default OK for your largest expected responses?

### 4. `src/opensearch/client.py`  (+62 lines)
Auth + log-hygiene fixes. **Look at:** the `_scrub_url_userinfo` helper, the partial-AWS-creds
fail-secure guard (raises instead of falling through to ambient identity), the bearer-header MERGE
(preserves User-Agent), and the IAM-ARN log moved to DEBUG.
**Ask:** does the fail-secure guard ever reject a legitimate config? (region-alone is carved out.)

### 5. `src/opensearch/helper.py`  (+57 lines)
Small: `get_opensearch_version` is now a thin wrapper over the cache + `_header_auth_active`
(the cache-bypass when header auth makes the target per-request).

### 6. `src/tools/compat.py`  (new, 90 lines)
`check_tool_compatibility` extracted to a leaf module to break an import cycle. The error message
is reproduced verbatim. **Ask:** does the message text match the old one exactly? (a test pins it.)

---

## TIER 2 — Skim (structure; logic is moved, not rewritten) — verify it's faithful

- **`src/tools/tools.py`**  (−426 net): the 343-line `TOOL_REGISTRY` literal was REMOVED and
  replaced by `_build_tool_registry()` (~30 lines calling `compose_registry`). The 35 handler
  *functions* are unchanged. **Skim** the bottom of the file (the build wiring).
- **`src/tools/domains/core.py`**  (new, 466 lines): this is the 343-line dict literal, **moved
  here verbatim** as `build_core_tools()`. Nothing new — it's the same metadata, relocated.
  Skim to confirm it's a move, not edits.
- **`src/tools/registry.py`** (169) + **`modules.py`** (90): the typed `ToolRegistry` +
  `compose_registry` that assemble the catalog. Small, self-contained, fully tested
  (`test_registry.py`, `test_modules.py`).
- **`src/tools/domains/generated/`** (schema/params/handlers/register): the 4 tools that used to be
  network-generated, now static. `handlers.py` is a **verbatim port** of the old generator's request
  logic; `schema.py` is byte-locked to `tests/fixtures/generated_tools_golden.json`. Skim.

---

## TIER 3 — Deleted (just confirm the deletion is intentional)

- **`src/tools/tool_generator.py`**  (−317, DELETED): the runtime OpenAPI generator. This is the
  big win — boot-time GitHub fetch, gone. Its tools live in `domains/generated/` now.
- **`tests/tools/test_tool_generator.py`** (−291, DELETED): tested the deleted generator.

---

## The safety nets (why the "moved" code is trustworthy)

- `tests/fixtures/generated_tools_golden.json` — captured from the live generator BEFORE deletion;
  `test_generated_tools_golden.py` asserts the static tools match it.
- `tests/tools/test_modules.py` — pins the exact 48-tool order (hand-frozen, not derived).
- `integration_tests/` (the ~30 black-box tests) — unchanged contract: same tool names, output text,
  endpoints. They're the 1:1 oracle.

---

## Suggested commands

```bash
# the 6 files that actually need your brain:
git diff 1a8b316..HEAD -- src/mcp_server_opensearch/tool_executor.py src/opensearch/version_cache.py \
  src/opensearch/connection.py src/opensearch/client.py src/opensearch/helper.py src/tools/compat.py

# the structural move (skim):
git diff 1a8b316..HEAD -- src/tools/tools.py src/tools/domains/

# per-commit story (each commit is one logical step):
git log --oneline --stat 1a8b316..HEAD
```
