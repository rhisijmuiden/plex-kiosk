#!/usr/bin/env python3
"""Stand-in for a NO-Flix server's download endpoints, used by CI to test
`marquee-ctl noflix install`. Serves a tiny NO-Flix-shaped package."""
import hashlib
import io
import json
import tarfile
from http.server import BaseHTTPRequestHandler, HTTPServer


def package() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def add(name, data, mode=0o644):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))
        add("NO-Flix/noflix", b"#!/bin/sh\necho fake noflix\n", 0o755)
        add("NO-Flix/data/flutter_assets/version.json", json.dumps({"app_name": "noflix", "version": "9.9.9"}).encode())
    return buf.getvalue()


PKG = package()
SUM = hashlib.sha256(PKG).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/clients/download/linux/sha256"):
            body = f"{SUM}  NO-Flix-App-9.9.9-linux.tar.gz\n".encode()
        elif self.path.startswith("/api/clients/download/linux"):
            body = PKG
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
