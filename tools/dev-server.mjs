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
// Initiatives stand-in: share keys are 64 'a's (company, /share/initiatives?k=...) and 64 'e's (executive, /share/executive?k=...);
// tasks are seeded from the imported calls of both boards
const SHARES = { initiatives: 'a'.repeat(64), executive: 'e'.repeat(64) }, SHARE_OF = { company: 'initiatives', executive: 'executive' };
const tasks = [];
for (const [board, dir] of [['company', 'initiatives'], ['executive', 'executive']]) { try { for (const c of JSON.parse(fs.readFileSync(path.join(ROOT, 's', dir, 'data/calls.json'), 'utf8')))
  for (const t of c.tasksImported) tasks.push({ id: crypto.randomUUID(), board, call_id: c.id, kind: c.kind, title: t.title, owner: t.owner, due: t.due, progress: 'Not started', note: '', created_at: c.at, updated_at: c.at, updated_by: 'Call import' }); } catch (e) { /* no calls yet */ } }
const iwho = (a) => { const p = a.p_token && who(a.p_token); if (p && !p.must_change && (a.p_board === 'company' || p.role === 'admin')) return p.name; return a.p_share === SHARES[SHARE_OF[a.p_board]] ? 'share' : null; };
const strip = ({ board, ...t }) => t;
Object.assign(RPC, {
  os_share_ok: (a) => ({ ok: SHARES[a.p_name] === a.p_share }),
  os_init_list: (a) => { const w = iwho(a); return w ? { ok: true, mode: w === 'share' ? 'share' : 'member', tasks: tasks.filter((t) => t.board === a.p_board).map(strip) } : { ok: false, error: 'signed_out' }; },
  os_init_progress: (a) => { const w = iwho(a); if (!w) return { ok: false, error: 'signed_out' }; const t = tasks.find((x) => x.id === a.p_id && x.board === a.p_board); if (!t) return { ok: false, error: 'not_found' };
    t.progress = a.p_progress; t.updated_at = new Date().toISOString(); t.updated_by = w === 'share' ? 'Share link' : w; return { ok: true }; },
  os_init_save: (a) => { const w = iwho(a); if (!w || w === 'share') return { ok: false, error: 'signed_out' }; const x = a.p_task;
    if (x.id) { const t = tasks.find((q) => q.id === x.id && q.board === a.p_board); Object.assign(t, { title: x.title, owner: x.owner, due: x.due || null, note: x.note, updated_by: w }); return { ok: true, id: t.id }; }
    const t = { id: crypto.randomUUID(), board: a.p_board, call_id: x.call_id || null, kind: x.kind || 'other', title: x.title, owner: x.owner, due: x.due || null, progress: 'Not started', note: x.note || '', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), updated_by: w };
    tasks.push(t); return { ok: true, id: t.id }; },
  os_init_delete: (a) => { const w = iwho(a); if (!w || w === 'share') return { ok: false, error: 'signed_out' }; const i = tasks.findIndex((q) => q.id === a.p_id && q.board === a.p_board); if (i >= 0) tasks.splice(i, 1); return { ok: i >= 0 }; },
  os_init_share_link: (a) => { const w = iwho(a); return w && w !== 'share' ? { ok: true, token: SHARES[SHARE_OF[a.p_board]] } : { ok: false, error: 'signed_out' }; },
});
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
