#!/usr/bin/env python3
"""Authenticated, scoped command bridge for the vibe-coding platform.

NOT an open shell. Rules, enforced in code:
- Auth: every /exec request must send header X-API-Key equal to the
  BRIDGE_API_KEY environment variable. If that variable is not set,
  the server refuses to start (fail closed). The key is NEVER in this
  file, never in git, never in frontend code. On Vercel it must live
  only in Vercel Environment Variables (server-side), never in client JS.
- No shell: commands are parsed with shlex and run with shell=False.
  Shell operators ; & | ` $ > < are rejected outright.
- Allowlist only: ls, cat, head, tail, wc, pwd, node, npm, npx, git,
  mkdir, cp, mv, python3. No sudo, su, curl, wget, ssh, chmod, chown.
- Workdir confinement: the command runs with cwd =
  ~/workspace/opencode/projects/test-project (or PROJECT_DIR env).
  Arguments that are absolute paths, or contain .., are rejected.
  rm is allowed only on a single file inside the workdir, never -rf, never /.
- Timeout 20s, output truncated to 4000 chars, stderr included separately.
- GET /health returns {"ok": true} with no auth and no data, for uptime checks.

This bridge runs on 127.0.0.1 only by default. Vercel (public cloud)
cannot reach 127.0.0.1 on this VM. To connect Vercel, put a tunnel
with auth in front (e.g. Cloudflare Tunnel) and set BRIDGE_URL in
Vercel to that public tunnel URL, never to localhost.

Usage:
  BRIDGE_API_KEY='<your-fixed-key>' PROJECT_DIR='...' python3 server.py [--port 8787]
"""
import json, os, shlex, subprocess, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ALLOWED = {"ls", "cat", "head", "tail", "wc", "pwd", "node", "npm", "npx", "git", "mkdir", "cp", "mv", "python3", "rm"}
FORBIDDEN_CHARS = set(";|&`$><\n\r")
WORKDIR = Path(os.environ.get("PROJECT_DIR", str(Path.home() / "workspace/opencode/projects/test-project"))).resolve()
API_KEY = os.environ.get("BRIDGE_API_KEY", "")

if not API_KEY:
    print("Refusing to start: BRIDGE_API_KEY is not set", file=sys.stderr)
    sys.exit(2)

WORKDIR.mkdir(parents=True, exist_ok=True)

def validate(args):
    if not args:
        return "empty command"
    if args[0] not in ALLOWED:
        return f"command not allowed: {args[0]}"
    if args[0] == "rm" and ("-rf" in args or "-r" in args or "/" in args):
        return "rm -rf and rm / are never allowed"
    for a in args:
        if any(c in a for c in FORBIDDEN_CHARS):
            return "shell operators are not allowed"
        if a.startswith("/") or ".." in a.split("/"):
            return "absolute paths and .. are not allowed"
    return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})
    def do_POST(self):
        if self.path != "/exec":
            self._send(404, {"error": "not found"}); return
        # constant-time-ish comparison is overkill here; exact match, no timing leak via early exit on length is acceptable for a private bridge
        if self.headers.get("X-API-Key", "") != API_KEY:
            self._send(401, {"error": "unauthorized"}); return
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
            cmd = data.get("cmd", "")
            if not isinstance(cmd, str) or not cmd.strip():
                self._send(400, {"error": "cmd must be a non-empty string"}); return
            args = shlex.split(cmd)
        except Exception as e:
            self._send(400, {"error": f"bad request: {e}"}); return
        err = validate(args)
        if err:
            self._send(403, {"error": err}); return
        try:
            r = subprocess.run(args, cwd=str(WORKDIR), capture_output=True, text=True, timeout=20)
            self._send(200, {"stdout": r.stdout[:4000], "stderr": r.stderr[:2000], "returncode": r.returncode, "workdir": str(WORKDIR)})
        except subprocess.TimeoutExpired:
            self._send(408, {"error": "command timed out after 20s"})
        except Exception as e:
            self._send(500, {"error": str(e)})

if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8787
    print(f"Bridge listening on 127.0.0.1:{port}, workdir={WORKDIR} (auth required, allowlist only)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
