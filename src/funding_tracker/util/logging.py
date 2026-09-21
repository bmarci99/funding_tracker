from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

_console = Console()
_logger: logging.Logger | None = None


def setup_logger() -> tuple[logging.Logger, Console]:
    global _logger
    if _logger is None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(console=_console, markup=True, show_path=False)],
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)
        _logger = logging.getLogger("funding_tracker")
    return _logger, _console


def section(console: Console, title: str) -> None:
    console.rule(f"[bold]{title}[/bold]")
