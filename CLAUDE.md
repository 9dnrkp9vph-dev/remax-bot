# CLAUDE.md — אֶפִי (Effie) / Family Bot — כללי עבודה מחייבים

> מסמכי הבסיס (לקרוא לפני עבודה על מסכים): `docs/handoff/effie-claude-code-prompt.md` (המפרט),
> `docs/handoff/effie-supabase-sync-map.md` (מיפוי מסך→טבלה), `docs/handoff/design/effie-design.dc.html` (מקור האמת הוויזואלי).

## ⚠️ מצב השקה — WHITE-LABEL בלבד
המותג "אֶפִי" **עדיין לא נחשף**. קבוע `BRAND_REVEAL=false`:
- כותרת עליונה, מסך כניסה, לוגו ← מציגים את **המשרד**: `offices.name` ("רימקס פמילי") + לוגו מ-`offices.settings.logo_url`.
- כש-`BRAND_REVEAL=true` ← המותג אפי (שם + לוגו האוריגמי `docs/handoff/effie-logo.svg`) בכל מקום.
- חריגים שנשארים ניטרליים גם אחרי החשיפה: סיכומי AI ← **"סיכום חכם"**; מסך הצ'אט ← **"העוזר החכם"** (לא "אפי סיכם").
- שם המוצר (לאחר חשיפה): **אֶפִי** (בלי דגש בפ'). שם המשרד תמיד מ-`offices.name` — **לעולם לא hardcoded**.

## 🎨 עיצוב (קבוע — אין להוסיף צבעים/סגנונות)
- **צבעים:** קרם `#F2EFE7` (רקע) · נייבי `#1E3A5F` (כותרות/טאב פעיל; גרדיאנט `#0E1D33→#2C4C77`) · כחול פעולה `#2E6BD6` · זהב `#C29435`/`#E4C56B` (AI/החתמה/נכס נולד) · ירוק `#1FAF5E` (וואטסאפ/טלפון/נחתם) · אדום `#C24040` (**מחיקה בלבד**).
- צ'יפים: זהב `#F6EEDB` · כחול `#EAF0FA` · ירוק `#E7F7EE` · אדום `#FBEDED` · אפור `#F0EDE3`. טקסט משני `#8B8F99`/`#5B6472`, גבולות `#E9E4D8`/`#DCD6C8`.
- **פונט Heebo (400–800), RTL מלא.** כרטיסים לבנים, radius 20-22, צל `0 6px 20px rgba(30,58,95,.06)`.
- **היררכיית כפתורים:** כחול=ראשי · זהב=הדגשה/AI/החתמה · ירוק=וואטסאפ/טלפון · לבן+מסגרת `#DCD6C8`=משני · אדום=מחיקה (אייקון פח 42×42 על `#FBEDED` בלבד, לעולם לא כפתור מלא).
- מינימום מגע 44px · **אין אימוג'י ב-UI** (לוגו וקטורי בלבד) · אין מסכי-ריק יבשים (אייקון עיגול זהב 72px + כותרת + הסבר + CTA).
- **ניווט תחתון, מימין לשמאל:** שיחות · קונים · **בית** (אריח נייבי מורם 44×44 radius 15, טבעת זהב כשפעיל) · חתימות · נכס נולד (לוגו + badge מונה). "נכסים" ו"תהליכים ועסקאות" — ממסך הבית ומתפריט הצד, לא טאבים.

## 🗄️ נתונים וארכיטקטורה
- **מחירים/תאריכים נשמרים כטקסט גולמי** (parity עם הגיליון) — פורמט (₪, פסיקים, dd/mm) בצד לקוח בלבד.
- **כתיבה ל-DB דרך השרת בלבד** (service_role). קליינט = קריאה + Realtime בלבד (JWT עם claim `office_id`, RLS אוכף).
- **מולטי-טננט:** הכל מסונן `office_id`. RE/MAX Family = `11111111-1111-4111-8111-111111111111`.
- **טבלת המשתמשים הקיימת היא `users`** (לא `agents` כפי שכתוב במפרט §6) — role: admin/coordinator/agent. להשתמש בקיים.
- טבלאות קיימות (אל תיגע בסכימות): offices, users, newborn_listings/status/notes/contacts, calls, hidden_calls, signatures, buyers (+RPC buyers_delete_row), external_exclusives, properties, office_config.
- חוסרים שנותרו להוסיף (מיגרציות חדשות בלבד): `buyers.status`, `deals`, `announcements`+`announcement_reads`, `users.coordinator_id`, `activity_log`, ובהמשך `daily_briefs`.
- **הרשאות תצוגה בכל מסך:** מנהל=כל המשרד · מתאמת=הסוכנים המשויכים לה · סוכן=רק שלו.

## 🔧 כללי עבודה בריפו (חובה — נלמדו בדם)
- **הקובץ הקנוני:** `/Users/eyal/Documents/GitHub/remax-bot/app.py`. יש עותקים ישנים במקומות אחרים — **תמיד נתיב מוחלט**, לעולם לא נתיב יחסי (ה-cwd מתאפס בין פקודות).
- אימות אחרי כל שינוי: `python3 -c "import ast; ast.parse(open('<נתיב מלא>/app.py').read())"` + חילוץ ה-JS מ-FAMILY_BOT_HTML ו-`node --check` + יבוא מודול אמיתי (דורש env דמה: MAYTAPI_TOKEN/MAYTAPI_PHONE_ID/MAYTAPI_PRODUCT_ID/CLAUDE_API_KEY).
- **סודות ב-Render env / Script Properties בלבד** — לעולם לא בקוד או ב-git. קובצי קוד עם טוקנים (קוד.gs המלא) — scratchpad בלבד, לא בריפו.
- לא לגעת ב-MOBILE-PATCH (fbAutoLogin/fbDoBio/fbShowLock) ולא ב-whatsapp:// של הסוכן.
- דגלי מקור נתונים (Render env): NEWBORN/CALLS/SIGNATURES/BUYERS/EXCL/PROPS/CONFIG_SOURCE = sheets|supabase. הגיליון עדיין מקור אמת לכתיבות (דרך Apps Script, עם כתיבה כפולה + סנכרון-השלמה כל דקה/30ד').
- דפלוי: Eyal בלבד (GitHub Desktop → Render Manual Deploy). פריסות Apps Script: 2-3 דקות הבהוב אחרי — רק בשעות שקטות.
- האפליקציה הנוכחית (FAMILY_BOT_HTML) משרתת סוכנים בפרודקשן — **אסור לשבור אותה** במהלך בניית אפי.

## 📓 יומן החלטות (להוסיף כל החלטה חדשה מיד)
- 2026-07-05: סשן 0 בוצע — handoff ב-docs/handoff/, קובץ העיצוב נקרא effie-design.dc.html.
- 2026-07-05: **הוחלט (אייל): אפי חיה במסלול /v2 באותו שרת**, במקביל לאפליקציה הקיימת.
- 2026-07-05: סשן 1 בוצע — מימוש ב-**מודול נפרד `effie_v2.py`** (וניל, אותו שרת); app.py נוגע במינימום:
  רישום `effie_v2.register(app, globals())` עטוף try/except לפני STARTUP + פרמטר `next=v2` לזרימת Google
  (חזרה ל-/v2/home במקום /app). אותם טוקנים/סשנים (fbTok) לשתי האפליקציות — כניסה אחת.
- 2026-07-05: מיגרציות החוסרים בקובץ חדש `supabase_schema_effie.sql` (buyers.status, deals,
  announcements+announcement_reads, users.coordinator_id, activity_log) — **ממתין לאייל להריץ ב-SQL Editor**.
- 2026-07-05: מסכי /v2 (כניסה), /v2/home (זמני עד סשן 2), /v2/admin (ניהול 31a). הניהול משתמש ב-API הקיים
  (/api/dev/people, /api/dev/role, /api/dev/coordinators, /api/dev/suspend) + חדשים תחת /v2/api/*
  (overview, invite בוואטסאפ, policy, office). מדיניות נשמרת בקונפיג תחת `v2_policies`
  (transcribe, shtaf_sharing, share_buyers, require_followup, who_contacted_admins_only) — האכיפה במסכים הבאים.
- ממתין לאישור/סשנים הבאים: אכיפת המדיניות במסכים ·
  "פעילה עכשיו" בשורת חבר צוות (דורש presence) · חיבור מסך /v2/admin ל-users בסופאבייס במקום הקונפיג (אחרי המעבר).
- 2026-07-05: המיגרציות הורצו ואומתו ב-Supabase ע"י אייל (4 טבלאות + 2 עמודות).
- 2026-07-05: סשן 2 בוצע — מסך הבית (14a) + בריף הבוקר (13a) ב-/v2/home בתוך effie_v2.py:
  סטורי 4 כרטיסים (פתיחה ← קונים בלי שיבוץ ← חתימות ← נכס נולד), נפתח פעם ביום (localStorage
  `v2BriefSeen` — בשלב זה, daily_briefs יגיע עם ה-Edge Function), דשבורד נטען ברקע בזמן הסטורי.
  נתונים מ-API קיימים בלבד: /api/report?period=week, /api/my/buyers, /api/my/properties, /api/newborn
  (badge המונה בניווט כבר מחובר מכאן). תפריט צד מינימלי (ניהול/אפליקציה קיימת/התנתקות) — הגרסה
  המלאה בסשן התפריט. טאבים/פעולות שטרם נבנו מציגים toast "בסשן הקרוב" — להחליף בקישורים אמיתיים בסשנים 3–8.
- 2026-07-05: שדרוגי מסך הניהול (בקשת אייל): (1) בגיליון חבר צוות — בקרת "נכס נולד: ממתי רואה מודעות"
  (ברירת מחדל של המשרד / מספר ימים מותאם / מוסתר, דרך /api/dev/agent_update newbornDelay);
  (2) הצגת המספר האישי + הווירטואלי בגיליון החבר; (3) מתג "שיתוף קונים בין סוכנים" הוחלף בכרטיס
  **"צוותי שיתוף"** על מנגנון teams הקיים — חברי צוות רואים הכל אחד של השני. הרחבה ב-app.py:
  `_deals_can_see` מכבד עכשיו גם צוות (תהליכים ועסקאות; שיחות/קונים/חתימות/נכסים/דוחות כבר כובדו).
