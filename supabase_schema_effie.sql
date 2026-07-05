-- ============================================================================
-- אֶפִי (Effie) — Supabase schema, סשן 1: השלמת החוסרים בלבד
-- ----------------------------------------------------------------------------
-- מריצים פעם אחת ב-SQL Editor של Supabase (Run). בטוח להרצה חוזרת
-- (IF NOT EXISTS / חריגים נבלעים). אף שינוי בטבלאות הקיימות מעבר להוספות
-- שהוגדרו ב-effie-supabase-sync-map.md (חוסרים 1–5):
--   1. buyers.status            — מחזור חיים לקונה (פעילים/חמים/בהקפאה/סגרו)
--   2. deals                    — תהליכים ועסקאות (הזנה ידנית בלבד, אין ייבוא)
--   3. announcements (+reads)   — עדכונים למשרד + אישורי קריאה
--   4. users.coordinator_id     — שיוך סוכן ← מתאמת
--   5. activity_log             — יומן שימוש במערכת (למנהל בלבד)
-- מחירים/תאריכים כטקסט גולמי (parity) — הפורמט בצד לקוח בלבד.
-- כתיבה דרך השרת בלבד (service_role); לדפדפן קריאה בלבד דרך RLS.
-- ============================================================================

-- ── 1) buyers.status — עמודה חדשה בלבד, לא נוגעים בשאר הטבלה ────────────────
alter table buyers add column if not exists status text not null default 'active';

do $$
begin
  alter table buyers add constraint buyers_status_chk
    check (status in ('active','hot','frozen','closed'));
exception when duplicate_object then null;
end $$;

create index if not exists buyers_office_status_idx on buyers (office_id, status);

-- ── 4) users.coordinator_id — שיוך סוכן למתאמת (על שורת הסוכן) ──────────────
alter table users add column if not exists coordinator_id uuid references users(id) on delete set null;

create index if not exists users_coordinator_idx on users (coordinator_id);

-- ── 2) deals — תהליכים ועסקאות (מפרט 9 + 9א + טופס 27a) ────────────────────
create table if not exists deals (
  id              uuid primary key default gen_random_uuid(),
  office_id       uuid not null references offices(id) on delete cascade,
  kind            text not null default 'process'
                  check (kind in ('process','deal')),        -- תהליך פתוח / עסקה
  status          text not null default 'open'
                  check (status in ('open','closed','canceled')),
  stage           text,                                      -- שלב בתהליך ("אצל עו\"ד"...)
  address         text,
  asking_price    text,                                      -- מחיר מבוקש — טקסט גולמי (parity)
  sale_price      text,                                      -- מחיר מכירה — טקסט גולמי
  close_date      text,                                      -- dd/mm/yyyy — טקסט גולמי
  agent1          text,
  agent1_side     text,                                      -- מייצג: seller/buyer/both/landlord/tenant
  agent2          text,
  agent2_side     text,
  side1           text,                                      -- פילוח דוחות: seller/buyer/landlord/tenant
  side2           text,
  lawyer          text,
  commission      text,                                      -- הסכום הסופי; ברירת המחדל (2%+מע"מ) מחושבת בצד לקוח
  commission_manual boolean not null default false,          -- true = נערך ידנית (דורס את החישוב)
  contract_path   text,                                      -- Storage: חוזה חתום
  property_id     uuid,                                      -- שיוך רופף לנכס (אופציונלי)
  buyer_id        uuid,                                      -- שיוך רופף לקונה (אופציונלי)
  notes           text,
  created_by      text,                                      -- שם הסוכן שהזין
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists deals_office_idx        on deals (office_id, status, created_at desc);
create index if not exists deals_office_agent_idx  on deals (office_id, agent1);

alter table deals enable row level security;

drop policy if exists office_read_deals on deals;
create policy office_read_deals on deals for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

-- ── 3) announcements + announcement_reads — עדכונים למשרד (מפרט 9ד) ─────────
create table if not exists announcements (
  id           uuid primary key default gen_random_uuid(),
  office_id    uuid not null references offices(id) on delete cascade,
  author_name  text not null,
  author_role  text,                                         -- admin/coordinator (רק הם מפרסמים)
  body         text not null,
  pinned       boolean not null default false,               -- הודעה נעוצה (מסגרת זהב)
  is_system    boolean not null default false,               -- עדכון מערכת אוטומטי (מסגרת מקווקוות)
  link_target  text,                                         -- קישור לנכס בתוך הודעה (מזהה/כתובת)
  created_at   timestamptz not null default now()
);

create index if not exists announcements_office_idx
  on announcements (office_id, pinned desc, created_at desc);

alter table announcements enable row level security;

drop policy if exists office_read_announcements on announcements;
create policy office_read_announcements on announcements for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

create table if not exists announcement_reads (
  id              uuid primary key default gen_random_uuid(),
  office_id       uuid not null references offices(id) on delete cascade,
  announcement_id uuid not null references announcements(id) on delete cascade,
  reader_phone    text not null,                             -- 9 ספרות אחרונות — המזהה העקבי במערכת
  reader_name     text,
  read_at         timestamptz not null default now(),
  unique (announcement_id, reader_phone)
);

create index if not exists announcement_reads_ann_idx on announcement_reads (announcement_id);

alter table announcement_reads enable row level security;

drop policy if exists office_read_announcement_reads on announcement_reads;
create policy office_read_announcement_reads on announcement_reads for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

-- ── 5) activity_log — יומן שימוש במערכת (מפרט 9ו, למנהל בלבד) ───────────────
create table if not exists activity_log (
  id         bigint generated always as identity primary key,
  office_id  uuid not null references offices(id) on delete cascade,
  user_name  text not null,
  role       text,
  phone      text,                                           -- 9 ספרות אחרונות
  action     text not null,                                  -- "כניסה", "הנכסים שלי"...
  target     text,
  ts         timestamptz not null default now()
);

create index if not exists activity_log_office_ts_idx on activity_log (office_id, ts desc);

alter table activity_log enable row level security;

-- קריאה למנהל בלבד (claim‏ role ב-JWT); הכתיבה תמיד דרך השרת (service_role)
drop policy if exists admin_read_activity_log on activity_log;
create policy admin_read_activity_log on activity_log for select
  using (
    office_id = (auth.jwt() ->> 'office_id')::uuid
    and coalesce(auth.jwt() ->> 'role', '') in ('admin','developer')
  );

-- ── Realtime — פיד חי לעדכונים וליומן השימוש ────────────────────────────────
do $$
begin
  begin
    alter publication supabase_realtime add table deals;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table announcements;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table activity_log;
  exception when duplicate_object then null;
  end;
end $$;

select 'deals' as t, count(*) from deals
union all select 'announcements', count(*) from announcements
union all select 'announcement_reads', count(*) from announcement_reads
union all select 'activity_log', count(*) from activity_log;
