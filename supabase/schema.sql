-- WalkSafe database schema for Supabase (Postgres).
-- Safe to run more than once.
--
-- Roles: 'admin' or 'blind'. The role lives in auth.users.raw_app_meta_data
-- so it is inside every login token (the server checks it without a DB call);
-- public.profiles mirrors it for listing users.
--
-- The Colab server writes with the secret key, which bypasses row level
-- security. The admin dashboard reads with the admin's own login.

-- ── Users ────────────────────────────────────────────────────────────────────

create table if not exists public.profiles (
    id           uuid        primary key references auth.users (id) on delete cascade,
    email        text,
    display_name text,
    role         text        not null default 'blind' check (role in ('admin', 'blind')),
    is_active    boolean     not null default true,
    settings     jsonb       not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);

-- Create / update the profile whenever an auth user is created or their role changes.
create or replace function public.sync_profile()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, email, display_name, role)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'display_name', new.email),
        coalesce(new.raw_app_meta_data ->> 'role', 'blind')
    )
    on conflict (id) do update
        set email = excluded.email,
            role  = excluded.role;
    return new;
end;
$$;

drop trigger if exists on_auth_user_changed on auth.users;
create trigger on_auth_user_changed
    after insert or update of email, raw_app_meta_data on auth.users
    for each row execute function public.sync_profile();

-- Users created before this script ran.
insert into public.profiles (id, email, display_name, role)
select id, email, email, coalesce(raw_app_meta_data ->> 'role', 'blind')
from auth.users
on conflict (id) do nothing;

create or replace function public.is_admin()
returns boolean
language sql
stable
as $$
    select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'admin';
$$;

-- ── Session data ─────────────────────────────────────────────────────────────

create table if not exists public.sessions (
    session_id   uuid        primary key default gen_random_uuid(),
    user_id      uuid        references public.profiles (id) on delete set null,
    started_at   timestamptz not null default now(),
    ended_at     timestamptz,
    total_frames integer     not null default 0
);

create table if not exists public.frames (
    session_id          uuid        not null references public.sessions (session_id) on delete cascade,
    frame_idx           integer     not null,
    ts                  timestamptz not null,
    command             text,
    detail              text,
    reasoning           text,
    action              text,
    action_confidence   real,
    ego_speed_ms        real,
    speed_trend_ms      real,
    lateral_drift       text,
    flow_lateral_ratio  real,
    flow_rotation_score real,
    num_agents          integer,
    num_critical        integer,
    num_gaps            integer,
    best_gap_width_m    real,
    best_gap_dist_m     real,
    best_gap_direction  text,
    primary key (session_id, frame_idx)
);

create table if not exists public.agents (
    id                bigint      generated always as identity primary key,
    session_id        uuid        not null references public.sessions (session_id) on delete cascade,
    frame_idx         integer     not null,
    ts                timestamptz not null,
    track_id          integer,
    name              text,
    conf              real,
    dist_m            real,
    dist_m_sigma      real,
    approach_speed_ms real,
    ttc_s             real,
    risk_level        text,
    motion            text,
    track_age         integer,
    cx                integer,
    cy                integer
);

create table if not exists public.gaps (
    id         bigint      generated always as identity primary key,
    session_id uuid        not null references public.sessions (session_id) on delete cascade,
    frame_idx  integer     not null,
    ts         timestamptz not null,
    direction  text,
    width_m    real,
    dist_m     real,
    cx_px      integer,
    width_px   integer
);

alter table public.sessions add column if not exists end_reason text;

create index if not exists idx_sessions_user  on public.sessions (user_id, started_at desc);
create index if not exists idx_frames_ts      on public.frames   (ts);
create index if not exists idx_agents_session on public.agents   (session_id, frame_idx);
create index if not exists idx_agents_track   on public.agents   (session_id, track_id);
create index if not exists idx_gaps_session   on public.gaps     (session_id, frame_idx);

-- ── Row level security ───────────────────────────────────────────────────────
-- Admin: read everything, manage profiles. Blind user: read own profile only.

alter table public.profiles enable row level security;
alter table public.sessions enable row level security;
alter table public.frames   enable row level security;
alter table public.agents   enable row level security;
alter table public.gaps     enable row level security;

