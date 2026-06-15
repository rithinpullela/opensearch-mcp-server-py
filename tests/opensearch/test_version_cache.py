# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from opensearch.version_cache import (
    clear_cache,
    get_cached_version,
    get_ttl_secs,
    make_cache_key,
)
from semver import Version
from tools.tool_params import baseToolArgs


class _Clock:
    """Controllable monotonic clock for tests (no real sleeps)."""

    def __init__(self, start=0.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, secs):
        self.t += secs


class _Counter:
    """Awaitable fetch factory that counts how many times it was invoked."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self.value


def _single_args(url=None):
    return baseToolArgs(opensearch_cluster_name='', opensearch_url=url)


def _multi_args(name):
    return baseToolArgs(opensearch_cluster_name=name)


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    # Ensure a known TTL and an empty cache for every test.
    monkeypatch.delenv('OPENSEARCH_VERSION_CACHE_TTL_SECS', raising=False)
    monkeypatch.delenv('OPENSEARCH_URL', raising=False)
    clear_cache()
    yield
    clear_cache()


# --- TTL configuration -----------------------------------------------------


def test_get_ttl_default():
    assert get_ttl_secs() == 600.0


def test_get_ttl_env_override(monkeypatch):
    monkeypatch.setenv('OPENSEARCH_VERSION_CACHE_TTL_SECS', '120')
    assert get_ttl_secs() == 120.0


def test_get_ttl_invalid_falls_back(monkeypatch):
    monkeypatch.setenv('OPENSEARCH_VERSION_CACHE_TTL_SECS', 'not-a-number')
    assert get_ttl_secs() == 600.0


def test_get_ttl_negative_falls_back(monkeypatch):
    monkeypatch.setenv('OPENSEARCH_VERSION_CACHE_TTL_SECS', '-5')
    assert get_ttl_secs() == 600.0


# --- Caching behavior ------------------------------------------------------


@pytest.mark.asyncio
async def test_hit_within_ttl_one_fetch():
    clock = _Clock()
    fetch = _Counter(Version.parse('2.11.0'))
    args = _multi_args('cluster-a')

    v1 = await get_cached_version(args, fetch, mode='multi', now=clock)
    clock.advance(599)
    v2 = await get_cached_version(args, fetch, mode='multi', now=clock)

    assert v1 == Version.parse('2.11.0')
    assert v2 == Version.parse('2.11.0')
    assert fetch.calls == 1


@pytest.mark.asyncio
async def test_expiry_triggers_refetch():
    clock = _Clock()
    fetch = _Counter(Version.parse('2.11.0'))
    args = _multi_args('cluster-a')

    await get_cached_version(args, fetch, mode='multi', now=clock)
    clock.advance(600)  # exactly at expiry -> no longer < expiry -> refetch
    await get_cached_version(args, fetch, mode='multi', now=clock)
    clock.advance(601)
    await get_cached_version(args, fetch, mode='multi', now=clock)

    assert fetch.calls == 3


@pytest.mark.asyncio
async def test_concurrent_gather_one_fetch():
    import asyncio

    clock = _Clock()
    fetch = _Counter(Version.parse('3.0.0'))
    args = _multi_args('cluster-a')

    results = await asyncio.gather(
        *[get_cached_version(args, fetch, mode='multi', now=clock) for _ in range(20)]
    )

    assert all(r == Version.parse('3.0.0') for r in results)
    assert fetch.calls == 1


@pytest.mark.asyncio
async def test_none_cached_only_for_short_floor():
    clock = _Clock()
    fetch = _Counter(None)
    args = _multi_args('cluster-a')

    r1 = await get_cached_version(args, fetch, mode='multi', now=clock)
    assert r1 is None
    assert fetch.calls == 1

    # Within the 5s floor -> still cached, no refetch.
    clock.advance(4)
    r2 = await get_cached_version(args, fetch, mode='multi', now=clock)
    assert r2 is None
    assert fetch.calls == 1

    # Past the 5s floor (well before the 600s TTL) -> refetch.
    clock.advance(2)
    await get_cached_version(args, fetch, mode='multi', now=clock)
    assert fetch.calls == 2


@pytest.mark.asyncio
async def test_negative_floor_capped_by_small_ttl(monkeypatch):
    # When TTL < floor, negative entries use the (smaller) TTL.
    monkeypatch.setenv('OPENSEARCH_VERSION_CACHE_TTL_SECS', '3')
    clock = _Clock()
    fetch = _Counter(None)
    args = _multi_args('cluster-a')

    await get_cached_version(args, fetch, mode='multi', now=clock)
    clock.advance(2)
    await get_cached_version(args, fetch, mode='multi', now=clock)
    assert fetch.calls == 1
    clock.advance(1)
    await get_cached_version(args, fetch, mode='multi', now=clock)
    assert fetch.calls == 2


@pytest.mark.asyncio
async def test_ttl_zero_disables_caching(monkeypatch):
    monkeypatch.setenv('OPENSEARCH_VERSION_CACHE_TTL_SECS', '0')
    clock = _Clock()
    fetch = _Counter(Version.parse('2.11.0'))
    args = _multi_args('cluster-a')

    for _ in range(5):
        await get_cached_version(args, fetch, mode='multi', now=clock)

    assert fetch.calls == 5


@pytest.mark.asyncio
async def test_distinct_targets_get_distinct_entries():
    clock = _Clock()
    fetch_a = _Counter(Version.parse('2.0.0'))
    fetch_b = _Counter(Version.parse('3.0.0'))

    va = await get_cached_version(_multi_args('a'), fetch_a, mode='multi', now=clock)
    vb = await get_cached_version(_multi_args('b'), fetch_b, mode='multi', now=clock)

    assert va == Version.parse('2.0.0')
    assert vb == Version.parse('3.0.0')
    assert fetch_a.calls == 1
    assert fetch_b.calls == 1


@pytest.mark.asyncio
async def test_clear_cache_forces_refetch():
    clock = _Clock()
    fetch = _Counter(Version.parse('2.11.0'))
    args = _multi_args('cluster-a')

    await get_cached_version(args, fetch, mode='multi', now=clock)
    clear_cache()
    await get_cached_version(args, fetch, mode='multi', now=clock)

    assert fetch.calls == 2


# --- Key normalization equivalence classes ---------------------------------


def test_key_multi_mode_uses_cluster_name():
    assert make_cache_key(_multi_args('my-cluster'), 'multi') == 'my-cluster'


def test_key_normalization_trailing_slash():
    a = make_cache_key(_single_args('http://localhost:9200'), 'single')
    b = make_cache_key(_single_args('http://localhost:9200/'), 'single')
    assert a == b


def test_key_normalization_uppercase_host():
    a = make_cache_key(_single_args('https://MyHost.Example.com:9200'), 'single')
    b = make_cache_key(_single_args('https://myhost.example.com:9200'), 'single')
    assert a == b


def test_key_normalization_omitted_default_port_https():
    a = make_cache_key(_single_args('https://example.com'), 'single')
    b = make_cache_key(_single_args('https://example.com:443'), 'single')
    assert a == b


def test_key_normalization_omitted_default_port_http():
    a = make_cache_key(_single_args('http://example.com'), 'single')
    b = make_cache_key(_single_args('http://example.com:80'), 'single')
    assert a == b


def test_key_normalization_strips_userinfo():
    a = make_cache_key(_single_args('https://user:pass@example.com:9200'), 'single')
    b = make_cache_key(_single_args('https://example.com:9200'), 'single')
    assert a == b


def test_key_all_equivalence_classes_collapse_to_one():
    urls = [
        'https://User:Pass@Example.COM/',
        'https://example.com:443',
        'https://example.com:443/',
        'HTTPS://EXAMPLE.COM',
    ]
    keys = {make_cache_key(_single_args(u), 'single') for u in urls}
    assert len(keys) == 1


def test_key_single_mode_reads_env_when_url_absent(monkeypatch):
    monkeypatch.setenv('OPENSEARCH_URL', 'http://localhost:9200/')
    key = make_cache_key(_single_args(None), 'single')
    assert key == make_cache_key(_single_args('http://localhost:9200'), 'single')


def test_key_distinct_hosts_differ():
    a = make_cache_key(_single_args('http://localhost:9200'), 'single')
    b = make_cache_key(_single_args('http://127.0.0.1:9200'), 'single')
    assert a != b
