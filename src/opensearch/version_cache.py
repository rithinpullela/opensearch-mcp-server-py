# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Per-connection-target, TTL-bounded, async-safe version cache.

Wraps the per-call OpenSearch version fetch (``GET /`` → ``version.number``) so
that the version gate (``check_tool_compatibility`` → ``get_opensearch_version``
on *every* tool invocation, in both single and multi mode) stops opening a fresh
``AsyncOpenSearch`` client per call against a static cluster identity.

Design (see ``DESIGN_DECISIONS.md`` §1)
--------------------------------------
- A module-level ``dict`` is GIL-safe for get/set of whole entries. A **per-key**
  :class:`asyncio.Lock` (NOT ``threading.RLock`` — the server is async) guards the
  check-fetch-store critical section, so N concurrent calls *for the same target*
  collapse to one underlying fetch + N-1 cache reads, while calls for *different*
  targets fetch concurrently (a slow/hung ``GET /`` for cluster A never blocks
  version resolution for cluster B). A short meta-lock guards per-key lock creation
  and is never held across a fetch.
- The cache key is per connection target: in multi mode the cluster name; in
  single mode a *normalized* connection URL (lowercase host, explicit default
  port, no trailing slash, userinfo stripped) so that equivalent URLs share an
  entry. ``localhost`` and ``127.0.0.1`` are deliberately NOT unified (a harmless
  extra fetch).
- TTL defaults to 600s (``OPENSEARCH_VERSION_CACHE_TTL_SECS``); ``0`` disables
  caching entirely (always fetch). A negative result (fetch returned ``None`` on
  an error/serverless path) is cached only for a short 5s floor so a flaky ``/``
  does not pin "unknown" for the full TTL while still collapsing a thundering
  herd.
- Time is injected via ``now`` (default :func:`time.monotonic`) so tests control
  expiry without real sleeps.
