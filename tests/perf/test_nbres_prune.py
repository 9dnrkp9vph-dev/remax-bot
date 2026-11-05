"""[05/11 זיכרון] מטמון תוצאות נכס נולד (nbres) לא נוקה מעולם: כל שינוי מעלה גרסה ומשאיר את הישנות, וכל חיפוש/
משתמש מפתח חדש — 154 עותקים ≈510MB בבוקר עבודה (לוג mem:). אחרי התיקון: העלאת גרסה מנקה, ושמירה גוזמת ישנים.
CLAUDE_API_KEY=dummy WARMUP_ON_BOOT=0 CONFIG_SOURCE=sheets python3 tests/perf/test_nbres_prune.py"""
import os, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import app
fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

app._TTL_CACHE.clear()
app._cache_put("nbres:0:111:::None:None:None:", {"x": 1})
app._cache_put("nbres:0:222:::None:None:None:", {"x": 2})
app._cache_put("newborn_rows", [1])
app._nb_result_bump()
check(not [k for k in app._TTL_CACHE if k.startswith("nbres:")], "העלאת גרסה מוחקת את כל תוצאות nbres")
check("newborn_rows" in app._TTL_CACHE, "מפתחות אחרים לא נגעים")
check(app._NB_RESULT_VER[0] == 1, "הגרסה עלתה")

old = time.time() - 3600
app._TTL_CACHE["nbres:1:333:::None:None:None:"] = (old, {"x": 3})
app._nb_cache_put("nbres:1:444:::None:None:None:", {"x": 4})
check("nbres:1:333:::None:None:None:" not in app._TTL_CACHE, "שמירה גוזמת תוצאה ישנה")
check("nbres:1:444:::None:None:None:" in app._TTL_CACHE, "התוצאה החדשה נשמרה")
check(app._cache_get("nbres:1:444:::None:None:None:", 90) == {"x": 4}, "קריאה עובדת")

src = open(os.path.join(os.path.dirname(app.__file__), "app.py"), encoding="utf-8").read()
check(src.count("_NB_RESULT_VER[0] += 1") == 1, "כל העלאות הגרסה עוברות דרך _nb_result_bump")
v2 = open(os.path.join(os.path.dirname(app.__file__), "effie_v2.py"), encoding="utf-8").read()
check('G["_NB_RESULT_VER"][0] += 1' not in v2 and 'G.get("_nb_result_bump")' in v2, "קליטת יד2 (effie_v2) מנקה דרך _nb_result_bump")
print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
