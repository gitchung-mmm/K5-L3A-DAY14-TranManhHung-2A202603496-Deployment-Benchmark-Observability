"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Lưu ý:
  • Không ping Redis lúc import để container/app vẫn khởi động được khi Redis chưa sẵn sàng.
  • redis_healthy() dùng cho GET /ready: trả True nếu Redis phản hồi PING, ngược lại False.
"""
import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1.5,
    socket_timeout=1.5,
)


def redis_healthy() -> bool:
    """Kiểm tra kết nối tới Redis cho readiness probe."""
    try:
        return bool(r.ping())
    except (redis.RedisError, OSError):
        return False


def close_redis() -> None:
    """Đóng connection pool khi app tắt (graceful shutdown)."""
    try:
        r.close()
    except Exception:
        pass
