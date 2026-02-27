# backend/logging_config.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

def get_logging_config():
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[{asctime}] {levelname} {name} - {message}",
                "style": "{",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG" if DEBUG else LOG_LEVEL,
                "formatter": "default",
            },
            "file_app": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "filename": str(LOGS_DIR / "app.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 10,
                "formatter": "default",
            },
            "file_error": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "filename": str(LOGS_DIR / "error.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 10,
                "formatter": "default",
            },
            "file_llm": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "filename": str(LOGS_DIR / "llm.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 10,
                "formatter": "default",
            },
        },
        "root": {
            "handlers": ["console", "file_app", "file_error"],
            "level": LOG_LEVEL,
        },
        "loggers": {
            # request lifecycle logs
            "monitoring": {
                "handlers": ["console", "file_app", "file_error"],
                "level": "INFO",
                "propagate": False,
            },
            # LLM logs (separate file)
            "llm": {
                "handlers": ["console", "file_llm", "file_error"],
                "level": "INFO",
                "propagate": False,
            },
            # optional: silence duplicate Django exception lines
            "django.request": {
                "handlers": ["console", "file_error"],
                "level": "CRITICAL",
                "propagate": False,
            },
        },
    }