drop policy if exists "own profile or admin" on public.profiles;
create policy "own profile or admin" on public.profiles
    for select to authenticated
    using (id = auth.uid() or public.is_admin());

drop policy if exists "admin updates profiles" on public.profiles;
create policy "admin updates profiles" on public.profiles
    for update to authenticated
    using (public.is_admin())
    with check (public.is_admin());

drop policy if exists "admin reads sessions" on public.sessions;
create policy "admin reads sessions" on public.sessions
    for select to authenticated using (public.is_admin());

drop policy if exists "admin reads frames" on public.frames;
create policy "admin reads frames" on public.frames
    for select to authenticated using (public.is_admin());

drop policy if exists "admin reads agents" on public.agents;
create policy "admin reads agents" on public.agents
    for select to authenticated using (public.is_admin());

drop policy if exists "admin reads gaps" on public.gaps;
create policy "admin reads gaps" on public.gaps
    for select to authenticated using (public.is_admin());

-- ── App settings ─────────────────────────────────────────────────────────────
-- server_url: the current Colab server address. The admin pastes it after each
-- new Colab session; every phone reads it on start. Temporary until the server
-- has a permanent address.

create table if not exists public.app_config (
    key        text        primary key,
    value      text        not null default '',
    updated_at timestamptz not null default now(),
    updated_by uuid        references auth.users (id) on delete set null
);

insert into public.app_config (key, value) values ('server_url', '')
on conflict (key) do nothing;

alter table public.app_config enable row level security;

drop policy if exists "signed-in users read config" on public.app_config;
create policy "signed-in users read config" on public.app_config
    for select to authenticated using (true);

drop policy if exists "admin writes config" on public.app_config;
create policy "admin writes config" on public.app_config
    for all to authenticated
    using (public.is_admin())
    with check (public.is_admin());

-- ── Dashboard queries ────────────────────────────────────────────────────────
-- Run with the caller's rights, so row level security limits them to admins.

create or replace function public.session_stats(p_session uuid default null, p_user uuid default null)
returns jsonb
language sql
stable
as $$
    with s as (
        select session_id from public.sessions
        where (p_session is null or session_id = p_session)
          and (p_user    is null or user_id    = p_user)
    ),
    f as (select * from public.frames where session_id in (select session_id from s)),
    a as (select * from public.agents where session_id in (select session_id from s))
    select jsonb_build_object(
        'sessions',       (select count(*) from s),
        'total_frames',   (select count(*) from f),
        'avg_speed_ms',   (select round(avg(ego_speed_ms)::numeric, 2) from f),
        'total_agents',   (select count(*) from a),
        'critical_count', (select count(*) from a where risk_level = 'critical'),
        'commands', coalesce((select jsonb_agg(jsonb_build_object('label', k, 'count', n) order by n desc)
                              from (select command as k, count(*) as n from f group by command) x), '[]'::jsonb),
        'actions',  coalesce((select jsonb_agg(jsonb_build_object('label', k, 'count', n) order by n desc)
                              from (select action as k, count(*) as n from f group by action) x), '[]'::jsonb),
        'risks',    coalesce((select jsonb_agg(jsonb_build_object('label', k, 'count', n) order by n desc)
                              from (select risk_level as k, count(*) as n from a group by risk_level) x), '[]'::jsonb)
    );
$$;

-- Speed over one session, thinned to at most p_points rows.
create or replace function public.session_speed(p_session uuid, p_points integer default 300)
returns table (frame_idx integer, ts timestamptz, ego_speed_ms real, action text)
language sql
stable
as $$
    with f as (
        select frame_idx, ts, ego_speed_ms, action,
               row_number() over (order by frame_idx) as rn,
               count(*)     over ()                   as n
        from public.frames
        where session_id = p_session
    )
    select frame_idx, ts, ego_speed_ms, action
    from f
    where (rn - 1) % greatest(1, ceil(n::numeric / greatest(p_points, 1))::integer) = 0
    order by frame_idx;
$$;

-- ── First admin ──────────────────────────────────────────────────────────────
-- After creating your user in Authentication → Users, run (with your email):
--
--   update auth.users
--   set raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'::jsonb
--   where email = 'you@example.com';
--
-- Log out and back in afterwards so the new role is in your login token.
