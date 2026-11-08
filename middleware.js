// Sign-in gate for the whole site (Vercel Routing Middleware: runs before every page and file).
// Each person has their own email and password. Passwords and sessions live in Supabase
// (tables os_members, os_sessions; see supabase/schema.sql) and are only reachable through
// the os_* functions called below. Nothing secret is stored in this file: the key is the
// project's publishable key, which can do nothing except call those functions.

const SUPABASE_URL = 'https://joogjxthmtndysxvkyov.supabase.co';
const SUPABASE_KEY = 'sb_publishable_UT1EYRPSCpKpomYB3_gqrA_e8On0HSs';
const COOKIE = 'os_session';
const DAYS = 30;
const CACHE_MS = 60 * 1000;   // how long a checked session is trusted before asking Supabase again
const SITE = 'Founder OS';
// Company Initiatives can be opened without an account through its share link (/share/initiatives?k=...).
// The link's key is checked by Supabase (table os_shares) and kept in its own cookie, which opens only
// the initiatives page, its files, and the two API calls below (read tasks, change a task's progress).
const SHARE_COOKIE = 'os_share_init';
const SHARE_DAYS = 365;
const SHARE_PATHS = /^\/(s\/initiatives(\/.*)?|assets\/os\.css|__api\/initiatives\/(list|progress))$/;

export const config = { matcher: '/:path*' };

const cache = new Map();      // token -> { who, until }

async function rpc(fn, args) {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/${fn}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', apikey: SUPABASE_KEY },
    body: JSON.stringify(args),
  });
  if (!r.ok) throw new Error(`sign-in service answered ${r.status}`);
  return r.json();
}

function cookieOf(req, name) {
  const m = (req.headers.get('cookie') || '').match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[1]) : null;
}
const setCookie = (value, maxAge) => `${COOKIE}=${value}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;
const next = () => new Response(null, { headers: { 'x-middleware-next': '1' } });
const BASE = { 'cache-control': 'no-store', 'x-robots-tag': 'noindex, nofollow' };
const json = (body, status = 200, extra = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', ...BASE, ...extra } });
const html = (body, status = 200, extra = {}) =>
  new Response(body, { status, headers: { 'content-type': 'text/html; charset=utf-8', ...BASE, ...extra } });
const redirect = (to, extra = {}) => new Response(null, { status: 303, headers: { location: to, ...BASE, ...extra } });

async function whoIs(token) {
  if (!token || !/^[0-9a-f]{64}$/.test(token)) return null;
  const hit = cache.get(token);
  if (hit && hit.until > Date.now() && !hit.who.must_change) return hit.who;
  const r = await rpc('os_session', { p_token: token });
  if (!r || !r.ok) { cache.delete(token); return null; }
  const who = { email: r.email, name: r.name, role: r.role, must_change: !!r.must_change };
  if (cache.size > 500) cache.clear();
  cache.set(token, { who, until: Date.now() + CACHE_MS });
  return who;
}

async function shareOk(key) {
  if (!key || !/^[0-9a-f]{64}$/.test(key)) return false;
  const hit = cache.get('share:' + key);
  if (hit && hit.until > Date.now()) return hit.ok;
  const r = await rpc('os_share_ok', { p_name: 'initiatives', p_share: key });
  const ok = !!(r && r.ok);
  cache.set('share:' + key, { ok, until: Date.now() + CACHE_MS });
  return ok;
}
const shareCookie = (value, maxAge) => `${SHARE_COOKIE}=${value}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;

