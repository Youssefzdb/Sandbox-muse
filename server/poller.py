#!/usr/bin/env python3
"""Reverse-polling worker for the Vercel queue (24/24 listener, outbound only).

Why this exists: Vercel cannot reach this VM (no public IP, localhost is
not reachable). So the worker makes OUTBOUND calls to Upstash Redis:
  - LPOP sandboxmuse:queue  -> take the next job {id, cmd}
  - execute it (same allowlist + workdir confinement as server.py)
  - stream output line by line: RPUSH sandboxmuse:job:<id>:log <line>
  - finish: SET sandboxmuse:job:<id> {status: done, returncode, ...}
The browser polls Vercel /api/job every second and shows the log live.

Env (never in git, never in frontend):
  UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN, PROJECT_DIR (optional)
Run:  nohup python3 poller.py > poller.log 2>&1 &
Stop:  pkill -f poller.py
Note: this VM is ephemeral - a restart stops the worker, it must be restarted.
"""
import json, os, shlex, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

URL = (os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL", "")).rstrip("/")
TOKEN = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
WORKDIR = Path(os.environ.get("PROJECT_DIR", str(Path.home() / "workspace/opencode/projects/test-project"))).resolve()
ALLOWED = {"ls", "cat", "head", "tail", "wc", "pwd", "node", "npm", "npx", "git", "mkdir", "cp", "mv", "python3", "rm"}
FORBIDDEN = set(";|&`$><\n\r")

if not URL or not TOKEN:
    print("Refusing to start: UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN not set", file=sys.stderr); sys.exit(2)
WORKDIR.mkdir(parents=True, exist_ok=True)

def redis(path, method="GET"):
    req = urllib.request.Request(URL + path, method=method, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b"{}")

def validate(args):
    if not args: return "empty command"
    if args[0] not in ALLOWED: return f"command not allowed: {args[0]}"
    if args[0] == "rm" and ("-rf" in args or "-r" in args or "/" in args): return "rm -rf and rm / are never allowed"
    for a in args:
        if any(c in a for c in FORBIDDEN): return "shell operators are not allowed"
        if a.startswith("/") or ".." in a.split("/"): return "absolute paths and .. are not allowed"
    return None

def set_job(job_id, obj):
    redis(f"/set/sandboxmuse:job:{urllib.parse.quote(job_id)}/{urllib.parse.quote(json.dumps(obj))}", "POST")
    redis(f"/expire/sandboxmuse:job:{urllib.parse.quote(job_id)}/3600", "POST")

def push_log(job_id, line):
    redis(f"/rpush/sandboxmuse:job:{urllib.parse.quote(job_id)}:log/{urllib.parse.quote(line[:2000])}", "POST")

print(f"Poller listening, workdir={WORKDIR}", flush=True)
while True:
    try:
        data = redis("/lpop/sandboxmuse:queue")
        raw = data.get("result")
        if not raw:
            time.sleep(2); continue
        job = json.loads(raw)
        job_id, cmd = job["id"], job["cmd"]
        print(f"Job {job_id}: {cmd}", flush=True)
        set_job(job_id, {**job, "status": "running"})
        try:
            args = shlex.split(cmd)
        except Exception as e:
            set_job(job_id, {**job, "status": "error", "stderr": str(e)}); continue
        err = validate(args)
        if err:
            push_log(job_id, f"error: {err}")
            set_job(job_id, {**job, "status": "error", "stderr": err}); continue
        try:
            p = subprocess.Popen(args, cwd=str(WORKDIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            out_lines = []
            for line in p.stdout:
                line = line.rstrip("\n")
                out_lines.append(line); push_log(job_id, line)
            rc = p.wait(timeout=20)
            set_job(job_id, {**job, "status": "done", "returncode": rc, "stdout": "\n".join(out_lines)[:4000]})
        except subprocess.TimeoutExpired:
            p.kill(); push_log(job_id, "error: command timed out after 20s")
            set_job(job_id, {**job, "status": "error", "stderr": "timeout"})
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"Poll error: {e}", flush=True); time.sleep(3)
