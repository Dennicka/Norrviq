import json
import logging
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette import status

from .config import Settings
from .db import get_schema_status
from .dependencies import get_current_lang, template_context, templates

REQUEST_ID_HEADER = "X-Request-Id"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        extra_fields = [
            "request_id",
            "path",
            "method",
            "status_code",
            "latency_ms",
            "user_id",
        ]
        for field in extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


class PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        request_id = getattr(record, "request_id", "-")
        method = getattr(record, "method", "-")
        path = getattr(record, "path", "-")
        status_code = getattr(record, "status_code", "-")
        latency_ms = getattr(record, "latency_ms", "-")
        return (
            f"[{timestamp}] {record.levelname} {record.getMessage()} "
            f"request_id={request_id} method={method} path={path} status={status_code} latency_ms={latency_ms}"
        )


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.request_count_total: dict[tuple[str, str, str], int] = {}
        self.errors_total = 0
        self.request_latency_seconds: dict[str, int] = {}
        self._buckets = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]

    def observe(self, *, method: str, path_template: str, status_code: int, latency_seconds: float) -> None:
        key = (method, path_template, str(status_code))
        with self._lock:
            self.request_count_total[key] = self.request_count_total.get(key, 0) + 1
            for bucket in self._buckets:
                label = str(bucket)
                if latency_seconds <= bucket:
                    self.request_latency_seconds[label] = self.request_latency_seconds.get(label, 0) + 1
            self.request_latency_seconds["+Inf"] = self.request_latency_seconds.get("+Inf", 0) + 1
            if status_code >= 500:
                self.errors_total += 1

    def export(self) -> dict:
        with self._lock:
            return {
                "request_count_total": [
                    {
                        "method": method,
                        "path_template": path_template,
                        "status": status,
                        "value": count,
                    }
                    for (method, path_template, status), count in sorted(self.request_count_total.items())
                ],
                "request_latency_seconds": {
                    "buckets": dict(sorted(self.request_latency_seconds.items(), key=lambda item: item[0]))
                },
                "errors_total": self.errors_total,
            }


metrics_registry = MetricsRegistry()


def configure_logging(settings: Settings) -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(PrettyFormatter())

    root_logger.handlers = [handler]


def resolve_request_id(request: Request) -> str:
    request_id = request.headers.get(REQUEST_ID_HEADER)
    if request_id:
        return request_id
    return str(uuid.uuid4())


def get_path_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return request.url.path


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


def _error_template_response(request: Request, status_code: int, title: str, message: str) -> HTMLResponse:
    lang = request.state.lang if hasattr(request.state, "lang") else "ru"
    context = template_context(request, lang)
    context.update(
        {
            "title": title,
            "message": message,
            "request_id": request.state.request_id,
            "status_code": status_code,
        }
    )
    return templates.TemplateResponse(
        f"errors/{status_code}.html",
        context,
        status_code=status_code,
        headers={REQUEST_ID_HEADER: request.state.request_id},
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    headers = dict(exc.headers or {})
    headers[REQUEST_ID_HEADER] = request_id

    if _wants_html(request) and exc.status_code in {403, 404, 500}:
        return _error_template_response(
            request,
            exc.status_code,
            "Ошибка",
            "Сообщите request_id в поддержку.",
        )

    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "request_id": request_id},
        headers=headers,
    )


async def validation_exception_handler(request: Request, _exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception, settings: Settings):
    request_id = getattr(request.state, "request_id", "unknown")
    logger = logging.getLogger("app.observability")

    if settings.allow_dev_defaults:
        logger.error(
            "Unhandled exception",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": 500,
            },
        )
        logger.error(traceback.format_exc())
    else:
        logger.error(
            "Unhandled exception",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": 500,
            },
        )

    if _wants_html(request):
        return _error_template_response(
            request,
            500,
            "Ошибка сервера",
            "Сообщите request_id в поддержку.",
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id},
    )


async def handle_readiness() -> tuple[bool, str]:
    return get_schema_status()


async def ensure_lang(request: Request) -> None:
    lang = await get_current_lang(request)
    request.state.lang = lang


def log_access(request: Request, status_code: int, latency_ms: float) -> None:
    logger = logging.getLogger("app.access")
    logger.info(
        "http_request",
        extra={
            "request_id": request.state.request_id,
            "path": get_path_template(request),
            "method": request.method,
            "status_code": status_code,
            "latency_ms": round(latency_ms, 2),
            "user_id": request.session.get("user_email") if hasattr(request, "session") else None,
        },
    )


def record_metrics(request: Request, status_code: int, latency_ms: float) -> None:
    metrics_registry.observe(
        method=request.method,
        path_template=get_path_template(request),
        status_code=status_code,
        latency_seconds=latency_ms / 1000,
    )


def now_ms() -> float:
    return time.perf_counter() * 1000
