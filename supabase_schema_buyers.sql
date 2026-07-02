-- ============================================================================
-- Family Bot — Supabase schema, שלב 4: "קונים"
-- ----------------------------------------------------------------------------
-- מריצים פעם אחת ב-SQL Editor של Supabase (Run). בטוח להרצה חוזרת.
-- הערה: פעולות הקונים באפליקציה עובדות לפי מספר שורה בגיליון (row) —
-- לכן הטבלה משמרת את מספר השורה, ומחיקה מזיזה את השורות שמעליה (RPC).
-- ============================================================================

create table if not exists buyers (
  id         uuid primary key default gen_random_uuid(),
  office_id  uuid not null references offices(id) on delete cascade,
  sheet_row  int  not null,          -- מספר השורה בגיליון (2 = הראשונה אחרי הכותרת)
  raw        jsonb not null default '{}'::jsonb,   -- {date,name,phone,budget,summary,agent,agent_phone,search}
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ייחודיות רגילה (נדרשת ל-upsert); הזזת השורות נעשית בשני צעדים דרך ערכים שליליים
do $$
begin
  alter table buyers add constraint buyers_office_row unique (office_id, sheet_row);
exception when duplicate_object then null;
end $$;

create index if not exists buyers_office_row_idx on buyers (office_id, sheet_row);

alter table buyers enable row level security;

drop policy if exists office_read_buyers on buyers;
create policy office_read_buyers on buyers for select
  using (office_id = (auth.jwt() ->> 'office_id')::uuid);

-- מחיקת שורה + הזזת כל השורות שאחריה מקום אחד למעלה (כמו deleteRow בגיליון)
create or replace function buyers_delete_row(p_office uuid, p_row int)
returns void
language plpgsql
security definer
as $$
begin
  delete from buyers where office_id = p_office and sheet_row = p_row;
  -- הזזה בשני צעדים דרך ערכים שליליים — נמנע מהתנגשות ייחודיות רגעית
  update buyers set sheet_row = -(sheet_row - 1), updated_at = now()
   where office_id = p_office and sheet_row > p_row;
  update buyers set sheet_row = -sheet_row
   where office_id = p_office and sheet_row < 0;
end $$;

-- הפונקציה זמינה רק ל-service_role (לא לדפדפן)
revoke execute on function buyers_delete_row(uuid, int) from public;
revoke execute on function buyers_delete_row(uuid, int) from anon;
revoke execute on function buyers_delete_row(uuid, int) from authenticated;

do $$
begin
  begin
    alter publication supabase_realtime add table buyers;
  exception when duplicate_object then null;
  end;
end $$;

select 'buyers' as t, count(*) from buyers;
