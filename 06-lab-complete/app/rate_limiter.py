"""
Rate limiting (tiêu chí 7) — Sliding Window 60 giây lưu trên Redis Sorted Set.

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây
  • Vượt giới hạn → HTTP 429 kèm header Retry-After
  • State nằm trong Redis nên dùng chung giữa các worker và vẫn giữ nguyên sau khi restart
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def _rate_key(api_key: str) -> str:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"ratelimit:{key_hash}"


def check_rate_limit(key: str) -> None:
    """Kiểm tra và ghi nhận request theo thuật toán sliding window trong Redis."""
    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = _rate_key(key)
    limit = settings.rate_limit_per_minute

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except (redis.RedisError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Rate limiter store unavailable",
        ) from exc
