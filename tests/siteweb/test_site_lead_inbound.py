"""'סוכן AI אישי' (14/10): הודעה מהאתר בוואטסאפ → קונה אצל אייל → דף קונה → תשובה אוטומטית."""

def _setup(make_app, monkeypatch, buyers=None, picks=("a", "b"), send_ok=True, leads=None, send_raises=False):
    monkeypatch.setenv("SITE_LEAD_AGENT", "אייל שמול")
    monkeypatch.delenv("SITE_LEADS", raising=False)
    sent, pushes, writes = [], [], []
    cfg = {"v2_office": {"name": "רימקס פמילי"}, "v2_site_leads": leads or {}}
    bl = list(buyers or [])
    def bw(action, p):
        writes.append((action, p))
        if action == "addbuyer":
            bl.append(dict(p, row=99)); return {"ok": True, "row": 99}
        return {"ok": True}
    def snd(to, t):
        sent.append((to, t)); return send_ok
    app = make_app(_load_config=lambda: cfg, _config_mutate=lambda fn: (fn(cfg), True)[1],
                   _fetch_manual_buyers=lambda: bl, _buyers_write=bw, _cache_clear=lambda *a: None,
                   _d360_send_text=snd, send_push=lambda title, body, to=None: pushes.append((title, body, to)),
                   fetch_agents_phones=lambda: {"אייל שמול": "0505709865"}, _last9=lambda p: str(p or "")[-9:])
    app.bpage_lead_pick = lambda q: list(picks)
    def lsend(buyer, keys, q):
        if send_raises:
            raise RuntimeError("supabase down")
        return {"url": "https://x/b/T", "n": len(keys), "first": True}
    app.bpage_lead_send = lsend
    return app, sent, pushes, writes

def test_full_flow_with_code(make_app, monkeypatch):
    app, sent, pushes, writes = _setup(make_app, monkeypatch, leads={"7K3F": {"q": "4 חדרים באפקה", "src": "home", "ts": 9e12}})
    st = app.site_lead_inbound("972521234567", "דנה כהן", "היי, אני מחפש/ת: משהו ערוך\n(קוד 7K3F)", sync=True)
    assert st == "sent" and writes[0][0] == "addbuyer" and writes[0][1]["search"] == "4 חדרים באפקה"
    assert writes[0][1]["agent"] == "אייל שמול" and writes[0][1]["summary"] == "ליד מהאתר · home"
    assert writes[0][1]["phone"] == "0521234567" and writes[0][1]["name"] == "דנה כהן"
    assert sent[0][0] == "972521234567" and sent[0][1].startswith("שלום דנה, כאן הסוכן האישי של רימקס פמילי.") and "https://x/b/T" in sent[0][1]
    assert pushes and pushes[0][0] == "ליד חדש מהאתר" and pushes[0][2] == ["505709865"]

def test_expired_code_uses_message_text(make_app, monkeypatch):
    app, sent, _, writes = _setup(make_app, monkeypatch, leads={"7K3F": {"q": "ישן", "src": "home", "ts": 1}})
    app.site_lead_inbound("972521234567", "", "היי, אני מחפש/ת: דירה בביאליק\n(קוד 7K3F)", sync=True)
    assert writes[0][1]["search"] == "דירה בביאליק" and writes[0][1]["name"] == "ליד מהאתר"

def test_ignored_and_no_match_and_limit(make_app, monkeypatch):
    app, sent, pushes, _ = _setup(make_app, monkeypatch, picks=())
    assert app.site_lead_inbound("972521234567", "", "בוקר טוב", sync=True) == "ignored" and not sent
    assert app.site_lead_inbound("972521234567", "", "היי, אני מחפש/ת: וילה בים עד מיליון", sync=True) == "no_match"
    assert "ונחזור אליכם עם אפשרויות" in sent[-1][1]
    app2, sent2, pushes2, _ = _setup(make_app, monkeypatch)
    for _ in range(3):
        app2.site_lead_inbound("972500000001", "", "היי, אני מחפש/ת: דירה בביאליק", sync=True)
    assert app2.site_lead_inbound("972500000001", "", "היי, אני מחפש/ת: דירה בביאליק", sync=True) == "limit"
    assert len(sent2) == 3 and pushes2[-1][0] == "ליד מהאתר — הגבלה יומית"

def test_existing_buyer_updated_and_send_failure(make_app, monkeypatch):
    b = {"row": 7, "name": "דנה", "phone": "052-1234567", "agent": "אייל שמול", "search": "ישן"}
    app, sent, pushes, writes = _setup(make_app, monkeypatch, buyers=[b], send_ok=False)
    st = app.site_lead_inbound("972521234567", "דנה", "היי, אני מחפש/ת: 3 חדרים במוצקין", sync=True)
    assert writes[0] == ("updatebuyer", {"row": 7, "search": "3 חדרים במוצקין"})
    assert st == "send_failed" and pushes[-1][0] == "ליד מהאתר — לא נשלח אוטומטית"

def test_page_failure_still_answers(make_app, monkeypatch):
    # Review Focus 4: כשל ביצירת הדף — הקונה נשמר, הלקוח מקבל 'נחזור אליכם', אייל מקבל פוש
    app, sent, pushes, writes = _setup(make_app, monkeypatch, send_raises=True)
    st = app.site_lead_inbound("972521234567", "", "היי, אני מחפש/ת: דירה בים", sync=True)
    assert writes[0][0] == "addbuyer" and "ונחזור אליכם עם אפשרויות" in sent[-1][1] and st == "no_match"

def test_kill_switch_and_async(make_app, monkeypatch):
    app, sent, _, _ = _setup(make_app, monkeypatch)
    monkeypatch.setenv("SITE_LEADS", "0")
    assert app.site_lead_inbound("972521234567", "", "היי, אני מחפש/ת: דירה בים", sync=True) == "ignored"
    monkeypatch.delenv("SITE_LEADS")
    assert app.site_lead_inbound("972521234567", "", "שלום", sync=False) == "ignored"
