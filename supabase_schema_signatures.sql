-- ============================================================================
-- Family Bot — Supabase schema, שלב 3: "חתימות"
-- ----------------------------------------------------------------------------
-- מריצים פעם אחת ב-SQL Editor של Supabase (Run). בטוח להרצה חוזרת.
-- ============================================================================

create table if not exists signatures (
  id             uuid primary key default gen_random_uuid(),
  office_id      uuid not null references offices(id) on delete cascade,
  source_key     text not null,      -- event_id (מ-Fireberry או SIGN... מהאפליקציה)
  event_id       text,
  deal_type      text,
  agent          text,
  client_name    text,
  address        text,
  city           text,
  commission_pct text,               -- בזרימת SMS מכיל את קישור המסמך החתום
  notes          text,
  received_at    date,               -- תאריך-בלבד (כמו parseDate_) לסינון/אינדוקס
  raw            jsonb not null default '{}'::jsonb,   -- השורה המקורית 1:1 (ל-parity)
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (office_id, source_key)
);
create index if not exists signatures_office_received
  on signatures (office_id, received_at desc);
create index if not exists signatures_office_agent
  on signatures (office_id, agent);

alter table signatures enable row level security;

drop policy if exists office_read_signatures on signatures;
create policy office_read_signatures on signatures for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

do $$
begin
  begin
    alter publication supabase_realtime add table signatures;
  exception when duplicate_object then null;
  end;
end $$;

select 'signatures' as t, count(*) from signatures;
