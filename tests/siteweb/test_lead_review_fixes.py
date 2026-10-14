"""תיקוני הביקורת הסופית של 'סוכן AI אישי' (14/10)."""
import effie_v2
from tests.siteweb.test_site_lead_inbound import _setup

MSG = "היי, אני מחפש/ת: דירה בביאליק"

def test_bp_url_outside_request_context(monkeypatch):            # C1: הליד רץ ב-thread בלי request
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    assert effie_v2.bpage_base_url() == "https://remax-bot.onrender.com"
    monkeypatch.setenv("APP_BASE_URL", "https://e.x/")
    assert effie_v2.bpage_base_url() == "https://e.x"

def test_code_is_single_use(make_app, monkeypatch):              # C2: קוד תקף פעם אחת
    leads = {"7K3F": {"q": "4 חדרים באפקה", "src": "home", "ts": 9e12}}
    app, sent, _, writes = _setup(make_app, monkeypatch, leads=leads)
    app.site_lead_inbound("972521234567", "", MSG + "\n(קוד 7K3F)", sync=True)
    assert "7K3F" not in leads

def test_codeless_leads_capped_per_day(make_app, monkeypatch):   # C2: הודעות בלי קוד — תקרה יומית כללית
    monkeypatch.setenv("SITE_LEAD_NOCODE_DAY", "2")
    app, sent, _, _ = _setup(make_app, monkeypatch)
    st = [app.site_lead_inbound("97250000000%d" % i, "", MSG, sync=True) for i in range(3)]
    assert st[:2] != ["ignored", "ignored"] and st[2] == "nocode_cap" and len(sent) == 4

def test_transferred_buyer_reused(make_app, monkeypatch):        # I1: קונה שהועבר לסוכנת — לא נוצר כפול
    b = {"row": 7, "name": "דנה", "phone": "0521234567", "agent": "דנה לוי", "summary": "ליד מהאתר · home"}
    app, sent, pushes, writes = _setup(make_app, monkeypatch, buyers=[b])
    app.site_lead_inbound("972521234567", "", MSG, sync=True)
    assert writes[0][0] == "updatebuyer" and writes[0][1]["row"] == 7

def test_limit_push_once_per_day(make_app, monkeypatch):         # I3
    app, _, pushes, _ = _setup(make_app, monkeypatch)
    for _ in range(6):
        app.site_lead_inbound("972500000001", "", MSG, sync=True)
    assert [p[0] for p in pushes].count("ליד מהאתר — הגבלה יומית") == 1

def test_duplicate_message_id_ignored(make_app, monkeypatch):    # I4: ניסיון חוזר של ה-webhook
    app, sent, _, writes = _setup(make_app, monkeypatch)
    assert app.site_lead_inbound("972521234567", "", MSG, sync=True, mid="wamid.1") != "ignored"
    assert app.site_lead_inbound("972521234567", "", MSG, sync=True, mid="wamid.1") == "duplicate"
    assert len(sent) == 2 and len(writes) == 1

def test_no_agent_phone_push_goes_to_default(make_app, monkeypatch):
    monkeypatch.setenv("SITE_LEAD_AGENT", "לא קיים")
    monkeypatch.delenv("SITE_LEADS", raising=False)
    calls = []
    cfg = {"v2_office": {"name": "x"}, "v2_site_leads": {}}
    app = make_app(_load_config=lambda: cfg, _config_mutate=lambda fn: (fn(cfg), True)[1],
                   _fetch_manual_buyers=lambda: [], _buyers_write=lambda a, p: {"ok": True, "row": 5},
                   _cache_clear=lambda *a: None, _d360_send_text=lambda to, t: True,
                   send_push=lambda *a: calls.append(a), fetch_agents_phones=lambda: {}, _last9=lambda p: str(p or "")[-9:])
    app.bpage_lead_pick = lambda q: []
    app.site_lead_inbound("972521234567", "", MSG, sync=True)
    assert calls and all(len(a) == 2 for a in calls)            # בלי [None] — ברירת המחדל של send_push (הבעלים)

def test_agent_for_name_and_phone_stay_together():               # I2
    page = {"agent_name": "דוד", "agent_phone": "0501111111"}
    assert effie_v2.bpage_agent_for(page, {"agent": "דודו עובדיה", "agent_phone": "0501111111"}, {}) == ("דוד", "0501111111")
    assert effie_v2.bpage_agent_for(page, {"agent": "דנה", "agent_phone": "0501111111"}, {"דנה": "0522222222"}) == ("דנה", "0522222222")
    assert effie_v2.bpage_agent_for(page, {"agent": "דוד", "agent_phone": ""}, {}) == ("דוד", "0501111111")
