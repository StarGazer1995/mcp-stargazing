import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisCacheItem:
    results: list[dict[str, Any]]
    created_at: float = field(default_factory=time.time)


class AnalysisCache:
    def __init__(self, ttl_seconds=3600):
        self._cache: dict[str, AnalysisCacheItem] = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> list[dict[str, Any]] | None:
        item = self._cache.get(key)
        if item:
            if time.time() - item.created_at < self.ttl:
                return item.results
            else:
                del self._cache[key]
        return None

    def set(self, key: str, results: list[dict[str, Any]]):
        self._cache[key] = AnalysisCacheItem(results=results)


# Global cache instance
ANALYSIS_CACHE = AnalysisCache()


def generate_cache_key(**kwargs) -> str:
    """Generate a stable cache key from arguments."""
    # Sort keys to ensure stability
    serialized = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode(), usedforsecurity=False).hexdigest()
