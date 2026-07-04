-- ============================================================================
-- Family Bot — Supabase schema, שלב 5: "קונפיג" (פירוק הבלוב)
-- ----------------------------------------------------------------------------
-- הבלוב היחיד (agents/roles/nbStatus/...) מתפרק לשורה-לכל-מפתח:
-- כתיבת מפתח אחד לא נוגעת באחרים — סוף לסכנת הדריסה של כל הקונפיג.
-- מריצים פעם אחת ב-SQL Editor (Run). בטוח להרצה חוזרת.
-- ============================================================================

create table if not exists office_config (
  id         uuid primary key default gen_random_uuid(),
  office_id  uuid not null references offices(id) on delete cascade,
  key        text not null,           -- agents / roles / nbStatus / nbNotes / gauth / ...
  value      jsonb,                   -- הערך כפי שהוא (אובייקט/מערך/מספר)
  updated_at timestamptz not null default now(),
  unique (office_id, key)
);
create index if not exists office_config_office_key on office_config (office_id, key);

-- אבטחה: מכיל טוקנים (gauth) — RLS פעיל *בלי אף policy* = גישה דרך service key בלבד.
-- שום דפדפן/anon לא קורא את הטבלה הזו.
alter table office_config enable row level security;

select 'office_config' as t, count(*) from office_config;
