import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from src.area_source_identity import area_source_identity
from src.response import MCPError

_UNSET = object()


class AreaSourceError(MCPError):
    """A business failure to verify the configuration used for cached results."""


@dataclass
class AnalysisCacheItem:
    results: list[Any]
    created_at: float  # Process-local monotonic publication time, not an epoch timestamp.
    revision: str = field(default_factory=lambda: uuid4().hex)


class AnalysisCache:
    """TTL-based in-memory cache with LRU eviction when maxsize is exceeded.

    Thread-safe: all public methods are guarded by a lock. TTL measures elapsed
    time since publication, independently of wall-clock corrections or reads.
    An optional source identity invalidates results and fences old publications.
    """

    def __init__(
        self,
        ttl_seconds=3600,
        maxsize=128,
        *,
        clock: Callable[[], float] = time.monotonic,
        source_identity: Callable | None = None,
    ):
        self._cache: OrderedDict[str, AnalysisCacheItem] = OrderedDict()
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._lock = threading.Lock()
        self._clock = clock
        self._source_identity = source_identity
        self._source_value = _UNSET
        self._source_token = uuid4().hex

    def _refresh_source(self) -> str:
        """Called under the cache lock, including inside guarded publication."""
        if self._source_identity is not None:
            try:
                value = self._source_identity()
            except Exception:
                self._cache.clear()
                self._source_token = uuid4().hex
                raise AreaSourceError(
                    MCPError.CONFIGURATION_ERROR,
                    'Area source configuration identity is unavailable; retry after checking it.',
                    {'reason': 'source_identity_unavailable'},
                ) from None
            if value != self._source_value:
                self._cache.clear()
                self._source_value = value
                self._source_token = uuid4().hex
        return self._source_token

    def source_token(self) -> str:
        with self._lock:
            return self._refresh_source()

    def get(self, key: str) -> list[Any] | None:
        cached = self.get_versioned(key)
        return cached[0] if cached is not None else None

    def get_versioned(self, key: str) -> tuple[list[Any], str] | None:
        """Read the payload and its publication identity under the same lock."""
        with self._lock:
            self._refresh_source()
            item = self._cache.get(key)
            if item is None:
                return None
            if self._clock() - item.created_at < self.ttl:
                self._cache.move_to_end(key)
                return item.results, item.revision
            del self._cache[key]
            return None

    def set(self, key: str, results: list[Any], *, expected_source: str | None = None) -> str:
        with self._lock:
            current_source = self._refresh_source()
            if expected_source is not None and current_source != expected_source:
                raise AreaSourceError(
                    MCPError.CONFIGURATION_ERROR,
                    'Area source configuration changed during calculation; resubmit the query.',
                    {'reason': 'source_configuration_changed', 'next_action': 'resubmit'},
                )
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)
            item = AnalysisCacheItem(results=results, created_at=self._clock())
            self._cache[key] = item
            return item.revision


# Global cache instance
ANALYSIS_CACHE = AnalysisCache(source_identity=area_source_identity)


def generate_cache_key(**kwargs) -> str:
    """Generate a stable cache key from arguments."""
    # Sort keys to ensure stability
    serialized = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode(), usedforsecurity=False).hexdigest()
