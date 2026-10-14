"""סוכן AI אישי — סבב 2 (אייל 15/10): 'חיפוש מס׳' במקום 'קוד', הודעה מיידית, 'סוכן AI אישי' בדף, 'ראיתי', בלי 'אייל יחזור'."""
import json, re, shutil, subprocess, pytest
import site_api, effie_v2
from tests.siteweb.test_site_lead_inbound import _setup

def test_parse_search_number_label():
    for txt in ("היי, אני מחפש/ת: 4 חדרים באפקה\n(חיפוש מס׳ SD4W)", "היי, אני מחפש/ת: 4 חדרים באפקה\n(חיפוש מס' SD4W)",
                "היי, אני מחפש/ת: 4 חדרים באפקה\n(קוד SD4W)"):
        m = site_api.parse_lead_message(txt)
        assert m and m["code"] == "SD4W" and m["q"] == "4 חדרים באפקה", txt

def test_instant_ack_before_results(make_app, monkeypatch):
    app, sent, _, _ = _setup(make_app, monkeypatch)
    app.site_lead_inbound("972521234567", "אריאל כהן", "היי, אני מחפש/ת: 4 חדרים באפקה", sync=True)
    assert len(sent) == 2 and "אריאל" in sent[0][1] and "כמה שניות" in sent[0][1]
    assert "https://x/b/T" in sent[1][1]

def test_seen_mark():
    assert effie_v2.BPAGE_MARKS["seen"] == "ראיתי"

def test_ai_lead_page_detection():
    page = {"agent_name": "אייל שמול"}
    assert effie_v2.bpage_is_ai(page, {"agent": "אייל שמול", "summary": "ליד מהאתר · home"}, "אייל שמול")
    assert not effie_v2.bpage_is_ai(page, {"agent": "דנה לוי", "summary": "ליד מהאתר · home"}, "אייל שמול")   # הועבר לסוכן
    assert not effie_v2.bpage_is_ai(page, {"agent": "אייל שמול", "summary": "מהחתמת מתעניין"}, "אייל שמול")

SRC = next(v for v in vars(effie_v2).values() if isinstance(v, str) and "function srchHtml(" in v)
def _fn(name):
    i = SRC.index("function " + name + "(")
    depth, j = 0, SRC.index("{", i)
    for k in range(j, len(SRC)):
        depth += {"{": 1, "}": -1}.get(SRC[k], 0)
        if depth == 0:
            return SRC[i:k + 1]

@pytest.mark.skipif(not shutil.which("node"), reason="node")
def test_public_page_seen_button_and_ai_search_box():
    js = ("var D={agent:{first:'אייל',name:'אייל שמול',ai:true},scanN:3840}, ST={}; function esc(s){return String(s==null?'':s)}\n"
          "function fmtP(x){return x} function itemAt(){return null} function galHtml(){return ''}\n" + _fn("srchHtml") + "\n" + _fn("cardHtml") +
          "\nvar a=srchHtml(); var c=cardHtml({key:'k',street:'דרור',images:[],mark:'seen'},0);"
          "D.agent.ai=false; var b=srchHtml(); console.log(JSON.stringify([a,c,b]));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[:500]
    a, c, b = json.loads(out.stdout)
    assert "יחזור אליך" not in a and "שלח ל" not in a and ">שלח<" in a        # דף AI: בלי 'אייל יחזור', כפתור 'שלח'
    assert "ראיתי" in c and 'class="sn on"' in c                            # כפתור ראיתי (מסומן)
    assert c.index("מתאים") < c.index("ראיתי")                              # משמאל (אחרון בשורה RTL)
    assert "יחזור אליך" in b                                                 # דף של סוכן — כמו קודם

BSRC = next(v for v in vars(effie_v2).values() if isinstance(v, str) and "function bpChip(" in v)
def _bfn(name):
    i = BSRC.index("function " + name + "(")
    depth, j = 0, BSRC.index("{", i)
    for k in range(j, len(BSRC)):
        depth += {"{": 1, "}": -1}.get(BSRC[k], 0)
        if depth == 0:
            return BSRC[i:k + 1]

@pytest.mark.skipif(not shutil.which("node"), reason="node")
def test_effie_screens_show_seen():
    """15/10 (אייל: 'קח בחשבון גם את אפי'): 'ראיתי' בשורת דף הקונה בכרטיס ובתג בחלון ההתאמות."""
    js = ("function esc(s){return String(s==null?'':s)} var BP_STATE={keys:{k1:'seen'},newK:{}}, BP_SUM={1:{like:1,seen:2,total:3}};\n" + _bfn("bpChip") + "\n" + _bfn("bpLine") +
          "\nconsole.log(JSON.stringify([bpChip('k1'), bpLine({row:1},0,{like:1,seen:2,total:3})]));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[:600]
    chip, line = json.loads(out.stdout)
    assert "בדף · ראיתי" in chip and "2 ראיתי" in line

def test_summary_counts_seen():
    src = open(effie_v2.__file__, encoding="utf-8").read()
    assert 'cnt = {"like": 0, "visit": 0, "dislike": 0, "seen": 0}' in src
