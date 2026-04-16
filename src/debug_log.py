"""Debug logging — two rotating log files under ~/.clueme/logs/.

verbose.log  — Python root logger at DEBUG (all libraries included).
app.log      — Structured app events: AI payloads/responses, transcript
               segments, recording lifecycle, and tee'd stdout/stderr.

All public functions are safe no-ops when logging is disabled.
"""

import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".clueme" / "logs"

_enabled = False
_verbose_handler: RotatingFileHandler | None = None
_app_logger: logging.Logger | None = None
_app_handler: RotatingFileHandler | None = None
_original_stdout = None
_original_stderr = None


class _Tee:
    """Wraps a stream so writes go to both the original stream and a logger."""

    def __init__(self, original, logger: logging.Logger, level: int = logging.INFO):
        self._original = original
        self._logger = logger
        self._level = level

    def write(self, msg):
        if self._original is not None:
            self._original.write(msg)
        if msg and msg.strip():
            self._logger.log(self._level, msg.rstrip())

    def flush(self):
        if self._original is not None:
            self._original.flush()

    # Forward any other attribute lookups (encoding, fileno, etc.)
    def __getattr__(self, name):
        return getattr(self._original, name)


def is_enabled() -> bool:
    return _enabled


def get_log_dir() -> Path:
    return LOG_DIR


def enable() -> None:
    """Activate both log files and tee stdout/stderr."""
    global _enabled, _verbose_handler, _app_logger, _app_handler
    global _original_stdout, _original_stderr

    if _enabled:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ── verbose.log — root logger at DEBUG ────────────────────────
    _verbose_handler = RotatingFileHandler(
        LOG_DIR / "verbose.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    _verbose_handler.setLevel(logging.DEBUG)
    _verbose_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(_verbose_handler)

    # Un-suppress library loggers so they flow to verbose.log
    for name in ("google.genai", "httpx", "httpcore", "faster_whisper"):
        logging.getLogger(name).setLevel(logging.DEBUG)

    # ── app.log — curated app events ──────────────────────────────
    _app_logger = logging.getLogger("clueme.app")
    _app_logger.setLevel(logging.DEBUG)
    _app_logger.propagate = True  # also goes into verbose.log

    _app_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    _app_handler.setLevel(logging.DEBUG)
    _app_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    _app_logger.addHandler(_app_handler)

    # ── Tee stdout / stderr into app.log ──────────────────────────
    _original_stdout = sys.stdout
    _original_stderr = sys.stderr
    sys.stdout = _Tee(_original_stdout, _app_logger, logging.INFO)
    sys.stderr = _Tee(_original_stderr, _app_logger, logging.ERROR)

    _enabled = True
    _app_logger.info("[DEBUG_LOG] Debug logging enabled — writing to %s", LOG_DIR)


def disable() -> None:
    """Tear down handlers and restore stdout/stderr."""
    global _enabled, _verbose_handler, _app_logger, _app_handler
    global _original_stdout, _original_stderr

    if not _enabled:
        return

    # Restore streams
    if _original_stdout is not None:
        sys.stdout = _original_stdout
    if _original_stderr is not None:
        sys.stderr = _original_stderr
    _original_stdout = None
    _original_stderr = None

    # Remove verbose handler
    if _verbose_handler:
        logging.getLogger().removeHandler(_verbose_handler)
        _verbose_handler.close()
        _verbose_handler = None

    # Remove app handler
    if _app_handler and _app_logger:
        _app_logger.removeHandler(_app_handler)
        _app_handler.close()
        _app_handler = None

    # Re-suppress noisy library loggers
    for name in ("google.genai", "httpx", "httpcore", "faster_whisper"):
        logging.getLogger(name).setLevel(logging.ERROR)

    _app_logger = None
    _enabled = False


# ── Convenience helpers (no-ops when disabled) ────────────────────

def log_event(tag: str, message: str) -> None:
    """Write a tagged event to app.log.  e.g. log_event("RECORDING", "started")"""
    if not _enabled or not _app_logger:
        return
    _app_logger.info("[%s] %s", tag, message)


def log_ai_payload(contents, model: str) -> None:
    """Serialize the assembled Content list and write to app.log."""
    if not _enabled or not _app_logger:
        return
    try:
        parts = []
        for c in contents:
            role = c.role
            texts = [p.text for p in c.parts if p.text]
            parts.append({"role": role, "parts": texts})
        blob = json.dumps({"model": model, "messages": parts}, indent=2, ensure_ascii=False)
        _app_logger.info("[AI_PAYLOAD]\n%s", blob)
    except Exception as exc:
        _app_logger.warning("[AI_PAYLOAD] Failed to serialize: %s", exc)


def log_ai_response(text: str, model: str) -> None:
    """Write the full model response to app.log."""
    if not _enabled or not _app_logger:
        return
    _app_logger.info("[AI_RESPONSE] model=%s\n%s", model, text)
