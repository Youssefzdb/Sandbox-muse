// Vercel serverless function: /api/exec
// Put this in your Vercel project as api/exec.js. It is SERVER-SIDE only.
// Env vars to set in Vercel (Settings -> Environment Variables, NOT in code, NOT in frontend):
//   BRIDGE_URL     = public tunnel URL of the bridge, e.g. https://bridge.example.com
//                    NEVER http://localhost:8787 — Vercel cannot reach this VM's localhost.
//   BRIDGE_API_KEY = the same fixed API key as BRIDGE_API_KEY on the bridge.
// Frontend code must NEVER contain the key. Frontend calls /api/exec, this
// function adds the key server-side and forwards to the bridge.

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "method not allowed" });
  const { cmd } = req.body || {};
  if (typeof cmd !== "string" || !cmd.trim()) return res.status(400).json({ error: "cmd required" });
  const bridgeUrl = process.env.BRIDGE_URL;
  const apiKey = process.env.BRIDGE_API_KEY;
  if (!bridgeUrl || !apiKey) return res.status(500).json({ error: "bridge not configured on server" });
  const r = await fetch(`${bridgeUrl.replace(/\/$/, "")}/exec`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({ cmd }),
  });
  const data = await r.json().catch(() => ({}));
  return res.status(r.status).json(data);
}
