// Local preview: serves public/ through the real middleware.js, with Supabase replaced by an in-memory stand-in.
// usage: node tools/dev-server.mjs [port]     sign in as owner@example.test / temp-pass-1234 (forced to change it)
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import crypto from 'node:crypto'; import { fileURLToPath } from 'node:url';
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public');
const people = [{ id: crypto.randomUUID(), email: 'owner@example.test', name: 'Test Owner', role: 'admin', pass: 'temp-pass-1234', must_change: true, created_at: new Date().toISOString(), last_seen: null }];
const sessions = new Map(); let fails = 0;
const who = (t) => people.find((p) => p.id === sessions.get(t));
const pub = (p) => ({ ok: true, email: p.email, name: p.name, role: p.role, must_change: p.must_change });
const RPC = {
  os_login: (a) => { const p = people.find((x) => x.email === String(a.p_email).toLowerCase().trim()); if (fails >= 8) return { ok: false, error: 'locked' };
    if (!p || p.pass !== a.p_password) { fails++; return { ok: false, error: 'invalid' }; } fails = 0; const t = crypto.randomBytes(32).toString('hex'); sessions.set(t, p.id); return { ...pub(p), token: t }; },
  os_session: (a) => { const p = who(a.p_token); if (p) p.last_seen = new Date().toISOString(); return p ? pub(p) : { ok: false }; },
  os_logout: (a) => { sessions.delete(a.p_token); return { ok: true }; },
  os_change_password: (a) => { const p = who(a.p_token); if (!p) return { ok: false, error: 'signed_out' }; if (p.pass !== a.p_old) return { ok: false, error: 'wrong_password' };
    if (String(a.p_new).length < 10) return { ok: false, error: 'too_short' }; p.pass = a.p_new; p.must_change = false; return { ok: true }; },
  os_people: (a) => { const p = who(a.p_token); if (!p) return { ok: false, error: 'signed_out' }; if (p.role !== 'admin') return { ok: false, error: 'not_admin' };
    return { ok: true, me: p.id, people: people.map((x) => ({ id: x.id, email: x.email, name: x.name, role: x.role, created_at: x.created_at, last_seen: x.last_seen, pending: x.must_change })) }; },
  os_add_person: (a) => { const p = who(a.p_token); if (!p || p.role !== 'admin') return { ok: false, error: 'not_admin' }; const e = String(a.p_email).toLowerCase().trim();
    if (people.some((x) => x.email === e)) return { ok: false, error: 'exists' }; const pw = 'abcd-efgh-jkmn-pqrs'; people.push({ id: crypto.randomUUID(), email: e, name: a.p_name, role: a.p_role, pass: pw, must_change: true, created_at: new Date().toISOString(), last_seen: null }); return { ok: true, email: e, temp_password: pw }; },
  os_reset_person: (a) => { const x = people.find((q) => q.id === a.p_id); if (!x) return { ok: false, error: 'not_found' }; x.pass = 'wxyz-2345-6789-abcd'; x.must_change = true; for (const [t, id] of sessions) if (id === x.id) sessions.delete(t); return { ok: true, email: x.email, temp_password: x.pass }; },
  os_remove_person: (a) => { const i = people.findIndex((q) => q.id === a.p_id); if (i < 0) return { ok: false, error: 'not_found' }; const [x] = people.splice(i, 1); for (const [t, id] of sessions) if (id === x.id) sessions.delete(t); return { ok: true, email: x.email }; },
};
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, init) => { const m = String(url).match(/supabase\.co\/rest\/v1\/rpc\/(\w+)$/); if (!m) return realFetch(url, init);
  if (!init.headers.apikey) return new Response('{}', { status: 401 }); return new Response(JSON.stringify(RPC[m[1]](JSON.parse(init.body))), { status: 200, headers: { 'content-type': 'application/json' } }); };
const { default: middleware } = await import('../middleware.js');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg' };
function file(p) { // Vercel cleanUrls: /a -> a.html, /a/ -> a/index.html
  let f = path.join(ROOT, decodeURIComponent(p)); if (!f.startsWith(ROOT)) return null;
  for (const c of [f, f + '.html', path.join(f, 'index.html')]) if (fs.existsSync(c) && fs.statSync(c).isFile()) return c; return null; }
http.createServer(async (req, res) => {
  const chunks = []; for await (const c of req) chunks.push(c);
  const url = 'http://' + req.headers.host + req.url;
  const r = await middleware(new Request(url, { method: req.method, headers: req.headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks) }));
  if (r.headers.get('x-middleware-next') !== '1') { const h = {}; r.headers.forEach((v, k) => { h[k] = v; }); res.writeHead(r.status, h); res.end(Buffer.from(await r.arrayBuffer())); return; }
  const f = file(new URL(url).pathname); if (!f) { res.writeHead(404); res.end('Not found'); return; }
  res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream', 'cache-control': 'no-store' }); fs.createReadStream(f).pipe(res);
}).listen(+process.argv[2] || 4173, () => console.log('preview on http://localhost:' + (+process.argv[2] || 4173)));
