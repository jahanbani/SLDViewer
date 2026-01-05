"""
TTL + LRU cache for parsed case data and graph handles.
"""
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from backend.core.config import settings

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A cache entry with TTL tracking."""

    value: T
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if this entry has expired."""
        return (time.time() - self.created_at) > ttl_seconds

    def touch(self) -> None:
        """Update last access time."""
        self.last_accessed = time.time()


class TTLLRUCache(Generic[T]):
    """
    A cache with both TTL (time-to-live) and LRU (least recently used) eviction.

    - Entries expire after ttl_seconds
    - When max_entries is reached, least recently used entries are evicted
    """

    def __init__(
        self,
        ttl_seconds: int | None = None,
        max_entries: int | None = None,
    ):
        self.ttl_seconds = ttl_seconds or settings.cache_ttl_seconds
        self.max_entries = max_entries or settings.cache_max_entries
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        """
        Get a value from the cache.

        Returns None if key not found or entry expired.
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]

        # Check TTL
        if entry.is_expired(self.ttl_seconds):
            del self._cache[key]
            return None

        # Update LRU order and access time
        entry.touch()
        self._cache.move_to_end(key)

        return entry.value

    def set(self, key: str, value: T) -> None:
        """
        Set a value in the cache.

        Evicts LRU entries if max_entries exceeded.
        """
        # Remove existing entry if present
        if key in self._cache:
            del self._cache[key]

        # Evict LRU entries if at capacity
        while len(self._cache) >= self.max_entries:
            self._cache.popitem(last=False)

        self._cache[key] = CacheEntry(value=value)

    def delete(self, key: str) -> bool:
        """
        Delete an entry from the cache.

        Returns True if entry was deleted, False if not found.
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._cache.clear()

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns the number of entries removed.
        """
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if entry.is_expired(self.ttl_seconds)
        ]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)

    def __contains__(self, key: str) -> bool:
        """Check if key is in cache (without updating LRU order)."""
        if key not in self._cache:
            return False
        return not self._cache[key].is_expired(self.ttl_seconds)

    def __len__(self) -> int:
        """Return the number of non-expired entries."""
        self.cleanup_expired()
        return len(self._cache)

    @property
    def keys(self) -> list[str]:
        """Return list of all non-expired keys."""
        self.cleanup_expired()
        return list(self._cache.keys())


# Global caches for different data types
# These will be typed more specifically when models are defined
parsed_case_cache: TTLLRUCache[Any] = TTLLRUCache()
graph_handle_cache: TTLLRUCache[Any] = TTLLRUCache()
