"""
Production AI Agent — Part 6 Final Project.

Đáp ứng đầy đủ 12 tiêu chí production-ready:
  • Config từ biến môi trường (12-Factor)
  • Health (/health) & Readiness (/ready) tách biệt
  • API Key authentication (X-API-Key → 401)
  • Rate limiting sliding window trên Redis (→ 429)
  • Cost guard trên Redis (→ 402)
  • Structured JSON logging
  • Graceful shutdown với lifespan + SIGTERM chaining
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import signal
import sys
import time
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mỗi dòng log của ứng dụng thành đúng 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "env": settings.environment,
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logger() -> logging.Logger:
    app_logger = logging.getLogger("production_agent")
    app_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _configure_logger()


def _log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"extra_fields": {"event": event, **fields}})


# Đăng ký SIGTERM để ghi log JSON, đồng thời gọi lại handler cũ của uvicorn để tắt êm
_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _on_sigterm(signum, frame) -> None:
    _log_event("sigterm_received", signal=signum)
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


if hasattr(signal, "SIGTERM"):
    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except ValueError:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _log_event("startup", port=settings.port, environment=settings.environment)
    try:
        yield
    finally:
        _log_event("graceful_shutdown", environment=settings.environment)
        close_redis()


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        _log_event(
            "unhandled_error",
            level=logging.ERROR,
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
            ms=elapsed_ms,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _log_event(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        ms=elapsed_ms,
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default="anonymous", max_length=128)


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn sống, không phụ thuộc Redis."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi Redis sẵn sàng, 503 khi mất kết nối Redis."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis not ready")
    return {"status": "ready", "redis": "connected"}


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = _estimate_tokens(body.question)
    output_tokens = _estimate_tokens(answer)
    cost_usd = record_cost(input_tokens, output_tokens)

    _log_event(
        "ask_completed",
        user_id=body.user_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 6),
    )
    return {
        "user_id": body.user_id,
        "question": body.question,
        "answer": answer,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6),
        },
    }
