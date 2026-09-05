
-- Run this once in Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.decks (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    source_files jsonb not null default '[]'::jsonb,
    cards jsonb not null default '[]'::jsonb,
    last_index integer not null default 0,
    created_at timestamptz not null default now()
);

alter table public.decks enable row level security;

drop policy if exists "Users can view own decks" on public.decks;
create policy "Users can view own decks"
on public.decks for select
using (auth.uid() = user_id);

drop policy if exists "Users can create own decks" on public.decks;
create policy "Users can create own decks"
on public.decks for insert
with check (auth.uid() = user_id);

drop policy if exists "Users can update own decks" on public.decks;
create policy "Users can update own decks"
on public.decks for update
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can delete own decks" on public.decks;
create policy "Users can delete own decks"
on public.decks for delete
using (auth.uid() = user_id);

create index if not exists decks_user_created_idx
on public.decks(user_id, created_at desc);
