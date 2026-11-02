# Sandbox-muse — Vercel side of the sandbox bridge

This repo is the **Vercel side only**. Deploy it on Vercel as a static site +
serverless function. It does NOT contain any API key.

## What is here
- `index.html` — a minimal frontend: type a command, it calls `/api/exec`, shows the output. No key in this page.
- `api/exec.js` — Vercel serverless function. It reads the key server-side and forwards the command to the bridge. This is the only place the key is used, and only from environment variables.
- `server/bridge-server.py` — reference copy of the bridge server that runs on the sandbox (NOT deployed to Vercel). Run it on the sandbox with `BRIDGE_API_KEY` set. It enforces: auth, allowlist only, workdir confinement, no shell operators, 20s timeout.
- `package.json` — `type: module`, no dependencies.

## Deploy on Vercel
1. Import this repo in Vercel (Framework: Other / no framework, root directory: this repo).
2. In Vercel → Project → Settings → Environment Variables, set **server-side only**:
   - `BRIDGE_URL` = public tunnel URL of the bridge, e.g. `https://bridge.example.com`
     - NEVER `http://localhost:8787` — Vercel (public cloud) cannot reach the sandbox's localhost.
   - `BRIDGE_API_KEY` = the same fixed API key as `BRIDGE_API_KEY` on the bridge server.
3. Deploy. Open the site, type `ls -la`, click Run. The output comes from the bridge's confined project directory.

## Security — read this before publishing
- The API key must NEVER be in frontend code, in this repo, or in a public commit. Only in Vercel Environment Variables and in the bridge server's environment.
- The bridge does NOT run arbitrary shell: it rejects shell operators, absolute paths, `..`, `sudo`, `curl`, `wget`, `ssh`, and `rm -rf`. Commands run only in one confined project directory, with an allowlist.
- If the key ever leaks, rotate it in both places (Vercel env + bridge env) and redeploy.
- The sandbox itself is not public: to connect Vercel, put a tunnel with auth in front of the bridge (e.g. Cloudflare Tunnel), do not expose the bridge port directly to the internet without the key check.
