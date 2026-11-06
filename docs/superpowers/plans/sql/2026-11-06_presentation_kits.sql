-- [PRESENTATION-KIT 06/11] תיק פרזנטציה אישי לבעל נכס — להריץ ב-Supabase SQL Editor (אייל)
-- קריאה/כתיבה דרך השרת בלבד (service_role): RLS פעיל בלי policies.
create table if not exists presentation_kits (
  id               uuid primary key default gen_random_uuid(),
  office_id        uuid not null references offices(id),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  status           text not null,                      -- pending → approved | rejected | expired ; approved → sent
  agent_name       text,
  agent_phone      text,                               -- last9
  created_by       text,
  created_by_phone text,
  source           text,                               -- nb / meet / manual
  listing_key      text,
  owner_name       text,
  owner_phone      text,
  snapshot         jsonb,
  review_token     text unique,
  view_token       text unique,
  sent_review_at   timestamptz,
  review_due       boolean default false,
  decided_by       text,
  decided_at       timestamptz,
  reject_reason    text,
  sent_at          timestamptz,
  views            jsonb default '{}'::jsonb
);
create index if not exists presentation_kits_office_created on presentation_kits (office_id, created_at desc);
create index if not exists presentation_kits_agent on presentation_kits (office_id, agent_phone);
alter table presentation_kits enable row level security;   -- בלי policies: שרת בלבד (service_role)
