"""Tiny no-cache static server for local web-editor development.

`python -m http.server` sends no Cache-Control, so browsers heuristically cache app.js/render.js
and you keep seeing stale code after an edit. This serves the same `web/` directory but with
`Cache-Control: no-store`, so every reload fetches fresh. Dev-only; the deployed site is static
files on GitHub Pages.

    python web/devserver.py [port]
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    web = str(Path(__file__).resolve().parent)
    handler = partial(NoCacheHandler, directory=web)
    print(f"serving {web} (no-cache) on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    main()
