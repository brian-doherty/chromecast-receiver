#!/usr/bin/env python3
"""Static server for HLS with the two things Cast requires.

1. CORS headers. Cast's adaptive pipeline fetches the manifest and segments
   via XHR, which is same-origin-restricted; progressive media goes through
   the media element and needs none of this. Without these headers the device
   fetches the playlist, gets blocked parsing it, retries, and gives up with
   a bare ERROR and no segment requests at all.
2. Correct segment MIME. Debian's mime table maps .ts to Qt Linguist
   translation files (text/vnd.trolltech.linguist), which Cast rejects.
"""
import functools
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".aac": "audio/aac",
}


class Handler(SimpleHTTPRequestHandler):
    def guess_type(self, path):
        for ext, mime in TYPES.items():
            if path.endswith(ext):
                return mime
        return super().guess_type(path)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")
        # A live window rolls; never let anything cache it.
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1])
    directory = sys.argv[2]
    handler = functools.partial(Handler, directory=directory)
    HTTPServer(("0.0.0.0", port), handler).serve_forever()
