-- ============================================================================
-- Family Bot — Supabase schema, שלב 1: "נכס נולד" (מולטי-טננט)
-- ----------------------------------------------------------------------------
-- מריצים פעם אחת ב-SQL Editor של Supabase (Run).
-- בטוח להרצה חוזרת (IF NOT EXISTS / ON CONFLICT).
-- אף שינוי באפליקציה הרצה — הסכימה חיה לצד המערכת הקיימת.
-- ============================================================================

-- ── משרדים (טננטים) ─────────────────────────────────────────────────────────
create table if not exists offices (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  slug       text not null unique,
  settings   jsonb not null default '{}'::jsonb,  -- כולל newborn_default_delay, ערים וכו'
  created_at timestamptz not null default now()
);

-- ── משתמשים (סוכנים/מתאמות/מנהלים) ─────────────────────────────────────────
create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  office_id     uuid not null references offices(id) on delete cascade,
  name          text not null,
  phone         text,                 -- 9 ספרות אחרונות (כמו _last9 באפליקציה)
  vphone        text,
  role          text not null default 'agent'
                check (role in ('admin','coordinator','agent')),
  aliases       text[] not null default '{}',
  newborn_delay int,                  -- NULL = ברירת מחדל של המשרד, -1 = מוסתר
  suspended     boolean not null default false,
  created_at    timestamptz not null default now(),
  unique (office_id, phone)
);

-- ── מודעות "נכס נולד" (FSBO מ-Fireberry) ────────────────────────────────────
-- source_key = אותו מפתח יציב כמו _nb_key ב-app.py:
--   'id:<מזהה>'  או  'ln:<קישור>'  או  'ad:<רחוב>|<נוצר בתאריך>'
create table if not exists newborn_listings (
  id                uuid primary key default gen_random_uuid(),
  office_id         uuid not null references offices(id) on delete cascade,
  source_key        text not null,
  pid               text,             -- מזהה (Fireberry)
  owner_name        text,             -- שם בעל הנכס
  owner_phone       text,             -- טלפון בעל הנכס-
  street            text,             -- רחוב
  city              text,             -- עיר
  neighborhood      text,             -- שכונה
  price             text,             -- נשמר כטקסט גולמי — הפורמט נעשה באפליקציה (parity)
  description       text,             -- תיאור נכס
  link              text,             -- קישור
  notes             text,             -- הערות חדש
  lister            text,             -- משתמש (הסוכן שפרסם) / סוכן 1
  created_at_source timestamptz,      -- נוצר בתאריך
  updated_at_source timestamptz,      -- עודכן בתאריך
  raw               jsonb not null default '{}'::jsonb,  -- השורה המקורית המלאה (ל-parity)
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (office_id, source_key)
);
create index if not exists nb_listings_office_created
  on newborn_listings (office_id, created_at_source desc);
create index if not exists nb_listings_office_pid
  on newborn_listings (office_id, pid);

-- ── סטטוס טיפול פר-סוכן (פגישה/פולואפ/לא מעוניין) ──────────────────────────
-- מחליף את nbStatus שבבלוב הקונפיג; מפתח לוגי = agent_key::listing_key (skey)
create table if not exists newborn_status (
  id           uuid primary key default gen_random_uuid(),
  office_id    uuid not null references offices(id) on delete cascade,
  listing_key  text not null,
  agent_key    text not null,          -- שם מקונן (canon) — כמו _canon_key
  agent_name   text not null,
  status       text not null check (status in ('meeting','followup','not_interested')),
  status_date  text,                   -- 'YYYY-MM-DD' או 'YYYY-MM-DDTHH:MM' — טקסט לשמירת parity
  addr         text,
  owner_name   text,
  owner_phone  text,
  price        text,
  note         text,
  cal          jsonb not null default '[]'::jsonb,   -- [{email,id}] אירועי יומן Google
  ts           bigint not null,        -- epoch שניות (כמו היום)
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (office_id, agent_key, listing_key)
);
create index if not exists nb_status_office_listing
  on newborn_status (office_id, listing_key);

