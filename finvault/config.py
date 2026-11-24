"""Paths, constants and small helpers for FinVault."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "FinVault"
APP_VERSION = "1.0.0"
APP_TAGLINE = "Your personal finance command center"

FROZEN = getattr(sys, "frozen", False)

# When frozen, everything lives beside FinVault.exe so the folder is portable.
# When running from source, everything lives in the project root.
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent

RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
WEB_DIR = (RESOURCE_DIR / "web") if FROZEN else (APP_DIR / "web")

DB_PATH = Path(os.environ.get("FINVAULT_DB", APP_DIR / "FinVault.db"))
BACKUP_DIR = APP_DIR / "backups"
EXPORT_DIR = APP_DIR / "exports"
LOG_PATH = APP_DIR / "finvault.log"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

# Quit the local server after this many minutes with no browser heartbeat or API call.
# 0 disables the automatic shutdown. Users can change it in Settings.
IDLE_QUIT_DEFAULT_MINUTES = 30
IDLE_CHECK_SECONDS = 15

BASE_CURRENCY = "LKR"

CURRENCY_SYMBOLS = {
    "LKR": "Rs",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "AUD": "A$",
    "CAD": "C$",
    "AED": "AED ",
    "SGD": "S$",
    "JPY": "¥",
    "CNY": "CN¥",
}


def ensure_dirs() -> None:
    for directory in (APP_DIR, BACKUP_DIR, EXPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def resource_path(*parts: str) -> Path:
    return RESOURCE_DIR.joinpath(*parts)
