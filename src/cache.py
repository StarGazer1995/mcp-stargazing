import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisCacheItem:
    results: list[dict[str, Any]]
    created_at: float = field(default_factory=time.time)


class AnalysisCache:
    """TTL-based in-memory cache with LRU eviction when maxsize is exceeded."""

    def __init__(self, ttl_seconds=3600, maxsize=128):
        self._cache: OrderedDict[str, AnalysisCacheItem] = OrderedDict()
        self.ttl = ttl_seconds
        self.maxsize = maxsize

    def get(self, key: str) -> list[dict[str, Any]] | None:
        item = self._cache.get(key)
        if item is None:
            return None
        if time.time() - item.created_at < self.ttl:
            self._cache.move_to_end(key)
            return item.results
        del self._cache[key]
        return None

    def set(self, key: str, results: list[dict[str, Any]]):
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = AnalysisCacheItem(results=results)
            return
        if len(self._cache) >= self.maxsize:
            self._cache.popitem(last=False)
        self._cache[key] = AnalysisCacheItem(results=results)


# Global cache instance
ANALYSIS_CACHE = AnalysisCache()


def generate_cache_key(**kwargs) -> str:
    """Generate a stable cache key from arguments."""
    # Sort keys to ensure stability
    serialized = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode(), usedforsecurity=False).hexdigest()