function deadLinkPage() {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Link not valid · Company Initiatives</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#1e1b17;color:#ede7dc;font:15px/1.5 system-ui,sans-serif;padding:24px 16px;text-align:center}
img{display:block;width:min(260px,70vw);margin:0 auto 24px}p{max-width:420px;color:#b3aa98}</style></head><body><div>
<img src="/brand/rc-wordmark.png" alt="Renaissance Commerce"><p>This Company Initiatives link is no longer valid. Ask a founder for the current link.</p></div></body></html>`;
}

// a POST must come from this site's own pages
function sameSite(req, url) {
  const o = req.headers.get('origin');
  if (!o) return req.headers.get('sec-fetch-site') !== 'cross-site';
  try { return new URL(o).host === url.host; } catch (e) { return false; }
}
const safeBack = (b) => (typeof b === 'string' && b.startsWith('/') && !b.startsWith('//') && !b.startsWith('/__')) ? b : '/';

const ERRORS = {
  invalid: 'That email and password do not match. Try again.',
  locked: 'Too many wrong tries. Wait 15 minutes, then try again.',
  down: 'Sign-in is not reachable right now. Try again in a minute.',
};

function loginPage(error, back, email) {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Sign in · ${SITE} · Renaissance Commerce</title>
<link rel="icon" type="image/png" href="/brand/favicon-64.png"><link rel="apple-touch-icon" href="/brand/apple-touch-icon.png">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@500;600&family=Schibsted+Grotesk:wght@400;600;700&display=swap">
<style>
:root{--bg:#1e1b17;--card:#26221c;--ink:#ede7dc;--ink2:#b3aa98;--line:#3d372e;--stone:#d4ccbe;--gold:#c6b048;--bad:#f08a7e}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px;background:var(--bg);color:var(--ink);font:15px/1.5 'Schibsted Grotesk',ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px 16px}
.logo{display:block;width:min(300px,78vw);height:auto}
form{width:100%;max-width:380px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:26px 26px 24px}
h1{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:30px;font-weight:600;line-height:1.1;margin:0 0 4px;color:var(--stone)}
p{margin:0 0 16px;color:var(--ink2);font-size:14px}
label{display:block;font-size:13px;font-weight:600;color:var(--ink2);margin:14px 0 6px}
input{width:100%;font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:#1b1814;color:var(--ink)}
input:focus-visible{outline:2px solid var(--gold);outline-offset:1px}
button{margin-top:20px;width:100%;font:inherit;font-weight:700;padding:11px;border:0;border-radius:8px;background:var(--stone);color:#1e1b17;cursor:pointer}
button:hover{background:#e3dccf}
button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.err{color:var(--bad);font-size:14px;margin-top:14px}
.foot{margin:16px 0 0;font-size:13px}
</style></head><body>
<img class="logo" src="/brand/rc-wordmark.png" alt="Renaissance Commerce" width="300" height="101">
<form method="POST" action="/__login">
<h1>${SITE}</h1><p>Sign in with your work email.</p>
<label for="em">Email</label><input id="em" name="email" type="email" autocomplete="username" value="${esc(email)}" ${email ? '' : 'autofocus'} required>
<label for="pw">Password</label><input id="pw" name="password" type="password" autocomplete="current-password" ${email ? 'autofocus' : ''} required>
<input type="hidden" name="back" value="${esc(back)}">
<button type="submit">Sign in</button>
${error ? `<div class="err" role="alert">${esc(ERRORS[error] || ERRORS.invalid)}</div>` : ''}
<p class="foot">No account, or forgot your password? Ask a founder to add you or reset it.</p>
</form></body></html>`;
}

async function body(req) { try { return await req.json(); } catch (e) { return {}; } }

export default async function middleware(req) {
  const url = new URL(req.url);
  const path = url.pathname;
  const token = cookieOf(req, COOKIE);

  // the logo and icons are the only files served before sign-in (the sign-in page shows them)
  if (/^\/brand\/[a-z0-9-]+\.png$/.test(path)) return next();

  // sign in
  if (path === '/__login') {
    if (req.method !== 'POST') return redirect('/');
    if (!sameSite(req, url)) return html(loginPage('invalid', '/', ''), 403);
    const form = await req.formData();
    const email = String(form.get('email') || '').trim().slice(0, 200);
    const back = safeBack(String(form.get('back') || '/'));
    const ip = (req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip') || '').split(',')[0].trim().slice(0, 60);
    let r;
    try { r = await rpc('os_login', { p_email: email, p_password: String(form.get('password') || '').slice(0, 500), p_ip: ip }); }
    catch (e) { return html(loginPage('down', back, email), 503); }
    if (!r || !r.ok) return html(loginPage(r && r.error === 'locked' ? 'locked' : 'invalid', back, email), 401);
    return redirect(r.must_change ? '/account?first=1' : back, { 'set-cookie': setCookie(r.token, DAYS * 86400) });
  }

  // sign out
  if (path === '/__logout') {
    if (token) { cache.delete(token); try { await rpc('os_logout', { p_token: token }); } catch (e) { /* cookie is cleared either way */ } }
    return redirect('/', { 'set-cookie': setCookie('', 0) });
  }

  // the Company Initiatives share link: check the key, keep it in a cookie, open the page
  if (path === '/share/initiatives') {
    const k = (url.searchParams.get('k') || '').trim();
    let ok = false;
    try { ok = await shareOk(k); } catch (e) { return html(loginPage('down', '/', ''), 503); }
    if (!ok) return html(deadLinkPage(), 404);
    return redirect('/s/initiatives/' + (url.hash || ''), { 'set-cookie': shareCookie(k, SHARE_DAYS * 86400) });
  }

  // everything else needs a session (or, for the initiatives page only, the share link)
  let who = null;
  try { who = await whoIs(token); }
  catch (e) { return path.startsWith('/__api/') ? json({ ok: false, error: 'down' }, 503) : html(loginPage('down', safeBack(path + url.search), ''), 503); }
  let share = null;
  if (!who && SHARE_PATHS.test(path)) {
    const k = cookieOf(req, SHARE_COOKIE);
    try { if (await shareOk(k)) share = k; } catch (e) { /* treated as signed out */ }
  }
  if (!who && !share) {
    if (path.startsWith('/__api/')) return json({ ok: false, error: 'signed_out' }, 401);
    return html(loginPage('', safeBack(path + url.search), ''), 401);
  }

  // Company Initiatives API: members and share-link holders read tasks and change progress;
  // only members add, edit or delete tasks and see the share link
  if (path.startsWith('/__api/initiatives/')) {
    const name = path.slice('/__api/initiatives/'.length);
    const sess = who ? token : null;
    try {
      if (name === 'list' && req.method === 'GET') return json(await rpc('os_init_list', { p_token: sess, p_share: share }));
      if (req.method !== 'POST' || !sameSite(req, url)) return json({ ok: false, error: 'not_allowed' }, 405);
      const b = await body(req);
      if (name === 'progress') {
        if (!/^[0-9a-f-]{36}$/.test(String(b.id || ''))) return json({ ok: false, error: 'not_found' }, 404);
        return json(await rpc('os_init_progress', { p_token: sess, p_share: share, p_id: String(b.id || ''), p_progress: String(b.progress || '') }));
      }
      if (!who) return json({ ok: false, error: 'signed_out' }, 401);
      if (name === 'save') return json(await rpc('os_init_save', { p_token: token, p_task: b.task || {} }));
      if (name === 'delete') {
        if (!/^[0-9a-f-]{36}$/.test(String(b.id || ''))) return json({ ok: false, error: 'not_found' }, 404);
        return json(await rpc('os_init_delete', { p_token: token, p_id: String(b.id || '') }));
      }
      if (name === 'share-link') {
        const r = await rpc('os_init_share_link', { p_token: token, p_new: !!b.renew });
        if (r && r.ok) { r.url = `${url.origin}/share/initiatives?k=${r.token}`; delete r.token; }
        return json(r);
      }
    } catch (e) { return json({ ok: false, error: 'down' }, 503); }
    return json({ ok: false, error: 'not_found' }, 404);
  }
  if (!who) return next();   // share-link holder on the initiatives page

  // small API for the account and people pages
  if (path.startsWith('/__api/')) {
    const name = path.slice(7);
    if (name === 'me' && req.method === 'GET') return json({ ok: true, ...who });
    if (req.method !== 'POST' || !sameSite(req, url)) return json({ ok: false, error: 'not_allowed' }, 405);
    const b = await body(req);
    try {
      if (name === 'password') {
        const r = await rpc('os_change_password', { p_token: token, p_old: String(b.old || ''), p_new: String(b.next || '') });
        if (r && r.ok) cache.delete(token);
        return json(r, r && r.ok ? 200 : 400);
      }
      if (name === 'people') return json(await rpc('os_people', { p_token: token }));
      if (name === 'people/add') return json(await rpc('os_add_person', { p_token: token, p_email: String(b.email || ''), p_name: String(b.name || ''), p_role: String(b.role || 'member') }));
      if (name === 'people/reset') return json(await rpc('os_reset_person', { p_token: token, p_id: String(b.id || '') }));
      if (name === 'people/remove') return json(await rpc('os_remove_person', { p_token: token, p_id: String(b.id || '') }));
    } catch (e) { return json({ ok: false, error: 'down' }, 503); }
    return json({ ok: false, error: 'not_found' }, 404);
  }

  // first sign-in: nothing opens until the temporary password is replaced
  if (who.must_change && path !== '/account' && path !== '/account.html' && !path.startsWith('/assets/')) return redirect('/account?first=1');

  return next();
}
