"""FinVault HTTP server: static UI, authenticated JSON API and startup logic."""
from __future__ import annotations

import hmac
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import api
from .api_base import ApiError, Ctx, Raw
from .config import (
    APP_DIR, APP_NAME, APP_VERSION, DB_PATH, DEFAULT_HOST, DEFAULT_PORT,
    IDLE_CHECK_SECONDS, IDLE_QUIT_DEFAULT_MINUTES, LOG_PATH, WEB_DIR, ensure_dirs,
)
from .db import database, get_setting, init_db, integrity_check, maybe_auto_backup

log = logging.getLogger("finvault")


def setup_logging() -> None:
    ensure_dirs()
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    except OSError:
        pass
    if sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        log.addHandler(stream)


class FinVaultHandler(BaseHTTPRequestHandler):
    server_version = f"FinVault/{APP_VERSION}"
    protocol_version = "HTTP/1.1"
    api_key = ""
    host = DEFAULT_HOST
    port = DEFAULT_PORT

    # ------------------------------------------------------------------ utils
    def log_message(self, fmt: str, *args: Any) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Max-Age", "86400")

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'",
        )

    def _send(self, status: int, body: bytes, content_type: str,
              extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        if self.path.startswith("/api/"):
            self._cors_headers()
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str, field: str | None = None) -> None:
        payload: dict[str, Any] = {"ok": False, "error": {"message": message}}
        if field:
            payload["error"]["field"] = field
        self._json(status, payload)

    # ------------------------------------------------------------------ verbs
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._security_headers()
        self._cors_headers()
        self.end_headers()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    # ------------------------------------------------------------------ routing
    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 25 * 1024 * 1024:
            raise ApiError("Request body is too large", 413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError("Request body must be valid JSON")
        if parsed is None:
            return {}
        if not isinstance(parsed, dict):
            raise ApiError("Request body must be a JSON object")
        return parsed

    def _authenticated(self, query: dict[str, str]) -> bool:
        supplied = self.headers.get("X-API-Key") or ""
        authorization = self.headers.get("Authorization") or ""
        if authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        if not supplied:
            supplied = query.get("api_key", "")
        return bool(supplied) and hmac.compare_digest(supplied, self.api_key)

    def _handle(self, method: str) -> None:
        touch_activity()
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()}

        if path.startswith("/api/"):
            self._handle_api(method, path, query)
            return
        if method in {"GET", "HEAD"}:
            self._serve_static(path)
            return
        self._error(405, "Method not allowed")

    def _handle_api(self, method: str, path: str, query: dict[str, str]) -> None:
        if not self._authenticated(query):
            if path != "/api/health":
                self._error(401, "Missing or invalid API key. Send X-API-Key or Authorization: Bearer <key>.")
                return
        fn, params = api.resolve(method, path)
        if not fn:
            self._error(404, f"No API route for {method} {path}")
            return
        try:
            body = self._read_body() if method in {"POST", "PUT", "PATCH"} else {}
            with database(DB_PATH) as conn:
                ctx = Ctx(conn=conn, query=query, body=body, params=params or {},
                          headers={k.lower(): v for k, v in self.headers.items()},
                          method=method, path=path, server=self.server)
                result = fn(ctx)
            if isinstance(result, Raw):
                self._send(result.status, result.body, result.content_type, result.headers)
                return
            self._json(200, {"ok": True, "data": result})
        except ApiError as error:
            self._error(error.status, error.message, error.field)
        except Exception as error:  # noqa: BLE001 - return a clean 500 and log the traceback
            log.exception("API error on %s %s", method, path)
            self._error(500, f"Internal error: {error}")

    def _serve_static(self, path: str) -> None:
        if path in {"/", "/index.html", "/app"}:
            self._serve_index()
            return
        relative = path.lstrip("/")
        try:
            target = (WEB_DIR / relative).resolve()
            if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
                self._error(404, "File not found")
                return
            content_type = {
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".ico": "image/x-icon",
                ".json": "application/json",
                ".woff2": "font/woff2",
            }.get(target.suffix.lower(), "application/octet-stream")
            data = target.read_bytes()
            self._send(200, data, content_type, {"Cache-Control": "no-cache"})
        except OSError:
            self._error(404, "File not found")

    def _serve_index(self) -> None:
        index_path = WEB_DIR / "index.html"
        if not index_path.exists():
            self._error(500, f"UI files are missing. Expected: {index_path}")
            return
        with database(DB_PATH) as conn:
            key = get_setting(conn, "api_key", "")
        html = index_path.read_text(encoding="utf-8")
        config = json.dumps({"apiKey": key, "base": "/api/v1", "version": APP_VERSION})
        html = html.replace("__FINVAULT_CONFIG__", config)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", {"Cache-Control": "no-store"})


class FinVaultServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ---------------------------------------------------------------------------
# Instance lock + startup
# ---------------------------------------------------------------------------

_lock_file = None


def acquire_instance_lock() -> bool:
    global _lock_file
    lock_path = APP_DIR / "finvault.lock"
    try:
        _lock_file = open(lock_path, "a+")
        if os.name == "nt":
            import msvcrt
            _lock_file.seek(0)
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (OSError, ImportError):
        return False


def release_instance_lock() -> None:
    global _lock_file
    if not _lock_file:
        return
    try:
        if os.name == "nt":
            import msvcrt
            _lock_file.seek(0)
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        _lock_file.close()
    except OSError:
        pass
    _lock_file = None
    try:
        (APP_DIR / "finvault.lock").unlink(missing_ok=True)
    except OSError:
        pass


