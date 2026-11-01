-- [SOCIAL-VIDEO 02/11] סרטוני סטורי + ריל לנכסי המשרד — להריץ ב-Supabase SQL Editor (אייל)
create table if not exists social_videos (
  id               uuid primary key default gen_random_uuid(),
  office_id        uuid not null,
  property_key     text not null,
  addr_key         text,
  floor            text,
  trigger          text not null default 'manual',      -- auto / manual
  mode             text not null default 'preview',     -- preview / publish
  status           text not null default 'rendering',   -- rendering/failed/preview/pending/approved/skipped/expired/published/partial
  by_phone         text,
  recipients       jsonb default '[]'::jsonb,           -- last9 של מי שקיבל אישור
  review_token     text,
  review_due       boolean default false,
  sent_at          timestamptz,
  decided_by       text,
  decided_at       timestamptz,
  publish_at       timestamptz,
  ai               boolean default false,
  ai_model         text,
  ai_cost_usd      numeric,
  video_token      text,
  music            text,
  texts            jsonb,
  ig_story_id      text, ig_story_status text,
  ig_reel_id       text, ig_reel_permalink text, ig_reel_status text,
  fb_story_id      text, fb_story_status text,
  fb_reel_id       text, fb_reel_permalink text, fb_reel_status text,
  error            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index if not exists social_videos_office_created on social_videos (office_id, created_at desc);
create index if not exists social_videos_review_token on social_videos (review_token);
alter table social_videos enable row level security;   -- בלי policies: שרת בלבד (service_role)

create table if not exists social_links (
  code           text primary key,
  office_id      uuid not null,
  video_id       uuid,
  property_key   text,
  channel        text,
  clicks         int not null default 0,
  last_click_at  timestamptz,
  created_at     timestamptz not null default now()
);
alter table social_links enable row level security;
