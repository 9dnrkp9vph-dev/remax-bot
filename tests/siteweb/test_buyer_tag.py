"""כרטיס קונה: תווית 'מהאתר' לליד מ'סוכן AI אישי' (14/10) — הרצת ה-JS האמיתי ב-node."""
import json, os, re, subprocess, shutil, pytest

import effie_v2
SRC = next(v for v in vars(effie_v2).values() if isinstance(v, str) and "function buyerCardHtml(" in v)

def _fn(name):
    i = SRC.index("function " + name + "(")
    depth, j = 0, SRC.index("{", i)
    for k in range(j, len(SRC)):
        depth += {"{": 1, "}": -1}.get(SRC[k], 0)
        if depth == 0:
            return SRC[i:k + 1]

@pytest.mark.skipif(not shutil.which("node"), reason="node")
def test_site_tag():
    js = ("var MULTI=false; function esc(s){return String(s||'')} function stOf(b){return b.status||''} var ST_LABEL={}; function fmtBd(x){return x} function bpLine(){return ''}\n" +
          _fn("buyerCardHtml") +
          "\nconsole.log(JSON.stringify([buyerCardHtml({name:'דנה',summary:'ליד מהאתר · home'},0,''), buyerCardHtml({name:'רון',summary:'מהחתמת…'},1,'')]));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[:500]
    a, b = json.loads(out.stdout)
    assert '<span class="tag site">מהאתר</span>' in a and "tag site" not in b
