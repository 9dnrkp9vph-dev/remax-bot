# -*- coding: utf-8 -*-
# ============================================================================
# effie_v2.py — אֶפִי: המסלול המקביל /v2 (סשן 1: כניסה + ניהול)
# ----------------------------------------------------------------------------
# מודול נפרד לחלוטין מהאפליקציה הרצה (FAMILY_BOT_HTML). app.py רק קורא
# effie_v2.register(app, globals()) בתוך try/except — כשל כאן לעולם לא מפיל
# את האפליקציה הקיימת.
#
# עקרונות (CLAUDE.md):
# - BRAND_REVEAL=False — white-label: שם/לוגו המשרד בלבד, לא המותג אפי.
# - שם המשרד מ-offices.name (Supabase) — לעולם לא hardcoded (fallback: env).
# - כתיבה דרך השרת בלבד; הקליינט קורא דרך ה-API הקיים (X-Auth-Token).
# - אותם טוקנים/סשנים כמו האפליקציה הקיימת (fbTok) — כניסה אחת לשתיהן.
# ============================================================================
import os
import time
import json as _json
from urllib.parse import quote as _quote

import requests as _requests

BRAND_REVEAL = False   # כשיוחלף ל-True: המותג אפי (שם + לוגו האוריגמי) בכל מקום

# הלוגו הווקטורי של אפי (docs/handoff/effie-logo.svg) — בשימוש רק כש-BRAND_REVEAL
EFFIE_LOGO_SVG = (
    '<svg width="{w}" height="{h}" viewBox="0 0 118 106" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/>'
    '<path d="M58 8L20 44h38z" fill="#C29435"/>'
    '<path d="M58 8l38 36H58z" fill="#EED9A0"/>'
    '<path d="M58 44L34 98h24z" fill="#D8AC4E"/>'
    '<path d="M20 44l-14 8 14 6z" fill="{beak}"/>'
    '<circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>'
)

