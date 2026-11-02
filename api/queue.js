// Reverse-polling queue: Vercel does NOT call the sandbox (it cannot reach it).
// Instead, Vercel stores the job in Upstash Redis, the sandbox poller pulls it,
// executes it, and writes the result back. The browser polls /api/job for the result.
// Env vars (Vercel, server-side only, never in frontend code):
//   UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN  (from Vercel Storage -> KV)
//   JOB_TOKEN  (optional but recommended: a password the user types in the UI;
//               without it, anyone who opens the site could queue commands)
async function redis(path, method = "GET") {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return null;
  const r = await fetch(`${url.replace(/\/$/, "")}${path}`, {
    method, headers: { Authorization: `Bearer ${token}` },
  });
  return r.json().catch(() => ({}));
}
export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "method not allowed" });
  const { cmd, token } = req.body || {};
  if (typeof cmd !== "string" || !cmd.trim() || cmd.length > 500)
    return res.status(400).json({ error: "cmd required, max 500 chars" });
  const jobToken = process.env.JOB_TOKEN;
  if (jobToken && token !== jobToken) return res.status(401).json({ error: "bad token" });
  if (!process.env.UPSTASH_REDIS_REST_URL || !process.env.UPSTASH_REDIS_REST_TOKEN)
    return res.status(503).json({ error: "queue not configured yet: create a KV (Upstash Redis) in Vercel Storage, connect it to this project, and redeploy." });
  const id = crypto.randomUUID();
  const job = { id, cmd: cmd.trim(), status: "pending", createdAt: Date.now() };
  await redis(`/rpush/sandboxmuse:queue/${encodeURIComponent(JSON.stringify(job))}`, "POST");
  await redis(`/set/sandboxmuse:job:${id}/${encodeURIComponent(JSON.stringify(job))}`, "POST");
  await redis(`/expire/sandboxmuse:job:${id}/3600`, "POST");
  return res.status(200).json({ jobId: id });
}