"""

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from semver import Version
from tools.tool_params import baseToolArgs
from typing import Optional
from urllib.parse import urlparse, urlunparse


# key -> (version, expiry_epoch); GIL-safe for whole-entry get/set.
_CACHE: dict[str, tuple[Optional[Version], float]] = {}

# Per-key locks so the check-fetch-store critical section serializes only within a
# single connection target. A slow/hung ``GET /`` for cluster A must NOT block
# version resolution for cluster B in multi mode. ``_LOCKS_META`` is a short-held
# meta-lock guarding creation/lookup of the per-key locks (never held across a fetch).
_LOCKS: dict[str, asyncio.Lock] = {}
_LOCKS_META = asyncio.Lock()


async def _lock_for(key: str) -> asyncio.Lock:
    """Return the per-key lock for ``key``, creating it under the meta-lock if needed.

    The meta-lock is held only for the brief dict lookup/insert — never across the
    awaited version fetch — so distinct keys never block one another.
    """
    async with _LOCKS_META:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[key] = lock
        return lock


# Default TTL (seconds) when the env var is unset/invalid.
_DEFAULT_TTL_SECS = 600.0

# Short floor (seconds) for caching a negative (None) fetch result.
_NEGATIVE_TTL_FLOOR_SECS = 5.0

# Explicit default ports by scheme, used to normalize the single-mode URL key.
_DEFAULT_PORTS_BY_SCHEME = {'http': 80, 'https': 443}


def get_ttl_secs() -> float:
    """Return the configured version-cache TTL in seconds.

    Reads ``OPENSEARCH_VERSION_CACHE_TTL_SECS``; falls back to the 600s default
    when unset or invalid. ``0`` is a valid value that disables caching (callers
    treat ``<= 0`` as "always fetch").

    Returns:
        float: The TTL in seconds (``0`` disables caching).
    """
    raw = os.getenv('OPENSEARCH_VERSION_CACHE_TTL_SECS', '').strip()
    if not raw:
        return _DEFAULT_TTL_SECS
    try:
        ttl = float(raw)
    except ValueError:
        return _DEFAULT_TTL_SECS
    if ttl < 0:
        return _DEFAULT_TTL_SECS
    return ttl


def make_cache_key(args: baseToolArgs, mode: str) -> str:
    """Compute the deterministic cache key for a connection target.

    In multi mode the key is ``args.opensearch_cluster_name``. In single mode the
    key is a normalized connection URL: scheme lowercased, host lowercased, an
    explicit default port added when omitted (http→80, https→443), any trailing
    slash on the path removed, and userinfo (``user:pass@``) stripped. The URL is
    resolved from ``args.opensearch_url`` when provided, else the
    ``OPENSEARCH_URL`` environment variable.

    Args:
        args: The tool arguments carrying the connection target / overrides.
        mode: The server mode, ``'single'`` or ``'multi'``.

    Returns:
        str: A pure, deterministic cache key.
    """
    if mode == 'multi':
        return args.opensearch_cluster_name or ''

    raw_url = args.opensearch_url
    if raw_url is None:
        raw_url = os.getenv('OPENSEARCH_URL', '')
    return _normalize_url(raw_url.strip())


def _normalize_url(url: str) -> str:
    """Normalize a connection URL into a stable cache key.

    Lowercases scheme and host, adds the explicit default port when omitted,
    strips a trailing slash from the path, and drops any userinfo. Unparseable
    input is returned lowercased and trailing-slash-stripped as a best effort.

    Args:
        url: The raw connection URL.

    Returns:
        str: The normalized URL.
    """
    if not url:
        return ''
    try:
        parsed = urlparse(url)
    except ValueError:
        return url.lower().rstrip('/')

    if not parsed.scheme or not parsed.hostname:
        return url.lower().rstrip('/')

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    host_literal = f'[{host}]' if ':' in host else host

    port = parsed.port
    if port is None:
        port = _DEFAULT_PORTS_BY_SCHEME.get(scheme)
    netloc = f'{host_literal}:{port}' if port is not None else host_literal

    path = parsed.path.rstrip('/')
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, parsed.fragment))


async def get_cached_version(
    args: baseToolArgs,
    fetch: Callable[[], Awaitable[Optional[Version]]],
    *,
    mode: str,
    now: Optional[Callable[[], float]] = None,
) -> Optional[Version]:
    """Return the cached version for ``args``'s target, fetching at most once.

    On a cache hit within the TTL the stored value is returned without calling
    ``fetch``. On a miss or expiry, ``fetch`` is awaited exactly once while the
    lock is held, so concurrent callers for the same target await a single
    underlying fetch and then read the stored result. A ``None`` result (error /
    serverless path) is cached only for the short negative floor. When the TTL is
    ``0`` (or negative env), caching is disabled and ``fetch`` is always awaited.

    Args:
        args: The tool arguments carrying the connection target / overrides.
        fetch: A zero-arg coroutine factory that performs the real version fetch.
        mode: The server mode, ``'single'`` or ``'multi'``.
        now: Monotonic clock injection for tests; defaults to ``time.monotonic``.

    Returns:
        Optional[Version]: The cached or freshly fetched version (may be ``None``).
    """
    clock = now if now is not None else time.monotonic
    ttl = get_ttl_secs()

    # TTL == 0 disables caching: always fetch, never store.
    if ttl <= 0:
        return await fetch()

    key = make_cache_key(args, mode)

    # Fast path: a fresh entry needs no lock at all (dict get is GIL-safe).
    cached = _CACHE.get(key)
    if cached is not None and clock() < cached[1]:
        return cached[0]

    # Slow path: serialize per-key so callers for the SAME target collapse to one
    # fetch, while DIFFERENT targets proceed concurrently.
    lock = await _lock_for(key)
    async with lock:
        # Double-check: another caller for this key may have populated it while we
        # waited for the lock.
        cached = _CACHE.get(key)
        if cached is not None and clock() < cached[1]:
            return cached[0]

        version = await fetch()
        entry_ttl = ttl if version is not None else min(ttl, _NEGATIVE_TTL_FLOOR_SECS)
        _CACHE[key] = (version, clock() + entry_ttl)
        return version


def clear_cache() -> None:
    """Clear all cached entries (and per-key locks).

    Test hook (and a seam for a future SIGHUP-driven refresh). Safe to call
    between tests to force a fresh fetch on the next lookup.
    """
    _CACHE.clear()
    _LOCKS.clear()
