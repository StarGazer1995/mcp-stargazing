import time

from src.cache import AnalysisCache, generate_cache_key


class TestAnalysisCache:
    """Tests for the LRU + TTL cache behaviour added in the sprint."""

    def test_get_set_basic(self):
        """Cache hit returns stored results."""
        cache = AnalysisCache()
        cache.set('k1', [{'a': 1}])
        assert cache.get('k1') == [{'a': 1}]

    def test_get_miss_returns_none(self):
        """Cache miss returns None."""
        cache = AnalysisCache()
        assert cache.get('nonexistent') is None

    def test_ttl_expiration_evicts_entry(self):
        """Entry is evicted (returns None) after TTL passes."""
        cache = AnalysisCache(ttl_seconds=0)
        cache.set('k1', [{'a': 1}])
        time.sleep(0.001)  # ensure time advances past zero TTL
        assert cache.get('k1') is None

    def test_get_moves_to_end_for_lru(self):
        """A cache hit promotes the entry (makes it most-recently-used)."""
        cache = AnalysisCache(maxsize=2)
        cache.set('a', [1])
        cache.set('b', [2])
        cache.get('a')  # now 'a' is MRU, 'b' is LRU
        cache.set('c', [3])  # should evict 'b', not 'a'
        assert cache.get('a') == [1]
        assert cache.get('b') is None
        assert cache.get('c') == [3]

    def test_maxsize_evicts_lru(self):
        """When cache is full, the least-recently-used entry is evicted."""
        cache = AnalysisCache(maxsize=2)
        cache.set('a', [1])
        cache.set('b', [2])
        cache.set('c', [3])
        assert cache.get('a') is None  # 'a' was LRU
        assert cache.get('b') == [2]
        assert cache.get('c') == [3]

    def test_set_existing_key_updates_and_promotes(self):
        """Setting an existing key updates its value and marks it as MRU."""
        cache = AnalysisCache(maxsize=2)
        cache.set('a', [1])
        cache.set('b', [2])
        cache.set('a', [99])  # update 'a', making 'b' the LRU
        cache.set('c', [3])  # should evict 'b'
        assert cache.get('a') == [99]
        assert cache.get('b') is None
        assert cache.get('c') == [3]

    def test_custom_ttl_defaults(self):
        """Default TTL is 3600 and maxsize is 128."""
        cache = AnalysisCache()
        assert cache.ttl == 3600
        assert cache.maxsize == 128

    def test_custom_parameters(self):
        """Custom TTL and maxsize are honoured."""
        cache = AnalysisCache(ttl_seconds=60, maxsize=10)
        assert cache.ttl == 60
        assert cache.maxsize == 10

    def test_maxsize_one(self):
        """Cache with maxsize=1 only keeps the most recent entry."""
        cache = AnalysisCache(maxsize=1)
        cache.set('a', [1])
        cache.set('b', [2])
        assert cache.get('a') is None
        assert cache.get('b') == [2]


class TestGenerateCacheKey:
    def test_stable_key(self):
        """Same kwargs produce the same key."""
        k1 = generate_cache_key(a=1, b=2)
        k2 = generate_cache_key(a=1, b=2)
        assert k1 == k2

    def test_order_independent(self):
        """Key is stable regardless of kwarg order."""
        k1 = generate_cache_key(a=1, b=2)
        k2 = generate_cache_key(b=2, a=1)
        assert k1 == k2

    def test_different_args_produce_different_keys(self):
        """Different kwargs produce different keys."""
        k1 = generate_cache_key(a=1)
        k2 = generate_cache_key(a=2)
        assert k1 != k2
