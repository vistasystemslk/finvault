from __future__ import annotations

import argparse
import sys


def main() -> int:
    from finvault.config import APP_NAME, APP_VERSION, DEFAULT_HOST, DEFAULT_PORT
    from finvault import server

    parser = argparse.ArgumentParser(
        prog="FinVault",
        description="FinVault - portable personal finance manager",
    )
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="Bind address (default 127.0.0.1; use 0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port (default 8787)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    parser.add_argument("--stop", action="store_true", help="Stop a running FinVault instance")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args()

    if args.version:
        _print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if args.stop:
        return server.stop(args.port)
    _print(f"{APP_NAME} {APP_VERSION} - starting...")
    return server.run(host=args.host, port=args.port, open_browser=not args.no_browser)


def _print(message: str) -> None:
    try:
        if sys.stdout is not None:
            print(message, flush=True)
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