# ── דף הכניסה (עיצוב 25c, מצב white-label) ──────────────────────────────────
V2_LOGIN_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>כניסה</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:linear-gradient(165deg,#0E1D33 0%,#1E3A5F 60%,#2C4C77 100%);
       min-height:100vh;min-height:100dvh;color:#fff;display:flex;flex-direction:column;align-items:center;
       text-align:center;padding:calc(env(safe-area-inset-top,0px) + 84px) 28px calc(env(safe-area-inset-bottom,0px) + 34px)}
  @keyframes glow{0%{box-shadow:0 0 0 0 rgba(228,197,107,.45)}70%{box-shadow:0 0 0 16px rgba(228,197,107,0)}100%{box-shadow:0 0 0 0 rgba(228,197,107,0)}}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
  .ring{width:104px;height:104px;border-radius:50%;border:3px solid #E4C56B;padding:6px;animation:glow 2.6s ease-out infinite}
  .ring>div{width:100%;height:100%;border-radius:50%;background:rgba(228,197,107,.13);display:flex;align-items:center;
            justify-content:center;animation:float 3s ease-in-out infinite;overflow:hidden}
  .ring img{width:66%;height:66%;object-fit:contain;border-radius:8px;background:#fff;padding:5px}
  h1{font-size:34px;font-weight:800;line-height:1.15;margin-top:24px}
  .tag{font-size:13px;font-weight:700;color:#E4C56B;letter-spacing:.26em;margin-top:6px;min-height:16px}
  .sub{font-size:14.5px;color:rgba(255,255,255,.65);line-height:1.65;max-width:300px;margin-top:16px}
  .stack{margin-top:auto;width:100%;max-width:330px;display:flex;flex-direction:column;gap:12px}
  .btn{display:flex;align-items:center;justify-content:center;gap:11px;border-radius:16px;padding:15px 0;
       font-size:15.5px;font-weight:800;border:0;width:100%;cursor:pointer;font-family:inherit;min-height:50px}
  .btn-g{background:#fff;color:#1E3A5F;box-shadow:0 10px 28px rgba(0,0,0,.25)}
  .btn-sms{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);color:#fff;font-size:14.5px;font-weight:700}
  .cap{font-size:12px;color:rgba(255,255,255,.5);line-height:1.6}
  .or{display:flex;align-items:center;gap:10px;margin:2px 0}
  .or i{flex:1;height:1px;background:rgba(255,255,255,.15)}
  .or span{font-size:11px;color:rgba(255,255,255,.4)}
  .foot{font-size:11px;color:rgba(255,255,255,.35);margin-top:6px}
  #smsBox{display:none;flex-direction:column;gap:10px}
  #smsBox input{width:100%;padding:14px;border-radius:14px;border:1px solid rgba(255,255,255,.22);
    background:rgba(255,255,255,.1);color:#fff;font-size:16px;text-align:center;font-family:inherit;outline:none}
  #smsBox input::placeholder{color:rgba(255,255,255,.45)}
  .btn-go{background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25);border-radius:14px;padding:14px 0;font-size:15px}
  #err{color:#F0B9B9;font-size:12.5px;min-height:17px;line-height:1.4}
</style></head><body>

  <div class="ring"><div id="logoWrap"><img id="logo" src="/assets/logo" alt=""
      onerror="this.style.display='none'"></div></div>
  <h1 id="officeName">&nbsp;</h1>
  <div class="tag" id="tagline"></div>
  <div class="sub">מסכם שיחות, מגייס נכסים ומחתים דיגיטלית — כדי שאתה תסגור עסקאות.</div>

  <div class="stack">
    <button class="btn btn-g" onclick="location.href='/auth/google/login?next=v2'">
      <svg width="18" height="18" viewBox="0 0 18 18"><path d="M17.6 9.2c0-.6-.1-1.2-.2-1.8H9v3.4h4.8a4.1 4.1 0 0 1-1.8 2.7v2.2h2.9c1.7-1.6 2.7-3.9 2.7-6.5z" fill="#4285F4"/><path d="M9 18c2.4 0 4.5-.8 6-2.2l-2.9-2.2c-.8.5-1.9.9-3.1.9-2.4 0-4.4-1.6-5.1-3.8H.9v2.3A9 9 0 0 0 9 18z" fill="#34A853"/><path d="M3.9 10.7a5.4 5.4 0 0 1 0-3.4V5H.9a9 9 0 0 0 0 8l3-2.3z" fill="#FBBC05"/><path d="M9 3.6c1.3 0 2.5.5 3.4 1.3l2.6-2.6A9 9 0 0 0 .9 5l3 2.3C4.6 5.1 6.6 3.6 9 3.6z" fill="#EA4335"/></svg>
      המשך עם Google
    </button>
    <div class="cap">היומן והפגישות יסתנכרנו אוטומטית עם חשבון ה-Google הזה</div>
    <div class="or"><i></i><span>או</span><i></i></div>
    <button class="btn btn-sms" id="smsBtn" onclick="toggleSms()">
      <svg width="15" height="15" viewBox="0 0 16 16"><rect x="4" y="1.5" width="8" height="13" rx="2" fill="none" stroke="#fff" stroke-width="1.5"/><path d="M7 12.5h2" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/></svg>
      כניסה עם קוד ב-SMS
    </button>
    <div id="smsBox">
      <input id="ph" type="tel" inputmode="numeric" placeholder="מספר הטלפון שלך">
      <input id="cd" type="tel" inputmode="numeric" placeholder="הקוד שקיבלת ב-SMS" style="display:none">
      <button class="btn btn-go" id="go" onclick="smsGo()">שלח קוד</button>
      <div id="err"></div>
    </div>
    <div class="foot">הצטרפות למשרד מתבצעת בהזמנת מנהל · תנאי שימוש ופרטיות</div>
  </div>

<script>
var stage = 0;
function el(id){ return document.getElementById(id); }
function px(u, d){
  return fetch(u, {method:'POST', headers:{'Content-Type':'application/json'},
                   body:JSON.stringify(d)}).then(function(r){ return r.json(); });
}
function toggleSms(){
  var b = el('smsBox');
  b.style.display = (b.style.display === 'flex') ? 'none' : 'flex';
  if (b.style.display === 'flex') el('ph').focus();
}
var REASONS = {unknown:'המספר לא רשום במערכת — הצטרפות בהזמנת מנהל בלבד',
               suspended:'המשתמש מושהה — פנה למנהל המשרד',
               sms_failed:'שליחת ה-SMS נכשלה, נסה שוב בעוד רגע',
               expired:'הקוד פג תוקף — שלח קוד חדש', wrong:'קוד שגוי, נסה שוב',
               too_many:'יותר מדי ניסיונות — שלח קוד חדש', bad_phone:'מספר לא תקין'};
function fail(reason){ el('err').textContent = REASONS[reason] || 'שגיאה, נסה שוב'; }
function smsGo(){
  el('err').textContent = '';
  var ph = el('ph').value.replace(/\D/g, '');
  if (stage === 0){
    px('/api/auth/request', {phone: ph}).then(function(j){
      if (!j.ok){ fail(j.reason); return; }
      stage = 1; el('cd').style.display = 'block'; el('go').textContent = 'כניסה'; el('cd').focus();
    });
  } else {
    var cd = el('cd').value.replace(/\D/g, '');
    px('/api/auth/verify', {phone: ph, code: cd}).then(function(p){
      if (!p.ok){ fail(p.reason); return; }
      try{
        localStorage.setItem('fbTok', p.token);
        localStorage.setItem('fbRole', p.role || '');
        localStorage.setItem('fbDrole', p.drole || '');
        localStorage.setItem('fbName', p.name || '');
        localStorage.setItem('fbDev', p.dev ? '1' : '0');
        localStorage.setItem('fbPhone', ph);
        localStorage.setItem('fbTabs', JSON.stringify(p.tabs || null));
      }catch(e){}
      location.replace('/v2/home');
    });
  }
}
// מיתוג: שם המשרד מהשרת (offices.name) — לעולם לא hardcoded
fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
  el('officeName').textContent = o.name || '';
  document.title = o.name || 'כניסה';
  if (o.reveal){
    el('tagline').textContent = 'העוזר של המתווך';
    el('logoWrap').innerHTML = o.logo_svg || '';
  }
}).catch(function(){});
// כבר מחובר? — ישר פנימה
(function(){
  var t = null;
  try{ t = localStorage.getItem('fbTok'); }catch(e){}
  if (!t) return;
  fetch('/api/auth/whoami', {headers:{'X-Auth-Token': t}}).then(function(r){ return r.json(); })
    .then(function(j){ if (j.ok) location.replace('/v2/home'); }).catch(function(){});
})();
</script></body></html>'''

# ── מסך הבית (עיצוב 14a) + בריף הבוקר (עיצוב 13a — סטורי 4 כרטיסים) ─────────
V2_HOME_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>בית</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;min-height:100vh;min-height:100dvh;
       display:flex;flex-direction:column;color:#1E3A5F}
  header{padding:calc(env(safe-area-inset-top,0px) + 10px) 18px 12px;display:flex;align-items:center;justify-content:space-between}
  .avatar{position:relative;width:44px;height:44px}
  .avatar .c{width:44px;height:44px;border-radius:50%;background:#1E3A5F;color:#fff;display:flex;
      align-items:center;justify-content:center;font-size:17px;font-weight:700}
  .avatar .dot{position:absolute;bottom:1px;right:1px;width:11px;height:11px;border-radius:50%;background:#1FAF5E;border:2px solid #F2EFE7}
  .brand{display:flex;align-items:center;gap:9px}
  .brand img{height:30px;max-width:110px;object-fit:contain}
  .brand .nm{font-size:16px;font-weight:800;letter-spacing:.02em}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 14px;display:flex;flex-direction:column;gap:13px;overflow:auto}
  .greet .g{font-size:24px;font-weight:800}
  .greet .d{font-size:13.5px;color:#8B8F99}
  .stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
  .stat{background:#fff;border-radius:18px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:13px 8px;
      display:flex;flex-direction:column;align-items:center;gap:2px}
  .stat .n{font-size:25px;font-weight:800;font-variant-numeric:tabular-nums}
  .stat .l{font-size:12px;font-weight:600;color:#8B8F99}
  .briefBar{background:linear-gradient(120deg,#0E1D33,#1E3A5F 70%,#2C4C77);border-radius:20px;padding:14px 16px;
      display:flex;align-items:center;gap:12px;box-shadow:0 8px 20px rgba(30,58,95,.25);cursor:pointer}
  .briefBar .ic{width:40px;height:40px;border-radius:13px;background:rgba(228,197,107,.15);
      border:1px solid rgba(228,197,107,.35);display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden}
  .briefBar .ic img{width:26px;height:26px;object-fit:contain;border-radius:6px;background:#fff;padding:2px}
  .briefBar .t{font-size:14.5px;font-weight:800;color:#fff}
  .briefBar .s{font-size:11.5px;color:rgba(255,255,255,.6)}
  .briefBar .cta{background:#E4C56B;color:#1E3A5F;border-radius:11px;padding:9px 15px;font-size:12.5px;
      font-weight:800;white-space:nowrap;border:0;cursor:pointer;font-family:inherit}
  .qa{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .qa .a{border-radius:18px;padding:14px 16px;display:flex;align-items:center;gap:11px;cursor:pointer;min-height:44px}
  .qa .a .ic{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .qa .a .l{font-size:14px;font-weight:700}
  .qa .blue{background:#2E6BD6;box-shadow:0 6px 16px rgba(46,107,214,.25)}
  .qa .gold{background:#C29435;box-shadow:0 6px 16px rgba(194,148,53,.25)}
  .qa .blue .l,.qa .gold .l{color:#fff}
  .qa .blue .ic,.qa .gold .ic{background:rgba(255,255,255,.18)}
  .qa .lite{background:#fff;border:1.5px solid #E9E4D8}
  .strip{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;align-items:center;gap:12px}
  .strip .ic{width:38px;height:38px;border-radius:12px;background:#EAF0FA;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .strip .t{font-size:14.5px;font-weight:800}
  .strip .s{font-size:11.5px;color:#8B8F99}
  .strip .cta{display:flex;align-items:center;gap:7px;background:#EAF0FA;color:#2E6BD6;border-radius:11px;
      padding:9px 15px;font-size:12.5px;font-weight:800;white-space:nowrap;border:0;cursor:pointer;font-family:inherit}
  .care{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:11px}
  .care .hd{display:flex;align-items:center;justify-content:space-between}
  .care .hd .t{font-size:15.5px;font-weight:800}
  .care .hd .all{font-size:12.5px;font-weight:700;color:#2E6BD6;cursor:pointer}
  .care .row{display:flex;align-items:center;gap:11px;min-height:40px}
  .care .row .ic{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .care .row .t{font-size:13.5px;font-weight:700}
  .care .row .s{font-size:12px;color:#8B8F99}
  .care .row .mid{flex:1;min-width:0}
  .care .row .mid div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .chip{font-size:12px;font-weight:700;padding:3px 9px;border-radius:999px;white-space:nowrap;flex-shrink:0}
  .chip.today{color:#B8902F;background:#F6EEDB}
  .chip.late{color:#C24040;background:#FBEDED}
  .chip.soon{color:#5B6472;background:#F0EDE3}
  .sep{height:1px;background:#F0EDE3}
  .careEmpty{display:flex;flex-direction:column;align-items:center;gap:8px;padding:12px 0 6px;text-align:center}
  .careEmpty .ic{width:56px;height:56px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .careEmpty .t{font-size:13.5px;font-weight:700}
  .careEmpty .s{font-size:12px;color:#8B8F99}
  nav{background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer;position:relative}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;border:2.5px solid #C29435;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center;box-sizing:border-box}
  nav .badge{position:absolute;top:-13px;z-index:2;background:#C29435;color:#fff;font-size:10px;font-weight:800;
      padding:1px 8px;border-radius:999px;display:none}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  /* ── סטורי הבריף ── */
  #story{position:fixed;inset:0;z-index:60;background:linear-gradient(165deg,#0E1D33 0%,#1E3A5F 55%,#2C4C77 100%);
      color:#fff;display:none;flex-direction:column;
      padding:calc(env(safe-area-inset-top,0px) + 20px) 22px calc(env(safe-area-inset-bottom,0px) + 22px)}
  #story .bars{display:flex;gap:6px;padding-bottom:16px}
  #story .bars i{flex:1;height:3.5px;border-radius:999px;background:rgba(255,255,255,.25);overflow:hidden;display:block}
  #story .bars i b{display:block;height:100%;width:0;background:#E4C56B;border-radius:999px}
  #story .shead{display:flex;align-items:center;justify-content:space-between}
  #story .shead .lg{width:40px;height:40px;border-radius:13px;background:rgba(228,197,107,.15);
      border:1px solid rgba(228,197,107,.4);display:flex;align-items:center;justify-content:center;overflow:hidden}
  #story .shead .lg img{width:26px;height:26px;object-fit:contain;border-radius:6px;background:#fff;padding:2px}
  #story .shead .t{font-size:14.5px;font-weight:800}
  #story .shead .s{font-size:11.5px;color:rgba(255,255,255,.55);white-space:nowrap}
  #story .x{width:34px;height:34px;display:flex;align-items:center;justify-content:center;border:0;background:transparent;cursor:pointer}
  #story .body{flex:1;display:flex;flex-direction:column;justify-content:center;gap:18px;padding-bottom:24px}
  #story .kicker{font-size:13px;font-weight:700;color:#E4C56B;letter-spacing:.12em}
  #story .big{display:flex;align-items:baseline;gap:14px}
  #story .big .n{font-size:96px;font-weight:800;line-height:1;color:#E4C56B;font-variant-numeric:tabular-nums}
  #story .big .w{font-size:24px;font-weight:800;line-height:1.3}
  #story .sub{font-size:15.5px;color:rgba(255,255,255,.75);line-height:1.65;max-width:300px}
  #story .btns{display:flex;flex-direction:column;gap:10px;margin-top:10px;max-width:300px;width:100%}
  #story .bMain{background:#E4C56B;color:#1E3A5F;border-radius:14px;padding:14px 0;text-align:center;
      font-size:15.5px;font-weight:800;box-shadow:0 8px 24px rgba(228,197,107,.3);border:0;cursor:pointer;font-family:inherit}
  #story .bSec{border:1.5px solid rgba(255,255,255,.3);background:transparent;color:#fff;border-radius:14px;
      padding:13px 0;text-align:center;font-size:14.5px;font-weight:700;cursor:pointer;font-family:inherit}
  #story .skip{background:none;border:0;color:rgba(255,255,255,.55);font-size:13px;font-weight:600;
      cursor:pointer;font-family:inherit;text-decoration:underline;text-underline-offset:3px}
  #story .sfoot{display:flex;flex-direction:column;align-items:center;gap:7px}
  #story .load{display:flex;align-items:center;gap:7px;font-size:11px;color:rgba(255,255,255,.45)}
  #story .load i{width:6px;height:6px;border-radius:50%;background:#1FAF5E;display:block}
  #story .hint{font-size:11.5px;color:rgba(255,255,255,.4);text-align:center}
  #story .ringWrap{align-self:center;width:104px;height:104px;border-radius:50%;border:3px solid #E4C56B;padding:6px}
  #story .ringWrap>div{width:100%;height:100%;border-radius:50%;background:rgba(228,197,107,.13);
      display:flex;align-items:center;justify-content:center;overflow:hidden}
  #story .ringWrap img{width:62%;height:62%;object-fit:contain;border-radius:8px;background:#fff;padding:4px}
  #story .teasers{display:flex;gap:10px}
  #story .teasers .tz{flex:1;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);
      border-radius:14px;padding:12px 6px;display:flex;flex-direction:column;align-items:center;gap:2px}
  #story .teasers .tz .n{font-size:24px;font-weight:800;color:#E4C56B;font-variant-numeric:tabular-nums}
  #story .teasers .tz .l{font-size:10.5px;color:rgba(255,255,255,.65);text-align:center}
  #story .nbList{display:flex;flex-direction:column;gap:9px;max-width:300px;width:100%}
  #story .nbList .r{display:flex;align-items:center;gap:9px;font-size:14.5px;font-weight:600;
      color:rgba(255,255,255,.92);white-space:nowrap;overflow:hidden}
  #story .nbList .r span{overflow:hidden;text-overflow:ellipsis}
  #story .nbList .r i{width:7px;height:7px;border-radius:50%;background:#E4C56B;flex-shrink:0}
  #story .nbList .more{font-size:12.5px;color:rgba(255,255,255,.55);padding-right:16px}
  @media (prefers-reduced-motion:no-preference){
    @keyframes glow{0%{box-shadow:0 0 0 0 rgba(228,197,107,.45)}70%{box-shadow:0 0 0 16px rgba(228,197,107,0)}100%{box-shadow:0 0 0 0 rgba(228,197,107,0)}}
    @keyframes pulseDot{0%,100%{opacity:1}50%{opacity:.35}}
    #story .ringWrap{animation:glow 2.6s ease-out infinite}
    #story .load i{animation:pulseDot 1.6s infinite}
    #story .bars i b{transition:width .25s linear}
  }
</style></head><body>

  <div id="impBar" style="display:none;position:sticky;top:0;z-index:75;background:#C29435;color:#fff;
       padding:calc(env(safe-area-inset-top,0px) + 8px) 14px 8px;align-items:center;justify-content:center;gap:10px;
       font-size:12.5px;font-weight:700">
    <span id="impTx"></span>
    <button onclick="impBack()" style="background:#fff;color:#B8902F;border:0;border-radius:999px;
        padding:5px 12px;font-size:11.5px;font-weight:800;font-family:inherit;cursor:pointer">חזרה למנהל</button>
  </div>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img id="brandLogo" src="/assets/logo" alt="" onerror="this.style.display='none'">
      <div class="nm" id="officeName">&nbsp;</div></div>
    <button class="menuBtn" onclick="openMenu()" aria-label="תפריט">
      <svg width="18" height="14" viewBox="0 0 18 14"><path d="M1 1h16M1 7h16M1 13h16" stroke="#1E3A5F" stroke-width="2" stroke-linecap="round"/></svg>
    </button>
  </header>

  <!-- תפריט צד מינימלי (הגרסה המלאה — סעיף 10 במפרט, בסשן התפריט) -->
  <div id="menuOvl" style="position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:70" onclick="closeMenu()"></div>
  <div id="menu" style="position:fixed;top:0;bottom:0;right:0;width:78%;max-width:320px;z-index:71;background:#fff;
       box-shadow:-16px 0 40px rgba(23,37,60,.25);padding:calc(env(safe-area-inset-top,0px) + 56px) 20px 36px;
       display:none;flex-direction:column;gap:3px">
    <div style="display:flex;align-items:center;gap:11px;padding-bottom:14px">
      <div class="avatar"><div class="c" id="menuAv"></div><div class="dot"></div></div>
      <div><div style="font-size:15.5px;font-weight:800" id="menuNm"></div>
           <div style="font-size:11.5px;color:#8B8F99" id="menuRole"></div></div>
    </div>
    <div style="height:1px;background:#F0EDE3;margin-bottom:8px"></div>
    <a id="menuAdmin" href="/v2/admin" style="display:none;align-items:center;gap:11px;padding:12px 4px;
       text-decoration:none;color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#1E3A5F" stroke-width="1.7"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linecap="round"/></svg>
      ניהול (מפתח)</a>
    <a href="/app" style="display:flex;align-items:center;gap:11px;padding:12px 4px;text-decoration:none;
       color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
      האפליקציה הקיימת</a>
    <a id="menuIg" target="_blank" rel="noopener" style="display:none;align-items:center;gap:11px;padding:12px 4px;
       text-decoration:none;color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><rect x="3.5" y="3.5" width="15" height="15" rx="4.5" fill="none" stroke="#1E3A5F" stroke-width="1.7"/><circle cx="11" cy="11" r="3.6" fill="none" stroke="#1E3A5F" stroke-width="1.7"/><circle cx="15.6" cy="6.4" r="1.1" fill="#1E3A5F"/></svg>
      האינסטגרם של המשרד</a>
    <a id="menuMd" target="_blank" rel="noopener" style="display:none;align-items:center;gap:11px;padding:12px 4px;
       text-decoration:none;color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/><path d="M7.5 16v-4.5h7V16" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
      המשרד במדלן</a>
    <div style="flex:1"></div>
    <button onclick="logout()" style="display:flex;align-items:center;gap:11px;padding:12px 4px;border:0;
       background:none;color:#C24040;font-size:14px;font-weight:700;font-family:inherit;cursor:pointer;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><path d="M8 11h11M15.5 7.5L19 11l-3.5 3.5M11 4H5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h6" fill="none" stroke="#C24040" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
      התנתקות</button>
  </div>

  <main>
    <div class="greet"><div class="g" id="greetTx">&nbsp;</div><div class="d" id="dateTx">&nbsp;</div></div>

    <div class="stats">
      <div class="stat"><div class="n" style="color:#1E3A5F" id="stCalls">—</div><div class="l">שיחות השבוע</div></div>
      <div class="stat"><div class="n" style="color:#1FAF5E" id="stSigs">—</div><div class="l">חתימות</div></div>
      <div class="stat"><div class="n" style="color:#B8902F" id="stBuyers">—</div><div class="l">קונים חדשים</div></div>
    </div>

    <div class="briefBar" onclick="openStory()">
      <div class="ic"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
      <div style="flex:1;display:flex;flex-direction:column;gap:1px">
        <div class="t">בריף הבוקר · 4 כרטיסים</div>
        <div class="s" id="briefSum">מתעדכן…</div>
      </div>
      <button class="cta" id="briefCta">צפה</button>
    </div>

    <div class="qa">
      <div class="a blue" onclick="toast('הוספת קונה — בסשן הקונים הקרוב')">
        <div class="ic"><svg width="15" height="15" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg></div>
        <div class="l">הוסף קונה</div>
      </div>
      <div class="a gold" onclick="toast('החתמה — בסשן החתימות הקרוב')">
        <div class="ic"><svg width="15" height="15" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg></div>
        <div class="l">החתם</div>
      </div>
      <div class="a lite" onclick="toast('חיפוש נכס — בסשן הנכסים הקרוב')">
        <div class="ic" style="background:#EAF0FA"><svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5" fill="none" stroke="#2E6BD6" stroke-width="1.8"/><path d="M10.5 10.5l3 3" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round"/></svg></div>
        <div class="l">חיפוש נכס</div>
      </div>
      <div class="a lite" onclick="toast('תהליכים ועסקאות — בסשן קרוב')">
        <div class="ic" style="background:#F6EEDB"><svg width="15" height="15" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#B8902F" stroke-width="1.6"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#B8902F" stroke-width="1.6" stroke-linecap="round"/></svg></div>
        <div class="l">תהליכים</div>
      </div>
    </div>

    <div class="strip">
      <div class="ic"><svg width="17" height="17" viewBox="0 0 16 16"><path d="M2 8L8 3l6 5v5a.8.8 0 0 1-.8.8H9.8V10H6.2v3.8H2.8A.8.8 0 0 1 2 13z" fill="none" stroke="#2E6BD6" stroke-width="1.6" stroke-linejoin="round"/></svg></div>
      <div style="flex:1;display:flex;flex-direction:column;gap:1px">
        <div class="t">הנכסים שלי</div>
        <div class="s" id="propsSum">מתעדכן…</div>
      </div>
      <button class="cta" onclick="toast('טאב הנכסים — בסשן קרוב')">הצג
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M7 1L2 5l5 4" fill="none" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>

    <div class="care">
      <div class="hd"><div class="t">דורש טיפול</div><div class="all" onclick="toast('פגישות ופולו-אפ — בסשן קרוב')">הכל</div></div>
      <div id="careList"><div class="careEmpty" style="padding:6px 0"><div class="s">מתעדכן…</div></div></div>
    </div>
  </main>

  <nav>
    <div class="it" onclick="toast('מסך השיחות — בסשן הקרוב')"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="toast('מסך הקונים — בסשן הקרוב')"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.7"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" style="color:#1E3A5F;font-weight:700"><div class="home"><svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg></div>בית</div>
    <div class="it" onclick="toast('מסך החתימות — בסשן הקרוב')"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="toast('נכס נולד — בסשן הקרוב')"><div class="badge" id="nbBadge"></div><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
  </nav>

  <!-- ── בריף הבוקר — סטורי ── -->
  <div id="story">
    <div class="bars"><i><b></b></i><i><b></b></i><i><b></b></i><i><b></b></i></div>
    <div class="shead">
      <div style="display:flex;align-items:center;gap:10px">
        <div class="lg"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
        <div><div class="t">בריף הבוקר</div><div class="s" id="storyDate"></div></div>
      </div>
      <button class="x" onclick="closeStory()" aria-label="סגירה">
        <svg width="14" height="14" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="rgba(255,255,255,.6)" stroke-width="1.8" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="body" id="storyBody"></div>
    <div class="sfoot">
      <div class="load" id="storyLoad"><i></i><span>האפליקציה נטענת ברקע — שיחות · קונים · חתימות · נכס נולד</span></div>
      <div class="hint" id="storyHint">הקש להמשך · החלק למטה לסגירה</div>
    </div>
  </div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function GET(u){ return fetch(u, {headers:{'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function el(id){ return document.getElementById(id); }
function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function toast(msg){
  var t = el('toast'); t.textContent = msg; t.style.opacity = '1';
  clearTimeout(t._h); t._h = setTimeout(function(){ t.style.opacity = '0'; }, 1800);
}
function openMenu(){ el('menuOvl').style.display = 'block'; el('menu').style.display = 'flex'; }
function closeMenu(){ el('menuOvl').style.display = 'none'; el('menu').style.display = 'none'; }
function impBack(){   // חזרה מסשן בדיקה לחשבון המנהל
  try{
    var t = localStorage.getItem('fbTokAdmin');
    if (t){ localStorage.setItem('fbTok', t); localStorage.setItem('fbDev', '1'); }
    localStorage.removeItem('fbTokAdmin');
  }catch(e){}
  location.href = '/v2/admin';
}
function logout(){
  try{
    ['fbTok','fbRole','fbDrole','fbName','fbDev','fbPhone','fbTabs'].forEach(function(k){ localStorage.removeItem(k); });
  }catch(e){}
  location.replace('/v2');
}
var HDAYS = ['ראשון','שני','שלישי','רביעי','חמישי','שישי','שבת'];
var HMON = ['ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר'];
function greetWord(){
  var h = new Date().getHours();
  return (h < 5) ? 'לילה טוב' : (h < 12) ? 'בוקר טוב' : (h < 18) ? 'צהריים טובים' : 'ערב טוב';
}
function todayStr(){
  var d = new Date();
  return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
}
function parseDMY(s){
  var m = /(\d{1,2})[\/.](\d{1,2})[\/.](\d{2,4})/.exec(String(s || ''));
  if (!m) return null;
  var y = +m[3]; if (y < 100) y += 2000;
  return new Date(y, +m[2] - 1, +m[1]);
}
function dayDiff(d){   // ימים מהיום (שלילי = עבר)
  var t = new Date(); t.setHours(0,0,0,0);
  var x = new Date(d); x.setHours(0,0,0,0);
  return Math.round((x - t) / 86400000);
}

/* ── מודל הנתונים — נטען ברקע בזמן שהסטורי מוצג ── */
var M = {ready:false, name:'', calls:0, sigs:0, sigSample:null, buyersNew:0, buyersUn:0, buyersTot:0,
         meets:[], meetToday:0, meetLate:0, props:0, excl:0, nb:-1};

function loadData(){
  return Promise.all([
    GET('/api/report?period=week').catch(function(){ return {}; }),
    GET('/api/my/buyers').catch(function(){ return {}; }),
    GET('/api/my/properties').catch(function(){ return {}; })
  ]).then(function(rs){
    var rep = rs[0] || {}, sm = rep.summary || {};
    M.calls = (sm.calls || {}).total || 0;
    M.sigs = (sm.sigs || {}).total || 0;
    M.sigSample = (sm.sigsList && sm.sigsList[0]) || null;
    M.excl = (sm.exclusives || []).length;
    M.meets = rep.meetings || [];
    M.meetToday = 0; M.meetLate = 0;
    M.meets.forEach(function(m){
      var d = parseDMY(m.date);
      if (!d) return;
      var dd = dayDiff(d);
      if (dd === 0) M.meetToday++;
      else if (dd < 0) M.meetLate++;
    });
    var buyers = (rs[1] && rs[1].results) || [];
    M.buyersTot = buyers.length;
    M.buyersUn = buyers.filter(function(b){ return !(b.agent || '').trim(); }).length;
    M.buyersNew = buyers.filter(function(b){
      var d = parseDMY(b.date);
      return d && dayDiff(d) > -7;
    }).length;
    M.props = (rs[2] && rs[2].count) || 0;
    M.ready = true;
    renderDash();
    var ld = el('storyLoad');
    if (ld) ld.innerHTML = '<i></i><span>הכל טעון — הדשבורד מוכן</span>';
    if (STORY.open) renderCard(STORY.i);   // רענון המספרים בכרטיס הנוכחי
  });
}

function renderDash(){
  el('stCalls').textContent = M.calls;
  el('stSigs').textContent = M.sigs;
  el('stBuyers').textContent = M.buyersNew || M.buyersTot;
  var open = M.meetLate + M.meetToday;
  el('dateTx').textContent = 'יום ' + HDAYS[new Date().getDay()] + ', ' + new Date().getDate() +
      ' ב' + HMON[new Date().getMonth()] + (open ? ' · ' + open + ' משימות פתוחות' : '');
  el('briefSum').textContent = (M.buyersUn || M.buyersNew || M.buyersTot) + ' קונים · ' +
      M.sigs + ' חתימות' +
      ((M.nbNew && M.nbNew.length) ? ' · ' + M.nbNew.length + ' נולדו ביממה האחרונה'
        : (M.nb >= 0 ? ' · ' + M.nb.toLocaleString() + ' נכסים' : ''));
  el('propsSum').textContent = M.props + ' פעילים' + (M.excl ? ' · ' + M.excl + ' בבלעדיות' : '');
  var care = [];
  M.meets.slice().sort(function(a, b){
    return (parseDMY(a.date) || 0) - (parseDMY(b.date) || 0);
  }).forEach(function(m){
    var d = parseDMY(m.date);
    var dd = d ? dayDiff(d) : 99;
    if (dd > 1) return;   // רק באיחור / היום / מחר
    care.push({t: (m.label || (m.status === 'meeting' ? 'פגישה' : 'פולו-אפ')) + ': ' + (m.addr || ''),
               s: 'נכס נולד · ' + (m.agent || '') + (m.date ? ' · ' + m.date : ''),
               chip: dd < 0 ? 'late' : dd === 0 ? 'today' : 'soon',
               chipTx: dd < 0 ? 'באיחור' : dd === 0 ? 'היום' : 'מחר',
               meeting: m.status === 'meeting'});
  });
  var h = '';
  care.slice(0, 4).forEach(function(c, i){
    h += (i ? '<div class="sep"></div>' : '') +
      '<div class="row">' +
      '<div class="ic" style="background:' + (c.meeting ? '#EAF0FA' : '#E7F7EE') + '">' +
      (c.meeting
        ? '<svg width="14" height="14" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#2E6BD6" stroke-width="1.6" stroke-linecap="round"/></svg>'
        : '<svg width="14" height="14" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#1FAF5E" stroke-width="1.8" stroke-linejoin="round"/></svg>') +
      '</div><div class="mid"><div class="t">' + esc(c.t) + '</div><div class="s">' + esc(c.s) + '</div></div>' +
      '<div class="chip ' + c.chip + '">' + c.chipTx + '</div></div>';
  });
  el('careList').innerHTML = h ||
    '<div class="careEmpty"><div class="ic"><svg width="24" height="24" viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5" fill="none" stroke="#C29435" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>' +
    '<div class="t">הכל מטופל</div><div class="s">אין פולו-אפים או פגישות שממתינים לך</div></div>';
}

/* ── הסטורי ── */
var STORY = {open:false, i:0, timer:null, DUR:6000};
function seenKey(){ return 'v2BriefSeen'; }
function openStory(fromBar){
  STORY.open = true; STORY.i = 0;
  el('story').style.display = 'flex';
  renderCard(0);
}
function closeStory(){
  STORY.open = false;
  clearTimeout(STORY.timer);
  el('story').style.display = 'none';
  try{ localStorage.setItem(seenKey(), todayStr()); }catch(e){}
  el('briefCta').textContent = 'צפה שוב';
}
function nextCard(){ (STORY.i < 3) ? go(STORY.i + 1) : closeStory(); }
function prevCard(){ if (STORY.i > 0) go(STORY.i - 1); }
function go(i){ STORY.i = i; renderCard(i); }
function setBars(i){
  var bars = el('story').querySelectorAll('.bars i b');
  for (var k = 0; k < 4; k++){
    bars[k].style.transition = 'none';
    bars[k].style.width = (k < i) ? '100%' : '0';
  }
  void bars[i].offsetWidth;
  bars[i].style.transition = 'width ' + STORY.DUR + 'ms linear';
  bars[i].style.width = '100%';
}
function card(kicker, n, w, sub, mainTx, mainFn, secTx){
  return '<div class="kicker">' + kicker + '</div>' +
    '<div class="big"><div class="n">' + n + '</div><div class="w">' + w + '</div></div>' +
    '<div class="sub">' + sub + '</div>' +
    '<div class="btns"><button class="bMain" onclick="' + mainFn + '">' + mainTx + '</button>' +
    (secTx ? '<button class="bSec" onclick="nextCard()">' + secTx + '</button>' : '') + '</div>';
}
function renderCard(i){
  clearTimeout(STORY.timer);
  setBars(i);
  el('storyDate').textContent = 'יום ' + HDAYS[new Date().getDay()] + ', ' + new Date().getDate() +
      ' ב' + HMON[new Date().getMonth()] + ' · ' + (i + 1) + ' מתוך 4';
  var b = el('storyBody'), q = function(v){ return M.ready ? v : '…'; };
  if (i === 0){
    b.innerHTML =
      '<div class="ringWrap"><div><img src="/assets/logo" alt="" onerror="this.style.display=\'none\'"></div></div>' +
      '<div style="text-align:center;display:flex;flex-direction:column;gap:6px">' +
      '<div style="font-size:30px;font-weight:800">' + greetWord() + ', ' + esc(M.name) + '</div>' +
      '<div style="font-size:13.5px;color:rgba(255,255,255,.55)">ככה נראה היום שלך</div></div>' +
      '<div class="teasers">' +
      '<div class="tz"><div class="n">' + q(M.buyersNew || M.buyersTot) + '</div><div class="l">קונים חדשים</div></div>' +
      '<div class="tz"><div class="n">' + q(M.sigs) + '</div><div class="l">חתימות השבוע</div></div>' +
      '<div class="tz"><div class="n">' + q(M.meetToday) + '</div><div class="l">ביומן היום</div></div></div>' +
      '<div class="btns" style="align-self:center;align-items:center">' +
      '<button class="bMain" style="width:100%" onclick="nextCard()">בוא נתחיל ←</button>' +
      '<button class="skip" onclick="closeStory()">דלג לדשבורד</button></div>';
  } else if (i === 1){
    var n = M.buyersUn || M.buyersNew || M.buyersTot;
    b.innerHTML = card('בזמן שישנת', q(n),
      M.buyersUn ? 'קונים חדשים<br>בלי שיבוץ' : 'קונים חדשים<br>השבוע',
      M.buyersUn ? ('מתוך ' + (M.buyersNew || M.buyersTot) + ' שנקלטו השבוע מהשיחות — עדיין בלי סוכן מטפל.')
                 : 'נקלטו מהשיחות של המשרד. שווה לעבור עליהם לפני שהם מתקררים.',
      M.buyersUn ? 'שבץ אותם עכשיו' : 'לרשימת הקונים',
      'toast(\'מסך הקונים — בסשן הקרוב\')', 'הבא: חתימות (3/4)');
  } else if (i === 2){
    b.innerHTML = card('על הקו', q(M.sigs), 'חתימות<br>השבוע',
      M.sigSample ? ('האחרונה: ' + esc(M.sigSample.client || '') + (M.sigSample.address ? ' · ' + esc(M.sigSample.address) : '') + '.')
                  : 'כל החתמה דיגיטלית נשמרת ומחכה לך במסך החתימות.',
      'לחתימות', 'toast(\'מסך החתימות — בסשן הקרוב\')', 'הבא: נכס נולד (4/4)');
  } else {
    var nn = (M.nbNew || []).length;
    if (nn){
      // הבלטה: כמה נכסים נולדו (יצאו למכירה) ביממה האחרונה — כולל כתובות
      var rows = M.nbNew.slice(0, 4).map(function(x){
        var t = (x.a || '') + (x.c ? (x.a ? ', ' : '') + x.c : '');
        return '<div class="r"><i></i><span>' + esc(t || 'ללא כתובת') + '</span></div>';
      }).join('');
      if (nn > 4) rows += '<div class="more">+ עוד ' + (nn - 4) + ' חדשים</div>';
      b.innerHTML =
        '<div class="kicker">נכס נולד · יממה אחרונה</div>' +
        '<div class="big"><div class="n">' + nn + '</div><div class="w">נכסים חדשים<br>יצאו למכירה</div></div>' +
        '<div class="nbList">' + rows + '</div>' +
        '<div class="sub">' + (M.nb >= 0 ? 'סה"כ ' + M.nb.toLocaleString() + ' נכסים בפול — מי שמתקשר ראשון, מגייס.' : '') + '</div>' +
        '<div class="btns"><button class="bMain" onclick="closeStory()">בוא נתחיל את היום</button></div>';
    } else {
      b.innerHTML = card('נכס נולד', (M.nb >= 0 ? M.nb.toLocaleString() : '…'), 'נכסים<br>מחכים לגיוס',
        'ביממה האחרונה לא נולדו נכסים חדשים — אבל הפול מלא. מי שמתקשר ראשון, מגייס.',
        'בוא נתחיל את היום', 'closeStory()', '');
    }
  }
  STORY.timer = setTimeout(nextCard, STORY.DUR);
}
/* ניווט בהקשה: שמאל=הבא (RTL), ימין=הקודם; החלקה למטה=סגירה */
el('story').addEventListener('click', function(e){
  if (e.target.closest('button')) return;
  var x = e.clientX, w = window.innerWidth;
  (x < w * 0.65) ? nextCard() : prevCard();
});
var _ty = null;
el('story').addEventListener('touchstart', function(e){ _ty = e.touches[0].clientY; }, {passive:true});
el('story').addEventListener('touchmove', function(e){
  if (_ty !== null && e.touches[0].clientY - _ty > 80){ _ty = null; closeStory(); }
}, {passive:true});

/* ── אתחול ── */
(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    M.name = j.name || '';
    el('greetTx').textContent = greetWord() + ', ' + M.name;
    el('avatarTx').textContent = M.name ? M.name.trim()[0] : '';
    el('menuAv').textContent = el('avatarTx').textContent;
    el('menuNm').textContent = M.name;
    el('menuRole').textContent = j.dev ? 'בעל המשרד' :
        (j.role === 'admin') ? 'מנהל' : (j.role === 'coordinator') ? 'מתאמת' : 'סוכן';
    if (j.dev) el('menuAdmin').style.display = 'flex';
    var impTok = null;
    try{ impTok = localStorage.getItem('fbTokAdmin'); }catch(e){}
    if (impTok && !j.dev){   // מצב "כניסה כסוכן (בדיקה)" — פס חזרה למנהל
      el('impTx').textContent = 'מצב בדיקה — אתה צופה כ' + (j.name || 'סוכן');
      el('impBar').style.display = 'flex';
    }
    var seen = null;
    try{ seen = localStorage.getItem(seenKey()); }catch(e){}
    if (seen !== todayStr()) openStory();   // פעם ביום — הסטורי הוא מסך הטעינה
    else el('briefCta').textContent = 'צפה שוב';
    loadData();
    GET('/api/newborn').then(function(nb){
      M.nb = (nb && (nb.total || (nb.results || []).length)) || 0;
      // נולדו ביממה האחרונה (ageDays=0) — לכרטיס הסיום של הבריף, כולל כתובות
      M.nbNew = ((nb && nb.results) || []).filter(function(r){ return r.ageDays === 0; })
        .map(function(r){ return {a: r.address || '', c: r.city || ''}; });
      if (M.nb > 0){
        var bd = el('nbBadge');
        bd.textContent = M.nb.toLocaleString(); bd.style.display = 'block';
      }
      renderDash();
      if (STORY.open && STORY.i === 3) renderCard(3);
    }).catch(function(){});
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    el('officeName').textContent = o.name || '';
    document.title = o.name || 'בית';
    if (o.instagram){ el('menuIg').href = o.instagram; el('menuIg').style.display = 'flex'; }
    if (o.madlan){ el('menuMd').href = o.madlan; el('menuMd').style.display = 'flex'; }
  }).catch(function(){});
})();
</script></body></html>'''

# ── מסך הניהול (עיצוב 31a + מתגי מדיניות מסעיף 9ג) ──────────────────────────
V2_ADMIN_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>ניהול</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;min-height:100vh;min-height:100dvh;
       display:flex;flex-direction:column;color:#1E3A5F}
  header{padding:calc(env(safe-area-inset-top,0px) + 14px) 18px 10px;display:flex;align-items:center;justify-content:space-between}
  .backBtn{width:40px;height:40px;border-radius:13px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
       display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  header .mid{display:flex;flex-direction:column;align-items:center}
  header .t{font-size:17px;font-weight:800}
  header .s{font-size:11px;color:#8B8F99}
  main{flex:1;overflow:auto;padding:2px 16px 14px;display:flex;flex-direction:column;gap:12px}
  .card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 16px;
        display:flex;flex-direction:column;gap:11px}
  .cardTitle{font-size:15.5px;font-weight:800}
  .rowHead{display:flex;align-items:center;justify-content:space-between}
  .btn-invite{display:flex;align-items:center;gap:6px;background:#2E6BD6;color:#fff;border-radius:11px;
       padding:8px 14px;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
       box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .sep{height:1px;background:#F0EDE3}
  .member{display:flex;align-items:center;gap:11px;cursor:pointer;min-height:44px}
  .member.pending{opacity:.55}
  .av{width:38px;height:38px;border-radius:50%;color:#fff;display:flex;align-items:center;justify-content:center;
      font-size:14px;font-weight:700;flex-shrink:0}
  .member .mid{flex:1;display:flex;flex-direction:column;min-width:0}
  .member .nm{font-size:13.5px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .member .sb{font-size:11.5px;color:#8B8F99;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .roleChip{display:flex;align-items:center;gap:7px;border-radius:10px;padding:7px 11px;font-size:12px;font-weight:700;flex-shrink:0}
  .role-agent{background:#F5F3EC;border:1px solid #E9E4D8;color:#1E3A5F}
  .role-coordinator{background:#F6EEDB;border:1px solid #E4C56B;color:#B8902F}
  .role-manager{background:#EAF0FA;border:1px solid #BFD2F0;color:#2E6BD6}
  .role-dev{background:#1E3A5F;border:1px solid #1E3A5F;color:#fff}
  .resend{font-size:11.5px;font-weight:700;color:#5B6472;background:#F0EDE3;padding:5px 11px;border-radius:999px;
       border:0;cursor:pointer;font-family:inherit;flex-shrink:0}
  .setRow{display:flex;align-items:center;gap:11px;min-height:44px;cursor:pointer}
  .setIc{width:34px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .setRow .mid{flex:1;display:flex;flex-direction:column;min-width:0}
  .setRow .nm{font-size:13.5px;font-weight:700}
  .setRow .sb{font-size:11.5px;color:#8B8F99}
  .tg{width:34px;height:20px;border-radius:999px;background:#DCD6C8;position:relative;flex-shrink:0;transition:background .15s;cursor:pointer}
  .tg::after{content:'';position:absolute;top:2px;right:2px;width:16px;height:16px;border-radius:50%;background:#fff;transition:transform .15s}
  .tg.on{background:#1FAF5E}
  .tg.on::after{transform:translateX(-14px)}
  nav{background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;font-weight:600;color:#9AA0AB}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
            box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  /* bottom sheet */
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:0;z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
       box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px calc(env(safe-area-inset-bottom,0px) + 20px);
       display:none;flex-direction:column;gap:12px;max-height:82vh;overflow:auto}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center}
  #sheet h3{font-size:19px;font-weight:800}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld span{font-size:11.5px;font-weight:700;color:#5B6472}
  .fld input{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:11px;padding:11px 13px;font-size:14px;
       font-weight:700;color:#1E3A5F;font-family:inherit;outline:none;width:100%}
  .segs{display:flex;gap:8px}
  .seg{flex:1;text-align:center;padding:10px 0;border-radius:11px;background:#F5F3EC;border:1px solid #E9E4D8;
       font-size:13px;font-weight:700;color:#5B6472;cursor:pointer}
  .seg.on{background:#2E6BD6;border-color:#2E6BD6;color:#fff}
  .chk{display:flex;align-items:center;gap:9px;padding:9px 2px;font-size:13.5px;font-weight:600;cursor:pointer;min-height:44px}
  .chk .box{width:20px;height:20px;border-radius:6px;border:1.5px solid #DCD6C8;background:#fff;display:flex;
       align-items:center;justify-content:center;flex-shrink:0}
  .chk.on .box{background:#2E6BD6;border-color:#2E6BD6}
  .btn{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:13px;padding:13px 0;width:100%;
       font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:46px}
  .btn-blue{background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .btn-green{background:#1FAF5E;color:#fff;box-shadow:0 4px 12px rgba(31,175,94,.25)}
  .btn-sec{background:#fff;color:#5B6472;border:1.5px solid #DCD6C8}
  .swRow{display:flex;align-items:center;justify-content:space-between;min-height:44px}
  .swRow .lb{font-size:13.5px;font-weight:700}
  .swRow .sb{font-size:11.5px;color:#8B8F99}
  .phChip{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:10px;padding:7px 11px;
      font-size:12px;font-weight:700;color:#1E3A5F;white-space:nowrap}
  .phChip.gold{background:#F6EEDB;border-color:#E4C56B;color:#B8902F}
  .trashBtn{width:42px;height:42px;border-radius:11px;background:#FBEDED;border:0;cursor:pointer;
      display:flex;align-items:center;justify-content:center;flex-shrink:0}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
       font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
       pointer-events:none;z-index:40;white-space:nowrap}
  #blocked{display:none;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:44px 18px}
  #blocked .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
</style></head><body>

  <header>
    <button class="backBtn" onclick="location.href='/v2/home'">
      <svg width="15" height="15" viewBox="0 0 14 14"><path d="M5 2L10 7l-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="mid"><div class="t">ניהול</div><div class="s" id="subTitle">&nbsp;</div></div>
    <div style="width:40px"></div>
  </header>

  <main id="main" style="display:none">
    <!-- הצוות -->
    <div class="card">
      <div class="rowHead">
        <div class="cardTitle" id="teamTitle">הצוות</div>
        <button class="btn-invite" onclick="openInvite()">
          <svg width="12" height="12" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>
          הזמן סוכן
        </button>
      </div>
      <div id="teamList"></div>
    </div>

    <!-- הגדרות המשרד -->
    <div class="card">
      <div class="cardTitle">הגדרות המשרד</div>
      <div class="setRow" onclick="openOffice()">
        <div class="setIc" style="background:#F6EEDB"><img id="miniLogo" src="/assets/logo" style="width:22px;height:22px;object-fit:contain" onerror="this.style.display='none'"></div>
        <div class="mid"><div class="nm">שם ולוגו המשרד</div><div class="sb" id="officeNameRow"></div></div>
        <svg width="8" height="12" viewBox="0 0 8 12"><path d="M6 1L2 6l4 5" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="sep"></div>
      <div class="setRow" style="cursor:default">
        <div class="setIc" style="background:#E7F7EE"><svg width="14" height="14" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#1FAF5E" stroke-width="1.7" stroke-linejoin="round"/></svg></div>
        <div class="mid"><div class="nm">המספר הווירטואלי</div><div class="sb" id="vphoneRow"></div></div>
        <div class="tg" id="tgTranscribe" onclick="togglePolicy('transcribe', this)"></div>
      </div>
      <div class="sep"></div>
      <div class="setRow" style="cursor:default">
        <div class="setIc" style="background:#EAF0FA"><svg width="14" height="14" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#2E6BD6" stroke-width="1.6" stroke-linecap="round"/></svg></div>
        <div class="mid"><div class="nm">גיליון הנכסים (Google Sheets)</div><div class="sb" id="sheetRow"></div></div>
      </div>
      <div class="sep"></div>
      <div class="setRow" style="cursor:default">
        <div class="setIc" style="background:#F6EEDB"><svg width="14" height="14" viewBox="0 0 16 16"><path d="M2 8L8 3l6 5v5a.8.8 0 0 1-.8.8H9.8V10H6.2v3.8H2.8A.8.8 0 0 1 2 13z" fill="none" stroke="#B8902F" stroke-width="1.6" stroke-linejoin="round"/></svg></div>
        <div class="mid"><div class="nm">שת"פ — שיתוף נכסים</div><div class="sb">שיתוף נכסים הדדי עם משרדים שותפים</div></div>
        <div class="tg" id="tgShtaf" onclick="togglePolicy('shtaf_sharing', this)"></div>
      </div>
    </div>

    <!-- צוותי שיתוף — חברי צוות רואים הכל אחד של השני -->
    <div class="card">
      <div class="rowHead">
        <div class="cardTitle">צוותי שיתוף</div>
        <button class="btn-invite" onclick="editTeam(-1)">
          <svg width="12" height="12" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>
          צוות חדש
        </button>
      </div>
      <div style="font-size:11.5px;color:#8B8F99;line-height:1.5">חברי צוות רואים הכל אחד של השני —
        שיחות, קונים, חתימות, נכסים, תהליכים ועסקאות.</div>
      <div id="teamsList"></div>
    </div>

    <!-- מדיניות (מפרט 9ג) -->
    <div class="card">
      <div class="cardTitle">מדיניות המשרד</div>
      <div class="swRow"><div><div class="lb">חיוב פולו-אפ לפני סגירה</div><div class="sb">אי אפשר לסגור נכס נולד בלי פולו-אפ</div></div>
        <div class="tg" id="tgFollowup" onclick="togglePolicy('require_followup', this)"></div></div>
      <div class="sep"></div>
      <div class="swRow"><div><div class="lb">"מי פנה" למנהלים בלבד</div><div class="sb">סוכן רגיל לא רואה מי פנה לנכס וכמה</div></div>
        <div class="tg" id="tgWho" onclick="togglePolicy('who_contacted_admins_only', this)"></div></div>
    </div>
  </main>

  <div id="blocked">
    <div class="ic"><svg width="30" height="30" viewBox="0 0 22 22"><rect x="4" y="9" width="14" height="9" rx="2" fill="none" stroke="#C29435" stroke-width="1.7"/><path d="M7 9V6.5a4 4 0 0 1 8 0V9" fill="none" stroke="#C29435" stroke-width="1.7"/></svg></div>
    <div style="font-size:17px;font-weight:800">המסך למנהל המשרד בלבד</div>
    <div style="font-size:13px;color:#5B6472;max-width:250px;line-height:1.6">אין לחשבון שלך הרשאת ניהול. אם זו טעות — פנה למנהל המשרד.</div>
    <button class="btn btn-sec" style="max-width:220px" onclick="location.href='/v2/home'">חזרה לבית</button>
  </div>

  <nav>
    <div class="it"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.7"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'" style="cursor:pointer"><div class="home"><svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg></div><span style="color:#1E3A5F;font-weight:700">בית</span></div>
    <div class="it"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function H(extra){
  var h = {'X-Auth-Token': TOK};
  if (extra) h['Content-Type'] = 'application/json';
  return h;
}
function GET(u){ return fetch(u, {headers: H()}).then(function(r){ return r.json(); }); }
function POST(u, d){
  return fetch(u, {method:'POST', headers: H(true), body: JSON.stringify(d || {})})
    .then(function(r){ return r.json(); });
}
function el(id){ return document.getElementById(id); }
function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function toast(msg){
  var t = el('toast'); t.textContent = msg; t.style.opacity = '1';
  clearTimeout(t._h); t._h = setTimeout(function(){ t.style.opacity = '0'; }, 1800);
}

var OV = null, PEOPLE = [], COORDS = [], TEAMS = [], NB_DEFAULT = 0;
var ROLE_LABEL = {agent:'סוכן', coordinator:'מתאמת', manager:'מנהל', developer:'בעל המשרד',
                  accountant:'הנה"ח', secretary:'מזכירות'};
var AV_COLORS = ['#1E3A5F', '#C29435', '#2E6BD6', '#1FAF5E', '#5B6472'];

function boot(){
  GET('/api/auth/whoami').then(function(w){
    if (!w.ok){ location.replace('/v2'); return; }
    if (!w.dev){ el('blocked').style.display = 'flex'; return; }
    Promise.all([GET('/v2/api/admin/overview'), GET('/api/dev/people'), GET('/api/dev/coordinators'),
                 GET('/api/dev/teams')])
      .then(function(rs){
        OV = rs[0]; PEOPLE = (rs[1] && rs[1].agents) || []; COORDS = (rs[2] && rs[2].coordinators) || [];
        NB_DEFAULT = (rs[1] && rs[1].nbDefault) || 0;
        TEAMS = (rs[3] && rs[3].teams) || [];
        render();
      });
  }).catch(function(){ location.replace('/v2'); });
}

function coordAgentsOf(name){
  for (var i = 0; i < COORDS.length; i++)
    if (COORDS[i].coordinator === name) return COORDS[i].agents || [];
  return [];
}
function isPending(p){
  if (!OV || !OV.invites) return false;
  var inv = OV.invites.some(function(v){ return v.phone === p.phone; });
  return inv && (OV.gauth_phones || []).indexOf(p.phone) < 0;
}
function inviteOf(phone){
  return (OV.invites || []).filter(function(v){ return v.phone === phone; })[0] || null;
}

function render(){
  el('main').style.display = 'flex';
  el('subTitle').textContent = OV.office.name + ' · בעל המשרד בלבד';
  document.title = 'ניהול · ' + OV.office.name;
  el('officeNameRow').textContent = OV.office.name;
  el('vphoneRow').textContent = (OV.office.vphone || 'לא הוגדר') +
      (OV.policies.transcribe ? ' · תמלול פעיל' : ' · תמלול כבוי');
  el('sheetRow').textContent = OV.office.sheet_connected ? 'מסונכרן דרך Apps Script' : 'לא מחובר';
  ['transcribe','shtaf_sharing','require_followup','who_contacted_admins_only']
    .forEach(function(k){ setTg(k, OV.policies[k]); });
  renderTeam();
  renderTeams();
}
var TG_IDS = {transcribe:'tgTranscribe', shtaf_sharing:'tgShtaf',
              require_followup:'tgFollowup', who_contacted_admins_only:'tgWho'};
function setTg(key, on){ el(TG_IDS[key]).classList.toggle('on', !!on); }

function renderTeam(){
  var list = PEOPLE.slice().sort(function(a, b){
    var r = {developer:0, manager:1, accountant:1, secretary:1, coordinator:2, agent:3};
    var ra = (a.role in r) ? r[a.role] : 3, rb = (b.role in r) ? r[b.role] : 3;
    return (ra - rb) || a.name.localeCompare(b.name, 'he');
  });
  el('teamTitle').textContent = 'הצוות · ' + list.length;
  var html = '';
  list.forEach(function(p, i){
    var pending = isPending(p);
    var role = p.role || 'agent';
    var sub;
    if (pending) sub = 'הוזמן · ממתין לכניסה ראשונה';
    else if (role === 'coordinator'){
      var n = coordAgentsOf(p.name).length;
      sub = n ? ('מקושרת ל-' + n + ' סוכנים') : 'ללא סוכנים משויכים';
    } else sub = p.phone ? ('0' + p.phone.slice(0, 2) + '-' + p.phone.slice(2)) : '';
    if (p.suspended) sub = 'מושהה' + (sub ? ' · ' + sub : '');
    var init = p.name.split(' ').map(function(w){ return w[0] || ''; }).slice(0, 2).join('');
    var roleCls = (role === 'developer') ? 'role-dev' :
                  (role === 'manager' || role === 'accountant' || role === 'secretary') ? 'role-manager' :
                  (role === 'coordinator') ? 'role-coordinator' : 'role-agent';
    html += (i ? '<div class="sep"></div>' : '') +
      '<div class="member' + (pending ? ' pending' : '') + '" onclick="openMember(' + i + ')">' +
      '<div class="av" style="background:' + AV_COLORS[i % AV_COLORS.length] + '">' + esc(init) + '</div>' +
      '<div class="mid"><div class="nm">' + esc(p.name) + '</div><div class="sb">' + esc(sub) + '</div></div>' +
      (pending
        ? '<button class="resend" onclick="event.stopPropagation();resend(\'' + esc(p.phone) + '\')">שלח שוב</button>'
        : '<div class="roleChip ' + roleCls + '">' + (ROLE_LABEL[role] || 'סוכן') +
          '<svg width="9" height="5" viewBox="0 0 10 6"><path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></div>') +
      '</div>';
  });
  el('teamList').innerHTML = html;
  el('teamList')._list = list;
}

/* ── צוותי שיתוף (קונפיג teams — משפיע על שיחות/קונים/חתימות/נכסים/תהליכים/דוחות) ── */
function renderTeams(){
  var h = '';
  TEAMS.forEach(function(t, i){
    h += (i ? '<div class="sep"></div>' : '') +
      '<div class="setRow" onclick="editTeam(' + i + ')">' +
      '<div class="setIc" style="background:#EAF0FA"><svg width="16" height="16" viewBox="0 0 22 22"><circle cx="8" cy="8" r="3" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><circle cx="15" cy="9.5" r="2.4" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><path d="M3 18c.6-2.8 2.6-4.3 5-4.3s4.4 1.5 5 4.3M13.5 14.2c1.9.3 3.3 1.5 3.8 3.8" fill="none" stroke="#2E6BD6" stroke-width="1.6" stroke-linecap="round"/></svg></div>' +
      '<div class="mid"><div class="nm">צוות ' + (i + 1) + ' · ' + t.length + ' חברים</div>' +
      '<div class="sb">' + esc(t.join(' · ')) + '</div></div>' +
      '<svg width="8" height="12" viewBox="0 0 8 12"><path d="M6 1L2 6l4 5" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg></div>';
  });
  el('teamsList').innerHTML = h ||
    '<div style="font-size:12px;color:#8B8F99;padding:4px 0">אין צוותים עדיין. צוות מחבר סוכנים שרואים הכל אחד של השני.</div>';
}
var TEAM_EDIT = -1;
function editTeam(i){
  TEAM_EDIT = i;
  var members = (i >= 0 && TEAMS[i]) ? TEAMS[i] : [];
  var opts = (el('teamList')._list || PEOPLE).filter(function(x){ return x.role !== 'developer'; });
  var picks = opts.map(function(a){
    var on = members.indexOf(a.name) >= 0;
    return '<div class="chk' + (on ? ' on' : '') + '" data-n="' + esc(a.name) + '" onclick="this.classList.toggle(\'on\')">' +
      '<div class="box"><svg width="11" height="9" viewBox="0 0 12 10"><path d="M1.5 5l3 3 6-6.5" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg></div>' +
      esc(a.name) + '</div>';
  }).join('');
  openSheet(
    '<div style="display:flex;align-items:center;justify-content:space-between">' +
    '<h3>' + (i >= 0 ? 'עריכת צוות ' + (i + 1) : 'צוות חדש') + '</h3>' +
    (i >= 0 ? '<button class="trashBtn" onclick="delTeam()" aria-label="מחיקת צוות">' +
      '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M2.5 4h11M6.5 2h3M5.5 4v9a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1V4M6.8 6.5v5M9.2 6.5v5" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round"/></svg></button>' : '') +
    '</div>' +
    '<div style="font-size:12px;color:#8B8F99;line-height:1.5">חברי הצוות רואים הכל אחד של השני — שיחות, קונים, חתימות, נכסים, תהליכים ועסקאות. סוכן יכול להיות בכמה צוותים.</div>' +
    '<div class="fld"><span>חברי הצוות</span><div id="teamPick">' + picks + '</div></div>' +
    '<button class="btn btn-blue" onclick="saveTeam()">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function _pickedNames(boxId){
  var names = [], rows = el(boxId).children;
  for (var k = 0; k < rows.length; k++)
    if (rows[k].classList.contains('on')) names.push(rows[k].getAttribute('data-n'));
  return names;
}
function saveTeam(){
  var names = _pickedNames('teamPick');
  if (names.length < 2){ toast('צוות צריך לפחות שני חברים'); return; }
  var next = TEAMS.slice();
  if (TEAM_EDIT >= 0) next[TEAM_EDIT] = names; else next.push(names);
  POST('/api/dev/teams', {teams: next}).then(function(j){
    if (!j.ok){ toast('שגיאה בשמירה'); return; }
    closeSheet(); toast('הצוות נשמר'); boot();
  });
}
function delTeam(){
  var next = TEAMS.filter(function(_, k){ return k !== TEAM_EDIT; });
  POST('/api/dev/teams', {teams: next}).then(function(j){
    if (!j.ok){ toast('שגיאה בשמירה'); return; }
    closeSheet(); toast('הצוות נמחק'); boot();
  });
}

/* ── bottom sheets ── */
function openSheet(html){
  el('sheet').innerHTML = '<div class="grip"></div>' + html;
  el('sheet').style.display = 'flex'; el('ovl').style.display = 'block';
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none'; }

var SEL_ROLE = 'agent';
function openInvite(){
  SEL_ROLE = 'agent';
  openSheet(
    '<h3>הזמן חבר צוות</h3>' +
    '<div class="fld"><span>שם מלא</span><input id="invNm" placeholder="שם החבר החדש"></div>' +
    '<div class="fld"><span>נייד</span><input id="invPh" type="tel" inputmode="numeric" placeholder="05X-XXXXXXX"></div>' +
    '<div class="fld"><span>תפקיד</span><div class="segs">' +
      seg('agent', 'סוכן') + seg('coordinator', 'מתאמת') + seg('manager', 'מנהל') + '</div></div>' +
    '<div style="font-size:11.5px;color:#8B8F99;line-height:1.5">ההזמנה נשלחת בוואטסאפ עם קישור כניסה. ' +
      'ההצטרפות למשרד היא בהזמנה בלבד — אין הרשמה פתוחה.</div>' +
    '<button class="btn btn-green" onclick="sendInvite()">' +
      '<svg width="16" height="16" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg>' +
      'שלח הזמנה בוואטסאפ</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function seg(val, label){
  return '<div class="seg' + (SEL_ROLE === val ? ' on' : '') + '" data-v="' + val +
         '" onclick="pickRole(this)">' + label + '</div>';
}
function pickRole(node){
  SEL_ROLE = node.getAttribute('data-v');
  var segsWrap = node.parentNode.children;
  for (var i = 0; i < segsWrap.length; i++)
    segsWrap[i].classList.toggle('on', segsWrap[i] === node);
}
function sendInvite(){
  var nm = el('invNm').value.trim(), ph = el('invPh').value.replace(/\D/g, '');
  if (!nm || ph.length < 9){ toast('שם ונייד תקין — חובה'); return; }
  POST('/v2/api/admin/invite', {name: nm, phone: ph, role: SEL_ROLE}).then(function(j){
    if (!j.ok){ toast('שגיאה בשמירה'); return; }
    closeSheet(); toast('נשמר — נפתח וואטסאפ');
    boot();
    if (j.wa) window.open(j.wa, '_blank');
  });
}
function resend(phone){
  POST('/v2/api/admin/invite', {phone: phone, resend: true}).then(function(j){
    if (j.ok && j.wa){ toast('נפתח וואטסאפ'); window.open(j.wa, '_blank'); }
  });
}

var SEL_NB = 'default';
function nbSeg(val, label){
  return '<div class="seg' + (SEL_NB === val ? ' on' : '') + '" data-v="' + val +
         '" onclick="pickNb(this)">' + label + '</div>';
}
function pickNb(node){
  SEL_NB = node.getAttribute('data-v');
  var segsWrap = node.parentNode.children;
  for (var i = 0; i < segsWrap.length; i++)
    segsWrap[i].classList.toggle('on', segsWrap[i] === node);
  el('nbDays').style.display = (SEL_NB === 'custom') ? 'block' : 'none';
  if (SEL_NB === 'custom') el('nbDays').focus();
}
function memberNb(p){   // מצב ההשהיה הנוכחי של החבר: default / custom / hidden
  if (p.nbHidden) return 'hidden';
  return (p.nbDelay === '' || p.nbDelay == null) ? 'default' : 'custom';
}
function openMember(i){
  var p = el('teamList')._list[i];
  SEL_ROLE = (p.role === 'developer') ? 'developer' :
             (p.role in {manager:1, coordinator:1, agent:1}) ? p.role : 'agent';
  SEL_NB = memberNb(p);
  var isDev = p.role === 'developer';
  var agentsHtml = '';
  if (SEL_ROLE === 'coordinator'){
    var mine = coordAgentsOf(p.name);
    var opts = el('teamList')._list.filter(function(x){
      return x.name !== p.name && (x.role === 'agent' || !x.role);
    });
    agentsHtml = '<div class="fld"><span>הסוכנים המשויכים למתאמת</span><div id="coordAgents">' +
      opts.map(function(a){
        var on = mine.indexOf(a.name) >= 0;
        return '<div class="chk' + (on ? ' on' : '') + '" data-n="' + esc(a.name) + '" onclick="this.classList.toggle(\'on\')">' +
          '<div class="box"><svg width="11" height="9" viewBox="0 0 12 10"><path d="M1.5 5l3 3 6-6.5" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg></div>' +
          esc(a.name) + '</div>';
      }).join('') + '</div></div>';
  }
  var phDisp = p.phone ? '0' + p.phone.slice(0, 2) + '-' + p.phone.slice(2) : '—';
  openSheet(
    '<h3>' + esc(p.name) + '</h3>' +
    '<div class="fld"><span>טלפונים</span><div style="display:flex;gap:8px;align-items:stretch">' +
    '<div class="phChip" style="display:flex;align-items:center">אישי · ' + esc(phDisp) + '</div>' +
    '<input id="memVp" value="' + esc(p.vphone || '') + '" placeholder="מספר וירטואלי" type="tel" ' +
    'style="flex:1;min-width:0;background:#F6EEDB;border:1px solid #E4C56B;border-radius:10px;' +
    'padding:7px 11px;font-size:12px;font-weight:700;color:#B8902F;font-family:inherit;outline:none"></div></div>' +
    (isDev
      ? '<div style="font-size:13px;font-weight:700;color:#B8902F">בעל המשרד — התפקיד קבוע</div>'
      : '<div class="fld"><span>תפקיד</span><div class="segs">' +
        seg('agent', 'סוכן') + seg('coordinator', 'מתאמת') + seg('manager', 'מנהל') + '</div></div>') +
    agentsHtml +
    (isDev ? '' :
      '<div class="fld"><span>נכס נולד — ממתי רואה מודעות</span><div class="segs">' +
      nbSeg('default', 'ברירת מחדל · ' + NB_DEFAULT + ' ימים') + nbSeg('custom', 'מותאם') + nbSeg('hidden', 'מוסתר') +
      '</div><input id="nbDays" type="number" min="0" inputmode="numeric" placeholder="ימים מרגע הפרסום" value="' +
      (SEL_NB === 'custom' ? esc(p.nbDelay) : '') + '" style="display:' + (SEL_NB === 'custom' ? 'block' : 'none') + '">' +
      '<div style="font-size:11px;color:#8B8F99;margin-top:4px">0 = רואה מיד · מוסתר = לא רואה נכס נולד בכלל</div></div>') +
    (isDev ? '' :
      '<div class="swRow"><div><div class="lb">השהיה</div><div class="sb">מושהה לא רואה נתונים ולא נכנס</div></div>' +
      '<div class="tg' + (p.suspended ? ' on' : '') + '" id="tgSusp" onclick="this.classList.toggle(\'on\')"></div></div>') +
    '<button class="btn btn-blue" onclick="saveMember(' + i + ')">שמירה</button>' +
    (isDev ? '' :
      '<button class="btn btn-sec" onclick="loginAs(' + i + ')">' +
      '<svg width="15" height="15" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#5B6472" stroke-width="1.7"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#5B6472" stroke-width="1.7" stroke-linecap="round"/></svg>' +
      'כניסה כסוכן (בדיקה)</button>') +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function loginAs(i){
  var p = el('teamList')._list[i];
  POST('/api/admin/loginas', {name: p.name}).then(function(j){
    if (!j.ok){ toast('לא ניתן להיכנס כ' + p.name); return; }
    try{
      localStorage.setItem('fbTokAdmin', TOK);   // שמירת סשן המנהל — לחזרה בלחיצה
      localStorage.setItem('fbTok', j.token);
      localStorage.setItem('fbName', j.name || '');
      localStorage.setItem('fbRole', j.role || '');
      localStorage.setItem('fbDrole', j.drole || '');
      localStorage.setItem('fbDev', '0');
      localStorage.setItem('fbTabs', JSON.stringify(j.tabs || null));
    }catch(e){}
    location.href = '/v2/home';
  });
}
function saveMember(i){
  var p = el('teamList')._list[i];
  var jobs = [];
  if (p.role !== 'developer'){
    if (SEL_ROLE !== (p.role || 'agent') && p.phone)
      jobs.push(POST('/api/dev/role', {phone: p.phone, role: SEL_ROLE}));
    var suspNow = el('tgSusp') && el('tgSusp').classList.contains('on');
    if (p.phone && suspNow !== !!p.suspended)
      jobs.push(POST('/api/dev/suspend', {phone: p.phone, suspend: suspNow}));
    // עדכוני agent_update (קריאה אחת): מספר וירטואלי + ימי נכס נולד — רק מה שהשתנה
    var upd = {name: p.name};
    var nbVal = (SEL_NB === 'hidden') ? 'hidden' :
                (SEL_NB === 'custom') ? String(parseInt(el('nbDays').value, 10) || 0) : '';
    var nbOrig = p.nbHidden ? 'hidden' :
                 (p.nbDelay === '' || p.nbDelay == null) ? '' : String(p.nbDelay);
    if (nbVal !== nbOrig) upd.newbornDelay = nbVal;
    var vpNow = el('memVp') ? el('memVp').value.trim() : null;
    if (vpNow !== null && vpNow !== (p.vphone || '')) upd.vphone = vpNow;
    if (Object.keys(upd).length > 1)
      jobs.push(POST('/api/dev/agent_update', upd));
  }
  var box = el('coordAgents');
  if (box){
    var names = _pickedNames('coordAgents');
    var next = COORDS.filter(function(c){ return c.coordinator !== p.name; });
    if (names.length) next.push({coordinator: p.name, agents: names});
    jobs.push(POST('/api/dev/coordinators', {coordinators: next}));
  }
  Promise.all(jobs).then(function(){ closeSheet(); toast('נשמר'); boot(); });
}

function openOffice(){
  openSheet(
    '<h3>פרטי המשרד</h3>' +
    '<div class="fld"><span>שם המשרד (white-label)</span><input id="offNm" value="' + esc(OV.office.name) + '"></div>' +
    '<div class="fld"><span>המספר הווירטואלי</span><input id="offVp" value="' + esc(OV.office.vphone || '') + '" placeholder="05X-XXXXXXX"></div>' +
    '<div class="fld"><span>אינסטגרם של המשרד</span><input id="offIg" dir="ltr" type="url" value="' + esc(OV.office.instagram || '') + '" placeholder="https://instagram.com/..."></div>' +
    '<div class="fld"><span>עמוד המשרד במדלן</span><input id="offMd" dir="ltr" type="url" value="' + esc(OV.office.madlan || '') + '" placeholder="https://www.madlan.co.il/..."></div>' +
    '<div style="display:flex;align-items:center;gap:10px;background:#fff;border:1px solid #E9E4D8;border-radius:13px;padding:10px 13px">' +
      '<img src="/assets/logo" style="width:34px;height:34px;object-fit:contain" onerror="this.style.display=\'none\'">' +
      '<div style="font-size:11.5px;color:#8B8F99;line-height:1.5">הלוגו מוצג מ-offices.settings.logo_url — החלפה דרך מנהל המערכת. הקישורים מוצגים לצוות בתפריט הצד.</div></div>' +
    '<button class="btn btn-blue" onclick="saveOffice()">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function saveOffice(){
  POST('/v2/api/admin/office', {name: el('offNm').value.trim(), vphone: el('offVp').value.trim(),
                                instagram: el('offIg').value.trim(), madlan: el('offMd').value.trim()})
    .then(function(j){
      if (!j.ok){ toast('שגיאה בשמירה'); return; }
      closeSheet(); toast('נשמר'); boot();
    });
}

function togglePolicy(key, node){
  var on = !node.classList.contains('on');
  node.classList.toggle('on', on);
  POST('/v2/api/admin/policy', {key: key, on: on}).then(function(j){
    if (!j.ok){ node.classList.toggle('on', !on); toast('שגיאה בשמירה'); return; }
    OV.policies[key] = on;
    if (key === 'transcribe') el('vphoneRow').textContent =
      (OV.office.vphone || 'לא הוגדר') + (on ? ' · תמלול פעיל' : ' · תמלול כבוי');
  });
}

boot();
</script></body></html>'''


def register(app, G):
    """רישום מסלולי /v2 על אפליקציית Flask הקיימת. G = globals() של app.py —
    גישה לעזרי האימות/קונפיג בלי לשכפל לוגיקה ובלי לגעת בקוד הקיים."""
    from flask import request, jsonify, Response

    _last9        = G["_last9"]
    _web_auth     = G["_web_auth"]
    _is_dev       = G["_is_dev"]
    _load_config  = G["_load_config"]
    _save_config  = G["_save_config"]
    _log_activity = G["_log_activity"]
    log           = G.get("log")

    _POLICY_DEFAULTS = {"transcribe": True, "shtaf_sharing": True, "share_buyers": False,
                        "require_followup": False, "who_contacted_admins_only": True}
    _POLICY_LABELS = {"transcribe": "תמלול שיחות", "shtaf_sharing": "שת\"פ — שיתוף נכסים",
                      "share_buyers": "שיתוף קונים בין סוכנים",
                      "require_followup": "חיוב פולו-אפ לפני סגירה",
                      "who_contacted_admins_only": "\"מי פנה\" למנהלים בלבד"}

    _office_cache = {"name": "", "logo_url": "", "ts": 0.0}

    def _sb_office():
        """offices.name/settings מ-Supabase (מקור האמת), עם cache של 10 דקות."""
        try:
            import supabase_db as _sb
            if not _sb.enabled():
                return {}
            if time.time() - _office_cache["ts"] < 600 and _office_cache["name"]:
                return dict(_office_cache)
            r = _requests.get(_sb.SUPABASE_URL + "/rest/v1/offices",
                              headers=_sb._headers(),
                              params={"id": "eq." + _sb.SB_OFFICE_ID, "select": "name,settings"},
                              timeout=8)
            r.raise_for_status()
            rows = r.json() or []
            if rows:
                st = rows[0].get("settings") or {}
                _office_cache.update({"name": rows[0].get("name") or "",
                                      "logo_url": st.get("logo_url") or "", "ts": time.time()})
            return dict(_office_cache)
        except Exception as e:
            if log: log.warning(f"effie v2: offices fetch failed: {e}")
            return dict(_office_cache)

    def _office_name(cfg=None):
        sb = _sb_office()
        if sb.get("name"):
            return sb["name"]
        cfg = cfg if cfg is not None else _load_config()
        v2o = cfg.get("v2_office") or {}
        return (v2o.get("name") or os.environ.get("OFFICE_NAME", "") or "רימקס פמילי").strip()

    def _policies(cfg=None):
        cfg = cfg if cfg is not None else _load_config()
        p = dict(_POLICY_DEFAULTS)
        saved = cfg.get("v2_policies")
        if isinstance(saved, dict):
            for k in p:
                if k in saved:
                    p[k] = bool(saved[k])
        return p

    def _dev_guard():
        s = _web_auth()
        if not s or not _is_dev(s.get("phone", "")):
            return None
        return s

    # ── דפים ────────────────────────────────────────────────────────────────
    def _page(html):
        resp = Response(html, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    @app.route("/v2", methods=["GET"])
    def v2_login():
        return _page(V2_LOGIN_HTML)

    @app.route("/v2/home", methods=["GET"])
    def v2_home():
        return _page(V2_HOME_HTML)

    @app.route("/v2/admin", methods=["GET"])
    def v2_admin():
        return _page(V2_ADMIN_HTML)

    # ── API ─────────────────────────────────────────────────────────────────
    @app.route("/v2/api/office", methods=["GET"])
    def v2_api_office():
        """שם/לוגו/קישורי המשרד — פתוח (אין עדיין טוקן בכניסה). white-label פר-משרד."""
        v2o = _load_config().get("v2_office") or {}
        out = {"ok": True, "name": _office_name(), "logo": "/assets/logo",
               "instagram": v2o.get("instagram", ""), "madlan": v2o.get("madlan", ""),
               "reveal": BRAND_REVEAL}
        if BRAND_REVEAL:
            out["name"] = "אֶפִי"
            out["logo_svg"] = EFFIE_LOGO_SVG.format(w=52, h=47, beak="#fff")
        return jsonify(out)

    @app.route("/v2/api/admin/overview", methods=["GET"])
    def v2_api_admin_overview():
        s = _dev_guard()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        cfg = _load_config()
        v2o = cfg.get("v2_office") or {}
        gauth = set()
        try:
            for rec in (cfg.get("gauth") or {}).values():
                p = _last9((rec or {}).get("phone", ""))
                if p:
                    gauth.add(p)
        except Exception:
            pass
        invites = [v for v in (cfg.get("v2_invites") or []) if isinstance(v, dict)]
        return jsonify({
            "ok": True,
            "office": {
                "name": _office_name(cfg),
                "logo": "/assets/logo",
                "vphone": v2o.get("vphone", "") or os.environ.get("VIRTUAL_PHONE_DISPLAY", ""),
                "instagram": v2o.get("instagram", ""),
                "madlan": v2o.get("madlan", ""),
                "sheet_connected": bool(G.get("APPS_SCRIPT_URL") and G.get("APPS_SCRIPT_TOKEN")),
            },
            "policies": _policies(cfg),
            "invites": invites,
            "gauth_phones": sorted(gauth),
        })

    @app.route("/v2/api/admin/invite", methods=["POST"])
    def v2_api_admin_invite():
        """הזמנת חבר צוות בוואטסאפ — הדרך היחידה להצטרף (אין הרשמה פתוחה).
        רושם את החבר בקונפיג (agents+roles) ומחזיר קישור wa.me עם הודעת הזמנה."""
        s = _dev_guard()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        phone = _last9(b.get("phone", ""))
        if not phone:
            return jsonify({"ok": False, "reason": "bad_phone"}), 400
        cfg = _load_config()
        invites = [v for v in (cfg.get("v2_invites") or []) if isinstance(v, dict)]
        existing = next((v for v in invites if v.get("phone") == phone), None)
        if b.get("resend"):
            if not existing:
                return jsonify({"ok": False, "reason": "not_invited"}), 404
            name, role = existing.get("name", ""), existing.get("role", "agent")
        else:
            name = (b.get("name") or "").strip()
            role = (b.get("role") or "agent").strip()
            if role not in ("agent", "coordinator", "manager"):
                role = "agent"
            if not name:
                return jsonify({"ok": False, "reason": "missing_name"}), 400
            # רישום בקונפיג: ספריית הסוכנים + תפקיד (אותו מנגנון כמו הקונסולה הקיימת)
            agents = cfg.setdefault("agents", [])
            entry = next((a for a in agents if _last9(a.get("phone", "")) == phone), None)
            if not entry:
                agents.append({"name": name, "phone": phone, "aliases": []})
            elif name and entry.get("name") != name:
                entry["name"] = name
            cfg.setdefault("roles", {})[phone] = role
            if existing:
                existing.update({"name": name, "role": role, "ts": int(time.time())})
            else:
                invites.append({"name": name, "phone": phone, "role": role, "ts": int(time.time())})
            cfg["v2_invites"] = invites
            if not _save_config(cfg):
                return jsonify({"ok": False, "reason": "save_failed"})
            _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                          "הזמנת חבר צוות", f"{name} ({role})")
        host = (request.host or "").split(":")[0] or "remax-bot.onrender.com"
        office = _office_name(cfg)
        msg = (f"היי {name}, הוזמנת להצטרף למערכת של {office}.\n"
               f"נכנסים כאן עם חשבון Google או קוד ב-SMS:\nhttps://{host}/v2")
        wa = "https://wa.me/972" + phone + "?text=" + _quote(msg)
        return jsonify({"ok": True, "wa": wa})

    @app.route("/v2/api/admin/policy", methods=["POST"])
    def v2_api_admin_policy():
        s = _dev_guard()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        key = (b.get("key") or "").strip()
        if key not in _POLICY_DEFAULTS:
            return jsonify({"ok": False, "reason": "bad_key"}), 400
        cfg = _load_config()
        pol = cfg.setdefault("v2_policies", {})
        pol[key] = bool(b.get("on"))
        if not _save_config(cfg):
            return jsonify({"ok": False, "reason": "save_failed"})
        _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                      "עדכון מדיניות", f"{_POLICY_LABELS.get(key, key)}: {'פעיל' if pol[key] else 'כבוי'}")
        return jsonify({"ok": True, "policies": _policies(cfg)})

    @app.route("/v2/api/admin/office", methods=["POST"])
    def v2_api_admin_office():
        """עדכון שם המשרד (white-label) + המספר הווירטואלי. השם נכתב גם ל-Supabase
        (offices.name — מקור האמת) וגם לקונפיג כגיבוי."""
        s = _dev_guard()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        name = (b.get("name") or "").strip()
        vphone = (b.get("vphone") or "").strip()
        cfg = _load_config()
        v2o = cfg.setdefault("v2_office", {})
        if name:
            v2o["name"] = name
        v2o["vphone"] = vphone
        for _lk in ("instagram", "madlan"):   # קישורי המשרד (white-label — פר-משרד)
            if _lk in b:
                v2o[_lk] = (b.get(_lk) or "").strip()
        if not _save_config(cfg):
            return jsonify({"ok": False, "reason": "save_failed"})
        if name:
            try:
                import supabase_db as _sb
                if _sb.enabled():
                    r = _requests.patch(_sb.SUPABASE_URL + "/rest/v1/offices",
                                        headers={**_sb._headers(), "Content-Type": "application/json"},
                                        params={"id": "eq." + _sb.SB_OFFICE_ID},
                                        json={"name": name}, timeout=8)
                    r.raise_for_status()
                    _office_cache["ts"] = 0.0   # רענון ה-cache בקריאה הבאה
            except Exception as e:
                if log: log.warning(f"effie v2: offices.name update failed: {e}")
        _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                      "עדכון פרטי משרד", name or vphone)
        return jsonify({"ok": True, "name": _office_name(cfg), "vphone": vphone})

    if log:
        log.info("effie v2 registered: /v2, /v2/home, /v2/admin")
