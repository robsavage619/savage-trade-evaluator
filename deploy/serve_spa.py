"""Serve frontend/dist on localhost with SPA fallback; `tailscale serve` puts it on the tailnet.

status.json is never cached so the footer pill always shows the latest refresh.
"""

from __future__ import annotations

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "dist"


class Handler(SimpleHTTPRequestHandler):
    """Static files, unknown extensionless paths fall back to the SPA shell."""

    def send_head(self):
        """Rewrite client-side routes to index.html."""
        target = Path(self.translate_path(self.path))
        if not target.exists() and "." not in Path(self.path).name:
            self.path = "/index.html"
        return super().send_head()

    def end_headers(self) -> None:
        """Never cache the status file or the shell."""
        if self.path.split("?")[0].endswith(("status.json", "index.html")):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    """Serve on the port given as argv[1] (default 8097)."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8097
    handler = partial(Handler, directory=str(ROOT))
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    main()
