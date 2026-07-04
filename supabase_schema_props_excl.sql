-- ============================================================================
-- Family Bot — Supabase schema, שלב 6: "נכסים במשרד" + "נכסים בשת"פ"
-- ----------------------------------------------------------------------------
-- שני המקורות נשארים בגיליונות (הזנה ידנית / אוטומציה חיצונית) — Supabase
-- משקף אותם דרך הסנכרון המתוזמן. מריצים פעם אחת ב-SQL Editor. בטוח להרצה חוזרת.
-- ============================================================================

-- ── נכסים בשת"פ (בלעדויות חיצוניות) — מוזן אוטומטית לגיליון ─────────────────
create table if not exists external_exclusives (
  id          uuid primary key default gen_random_uuid(),
  office_id   uuid not null references offices(id) on delete cascade,
  source_key  text not null,          -- event_id (ext-hash) / סינתטי
  event_id    text,
  street      text,
  dest        text,                   -- המשרד המפרסם
  link        text,
  price       text,
  received_at date,                   -- תאריך-בלבד (parseDate_) לסינון/אינדוקס
  raw         jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (office_id, source_key)
);
create index if not exists excl_office_received
  on external_exclusives (office_id, received_at desc);

-- ── נכסים במשרד — גיליון ידני נפרד; משוקף כתמונת-מצב לפי מספר שורה ──────────
create table if not exists properties (
  id         uuid primary key default gen_random_uuid(),
  office_id  uuid not null references offices(id) on delete cascade,
  sheet_row  int  not null,
  raw        jsonb not null default '{}'::jsonb,   -- השורה כפי שהאפליקציה מקבלת אותה (כולל _desc_ae)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (office_id, sheet_row)
);
create index if not exists properties_office_row on properties (office_id, sheet_row);

alter table external_exclusives enable row level security;
alter table properties          enable row level security;

drop policy if exists office_read_excl on external_exclusives;
create policy office_read_excl on external_exclusives for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

drop policy if exists office_read_properties on properties;
create policy office_read_properties on properties for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

do $$
begin
  begin
    alter publication supabase_realtime add table external_exclusives;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table properties;
  exception when duplicate_object then null;
  end;
end $$;

select 'external_exclusives' as t, count(*) from external_exclusives
union all select 'properties', count(*) from properties;
