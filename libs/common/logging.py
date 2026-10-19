import json
import logging
import sys
from datetime import UTC, datetime

# Only these extras are emitted, so a stray `extra={"text": ...}` can never leak complaint text.
_CONTEXT_FIELDS = ("trace_id", "complaint_id", "incident_id", "draft_id", "topic", "offset")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            # Type only: exception messages (e.g. pydantic ValidationError) can echo input text.
            entry["error_type"] = record.exc_info[0].__name__
        return json.dumps(entry)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
