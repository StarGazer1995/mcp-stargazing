import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class AnalysisCacheItem:
    results: list[Any]
    created_at: float = field(default_factory=time.time)
    revision: str = field(default_factory=lambda: uuid4().hex)


class AnalysisCache:
    """TTL-based in-memory cache with LRU eviction when maxsize is exceeded.

    Thread-safe: all public methods are guarded by a reentrant lock.
    """

    def __init__(self, ttl_seconds=3600, maxsize=128):
        self._cache: OrderedDict[str, AnalysisCacheItem] = OrderedDict()
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key: str) -> list[Any] | None:
        cached = self.get_versioned(key)
        return cached[0] if cached is not None else None

    def get_versioned(self, key: str) -> tuple[list[Any], str] | None:
        """Read the payload and its publication identity under the same lock."""
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            if time.time() - item.created_at < self.ttl:
                self._cache.move_to_end(key)
                return item.results, item.revision
            del self._cache[key]
            return None

    def set(self, key: str, results: list[Any]) -> str:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)
            item = AnalysisCacheItem(results=results)
            self._cache[key] = item
            return item.revision


# Global cache instance
ANALYSIS_CACHE = AnalysisCache()


def generate_cache_key(**kwargs) -> str:
    """Generate a stable cache key from arguments."""
    # Sort keys to ensure stability
    serialized = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode(), usedforsecurity=False).hexdigest()
