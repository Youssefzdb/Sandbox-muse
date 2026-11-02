// Poll a queued job: GET /api/job?id=<jobId>
// Returns { job: {status, cmd, returncode, stdout, stderr}, log: [lines...] }
async function redis(path, method = "GET") {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return null;
  const r = await fetch(`${url.replace(/\/$/, "")}${path}`, {
    method, headers: { Authorization: `Bearer ${token}` },
  });
  return r.json().catch(() => ({}));
}
export default async function handler(req, res) {
  const id = req.query.id;
  if (!id) return res.status(400).json({ error: "id required" });
  if (!(process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL) || !(process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN))
    return res.status(503).json({ error: "queue not configured yet" });
  const jobData = await redis(`/get/sandboxmuse:job:${encodeURIComponent(id)}`);
  if (!jobData || !jobData.result) return res.status(404).json({ error: "job not found (expired?)" });
  const logData = await redis(`/lrange/sandboxmuse:job:${encodeURIComponent(id)}:log/0/-1`);
  let job;
  try { job = JSON.parse(jobData.result); } catch { job = { status: "unknown" }; }
  return res.status(200).json({ job, log: logData?.result || [] });
}
