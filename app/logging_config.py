from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_level: str = "INFO", log_file: str = "./logs/app.log") -> None:
    """Configure app + uvicorn logging for console and file output."""
    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload.
    if root.handlers:
        root.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root.addHandler(console)
    root.addHandler(file_handler)

    # Keep uvicorn logs consistent with app logger level/handlers.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.setLevel(level)

