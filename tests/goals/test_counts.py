import sys, os, datetime, calendar
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import goals as g

ALIAS = {"בינימין אביטן": "בנימין אביטן"}
def canon(n):
    s = " ".join(str(n or "").split())
    return ALIAS.get(s, s)

DAY = datetime.date(2026, 10, 28)
B = g.day_bounds(DAY)
A = "בנימין אביטן"
N = 0
def ok():
    global N
    N += 1

def ep(iso):
    return datetime.datetime.fromisoformat(iso).timestamp()

def src(**kw):
    base = {"nb": {}, "buyers": [], "bpages": [], "activity": [], "reviews": [], "missed": []}
    base.update(kw)
    return base

def test_day_bounds_il():
    assert B[0] == ep("2026-10-28T00:00:00+02:00"), B
    assert B[1] == ep("2026-10-29T00:00:00+02:00")
    act = [{"ts": ep("2026-10-28T23:30:00+02:00"), "name": A, "action": g.ACT_REMIND, "detail": "501111111"},
           {"ts": ep("2026-10-29T00:10:00+02:00"), "name": A, "action": g.ACT_REMIND, "detail": "502222222"}]
    # the caller filters by day; parse_ts must place them correctly
    inside = [a for a in act if B[0] <= a["ts"] < B[1]]
    assert len(inside) == 1
    ok()

def test_targets_override():
    cfg = {"v2_goals": {"default": {"meetings": 1, "reviews": "x"}, "agents": {A: {"buyers": 5, "past_clients": 99}}}}
    t = g.targets_for(cfg, "בינימין אביטן", canon)
    assert t == dict(g.DEFAULTS, meetings=1, buyers=5, past_clients=50, reviews=2), t
    assert g.targets_for({}, "x", canon) == g.DEFAULTS
    ok()

def test_meetings_rules():
    nb = {
        "a": {"status": "meeting", "agent": A, "pkey": "N:1", "meeting_at": ep("2026-10-28T10:00:00+02:00"), "by": "מתאמת"},
        "b": {"status": "meeting", "agent": A, "pkey": "manual:xyz", "meeting_at": ep("2026-10-28T11:00:00+02:00")},
        "c": {"status": "meeting", "agent": A, "pkey": "N:2", "meeting_at": ep("2026-10-27T11:00:00+02:00")},
    }
    r = g.count_agent(A, B, src(nb=nb), canon)
    assert r["meetings"] == 1, r
    ok()

def test_buyer_date_formats():
    bs = [{"row": 1, "date": "28/10/2026", "agent": A}, {"row": 2, "date": "2026-10-28T09:15:00+02:00", "agent": A},
          {"row": 3, "date": "", "agent": A}, {"row": 4, "date": "27/10/2026", "agent": A},
          {"row": 5, "date": "28/10/2026 14:30", "agent": "אחר"}]
    r = g.count_agent(A, B, src(buyers=bs), canon)
    assert r["buyers"] == 2, r
    ok()

def test_bpage_today():
    bs = [{"row": 1, "date": "28/10/2026", "agent": A}, {"row": 2, "date": "28/10/2026", "agent": A},
          {"row": 3, "date": "01/10/2026", "agent": A}]
    pages = [{"row": 1, "last_sent_at": "2026-10-28T08:00:00+00:00", "created_at": "2026-10-01T08:00:00+00:00"},
             {"row": 2, "last_sent_at": "2026-10-20T08:00:00+00:00"},
             {"row": 3, "last_sent_at": "2026-10-28T08:00:00+00:00"}]
    r = g.count_agent(A, B, src(buyers=bs, bpages=pages), canon)
    assert r["bpage"] == 1, r
    ok()

def test_bpage_none_row_skipped():
    bs = [{"row": None, "date": "28/10/2026", "agent": A}]
    pages = [{"row": None, "last_sent_at": "2026-10-28T08:00:00+00:00"}]
    r = g.count_agent(A, B, src(buyers=bs, bpages=pages), canon)
    assert r["bpage"] == 0, r
    ok()

def test_past_clients_distinct():
    act = [{"name": A, "action": g.ACT_REMIND, "detail": "501111111"},
           {"name": A, "action": g.ACT_REMIND, "detail": "501111111"},
           {"name": A, "action": g.ACT_REMIND, "detail": "502222222"},
           {"name": A, "action": g.ACT_REVIEW_MANUAL, "detail": "503333333"},
           {"name": "מנהל", "action": g.ACT_REMIND, "detail": "504444444"}]
    r = g.count_agent(A, B, src(activity=act), canon)
    assert r["past_clients"] == 2, r
    ok()

def test_reviews_count():
    rv = [{"id": 1, "agents": [A], "at": "2026-10-28T07:00:00Z", "created_by": "מנהל"},
          {"id": 2, "agents": [A], "at": "2026-10-27T07:00:00Z"},
          {"id": 3, "agents": ["אחר"], "at": "2026-10-28T07:00:00Z"}]
    r = g.count_agent(A, B, src(reviews=rv), canon)
    assert r["reviews"] == 1, r
    ok()

def test_name_variants_count():
    bs = [{"row": 1, "date": "28/10/2026", "agent": "בינימין  אביטן"}]
    r = g.count_agent(A, B, src(buyers=bs), canon)
    assert r["buyers"] == 1
    ok()

def test_source_failure():
    r = g.count_agent(A, B, src(buyers=RuntimeError("x"), missed=[{"agent": A}]), canon)
    assert r["buyers"] is None and r["bpage"] is None
    assert r["meetings"] == 0 and r["reviews"] == 0 and r["missed"] == 1
    ok()

