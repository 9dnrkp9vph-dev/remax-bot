# tests/crm/test_wa_beacon.py — הקוד האמיתי מ-V2_BOOST (node): פתיחת וואטסאפ שולחת דיווח אחד לשרת, בטלפון ובמחשב
import os, subprocess, tempfile
SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "effie_v2.py"), encoding="utf-8").read()
a = SRC.index("/* [wa-web 27/09]"); b = SRC.index("/* end wa-web */")
iife = SRC[a:b]
harness = r"""
function run(ua, cap){
  var sent=[], listeners=[], opened=[];
  global.window = {open:function(u,n){opened.push(u);return {focus:function(){}};}, Capacitor: cap?{}:undefined};
  global.navigator = {userAgent:ua, maxTouchPoints:0};
  global.localStorage = {getItem:function(){return 'tok';}};
  global.location = {pathname:'/v2/buyers'};
  global.fetch = function(u,o){sent.push([u,JSON.parse(o.body).page,o.headers['X-Auth-Token']]);return Promise.resolve({});};
  global.document = {addEventListener:function(t,f){listeners.push(f);}};
  global.Date = Date;
  eval(CODE);
  window.open('https://wa.me/972501234567?text=hi');
  return {sent:sent, opened:opened};
}
var m = run('Mozilla/5.0 (iPhone)', false), d = run('Mozilla/5.0 (Macintosh)', false);
if (m.sent.length!==1 || m.sent[0][0]!=='/v2/api/wa/click' || m.sent[0][1]!=='/v2/buyers' || m.sent[0][2]!=='tok') throw new Error('mobile '+JSON.stringify(m));
if (d.sent.length!==1 || d.opened[0].indexOf('web.whatsapp.com')<0) throw new Error('desktop '+JSON.stringify(d));
console.log('wa_beacon OK');
"""
f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
f.write("var CODE = " + __import__("json").dumps(iife) + ";\n" + harness); f.close()
out = subprocess.run(["node", f.name], capture_output=True, text=True)
print(out.stdout.strip() or out.stderr.strip()[-400:])
assert out.returncode == 0
