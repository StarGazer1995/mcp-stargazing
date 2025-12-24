from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import time
import json
import hashlib

@dataclass
class AnalysisCacheItem:
    results: List[Dict[str, Any]]
    created_at: float = field(default_factory=time.time)

class AnalysisCache:
    def __init__(self, ttl_seconds=3600):
        self._cache: Dict[str, AnalysisCacheItem] = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        item = self._cache.get(key)
        if item:
            if time.time() - item.created_at < self.ttl:
                return item.results
            else:
                del self._cache[key]
        return None

    def set(self, key: str, results: List[Dict[str, Any]]):
        self._cache[key] = AnalysisCacheItem(results=results)

# Global cache instance
ANALYSIS_CACHE = AnalysisCache()

def generate_cache_key(**kwargs) -> str:
    """Generate a stable cache key from arguments."""
    # Sort keys to ensure stability
    serialized = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode()).hexdigest()