def test_followups():
    nb = {"a": {"status": "followup", "agent": A, "date": "2026-10-28", "done": True},
          "b": {"status": "followup", "agent": A, "date": "28/10/2026"},
          "c": {"status": "followup", "agent": A, "date": "2026-10-27"}}
    r = g.count_agent(A, B, src(nb=nb), canon)
    assert r["followups"] == {"due": 2, "done": 1}, r
    ok()

def test_parse_ts():
    assert g.parse_ts("1792000000") == 1792000000.0
    assert g.parse_ts(1792000000) == 1792000000.0
    assert g.parse_ts("28/10/2026 14:30") == ep("2026-10-28T14:30:00+02:00")
    assert g.parse_ts("2026-10-28T09:15:00") == ep("2026-10-28T09:15:00+02:00")
    assert g.parse_ts("junk") is None and g.parse_ts("") is None and g.parse_ts(None) is None
    ok()

def test_rollup():
    a = {"meetings": 1, "buyers": 2, "bpage": 1, "past_clients": 3, "reviews": None, "followups": {"due": 2, "done": 1}, "missed": 0}
    b = {"meetings": 2, "buyers": 0, "bpage": 0, "past_clients": 1, "reviews": 2, "followups": {"due": 1, "done": 1}, "missed": 1}
    tg = {"x": dict(g.DEFAULTS), "y": dict(g.DEFAULTS)}
    r = g.rollup({"x": a, "y": b}, tg)
    assert r["counts"]["reviews"] == 2 and r["partial"] is True
    assert r["counts"]["meetings"] == 3 and r["counts"]["followups"] == {"due": 3, "done": 2}
    assert r["targets"]["meetings"] == 4
    ok()

def test_nb_wa_dedup():
    """[GOALS2] פניות לנכס נולד: אותה מודעה פעמיים באותו יום = אחת; מחוץ ליום / סוכן אחר — לא."""
    act = [{"ts": ep("2026-10-28T10:00:00+02:00"), "name": "בינימין אביטן", "action": g.ACT_NB_WA, "detail": "הרצל 5"},
           {"ts": ep("2026-10-28T10:05:00+02:00"), "name": A, "action": g.ACT_NB_WA, "detail": "הרצל 5"},
           {"ts": ep("2026-10-28T11:00:00+02:00"), "name": A, "action": g.ACT_NB_WA, "detail": "בגין 3"},
           {"ts": ep("2026-10-27T11:00:00+02:00"), "name": A, "action": g.ACT_NB_WA, "detail": "ויצמן 1"},
           {"ts": ep("2026-10-28T11:00:00+02:00"), "name": "אחר", "action": g.ACT_NB_WA, "detail": "x"}]
    c = g.count_agent(A, B, src(activity=act), canon)
    assert c["nb_wa"] == 2, c
    assert g.count_agent(A, B, src(activity=RuntimeError("x")), canon)["nb_wa"] is None
    ok()

def test_buyers_sign_included():
    t = "28/10/2026 12:00"
    b = [{"agent": A, "date": t, "summary": "מהחתמת מתעניין · הרצל 5"}, {"agent": A, "date": t, "summary": "שיחה"}]
    c = g.count_agent(A, B, src(buyers=b), canon)
    assert c["buyers"] == 2 and c["buyers_sign"] == 1, c
    ok()

def test_listings_week_to_date():
    """גיוס נכסים: בלעדיות חתומה מתחילת השבוע (ראשון 25/10) עד היום; נכס ייחודי לפי עוגן-כתובת."""
    sigs = [{"agent": A, "address": "הרצל 5, קרית ביאליק", "type": "בלעדיות", "signed": True, "ts": "25/10/2026 09:00"},
            {"agent": A, "address": "הרצל 5 קריית ביאליק", "type": "בלעדיות", "signed": True, "ts": "27/10/2026 09:00"},
            {"agent": A, "address": "בגין 3", "type": "בלעדיות", "signed": True, "ts": "28/10/2026 09:00"},
            {"agent": A, "address": "ויצמן 1", "type": "בלעדיות", "signed": True, "ts": "24/10/2026 22:00"},   # שבוע קודם
            {"agent": A, "address": "סוקולוב 2", "type": "בלעדיות", "signed": False, "ts": "28/10/2026 09:00"},
            {"agent": A, "address": "הנשיא 4", "type": "מוכר", "signed": True, "ts": "28/10/2026 09:00"}]
    c = g.count_agent(A, B, src(sigs=sigs), canon)
    assert c["listings"] == 2, c
    d = g.count_days(A, [datetime.date(2026, 10, 25), datetime.date(2026, 10, 26)], src(sigs=sigs), canon)
    assert d["listings"] == 1, d                                 # עד סוף התקופה (26/10), לא סכום ימים
    assert g.count_agent(A, B, src(sigs=[]), canon)["listings"] == 0
    assert g.count_agent(A, B, src(sigs=RuntimeError("x")), canon)["listings"] is None
    ok()

def test_weekly_target_not_scaled():
    day = datetime.date(2026, 10, 30)    # שישי — משקל חצי
    # [GOALS3] יעד המשרד לחודש: אוקטובר 2026 = 23.5 ימי עבודה, 31 יום. סוכן יחיד מקבל את כל היעד.
    s = src(roster=[A], cfg={"v2_goals": {"office": {"meetings": 47, "listings": 31}}}, seen=[], sigs=[])
    p = g.build_periods(s, day, canon)
    assert p["today"]["rows"][0]["targets"]["listings"] == 7 and p["today"]["rows"][0]["targets"]["meetings"] == 1
    assert p["week"]["rows"][0]["targets"]["listings"] == 7 and p["week"]["rows"][0]["targets"]["meetings"] == 11
    ok()

for name, fn in list(globals().items()):
    if name.startswith("test_"):
        fn()
print("ok", N)
