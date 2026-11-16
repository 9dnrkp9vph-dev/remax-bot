# tests/crm/test_team_gsync.py — [16/11 אייל: 'שתוסיף ל-CRM מי מסונכרן עם המייל'] במסך הצוות:
# חשבון ה-Google המקושר ומצב סנכרון היומן, לפי כל הטלפונים של האדם, בלי קריאה ל-Google לכל שורה.
import os, sys, re, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, ck, _SRC
import _load
ns = load("crm_gsync")
g = ns["crm_gsync"]
GA = {"a@gmail.com": {"phone": "0501111111", "refresh_token": "rt1", "ts": 10},
      "old@gmail.com": {"phone": "0501111111", "ts": 50},                       # בלי טוקן — לא גובר על a
      "b@gmail.com": {"phone": "0522222222", "ts": 5},                          # מקושר בלי יומן
      "c@gmail.com": {"phone": "0533333333", "refresh_token": "rt3", "cal_off": True, "ts": 5},
      "d@gmail.com": {"phone": "0544444444", "refresh_token": "rt4", "ts": 5}}
ck(g(["501111111", "599999999"], GA) == ("a@gmail.com", "מסונכרן"), g(["501111111"], GA))
ck(g(["522222222"], GA) == ("b@gmail.com", "מחובר בלי יומן"), g(["522222222"], GA))
ck(g(["533333333"], GA) == ("c@gmail.com", "יומן כבוי"), g(["533333333"], GA))
ck(g(["544444444"], GA, expired={"d@gmail.com"}) == ("d@gmail.com", "פג — לחבר מחדש"), "expired")
ck(g(["555555555"], GA) == ("", "לא מחובר"), "none")
ck(g([], GA) == ("", "לא מחובר"), "no phones")
# טלפון שני של האדם (כניסה) — נמצא דרך כל הטלפונים
ck(g(["599999999", "544444444"], GA)[0] == "d@gmail.com", "any phone")

# העמודות והתצוגות במודול הצוות
i = _SRC.index('    "team": {\n        "title": "צוות"'); seg = _SRC[i:i + 1600]
ck('("gmail", "חשבון Google", "text")' in seg and '("gsync", "סנכרון יומן", "status")' in seg, "columns")
ck('"gsync"' in seg.split('"default_cols"')[1].split("]")[0], "gsync shown by default")
ck('("gsync_ok", "מסונכרנים עם Google")' in seg and '("gsync_no", "לא מסונכרנים")' in seg, "views")
j = _SRC.index('    "team": {"all": lambda r, t'); vs = _SRC[j:j + 1400]
ck('"gsync_ok"' in vs and '"gsync_no"' in vs, "view filters")
# הצבע: מסונכרן ירוק, פג אדום
ck("'מסונכרן'" in _SRC[_SRC.index("function stCls(l)"):_SRC.index("function stCls(l)") + 400], "stCls green")
print("team_gsync OK", _load.n)
