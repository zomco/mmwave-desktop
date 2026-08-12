"""TraceCue Desktop backend package."""

from typing import Any

from .config import AppConfig

__all__ = ["AppConfig", "create_app"]
__version__ = "0.1.0"


def create_app(*args: Any, **kwargs: Any) -> Any:
    """Load the HTTP framework only when an application instance is requested."""
    from .app import create_app as factory

    return factory(*args, **kwargs)
