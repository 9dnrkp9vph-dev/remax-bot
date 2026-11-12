"""[DIAL-GUARD 12/11] 'חייג חזרה' דורש אישור, ונגיעה תוך 1.5ש' אחרי חיוג לא מחייגת."""
import re, subprocess, json, pathlib
src = pathlib.Path(__file__).resolve().parents[2].joinpath("effie_v2.py").read_text()
start = src.index("function dialAny(){")
end = src.index("function openWa(i){")
js = src[start:end]
harness = r"""
var calls=[], sheet=null, now=1000000;
Date.now=function(){return now};
function el(id){ if(id==='list') return {_src:[{caller:'054-5544748',tel:'0545544748',time:'18:13'}]};
  if(id==='anyTel') return {value:'046000800'}; return {textContent:'052-9125944'}; }
function openSheet(h){sheet=h} function closeSheet(){sheet=null}
function esc(x){return String(x)} function toast(){} function c2cDial(t){calls.push(t);return Promise.resolve(true)}
""" + js + r"""
var out={};
dialAnyGo(); out.afterAny=calls.slice();
now+=800; dialBack(0); out.ghostSheet=sheet; out.ghostCalls=calls.length;
now+=3000; dialBack(0); out.sheetOpen=!!sheet; out.noDialYet=calls.length;
dialBackGo(0); out.final=calls.slice(); out.closed=sheet===null;
console.log(JSON.stringify(out));
"""
r = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
o = json.loads(r.stdout)
assert o["afterAny"] == ["046000800"], o
assert o["ghostSheet"] is None and o["ghostCalls"] == 1, o
assert o["sheetOpen"] and o["noDialYet"] == 1, o
assert o["final"] == ["046000800", "0545544748"] and o["closed"], o
print("ok")
