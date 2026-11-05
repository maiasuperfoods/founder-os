-- Founder OS sign-in. Everything lives in three tables that nobody can read directly
-- (row level security on, no policies) and a handful of functions the site calls.
-- Passwords are stored as bcrypt hashes; session tokens as SHA-256 hashes.

create table if not exists public.os_members (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  name text not null default '',
  role text not null default 'member' check (role in ('admin','member')),
  pass_hash text not null,
  must_change boolean not null default true,
  created_at timestamptz not null default now(),
  last_seen timestamptz
);
create table if not exists public.os_sessions (
  token_hash text primary key,
  member_id uuid not null references public.os_members(id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  last_seen timestamptz not null default now()
);
create index if not exists os_sessions_member on public.os_sessions(member_id);
create table if not exists public.os_login_attempts (
  id bigint generated always as identity primary key,
  email text not null,
  ip text,
  at timestamptz not null default now()
);
create index if not exists os_login_attempts_email on public.os_login_attempts(email, at);
create index if not exists os_login_attempts_ip on public.os_login_attempts(ip, at);

alter table public.os_members enable row level security;
alter table public.os_sessions enable row level security;
alter table public.os_login_attempts enable row level security;
revoke all on public.os_members, public.os_sessions, public.os_login_attempts from anon, authenticated;

-- helpers (not callable from outside)
create or replace function public.os__hash(p text) returns text language sql immutable set search_path = '' as
$$ select encode(extensions.digest(p, 'sha256'), 'hex') $$;

create or replace function public.os__temp_password() returns text language plpgsql volatile set search_path = '' as $$
declare alphabet constant text := 'abcdefghjkmnpqrstuvwxyz23456789'; b bytea := extensions.gen_random_bytes(16); out text := ''; i int;
begin
  for i in 0..15 loop
    out := out || substr(alphabet, (get_byte(b, i) % length(alphabet)) + 1, 1);
    if i in (3, 7, 11) then out := out || '-'; end if;
  end loop;
  return out;
end $$;

create or replace function public.os__member(p_token text) returns public.os_members language plpgsql security definer set search_path = '' as $$
declare m public.os_members; h text := public.os__hash(coalesce(p_token, ''));
begin
  if p_token is null or length(p_token) < 32 then return null; end if;
  select mem.* into m from public.os_sessions s join public.os_members mem on mem.id = s.member_id
   where s.token_hash = h and s.expires_at > now();
  if m.id is null then return null; end if;
  update public.os_sessions set last_seen = now() where token_hash = h and last_seen < now() - interval '5 minutes';
  update public.os_members set last_seen = now() where id = m.id and (last_seen is null or last_seen < now() - interval '5 minutes');
  return m;
end $$;

-- sign in: returns a session token, or an error after too many wrong tries
create or replace function public.os_login(p_email text, p_password text, p_ip text default null) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare e text := lower(trim(coalesce(p_email, ''))); m public.os_members; tok text; fails int; ipfails int := 0; ok boolean;
  dummy constant text := '$2a$10$C6UzMDM.H6dfI/f/IKcEeO5B0iZrFhXW0n1oT5wZ8B3mJc1eFvG7u';
begin
  delete from public.os_login_attempts where at < now() - interval '1 day';
  select count(*) into fails from public.os_login_attempts where email = e and at > now() - interval '15 minutes';
  if p_ip is not null and p_ip <> '' then
    select count(*) into ipfails from public.os_login_attempts where ip = p_ip and at > now() - interval '15 minutes';
  end if;
  if fails >= 8 or ipfails >= 40 then return jsonb_build_object('ok', false, 'error', 'locked'); end if;
  select * into m from public.os_members where email = e;
  -- always run one bcrypt so a wrong email and a wrong password take the same time
  ok := coalesce(m.pass_hash, dummy) = extensions.crypt(coalesce(p_password, ''), coalesce(m.pass_hash, dummy));
  if m.id is null or not ok then
    insert into public.os_login_attempts(email, ip) values (e, nullif(p_ip, ''));
    return jsonb_build_object('ok', false, 'error', 'invalid');
  end if;
  delete from public.os_login_attempts where email = e;
  delete from public.os_sessions where expires_at < now();
  tok := encode(extensions.gen_random_bytes(32), 'hex');
  insert into public.os_sessions(token_hash, member_id, expires_at) values (public.os__hash(tok), m.id, now() + interval '30 days');
  update public.os_members set last_seen = now() where id = m.id;
  return jsonb_build_object('ok', true, 'token', tok, 'email', m.email, 'name', m.name, 'role', m.role, 'must_change', m.must_change);
end $$;

-- who does this session belong to (called on every page load, cached briefly by the site)
create or replace function public.os_session(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare m public.os_members := public.os__member(p_token);
begin
  if m.id is null then return jsonb_build_object('ok', false); end if;
  return jsonb_build_object('ok', true, 'email', m.email, 'name', m.name, 'role', m.role, 'must_change', m.must_change);
end $$;

create or replace function public.os_logout(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  delete from public.os_sessions where token_hash = public.os__hash(coalesce(p_token, ''));
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.os_change_password(p_token text, p_old text, p_new text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare m public.os_members := public.os__member(p_token);
begin
  if m.id is null then return jsonb_build_object('ok', false, 'error', 'signed_out'); end if;
  if m.pass_hash <> extensions.crypt(coalesce(p_old, ''), m.pass_hash) then return jsonb_build_object('ok', false, 'error', 'wrong_password'); end if;
  if length(coalesce(p_new, '')) < 10 then return jsonb_build_object('ok', false, 'error', 'too_short'); end if;
  if p_new = p_old then return jsonb_build_object('ok', false, 'error', 'same'); end if;
  update public.os_members set pass_hash = extensions.crypt(p_new, extensions.gen_salt('bf', 10)), must_change = false where id = m.id;
  delete from public.os_sessions where member_id = m.id and token_hash <> public.os__hash(p_token);
  return jsonb_build_object('ok', true);
end $$;

-- people (admins only)
create or replace function public.os_people(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare m public.os_members := public.os__member(p_token);
begin
  if m.id is null then return jsonb_build_object('ok', false, 'error', 'signed_out'); end if;
  if m.role <> 'admin' then return jsonb_build_object('ok', false, 'error', 'not_admin'); end if;
  return jsonb_build_object('ok', true, 'me', m.id, 'people', coalesce((select jsonb_agg(jsonb_build_object(
    'id', p.id, 'email', p.email, 'name', p.name, 'role', p.role, 'created_at', p.created_at, 'last_seen', p.last_seen,
    'pending', p.must_change) order by p.created_at) from public.os_members p), '[]'::jsonb));
end $$;

create or replace function public.os_add_person(p_token text, p_email text, p_name text, p_role text default 'member') returns jsonb
language plpgsql security definer set search_path = '' as $$
declare m public.os_members := public.os__member(p_token); e text := lower(trim(coalesce(p_email, ''))); pw text; r text := coalesce(nullif(p_role, ''), 'member');
begin
  if m.id is null then return jsonb_build_object('ok', false, 'error', 'signed_out'); end if;
  if m.role <> 'admin' then return jsonb_build_object('ok', false, 'error', 'not_admin'); end if;
  if e !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then return jsonb_build_object('ok', false, 'error', 'bad_email'); end if;
  if r not in ('admin', 'member') then return jsonb_build_object('ok', false, 'error', 'bad_role'); end if;
  if exists (select 1 from public.os_members where email = e) then return jsonb_build_object('ok', false, 'error', 'exists'); end if;
  pw := public.os__temp_password();
  insert into public.os_members(email, name, role, pass_hash, must_change)
    values (e, left(trim(coalesce(p_name, '')), 80), r, extensions.crypt(pw, extensions.gen_salt('bf', 10)), true);
  return jsonb_build_object('ok', true, 'email', e, 'temp_password', pw);
end $$;

create or replace function public.os_reset_person(p_token text, p_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare m public.os_members := public.os__member(p_token); pw text; e text;
begin
  if m.id is null then return jsonb_build_object('ok', false, 'error', 'signed_out'); end if;
  if m.role <> 'admin' then return jsonb_build_object('ok', false, 'error', 'not_admin'); end if;
  if p_id = m.id then return jsonb_build_object('ok', false, 'error', 'self'); end if;
  pw := public.os__temp_password();
  update public.os_members set pass_hash = extensions.crypt(pw, extensions.gen_salt('bf', 10)), must_change = true where id = p_id returning email into e;
  if e is null then return jsonb_build_object('ok', false, 'error', 'not_found'); end if;
  delete from public.os_sessions where member_id = p_id;
  return jsonb_build_object('ok', true, 'email', e, 'temp_password', pw);
end $$;

create or replace function public.os_remove_person(p_token text, p_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare m public.os_members := public.os__member(p_token); e text;
begin
  if m.id is null then return jsonb_build_object('ok', false, 'error', 'signed_out'); end if;
  if m.role <> 'admin' then return jsonb_build_object('ok', false, 'error', 'not_admin'); end if;
  if p_id = m.id then return jsonb_build_object('ok', false, 'error', 'self'); end if;
  delete from public.os_members where id = p_id returning email into e;   -- sessions go with it
  if e is null then return jsonb_build_object('ok', false, 'error', 'not_found'); end if;
  return jsonb_build_object('ok', true, 'email', e);
end $$;

-- only the listed functions are reachable with the site's public key
revoke all on function public.os__hash(text), public.os__temp_password(), public.os__member(text) from public, anon, authenticated;
revoke all on function public.os_login(text, text, text), public.os_session(text), public.os_logout(text),
  public.os_change_password(text, text, text), public.os_people(text), public.os_add_person(text, text, text, text),
  public.os_reset_person(text, uuid), public.os_remove_person(text, uuid) from public, authenticated;
grant execute on function public.os_login(text, text, text), public.os_session(text), public.os_logout(text),
  public.os_change_password(text, text, text), public.os_people(text), public.os_add_person(text, text, text, text),
  public.os_reset_person(text, uuid), public.os_remove_person(text, uuid) to anon;
notify pgrst, 'reload schema';
