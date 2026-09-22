-- StegoShield authentication schema.
--
-- Run this once in your Supabase project's SQL Editor
-- (https://app.supabase.com/project/_/sql/new) after creating the
-- project and before setting SUPABASE_URL / SUPABASE_ANON_KEY in the
-- app's environment. It is idempotent (safe to re-run).
--
-- Design: two tables, both with Row Level Security enabled and a
-- policy that restricts every row to auth.uid() = <owner column>. This
-- is the actual IDOR defense - it holds even if a bug in the Flask
-- app's route logic ever forgot to filter by user, because the
-- database itself won't return or accept another user's rows for a
-- request made with that user's own access token. No raw uploaded
-- images are stored anywhere - analysis_history is metadata only.

-- ---------------------------------------------------------------------
-- profiles: one row per auth.users row, created automatically on signup.
-- ---------------------------------------------------------------------
create table if not exists public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    email text not null,
    created_at timestamptz not null default now(),
    last_login timestamptz
);

alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
    on public.profiles for select
    using (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
    on public.profiles for update
    using (auth.uid() = id);

-- Auto-create a profile row whenever a new Supabase Auth user is created.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, email, created_at)
    values (new.id, new.email, now())
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_user();

-- ---------------------------------------------------------------------
-- analysis_history: metadata only (no image bytes) about a signed-in
-- user's encode/decode/steganalysis/image-analysis runs.
-- ---------------------------------------------------------------------
create table if not exists public.analysis_history (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    created_at timestamptz not null default now(),
    analysis_type text not null check (analysis_type in ('encode', 'decode', 'steganalysis', 'image_analysis')),
    filename text,
    result text,
    confidence double precision,
    model_version text
);

alter table public.analysis_history enable row level security;

drop policy if exists "history_select_own" on public.analysis_history;
create policy "history_select_own"
    on public.analysis_history for select
    using (auth.uid() = user_id);

drop policy if exists "history_insert_own" on public.analysis_history;
create policy "history_insert_own"
    on public.analysis_history for insert
    with check (auth.uid() = user_id);

create index if not exists analysis_history_user_created_idx
    on public.analysis_history (user_id, created_at desc);