def _write_port(port: int) -> None:
    try:
        (APP_DIR / "finvault.port").write_text(str(port), encoding="utf-8")
    except OSError:
        pass


def _read_port() -> int:
    try:
        return int((APP_DIR / "finvault.port").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return DEFAULT_PORT


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        log.exception("Could not open the browser")


def _existing_instance(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("app") == "finvault"
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Idle auto-quit
# ---------------------------------------------------------------------------

_activity_lock = threading.Lock()
_last_activity = time.monotonic()


def touch_activity() -> None:
    """Record that the UI or an API client is still using the app."""
    global _last_activity
    with _activity_lock:
        _last_activity = time.monotonic()


def seconds_since_activity() -> float:
    with _activity_lock:
        return time.monotonic() - _last_activity


def idle_quit_minutes() -> int:
    """Read the current setting; 0 means the feature is off."""
    try:
        with database(DB_PATH) as conn:
            raw = get_setting(conn, "idle_quit_minutes", str(IDLE_QUIT_DEFAULT_MINUTES))
    except Exception:  # noqa: BLE001 - a locked/syncing database must not crash the monitor
        return IDLE_QUIT_DEFAULT_MINUTES
    try:
        return max(0, min(int(str(raw).strip()), 24 * 60))
    except (TypeError, ValueError):
        return 0


class IdleMonitor:
    """Shuts the server down after a period without UI heartbeats or API calls."""

    def __init__(self, server: FinVaultServer) -> None:
        self._server = server
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="finvault-idle", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(2.0)

    def _run(self) -> None:
        while not self._stop.wait(IDLE_CHECK_SECONDS):
            minutes = idle_quit_minutes()
            if minutes <= 0:
                continue
            idle = seconds_since_activity()
            if idle < minutes * 60:
                continue
            log.info(
                "No activity for %.1f minutes (idle limit %s); shutting down.",
                idle / 60, minutes,
            )
            try:
                self._server.shutdown()
            except Exception:  # noqa: BLE001
                log.exception("Idle shutdown failed")
            return


def _start_tray(url: str, server: FinVaultServer, enabled: bool):
    if not enabled or os.name != "nt" or os.environ.get("FINVAULT_NO_TRAY"):
        return None
    from . import tray

    return tray.start(
        url=url,
        on_open=lambda: _open_browser(url),
        on_quit=server.shutdown,
    )


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
        open_browser: bool = True, tray: bool = True) -> int:
    setup_logging()
    ensure_dirs()

    if not acquire_instance_lock():
        existing_port = _read_port()
        if _existing_instance(existing_port):
            url = f"http://127.0.0.1:{existing_port}/"
            log.info("FinVault is already running; opening %s", url)
            if open_browser:
                _open_browser(url)
            return 0
        log.warning("Could not acquire the instance lock, but no running instance was found.")
        return 1

    exit_code = 0
    server = None
    try:
        init_db(DB_PATH)
        check = integrity_check(DB_PATH)
        if check != "ok":
            log.error("Database integrity check failed: %s", check)
        with database(DB_PATH) as conn:
            backup = maybe_auto_backup(conn, DB_PATH)
            if backup:
                log.info("Automatic backup created: %s", backup)

        actual_host = host
        actual_port = port
        for candidate in range(port, port + 25):
            try:
                server = FinVaultServer((actual_host, candidate), FinVaultHandler)
                actual_port = candidate
                break
            except OSError as error:
                if candidate == port:
                    log.warning("Port %s unavailable: %s", candidate, error)
                continue
        if not server:
            log.error("No free port found in range %s-%s", port, port + 24)
            return 1

        with database(DB_PATH) as conn:
            FinVaultHandler.api_key = get_setting(conn, "api_key", "")
        FinVaultHandler.host = actual_host
        FinVaultHandler.port = actual_port
        _write_port(actual_port)
        display_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
        url = f"http://{display_host}:{actual_port}/"
        log.info("%s %s running at %s", APP_NAME, APP_VERSION, url)
        log.info("Database: %s", DB_PATH)
        if open_browser:
            threading.Timer(0.5, _open_browser, args=(url,)).start()
        touch_activity()
        idle_monitor = IdleMonitor(server)
        idle_monitor.start()
        tray_icon = _start_tray(url, server, enabled=tray)
        try:
            server.serve_forever(poll_interval=0.4)
        except KeyboardInterrupt:
            pass
        finally:
            idle_monitor.stop()
            if tray_icon:
                tray_icon.stop()
            server.server_close()
    except Exception:
        log.exception("Fatal startup error")
        exit_code = 1
    finally:
        try:
            (APP_DIR / "finvault.port").unlink(missing_ok=True)
        except OSError:
            pass
        release_instance_lock()
        log.info("FinVault stopped")
    return exit_code


def stop(port: int | None = None) -> int:
    """Ask a running instance to shut down."""
    setup_logging()
    if not DB_PATH.exists():
        return 0
    with database(DB_PATH) as conn:
        key = get_setting(conn, "api_key", "")
    target_port = port or _read_port()
    request = urllib.request.Request(
        f"http://127.0.0.1:{target_port}/api/v1/admin/shutdown",
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json", "X-API-Key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
        return 0
    except Exception as error:  # noqa: BLE001
        log.error("Could not stop FinVault: %s", error)
        return 1
