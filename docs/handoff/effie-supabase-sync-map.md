# אֶפִי — מפת סנכרון: העיצוב ↔ סכימת Supabase

עודכן לפי הקבצים: `supabase_schema.sql` (נכס נולד + offices/users), `_calls`, `_signatures`, `_buyers`, `sales_seed_2026.json`.

## ארכיטקטורה שצריך שֿClaude Code יכיר
- **מולטי-טננט**: כל הנתונים מסוננים לפי `office_id`. RE/MAX Family = `11111111-1111-4111-8111-111111111111`.
- **מיגרציה** מ-Google Sheets + Fireberry → Supabase. שדות רבים נשמרים כ**טקסט גולמי** ("parity") — מחיר, תאריכים. **הפורמט נעשה באפליקציה** (₪, פסיקים) — בדיוק כמו בעיצוב.
- **כתיבה דרך השרת בלבד** (service_role). הדפדפן מקבל **קריאה בלבד** דרך RLS לפי claim‏ `office_id` ב-JWT. → העיצוב צריך להניח **Optimistic UI + server actions**, לא כתיבה ישירה מהקליינט.
- **Realtime מופעל** על `newborn_listings/status/notes/contacts`, `calls`, `hidden_calls`, `signatures`, `buyers`. → כל אינדיקטורי ה"חי/מתעדכן" בעיצוב **נתמכים באמת**.
- **White-label**: `offices.name` + `offices.settings` (jsonb). מתחבר ישירות להפרדה שעשינו: `אֶפִי` = שם האפליקציה (קבוע), `officeName` = `offices.name` (משתנה לכל משרד).

## מסכים שמתחברים חלק (הטבלה כבר קיימת)
| מסך בעיצוב | טבלה | הערות סנכרון |
|---|---|---|
| **נכס נולד** | `newborn_listings` | `owner_name`+`owner_phone` — **המזכירה מעדכנת יומית**, בדיוק כפי שאמרת. `price` טקסט. |
| ותק (חודשים 1–7+) | `newborn_status.newborn_delay` / `users.newborn_delay` | `NULL`=ברירת מחדל משרד, `-1`=מוסתר. |
| סטטוס פר-סוכן (פגישה/פולואפ/לא מעוניין) | `newborn_status.status` | `meeting`/`followup`/`not_interested`. |
| הערות משותפות (כולם רואים) | `newborn_notes` | מחיקה לפי `ts`. |
| **"מי פנה / כמה"** (מנהלים בלבד) | `newborn_contacts` | ייחודיות (נכס, סוכן) = "כבר פנו". ההחלטה שלנו (מנהלים בלבד) תקפה. |
| **פגישות ופולואפ** (הגיליון התחתון) | `newborn_status` (status=meeting/followup) + `cal` jsonb | ה-`cal` מחזיק אירועי **Google Calendar** — מתחבר להחלטה שהכניסה = חשבון Google לסנכרון יומן. |
| **שיחות** | `calls` | `status` ANSWER/NOANSWER, `transcript_summary` (=סיכום אפי), `agent`. |
| **שיחות מוסתרות** ("נקה את הרשימה") | `hidden_calls` | בדיוק הפיצ'ר שבנינו. |
| **חתימות** | `signatures` | `deal_type`, `client_name`, `commission_pct` (בזרימת SMS = **קישור למסמך החתום**). |
| **קונים** | `buyers` | `raw`: `{date,name,phone,budget,summary,agent,agent_phone,search}`. פעולות לפי `sheet_row` (מחיקה מזיזה שורות — `buyers_delete_row`). |
| **דוחות / עסקאות** | `sales_seed_2026.json` | `agents[]`, `side1`/`side2` (**עסקה דו-צדדית!**), `sale_price`, `close_date`, `notes`=כתובת. מזין פילוח לפי צד (מוכר/קונה/שוכר/משכיר) ואת המובילים. |
| **ניהול / מפתח** | `users` + `offices` | `role`: admin/coordinator/agent, `suspended`, `aliases[]`. תואם 1:1 למסך 31a. |
| מתאמת רואה את הסוכנים שלה | `role='coordinator'` | צריך שיוך coordinator→agents (ראה חוסר #4). |

## חוסרים — צריך טבלה/עמודה חדשה (להוסיף לפני שהמסך עובד)
1. **סטטוס קונה** — `buyers.raw` **אין בו סטטוס**. העיצוב הוסיף מחזור חיים (פעילים/חמים/בהקפאה/סגרו) ותג "חם". → להוסיף `status` ל-`buyers.raw` או עמודה ייעודית.
2. **תהליכים ועסקאות (פייפליין פתוח)** — טבלת `deals` חדשה (שלב, מחיר מבוקש, עו"ד, צד 1/צד 2, שיוך לנכס/קונה). **החלטה: אין ייבוא היסטוריה מאקסל** — הזנה ידנית באפליקציה בלבד (טופס 27a). `sales_seed_2026.json` משמש רק כנתוני דמו לדוחות.
3. **עדכונים למשרד** — אין טבלה. → `announcements` (+ `announcement_reads` לאישורי "נקראה ע"י X מתוך Y", ונעיצה `pinned`).
4. **שיוך מתאמת→סוכנים** — `users` יש `role='coordinator'` אבל אין קשר מי-משויך-למי. → עמודה `coordinator_id uuid references users(id)` על סוכן, או טבלת קישור.
5. **יומן שימוש במערכת** — קיים באפליקציה ("עדכונים — שימוש במערכת", 18 פעולות אחרונות, חי) אבל אין לו טבלה בסכימה. → `activity_log` (office_id, user_name, action, target, ts) + Realtime. למנהל בלבד.
6. **בריף בוקר / אפי AI** — נגזרים (אין צורך בטבלה). אופציונלי: `briefs`(seen state) ו-`ai_messages`(היסטוריית צ'אט). כרגע אפשר localStorage לבריף.

## סדר עבודה מומלץ ל-Claude Code (מהקל למורכב)
1. **תשתית**: offices/users כבר קיימים → מסך כניסה (Google+SMS) + בחירת office_id ל-JWT + מסך ניהול (31a).
2. **קריאה בלבד מ-Realtime** (הכי קל, אין כתיבה): נכס נולד, שיחות (+מוסתרות), חתימות, קונים — כל אלה כבר עם טבלה ו-Realtime.
3. **כתיבות פשוטות דרך השרת**: סטטוס נכס נולד, הערות, "פנו", הסתרת שיחה, הוספת קונה.
4. **חוסרים**: להוסיף buyers.status, טבלת deals, טבלת announcements, שיוך coordinator.
5. **נגזרים**: דוחות (אגרגציה), בריף בוקר, אפי AI.

## עקרונות שנשמור בעיצוב (כבר תואמים — לא לשנות)
- מחירים/תאריכים כטקסט גולמי → פורמט בצד הלקוח.
- אֶפִי = מותג האפליקציה; שם המשרד נפרד (officeName).
- עמלת שת"פ ירדה מהעיצוב — נכון: העמלה חיה על `signatures.commission_pct`, לא על נכס שת"פ.
- אינדיקטורי "חי" נתמכים ב-Realtime אמיתי.
