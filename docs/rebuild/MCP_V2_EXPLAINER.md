# MCP "v2" — What the Protocol Beta Says and What Would Change

> Audience: the engineer rebuilding `opensearch-mcp-server-py` on the official Python SDK pinned `mcp>=1.25,<2` (low-level `mcp.server.Server`, deliberately NOT adopting SDK v2 yet).
> As of: mid-June 2026. Every forward-looking item below carries an explicit maturity tag. Where sources were thin, that is called out.

**Maturity legend**
- **SHIPPED** — in a stable, released spec version or an installable package today.
- **IN JUNE-2026 SPEC** — merged/Final in the spec repo, slated for the upcoming `2026-07-28` release (currently Release Candidate, NOT released).
- **DRAFT PR** — open, unmerged pull request.
- **PROPOSAL** — talk/roadmap claim only; no corresponding merged spec entry or shipped code found.

---

## 1. TL;DR

- **The single big idea is horizontal scaling.** Everything in "v2" exists to make MCP servers survive behind a load balancer. Today, stateful Streamable HTTP holds an SSE stream open on one instance; elicitation/sampling break if a later request lands on a different replica. v2 makes each request self-contained.
- **There are two different "v2"s, and people conflate them.** (a) The **protocol spec** revision (stateless-by-default Streamable HTTP, MRTR) and (b) the **Python SDK v2** library rewrite (Dispatcher, `FastMCP`→`MCPServer`, typed handlers). They move on separate clocks.
- **Maturity reality, honestly:** The current *stable* spec is **`2025-11-25`**, which makes sessions **optional** but is **not** stateless-by-default. Stateless-by-default (SEP-2575) and **MRTR** (SEP-2322) are **Final in the spec repo** but ship in the **`2026-07-28`** release that is **still a Release Candidate** — not out yet.
- **SDK reality:** Python SDK **v2 is alpha** (`v2.0.0a1`, June 2026), beta targeted ~June 30, stable ~July 27. The `FastMCP`→`MCPServer` rename **shipped** in the alpha (hard break, no alias). The **Dispatcher pattern is still a DRAFT PR (#2320)**. MRTR has **no SDK implementation merged** yet. TypeScript SDK v2 alpha **is** published and installable.
- **One-line impact on our rebuild:** Pinning `mcp>=1.25,<2` is correct — none of this is stable enough to adopt — and because we already run `StreamableHTTPSessionManager(stateless=True)` on the low-level `Server`, we are philosophically aligned with where the spec is going and a future v2 migration is a contained, transport-layer change.

---

## 2. Two things people conflate

"MCP v2" is shorthand for two independent tracks. Mixing them up is the #1 source of confusion.

| Layer | What changes | Maturity |
|---|---|---|
| **Protocol spec** (`2026-07-28`, currently RC) | Stateless-by-default Streamable HTTP (SEP-2575); MRTR multi-round elicitation/sampling (SEP-2322); session IDs formalized | SEPs **Final** in repo → **IN JUNE-2026 SPEC** (release is RC, not shipped). Current stable = `2025-11-25` (sessions **optional**, not stateless-default) — **SHIPPED** |
| **Python SDK v2** (`v2.0.0a1` alpha) | `FastMCP`→`MCPServer`; decorators → typed constructor handlers; Dispatcher pattern; snake_case fields; auth rework | Rename + typed handlers **SHIPPED in alpha**; Dispatcher = **DRAFT PR**; MRTR support = not merged; full v2 stable ~July 27 = **IN JUNE-2026 SPEC** target |

The protocol is the wire contract (what bytes go over HTTP). The SDK is one library's implementation of it. You can be spec-compliant on the low-level `Server` (where we are) without ever touching SDK v2 classes.

---

## 3. The core problem v2 solves: horizontal scaling

MCP began as a single-process, bidirectional protocol (stdio). When it moved to HTTP, the bidirectionality was preserved using **Streamable HTTP with an SSE stream**: the server can push messages *back* to the client (elicitation: "ask the user a question"; sampling: "ask the client's LLM to complete this") over a long-lived stream tied to one TCP connection on **one server instance**.

That breaks behind a load balancer. Walk the failure:

1. Client opens a session and a tool call hits **replica A**. The tool calls `await ctx.elicit(...)` to ask the user something.
2. Replica A is now **blocked on an in-memory coroutine**, holding the SSE stream open, waiting for the answer. The pending state lives only in A's RAM.
3. The user answers. The client POSTs the response — but the load balancer routes it to **replica B**.
4. Replica B has **no idea** this session is mid-elicitation. The coroutine and its captured state are on A. The request fails or hangs.

The classic patches are **sticky sessions** (pin a client to one replica — fragile, defeats elastic scaling, breaks on deploys) or a **shared state store** (correlate responses back to the pending call — operationally heavy). The `2025-11-25` spec's official **`MCP-Session-Id`** header (server assigns at init, client echoes) helps a load balancer *route to the right replica*, but that still requires the original replica to be alive and holding the stream. **SHIPPED but partial.**

The v2 answer is to **stop holding state in one process at all**: make every round a complete, self-contained HTTP request that any replica can serve. That is what stateless-by-default + MRTR deliver (Section 4–5).

---

## 4. The headline changes

Each item: *what it replaces / why it matters / maturity*.

### 4.1 MRTR — Multi-Round-Trip Requests (SEP-2322)
- **Replaces:** SSE-stream-held elicitation/sampling tied to one instance (the Section 3 failure).
- **Why it matters:** Instead of holding a stream, the server returns an `IncompleteResult` (`resultType: input_required`) carrying `inputRequests` and an optional opaque `requestState` blob, then the request **terminates cleanly**. The client collects the user's answer and makes a **new** tool/prompt/resource call echoing `inputResponses` + `requestState`. The function **re-runs from the top** each round (so side effects fire each round), reconstituting context from `requestState`. Because each round is a standalone HTTP request, **any replica can handle it** — no stream affinity, no shared store. Security note: `requestState` flows through the untrusted client, so a server **must** cryptographically bind it to the authenticated user (signed JWT / AES-GCM) to prevent replay/tampering.
- **Maturity:** SEP-2322 is **Final** in the spec repo (merged May 2026), but ships in `2026-07-28` → **IN JUNE-2026 SPEC** (RC, not released). **No Python SDK implementation merged.** The author-facing compatibility layer (how the SDK hides the re-call so `await ctx.elicit()` stays unchanged) is an explicit **open question** in the SEP → **PROPOSAL** for the SDK piece.

### 4.2 Stateless-by-default + official stateless Streamable HTTP (SEP-2575)
- **Replaces:** Mandatory stateful sessions; today's stateless mode is an **unofficial SDK convention** (init optional, no session IDs) that is non-compliant and does **not** support elicitation/sampling.
- **Why it matters:** SEP-2575 removes mandatory session initialization and pushes per-request `MCP-Protocol-Version` + capabilities, so a request needs no prior handshake. Combined with MRTR (which handles the elicitation/sampling case statelessly), this makes fully stateless, horizontally scalable MCP a **first-class, spec-blessed** deployment — not a workaround.
- **Maturity:** SEP-2575 is **Final** (June 2025) but **not yet incorporated into a stable release**. Becomes official in `2026-07-28` → **IN JUNE-2026 SPEC** (RC). The current stable `2025-11-25` spec makes sessions **optional**, **not** stateless-by-default. (Claims that "official stateless mode landed in a June-2026 stable spec" are **false** as of this writing — it is RC, dated July 28.)

### 4.3 Dispatcher / pluggable transports (Python SDK PR #2320)
- **Replaces:** The monolithic `BaseSession` that mixes wire protocol (JSON-RPC framing, ID correlation, receive loop, stream management) with the 19 MCP-semantic methods.
- **Why it matters:** Extracts wire handling into a `Dispatcher` with **5 methods** (`send_request`, `send_notification`, `send_response`, `set_handlers`, `run`). Implement those 5 and you inherit all 19 MCP methods — enabling gRPC/Protobuf/WebSocket transports without reimplementing session semantics. Cleanly separates *message format* (JSON-RPC vs Protobuf) from *transport* (stdio vs Streamable HTTP vs gRPC). It is also the foundation MRTR's request re-call / coroutine-parking will sit on.
- **Maturity:** **DRAFT PR** — #2320 is open, `draft=true`, unmerged (in draft since March 2026). Do not design against its API yet.

### 4.4 `FastMCP` → `MCPServer` rename + typed low-level handlers
- **Replaces:** The `FastMCP` class name (collided with the popular third-party `fastmcp` package); and decorator-based registration (`@server.call_tool()`) → explicit constructor args (`Server(call_tool=fn, ...)`) with fully typed `(ctx, params)` handlers.
- **Why it matters:** Namespace clarity; explicit, statically-checkable, IDE-friendly handler wiring. v2 also moves Pydantic field names camelCase→snake_case (`inputSchema`→`input_schema`), preserving wire camelCase via aliases.
- **Maturity:** Rename **SHIPPED** in `v2.0.0a1` (June 2026) as a **hard break — no `FastMCP` alias** (`from mcp.server.fastmcp import FastMCP` → `from mcp.server import MCPServer`). Typed-handler / constructor-arg redesign is in the alpha → **IN JUNE-2026 SPEC** (stabilizing toward July). **Note: we do not use `FastMCP`** — both our servers use the low-level `mcp.server.Server` with decorators, so the rename does not affect us; the *typed handler* shift would (Section 6).

### 4.5 Auth rework
- **Replaces:** Today's manual OAuth 2.1 resource-server token verification (bearer/API key checks inside handlers); no unified SSO or token-lifecycle pattern.
- **Why it matters:** Aims at composable, standardized auth (the TS v2 direction points to delegated/SSO via external providers, redesigned error types).
- **Maturity:** **DRAFT / design phase** — no merged Python design. Details TBD; treat as **PROPOSAL** for planning.

### 4.6 TypeScript SDK v2 alpha
- **Replaces:** TS v1 monolith / Zod-hard-dependency / Node-only.
- **Why it matters:** Useful as a **parity reference** for where Python v2 is heading: modular packages, multi-runtime (Node/Bun/Deno/Cloudflare Workers), bring-your-own validator (Zod/Valibot/ArkType), framework middleware (Hono/Express/Fastify), redesigned `ProtocolError` vs `SdkError`.
- **Maturity:** **SHIPPED (alpha)** — `2.0.0-alpha.2` published and installable on npm (April 2026). Two caveats where the conference talk over-claimed: a **bundled migration skill** and **built-in SSO** were *not* found shipped — SSO is via external providers, migration is a docs guide → those specific claims are **PROPOSAL**.

---

## 5. Before / after: elicitation under MRTR (concrete)

The scenario: an OpenSearch tool needs to ask the user a question mid-execution (e.g., "this query will scan 40 indices — confirm?").

**Today (stateful Streamable HTTP — what our SSE path does):**

```python
@server.call_tool()
async def call_tool(name, arguments):
    # ... server holds the SSE stream open on THIS replica ...
    answer = await ctx.elicit("Scan 40 indices? (y/n)")   # coroutine parks here, in-RAM
    if answer == "y":
        return run_search()
    return cancelled()
```

The replica is blocked holding the stream; the user's answer must route back to *this* process. Behind an LB without sticky routing → broken.

**Under MRTR (stateless — the `2026-07-28` direction):**

1. **Round 1.** Tool runs from the top, reaches the elicitation point. The server returns an `IncompleteResult`:
   ```jsonc
   { "resultType": "input_required",
     "inputRequests": { "confirm": { /* ElicitRequest: "Scan 40 indices?" */ } },
     "requestState": "<opaque, signed-to-user blob>" }
   ```
   The HTTP request **completes and closes.** No replica holds state.
2. **Client** collects the answer.
3. **Round 2.** Client sends a **new** `CallTool` request (different JSON-RPC id), echoing:
   ```jsonc
   { "inputResponses": { "confirm": { /* ElicitResult: "y" */ } },
     "requestState": "<same opaque blob>" }
   ```
   It can land on **any replica**. The server validates/decrypts `requestState`, **re-runs the function from the top**, fast-forwards past the already-answered elicitation, and proceeds. (Side effects re-fire each round — that is by design; author code must tolerate it.)

**The point of the SDK compat layer:** authors should keep writing `await ctx.elicit(...)`; the SDK parks/resumes the coroutine and handles the `IncompleteResult`/re-call plumbing underneath. **That compat layer is not implemented yet (PROPOSAL/open question), and MRTR itself is IN JUNE-2026 SPEC, not shipped.** So this is the *direction*, not something to build against today.

---

## 6. What this means for OUR rebuild

**Bottom line: pinning `mcp>=1.25,<2` is the right call, and our current architecture is already aligned with the destination.** Today the project actually pins `mcp[cli]>=1.9.4` with **no upper bound** (`pyproject.toml` line 11) — the rebuild should tighten this to `mcp>=1.25,<2`.

**Why pin `<2` now:**
- SDK v2 is **alpha** with monthly breaking changes; `FastMCP`→`MCPServer` shipped as a **hard break with no alias**; the Dispatcher (the biggest structural change) is still a **draft PR**. An unbounded pin would auto-upgrade us into a broken build the moment v2 hits PyPI's default tag.
- The protocol features that justify v2 (stateless-by-default, MRTR) are **IN JUNE-2026 SPEC / RC**, not in any stable release. There is nothing stable to adopt.
- `>=1.25` gets us the mature, stable Streamable HTTP + optional sessions from the `2025-11-25` era without betting on RC behavior.

**We are already philosophically aligned with where the spec is going:**
- `streaming_server.py` constructs `StreamableHTTPSessionManager(app=self.mcp_server, event_store=None, json_response=False, stateless=stateless)` and `serve(...)` defaults `stateless=True`. We already run the **stateless Streamable HTTP** posture that SEP-2575 is formalizing — we just get it via the SDK convention today rather than the (not-yet-released) official mode. When the official mode lands, we are a short hop, not a rewrite.
- We are on the **low-level `mcp.server.Server`**, not `FastMCP`. So the headline `FastMCP`→`MCPServer` rename **does not touch us at all.**

**What a future v2 migration *would* touch (leave seams here):**
- **Transport wiring.** Keep all transport setup isolated. Today it lives in `streaming_server.py` (`MCPStarletteApp`, `StreamableHTTPSessionManager`, Starlette routes, the `/sse` + `/messages/` SSE path) and `stdio_server.py` (`stdio_server()`), each behind a `serve(...)` function dispatched from `__init__.py:main()`. The rebuild should formalize this into a `transport/` package (e.g. `transport/streamable_http.py`, `transport/stdio.py`) so that adopting the Dispatcher/pluggable-transport model later, or dropping the legacy SSE route, is a localized change. Our `_ASGIApp`/`MCPStarletteApp` split is already a good seam — preserve it.
- **Handler shape.** Our `@server.list_tools()` / `@server.call_tool()` decorators become the **typed constructor-arg handlers** (`Server(call_tool=fn, list_tools=fn)`, handlers receiving `(ctx, params)` and returning full result types) in v2. This is a mechanical but real change — keep `list_tools`/`call_tool` as thin, independently-testable functions (we already delegate `call_tool` to `tool_executor.execute_tool`, which is exactly right) so the v2 swap is a wiring change, not a logic rewrite.
- **Field names.** If we touch SDK Pydantic models directly, expect camelCase→snake_case in v2 (`inputSchema`→`input_schema`). We pass `inputSchema=...` into `mcp.types.Tool` today; that is one rename point.
- **Elicitation/sampling.** We do **not** currently use server-initiated elicitation/sampling, so MRTR does not force anything on us. If we ever add it, design tools to be **idempotent / side-effect-tolerant on re-run** so we are MRTR-ready by construction.
- **Don't build against:** the Dispatcher API (draft PR), MRTR message types, or the auth rework (no merged design). These are PROPOSAL/DRAFT — leave seams, don't implement.

---

## 7. Sources

Spec:
- Transports history: `2024-11-05` (HTTP+SSE, deprecated) → `2025-03-26` (Streamable HTTP + session ID) → `2025-06-18` → `2025-11-25` (current stable). https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Lifecycle / capability negotiation: https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- Schema (`LATEST_PROTOCOL_VERSION = 2025-11-25`): https://github.com/modelcontextprotocol/specification/blob/main/schema/2025-11-25/schema.ts
- Draft `2026-07-28-RC` transports (stateless-by-default, MRTR types): https://github.com/modelcontextprotocol/specification/blob/main/docs/specification/draft/basic/transports/streamable-http.mdx
- SEP-2322 (MRTR, Status: Final, PR #2322 merged May 2026): https://modelcontextprotocol.io/seps/2322-MRTR
- SEP-2575 (Make MCP Stateless, Status: Final, June 2025): https://modelcontextprotocol.io/seps/2575-stateless-mcp

Python SDK:
- Repo / `v2.0.0a1` release notes: https://github.com/modelcontextprotocol/python-sdk/releases
- Migration guide (`FastMCP`→`MCPServer`, Dispatcher architecture): https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md
- Dispatcher pattern (DRAFT, open/unmerged): https://github.com/modelcontextprotocol/python-sdk/pull/2320
- PyPI: https://pypi.org/project/mcp/

TypeScript SDK:
- v2 alpha releases / `@modelcontextprotocol/server@2.0.0-alpha.2`: https://github.com/modelcontextprotocol/typescript-sdk/releases ; https://www.npmjs.com/package/@modelcontextprotocol/server
- TS v2 migration guide: https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/migration.md

Talk:
- Max Isbey (Anthropic, MCP Python SDK maintainer), "Path to V2 for MCP SDKs," MCP Dev Summit, April 2026 — primary source for the v2 roadmap. **Caveats:** the talk's "official stateless mode in June 2026" framing is RC/`2026-07-28`, not a shipped stable release; "bundled migration skill" and "built-in SSO" were not found shipped (PROPOSAL).

Our codebase (grounding for Section 6):
- `src/mcp_server_opensearch/streaming_server.py` — `StreamableHTTPSessionManager(..., stateless=stateless)`, `serve(stateless=True)`, `MCPStarletteApp`, low-level `Server` + decorators.
- `src/mcp_server_opensearch/stdio_server.py` — `stdio_server()`, low-level `Server` + decorators.
- `src/mcp_server_opensearch/__init__.py` — `main()` transport dispatch (`--transport stdio|stream`).
- `pyproject.toml` line 11 — current `mcp[cli]>=1.9.4` (no upper bound; rebuild should pin `mcp>=1.25,<2`).
