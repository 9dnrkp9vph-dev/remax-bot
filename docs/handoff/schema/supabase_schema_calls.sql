-- ============================================================================
-- Family Bot — Supabase schema, שלב 2: "שיחות" (+ שיחות מוסתרות)
-- ----------------------------------------------------------------------------
-- מריצים פעם אחת ב-SQL Editor של Supabase (Run). בטוח להרצה חוזרת.
-- אף שינוי באפליקציה הרצה — חי לצד המערכת הקיימת.
-- ============================================================================

-- ── שיחות (מ-Fireberry: תמלול, סטטוס, סוכן) ────────────────────────────────
-- source_key = event_id; לשורות היסטוריות בלי event_id נוצר מפתח סינתטי יציב
create table if not exists calls (
  id                 uuid primary key default gen_random_uuid(),
  office_id          uuid not null references offices(id) on delete cascade,
  source_key         text not null,
  event_id           text,               -- כפי שמגיע מ-Fireberry (יכול להיות ריק בישנות)
  status             text,               -- ANSWER / NOANSWER / ...
  agent              text,
  agent_phone        text,
  caller_phone       text,
  duration_sec       text,
  transcript_summary text,
  received_at        date,               -- תאריך (כמו parseDate_ — ללא שעה) לסינון/אינדוקס
  raw                jsonb not null default '{}'::jsonb,  -- השורה המקורית 1:1 (ל-parity)
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (office_id, source_key)
);
create index if not exists calls_office_received
  on calls (office_id, received_at desc);
create index if not exists calls_office_agent_phone
  on calls (office_id, agent_phone);

-- ── שיחות מוסתרות (טאב "מוסתרות" — עמודת מזהים אחת) ────────────────────────
create table if not exists hidden_calls (
  id         uuid primary key default gen_random_uuid(),
  office_id  uuid not null references offices(id) on delete cascade,
  event_id   text not null,
  created_at timestamptz not null default now(),
  unique (office_id, event_id)
);

-- ── RLS ─────────────────────────────────────────────────────────────────────
alter table calls        enable row level security;
alter table hidden_calls enable row level security;

drop policy if exists office_read_calls on calls;
create policy office_read_calls on calls for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

drop policy if exists office_read_hidden_calls on hidden_calls;
create policy office_read_hidden_calls on hidden_calls for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

-- ── Realtime ────────────────────────────────────────────────────────────────
do $$
begin
  begin
    alter publication supabase_realtime add table calls;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table hidden_calls;
  exception when duplicate_object then null;
  end;
end $$;

-- אימות
select 'calls' as t, count(*) from calls
union all select 'hidden_calls', count(*) from hidden_calls;
