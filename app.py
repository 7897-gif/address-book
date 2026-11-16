"""Entry point: ``python app.py`` starts the address book on http://127.0.0.1:8000."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

from server import create_server

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "data" / "addressbook.db"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the address book web app.")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port to bind, 0 picks a free one (default: 8000)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the SQLite database file")
    parser.add_argument("--open", action="store_true", help="open the app in the default browser")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    httpd = create_server(args.host, args.port, args.db, BASE_DIR / "static")
    host, port = httpd.server_address[:2]
    url = f"http://{host}:{port}/"

    print("Address Book is running")
    print(f"  URL : {url}")
    print(f"  DB  : {args.db}")
    print("Press Ctrl+C to stop.")

    if args.open:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