-- ── הערות משותפות (כולם רואים את של כולם) ──────────────────────────────────
-- מחליף את nbNotes שבבלוב הקונפיג; מחיקה מזוהה לפי ts (כמו היום)
create table if not exists newborn_notes (
  id            uuid primary key default gen_random_uuid(),
  office_id     uuid not null references offices(id) on delete cascade,
  listing_key   text not null,
  author_name   text not null,
  author_phone9 text not null default '',
  text          text not null,
  ts            bigint not null,       -- epoch שניות
  created_at    timestamptz not null default now()
);
create index if not exists nb_notes_office_listing
  on newborn_notes (office_id, listing_key);

-- ── מעקב פניות וואטסאפ ("כבר פנו") ─────────────────────────────────────────
-- מקביל לטאב נכסנולד_פניות; ייחודיות (נכס, סוכן) כמו הדדופ בגיליון
create table if not exists newborn_contacts (
  id           uuid primary key default gen_random_uuid(),
  office_id    uuid not null references offices(id) on delete cascade,
  listing_key  text not null,
  agent_name   text not null,
  addr         text,
  contacted_at timestamptz not null default now(),
  unique (office_id, listing_key, agent_name)
);
create index if not exists nb_contacts_office_listing
  on newborn_contacts (office_id, listing_key);

-- ============================================================================
-- Row Level Security — הפרדה לוגית בין משרדים
-- ה-Backend עובד עם service_role (עוקף RLS ומסנן office_id בקוד).
-- ה-RLS מגן על הערוץ הישיר מהדפדפן (Realtime/קריאה) לפי claim בשם office_id
-- בתוך ה-JWT שהשרת ינפיק. בשלב זה: קריאה בלבד מהדפדפן, כל הכתיבות דרך השרת.
-- ============================================================================
alter table offices          enable row level security;
alter table users            enable row level security;
alter table newborn_listings enable row level security;
alter table newborn_status   enable row level security;
alter table newborn_notes    enable row level security;
alter table newborn_contacts enable row level security;

drop policy if exists office_members_read on offices;
create policy office_members_read on offices for select
  using (id = (auth.jwt() ->> 'office_id')::uuid);

drop policy if exists office_read_users on users;
create policy office_read_users on users for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

drop policy if exists office_read_nb_listings on newborn_listings;
create policy office_read_nb_listings on newborn_listings for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

drop policy if exists office_read_nb_status on newborn_status;
create policy office_read_nb_status on newborn_status for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

drop policy if exists office_read_nb_notes on newborn_notes;
create policy office_read_nb_notes on newborn_notes for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

drop policy if exists office_read_nb_contacts on newborn_contacts;
create policy office_read_nb_contacts on newborn_contacts for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

-- ── Realtime: פרסום שינויים בטבלאות נכס נולד ────────────────────────────────
do $$
begin
  begin
    alter publication supabase_realtime add table newborn_listings;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table newborn_status;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table newborn_notes;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table newborn_contacts;
  exception when duplicate_object then null;
  end;
end $$;

-- ── טננט ראשון: RE/MAX Family ──────────────────────────────────────────────
-- מזהה קבוע — ישמש את ה-Apps Script (כתיבה כפולה) ואת ה-Backend
insert into offices (id, name, slug)
values ('11111111-1111-4111-8111-111111111111', 'RE/MAX Family', 'remax-family')
on conflict (slug) do nothing;

-- אימות: אמורות להופיע 6 טבלאות והמשרד הראשון
select 'offices' as t, count(*) from offices
union all select 'users', count(*) from users
union all select 'newborn_listings', count(*) from newborn_listings
union all select 'newborn_status', count(*) from newborn_status
union all select 'newborn_notes', count(*) from newborn_notes
union all select 'newborn_contacts', count(*) from newborn_contacts;
