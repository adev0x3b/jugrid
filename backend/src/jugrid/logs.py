"""Logs as one JSON object per line, for CloudWatch Logs Insights; plain text for a terminal.

fields @timestamp, status, duration_ms, path | filter status >= 500
"""

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Literal, TextIO

LogFormat = Literal["json", "text"]

# The request being served, put on every line logged while it is.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

_PLAIN_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_RESERVED = {"time", "level", "logger", "message", "error"}


def request_id_from(header: str | None) -> str:
    """The caller's id when it is short and plain (so it can join a trace), else a new one."""
    if header and _PLAIN_ID.fullmatch(header):
        return header
    return uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, object] = {}
        # Extra fields first, so they can never pass for the line's own keys.
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            line.update({k: v for k, v in fields.items() if k not in _RESERVED})
        rid = getattr(record, "request_id", None) or request_id.get()
        if rid:
            line["request_id"] = rid
        line |= {
            "time": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str, ensure_ascii=False)


def configure(fmt: LogFormat, level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """Send every logger, uvicorn's included, through one handler in the chosen format."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    # The API logs each request itself, with its id and duration.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
