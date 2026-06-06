"""
TeleCRM Backend — apps/core/logging.py

JSON log formatter for production environments.
Outputs structured JSON logs compatible with:
- AWS CloudWatch
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Datadog
- Grafana Loki
"""
import json
import logging
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """
    Format log records as JSON for log aggregation pipelines.

    Output format:
    {
      "timestamp": "2024-01-15T10:30:00.123Z",
      "level": "ERROR",
      "logger": "apps.authentication.views",
      "message": "Login failed for agent@acme.com",
      "tenant": "acme_realty",
      "request_id": "abc123",
      "exception": "...",   ← only on exceptions
      "extra": { ... }      ← extra fields passed to logger.error(..., extra={...})
    }
    """

    RESERVED_ATTRS = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_object["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Add stack info
        if record.stack_info:
            log_object["stack_info"] = self.formatStack(record.stack_info)

        # Add extra fields (passed via logger.info("msg", extra={"key": "val"}))
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self.RESERVED_ATTRS
        }
        if extra:
            log_object["extra"] = extra

        return json.dumps(log_object, default=str, ensure_ascii=False)
