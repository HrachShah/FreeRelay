"""
FreeRelay — Semantic Cache (§11)
==================================
LSH-based semantic caching using MinHash + datasketch.
Finds near-duplicate prompts above a configurable similarity threshold.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from freerelay.core.models.openai import ChatCompletionRequest, ChatCompletionResponse

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("freerelay.cache")


@dataclass
class CacheEntry:
    """A cached response with its MinHash signature."""

    key: str
    minhash: object | None = None  # datasketch.MinHash when available
    response_json: str = ""
    created_at: float = field(default_factory=time.time)
    ttl: int = 3600  # seconds


class SemanticCache:
    """
    In-memory semantic cache with optional Redis backing.

    When datasketch is available, uses MinHash + LSH for similarity search.
    Falls back to exact-match caching when datasketch is not installed.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        ttl: int = 3600,
        num_perm: int = 128,
        enabled: bool = False,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.ttl = ttl
        self.num_perm = num_perm
        self.enabled = enabled

        self._entries: dict[str, CacheEntry] = {}
        self._lsh: object | None = None

        # Redis support
        from freerelay.config.settings import get_settings
        settings = get_settings()
        self.enable_redis = settings.enable_redis
        self._redis: Optional[Redis] = None
        if self.enable_redis:
            from freerelay.shared.redis import get_redis_client
            self._redis = get_redis_client(settings)

        if enabled:
            self._init_lsh()

    def _init_lsh(self) -> None:
        """Initialize LSH index if datasketch is available."""
        try:
            from datasketch import MinHashLSH

            self._lsh = MinHashLSH(
                threshold=self.similarity_threshold, num_perm=self.num_perm
            )
            logger.info("Semantic cache initialized (datasketch)")
        except ImportError:
            logger.warning(
                "datasketch not installed — falling back to exact-match cache"
            )
            self._lsh = None

    def _text_to_minhash(self, text: str) -> object | None:
        """Convert text to a MinHash signature."""
        if self._lsh is None:
            return None

        try:
            from datasketch import MinHash

            m = MinHash(num_perm=self.num_perm)
            # Shingling: split into 3-char shingles
            shingles = (
                {text[i : i + 3] for i in range(len(text) - 2)}
                if len(text) > 3
                else {text}
            )
            for s in shingles:
                m.update(s.encode("utf-8"))
            return m
        except ImportError:
            return None

    def _canonicalize(self, request: ChatCompletionRequest) -> str:
        """
        Canonicalize a request for hashing.
        Strips whitespace, excludes irrelevant params.
        """
        parts: list[str] = []
        for msg in request.messages:
            content = msg.content if isinstance(msg.content, str) else ""
            entry = f"{msg.role}:{content.strip()}"
            if msg.tool_calls:
                import json

                tc_parts = []
                for tc in msg.tool_calls:
                    tc_parts.append(f"{tc.function.name}:{tc.function.arguments}")
                entry += f"|tools:{json.dumps(tc_parts)}"
            if msg.tool_call_id:
                entry += f"|tool_id:{msg.tool_call_id}"
            parts.append(entry)
        return "\n".join(parts)

    def _compute_key(self, text: str) -> str:
        """Compute a cache key from canonical text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    async def lookup(self, request: ChatCompletionRequest) -> ChatCompletionResponse | None:
        """
        Look up a request in the cache.

        Returns cached response if found (exact or semantic match), else None.
        """
        if not self.enabled:
            return None

        canonical = self._canonicalize(request)
        key = self._compute_key(canonical)

        # Exact match first (Redis)
        if self._redis:
            redis_key = f"freerelay:cache:{key}"
            cached_json = await self._redis.get(redis_key)
            if cached_json:
                try:
                    return ChatCompletionResponse.model_validate_json(cached_json)
                except Exception:
                    pass
        else:
            # Exact match first (In-memory)
            entry = self._entries.get(key)
            if entry and (time.time() - entry.created_at) < entry.ttl:
                try:
                    return ChatCompletionResponse.model_validate_json(entry.response_json)
                except Exception:
                    del self._entries[key]
                    return None

        # Semantic match via LSH
        if self._lsh is not None:
            minhash = self._text_to_minhash(canonical)
            if minhash is not None:
                try:
                    results = self._lsh.query(minhash) # type: ignore
                    for result_key in results:
                        if self._redis:
                            redis_key = f"freerelay:cache:{result_key}"
                            cached_json = await self._redis.get(redis_key)
                            if cached_json:
                                try:
                                    return ChatCompletionResponse.model_validate_json(cached_json)
                                except Exception:
                                    continue
                        else:
                            candidate = self._entries.get(result_key)
                            if (
                                candidate
                                and (time.time() - candidate.created_at) < candidate.ttl
                            ):
                                try:
                                    return ChatCompletionResponse.model_validate_json(
                                        candidate.response_json
                                    )
                                except Exception:
                                    continue
                except Exception:
                    pass

        return None

    async def store(
        self,
        request: ChatCompletionRequest,
        response: ChatCompletionResponse,
    ) -> None:
        """Store a response in the cache."""
        if not self.enabled:
            return

        canonical = self._canonicalize(request)
        key = self._compute_key(canonical)
        response_json = response.model_dump_json(exclude_none=True)

        if self._redis:
            redis_key = f"freerelay:cache:{key}"
            await self._redis.setex(redis_key, self.ttl, response_json)
        else:
            minhash = self._text_to_minhash(canonical)
            entry = CacheEntry(
                key=key,
                minhash=minhash,
                response_json=response_json,
                ttl=self.ttl,
            )
            self._entries[key] = entry
            
            if self._lsh is not None and minhash is not None:
                try:
                    self._lsh.insert(key, minhash) # type: ignore
                except ValueError:
                    pass  # Key already exists

        # For semantic matching, we still need to maintain the local LSH index
        # if Redis is used but we want semantic search. 
        # In a real cluster, we'd need a more robust approach.
        # But for now, if Redis is enabled, we still use the local LSH index for lookups.
        # So we should insert into LSH even if using Redis for storage.
        if self._redis and self._lsh is not None:
            minhash = self._text_to_minhash(canonical)
            if minhash is not None:
                try:
                    self._lsh.insert(key, minhash) # type: ignore
                except ValueError:
                    pass

        # Evict old entries
        self._evict_expired()

    def _evict_expired(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, v in self._entries.items() if (now - v.created_at) >= v.ttl]
        for k in expired:
            del self._entries[k]
            if self._lsh is not None:
                with contextlib.suppress(KeyError):
                    self._lsh.remove(k)

    def flush(self) -> None:
        """Clear the entire cache."""
        self._entries.clear()
        if self._lsh is not None:
            with contextlib.suppress(Exception):
                self._init_lsh()

    def stats(self) -> dict[str, object]:
        """Cache statistics."""
        return {
            "enabled": self.enabled,
            "entries": len(self._entries),
            "similarity_threshold": self.similarity_threshold,
            "ttl": self.ttl,
            "lsh_available": self._lsh is not None,
        }
