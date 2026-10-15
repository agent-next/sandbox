#!/usr/bin/env python3
"""Static server for the web-scrape-dataset fixture, with a request log.

Serves a fixture directory built by fixture.py and records every request
(path, method, user-agent, timestamp) to a JSON-lines file, so the judge can
check what the artifact actually *asked* for -- not merely what it wrote.

Log format, one JSON object per line:
    {"path": "/internal/index.html", "method": "GET",
     "ua": "Mozilla/5.0 ...", "n": 7}

The count `n` is the number of times that (path, ua) pair was requested. The
robots.txt gate reads this log: any path under the disallowed prefix is a
failure, no matter what the scraper wrote in its CSV.

?page=N on /index.html is redirected to the pre-rendered pageN.html, so a
scraper that follows the pager links finds all five pages.

Usage:
    python3 serve.py --root <fixture_dir> --port 0 --log <path>
    # prints the chosen port as the last line of stdout
"""
import argparse
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


class LoggingHandler(SimpleHTTPRequestHandler):
    """Serves a fixture dir and records every request to a JSON-lines log."""

    log_lock = threading.Lock()
    log_path = None
    request_log = []

    def _record(self):
        ua = self.headers.get('User-Agent', '')
        path = urlparse(self.path).path
        with LoggingHandler.log_lock:
            LoggingHandler.request_log.append(
                {'path': path, 'method': self.command, 'ua': ua})
            self._flush()

    def _flush(self):
        counts = {}
        for r in LoggingHandler.request_log:
            k = (r['path'], r['ua'])
            counts[k] = counts.get(k, 0) + 1
        with open(LoggingHandler.log_path, 'w') as f:
            for (path, ua), n in sorted(counts.items()):
                f.write(json.dumps({'path': path, 'ua': ua, 'n': n}) + '\n')

    def log_message(self, fmt, *args):
        # the base handler is chatty on stderr; the judge owns that stream
        sys.stderr.write('[serve] %s\n' % (fmt % args))

    def do_GET(self):
        self._record()
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/index.html'):
            q = parse_qs(parsed.query)
            if q.get('page', ['1'])[0] != '1':
                # ?page=N serves the pre-rendered pageN.html
                self.path = '/page%s.html' % q['page'][0]
        if self.path.endswith('/'):
            self.path += 'index.html'
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_HEAD(self):
        self._record()
        return SimpleHTTPRequestHandler.do_HEAD(self)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--log', required=True)
    ap.add_argument('--bind', default='127.0.0.1')
    args = ap.parse_args()

    LoggingHandler.log_path = os.path.abspath(args.log)
    # start from an empty log so a stale file can never satisfy the robots gate
    with open(LoggingHandler.log_path, 'w') as f:
        f.write('')

    os.chdir(args.root)
    srv = Server((args.bind, args.port), LoggingHandler)
    port = srv.server_address[1]
    print(port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
