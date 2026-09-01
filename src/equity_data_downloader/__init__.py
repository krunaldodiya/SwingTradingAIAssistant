"""Configured-root structured daily OHLCV downloading and persistence."""

from .core import (
    DownloadError,
    DownloadReceipt,
    PersistenceError,
    default_storage_root,
    download_daily_ohlcv,
)

__all__ = [
    "DownloadError",
    "DownloadReceipt",
    "PersistenceError",
    "default_storage_root",
    "download_daily_ohlcv",
]
