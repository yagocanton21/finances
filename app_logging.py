import json
import logging
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


request_id_context: ContextVar[Optional[str]] = ContextVar(
    "request_id", default=None
)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def normalize_request_id(value: str) -> str:
    return value if REQUEST_ID_PATTERN.fullmatch(value) else uuid4().hex


class JsonFormatter(logging.Formatter):
    """Formata logs da aplicacao como JSON de uma linha para o Docker."""

    extra_fields = (
        "event",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "client_ip",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for field in self.extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # O middleware registra uma linha estruturada por requisicao.
    logging.getLogger("uvicorn.access").disabled = True


def log_internal_error(event: str) -> None:
    """Registra a excecao ativa sem expor detalhes na resposta HTTP."""
    logging.getLogger("financas.errors").exception(
        "Falha interna na operacao",
        extra={"event": event},
    )
