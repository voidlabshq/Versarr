from __future__ import annotations

import logging
import sys
from typing import Any, cast
from uuid import uuid4

import structlog

_RUN_ID = str(uuid4())


def configure_logging(level: str) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level.upper(),
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            structlog.stdlib.add_log_level,
            structlog.processors.EventRenamer("event"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(component: str, **fields: Any) -> structlog.stdlib.BoundLogger:
    return cast(
        structlog.stdlib.BoundLogger,
        structlog.get_logger("versarr").bind(
            service="versarr",
            run_id=_RUN_ID,
            component=component,
            **fields,
        ),
    )
