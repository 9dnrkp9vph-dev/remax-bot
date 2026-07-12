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
import base64 as _b64
import os
import re as _re
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
       justify-content:center;text-align:center;
       padding:calc(env(safe-area-inset-top,0px) + 40px) 28px calc(env(safe-area-inset-bottom,0px) + 28px)}
  @keyframes glow{0%{box-shadow:0 0 0 0 rgba(228,197,107,.45)}70%{box-shadow:0 0 0 16px rgba(228,197,107,0)}100%{box-shadow:0 0 0 0 rgba(228,197,107,0)}}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
  .ring{width:104px;height:104px;border-radius:50%;border:3px solid #E4C56B;padding:6px;animation:glow 2.6s ease-out infinite}
  .ring>div{width:100%;height:100%;border-radius:50%;background:#fff;display:flex;align-items:center;
            justify-content:center;animation:float 3s ease-in-out infinite;overflow:hidden}
  .ring img{width:76%;height:76%;object-fit:contain}
  h1{font-size:34px;font-weight:800;line-height:1.15;margin-top:24px}
  .tag{font-size:13px;font-weight:700;color:#E4C56B;letter-spacing:.26em;margin-top:6px}
  .tag:empty{display:none}
  .sub{font-size:14.5px;color:rgba(255,255,255,.65);line-height:1.65;max-width:300px;margin-top:16px}
  .stack{margin-top:34px;width:100%;max-width:330px;display:flex;flex-direction:column;gap:12px}
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
  /* ── דסקטופ: עמודה ממורכזת (המובייל הוא המקור; מסך רחב מלא — בשלב הדסקטופ) ── */
  @media (min-width:700px){
    header,main,nav,#impBar{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
    #menu{max-width:340px}
    #story .bars,#story .shead,#story .body,#story .sfoot{width:100%;max-width:600px;
        margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
</style></head><body>

  <div class="ring"><div id="logoWrap"><img id="logo" src="/assets/logo" alt=""
      onerror="this.style.display='none'"></div></div>
  <div class="tag" id="tagline"></div>
  <div class="sub">מסכם שיחות, מגייס נכסים ומחתים דיגיטלית — כדי שאתה תסגור עסקאות.</div>

  <div class="stack">
    <button class="btn btn-g" onclick="location.href='/auth/google/login?' + (window.Capacitor ? 'native=1' : 'next=v2')">
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
      <input id="ph" type="tel" inputmode="numeric" autocomplete="tel" placeholder="מספר הטלפון שלך">
      <input id="cd" type="tel" inputmode="numeric" autocomplete="one-time-code" placeholder="הקוד שקיבלת ב-SMS" style="display:none">
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
        localStorage.removeItem('v2who');
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
  document.title = o.name || 'כניסה';
  if (o.reveal){
    el('tagline').textContent = 'העוזר של המתווך';
    el('logoWrap').innerHTML = o.logo_svg || '';
  }
}).catch(function(){});

/* Capacitor (האפליקציה העטופה): כניסת Google חוזרת בדיפ-לינק עם טוקן */
(function(){
  try{
    if (!window.Capacitor || !Capacitor.Plugins || !Capacitor.Plugins.App) return;
    Capacitor.Plugins.App.addListener('appUrlOpen', function(data){
      try{
        var m = String((data && data.url) || '').match(/[?&#]token=([^&]+)/);
        if (!m) return;
        localStorage.setItem('fbTok', decodeURIComponent(m[1]));
        localStorage.removeItem('v2who');
        try{ if (Capacitor.Plugins.Browser) Capacitor.Plugins.Browser.close(); }catch(e){}
        location.replace('/v2/home');
      }catch(e){}
    });
  }catch(e){}
})();
// שער Face ID — פעיל רק בתוך אפליקציית Capacitor; בדפדפן נכנסים ישר
function bioPlugin(){ try{ return (window.Capacitor && Capacitor.Plugins && Capacitor.Plugins.NativeBiometric) || null; }catch(e){ return null; } }
function bioLock(){
  if (el('biolock')) return;
  var d = document.createElement('div');
  d.id = 'biolock';
  d.setAttribute('style', 'position:fixed;inset:0;z-index:9999;background:#F2EFE7;display:flex;flex-direction:column;' +
    'align-items:center;justify-content:center;text-align:center;padding:24px;font-family:Heebo,Arial,sans-serif');
  d.innerHTML =
    '<div style="width:92px;height:92px;border-radius:50%;background:#fff;border:2px solid #E4C56B;display:flex;' +
      'align-items:center;justify-content:center;margin-bottom:20px;overflow:hidden">' +
      '<img src="/assets/logo" style="width:64px;height:64px;object-fit:contain" onerror="this.style.display=\'none\'"></div>' +
    '<svg width="34" height="34" viewBox="0 0 24 24" style="margin-bottom:10px"><rect x="5" y="10" width="14" height="10" rx="3" ' +
      'fill="none" stroke="#1E3A5F" stroke-width="1.8"/><path d="M8 10V7.5a4 4 0 018 0V10" fill="none" stroke="#1E3A5F" ' +
      'stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="15" r="1.6" fill="#1E3A5F"/></svg>' +
    '<div style="font-size:19px;font-weight:800;color:#1E3A5F;margin-bottom:4px">האפליקציה נעולה</div>' +
    '<div style="font-size:13.5px;color:#8B8F99;margin-bottom:24px">אמת את זהותך כדי להיכנס</div>' +
    '<button id="biobtn" onclick="bioGo()" style="width:100%;max-width:320px;padding:15px;background:#2E6BD6;color:#fff;' +
      'border:none;border-radius:14px;font-size:15.5px;font-weight:800;font-family:inherit">כניסה עם Face ID</button>' +
    '<button onclick="bioSkip()" style="margin-top:14px;background:none;border:none;color:#8B8F99;font-size:13.5px;' +
      'font-family:inherit;text-decoration:underline">כניסה עם מספר טלפון</button>';
  document.body.appendChild(d);
}
function bioGo(){
  var bp = bioPlugin(), b = el('biobtn');
  if (!bp){ bioEnter(); return; }
  if (b){ b.textContent = 'מאמת…'; b.disabled = true; }
  bp.verifyIdentity({reason:'כניסה מאובטחת', title:'אימות זהות', subtitle:'', description:'אמת את זהותך כדי להיכנס',
      useFallback:true, maxAttempts:3})
    .then(bioEnter)
    .catch(function(){ var b2 = el('biobtn'); if (b2){ b2.textContent = 'נסה שוב'; b2.disabled = false; } });
}
function bioEnter(){ location.replace('/v2/home'); }
function bioSkip(){
  // כניסה מחדש עם טלפון — מנקים את הסשן ונשארים במסך הכניסה
  try{ ['fbTok','fbRole','fbDrole','fbName','fbDev','fbPhone','fbTabs'].forEach(function(k){ localStorage.removeItem(k); }); }catch(e){}
  var d = el('biolock'); if (d) d.remove();
}
// כבר מחובר? — באפליקציה עוברים דרך Face ID, בדפדפן ישר פנימה
(function(){
  var t = null;
  try{ t = localStorage.getItem('fbTok'); }catch(e){}
  if (!t) return;
  fetch('/api/auth/whoami', {headers:{'X-Auth-Token': t}}).then(function(r){ return r.json(); })
    .then(function(j){
      if (!j.ok) return;
      var bp = bioPlugin();
      if (!bp){ bioEnter(); return; }
      bp.isAvailable().then(function(res){
        if (res && res.isAvailable){ bioLock(); bioGo(); } else bioEnter();
      }).catch(bioEnter);
    }).catch(function(){});
})();
</script></body></html>'''


# ── שכבת מהירות (V2_BOOST): preconnect לפונטים, whoami מהמטמון, prefetch טאבים ──
V2_BOOST = r"""<style>
/* iOS (בעיקר \"הוסף למסך הבית\"/standalone): אוברסקרול שקוף — רקע קרם במקום פס לבן,
   וביטול הריצודים של הניווט הקבוע מעל הגלילה הפנימית. חל רק על דפי הטאבים (:has(nav)). */
html:has(nav){ background:#F2EFE7; overscroll-behavior:none; }
body:has(nav){ overscroll-behavior:none; }
body:has(nav) nav{ transform:translateZ(0); -webkit-backface-visibility:hidden; backface-visibility:hidden; }
/* לא כופים גלילת-מומנטום על main גלובלית: ב-10 מ-12 הדפים main אינו הגולל (החלון הוא),
   וב-iOS זה יצר אזור מומנטום שלכד את המגע ומנע גלילת חלון. overscroll-behavior נשאר. */
body:has(nav) main{ overscroll-behavior-y:contain; }
/* iOS PWA standalone (\"הוסף למסך הבית\") בלבד — מזוהה ע\"י class .pwa על <html>:
   שם גלילת המסמך מרצדת את הניווט הקבוע בבאונס. נועלים את הגוף ומעבירים את הגלילה ל-main
   (כמו מסך היומן) — הגוף לא זז, הניווט לא מרצד. דפדפן רגיל/דסקטופ/אפליקציה לא מקבלים את הקלאס. */
html.pwa, html.pwa body{ height:100%; }
html.pwa body:has(nav){ overflow:hidden; }
html.pwa body:has(nav) main{ overflow:auto; -webkit-overflow-scrolling:touch; }
</style>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<script>
(function(){
  /* מסמנים אך ורק PWA standalone של iOS (הוסף למסך הבית ב-Safari) — navigator.standalone
     הוא true רק שם; ב-Safari רגיל=false, בדסקטופ ובאפליקציית Capacitor=undefined. מוקדם, בלי הבהוב. */
  try{ if (navigator.standalone === true) document.documentElement.classList.add('pwa'); }catch(e){}
})();
(function(){
  /* whoami מיידי מהמטמון (10 דק') — הדף לא מחכה לרשת; רענון רץ ברקע ומעדכן.
     טוקן שפג: הרענון ברקע מוחק את המטמון ומחזיר למסך הכניסה. */
  var _f = window.fetch.bind(window);
  window.fetch = function(u, o){
    try{
      if (String(u).indexOf('/api/auth/whoami') >= 0){
        var c = null;
        try{ c = JSON.parse(localStorage.getItem('v2who') || 'null'); }catch(e){}
        var live = _f(u, o).then(function(r){ return r.json(); }).then(function(j){
          try{
            if (j && j.ok) localStorage.setItem('v2who', JSON.stringify({t: Date.now(), j: j}));
            else{
              localStorage.removeItem('v2who');
              if (c) location.replace('/v2');
            }
          }catch(e){}
          return new Response(JSON.stringify(j), {headers: {'Content-Type': 'application/json'}});
        });
        if (c && c.j && c.j.ok && (Date.now() - c.t) < 600000){
          live.catch(function(){});
          return Promise.resolve(new Response(JSON.stringify(c.j), {headers: {'Content-Type': 'application/json'}}));
        }
        return live;
      }
    }catch(e){}
    return _f(u, o);
  };
  /* prefetch: נגיעה/ריחוף על טאב מחמם את הדף הבא עוד לפני הניווט */
  function warm(e){
    var it = e.target && e.target.closest ? e.target.closest('nav .it') : null;
    if (!it) return;
    var m = /location\.href='([^']+)'/.exec(it.getAttribute('onclick') || '');
    if (m && !it._warmed){ it._warmed = 1; _f(m[1], {credentials: 'same-origin'}).catch(function(){}); }
  }
  document.addEventListener('touchstart', warm, {passive: true, capture: true});
  document.addEventListener('mouseover', warm, {passive: true, capture: true});
})();
</script>"""

# ── שכבת דסקטופ/טאבלט (עיצוב §13): סרגל צד מימין, תוכן רחב, בית בגריד ─────────
# מוזרק לכל דף ב-_page(); ממוקד ב-body:has(nav) כדי לא לגעת בדף הכניסה/טפסים.
V2_DESKTOP_CSS = r"""<style>
nav .it.dk{display:none}   /* תהליכים+יומן — רק בסרגל הצד (טאבלט/דסקטופ) */
/* כשהחלון הוא הגולל (כל מה שאינו iOS-PWA: אנדרואיד, ספארי רגיל, דסקטופ) — main אינו מיכל-גלילה.
   overscroll-behavior:contain על main לוכד את המגע באנדרואיד ומונע גלילת חלון (iOS Safari סלחני).
   iOS-PWA (html.pwa) שומר על main-scroll ותיקון הריצוד — לא מושפע. */
html:not(.pwa) body:has(nav) main{ overflow:visible; overscroll-behavior:auto; }
/* טאבלט 768–1023: הסרגל מתכווץ לאייקונים (§13) */
@media (min-width:768px){
  nav .it.dk{display:flex}
  body:has(nav){padding-right:96px}
  body:has(nav) header, body:has(nav) main, body:has(nav) #impBar{max-width:640px}
  body:has(nav) main{padding-bottom:28px}
  /* דסקטופ/טאבלט: החלון הוא הגולל. main אינו מיכל-גלילה (בלי overflow:auto+contain
     שלוכד את הגלגלת ומונע גלילת חלון). מבטל את הכלל הגלובלי מ-V2_BOOST במסכים רחבים. */
  body:has(nav) main{overflow:visible;overscroll-behavior:auto}
  nav{position:fixed;top:16px;bottom:16px;right:14px;left:auto;width:66px;max-width:none;margin:0;
      border:1px solid #E9E4D8;border-radius:20px;box-shadow:0 8px 26px rgba(30,58,95,.07);
      padding:14px 8px;display:flex;flex-direction:column;justify-content:flex-start;align-items:center;gap:8px}
  nav .it{flex-direction:column;width:100%;padding:10px 0;border-radius:13px;font-size:0;gap:0;min-width:0}
  nav .it:hover{background:#F5F2E9}
  nav .it:has(.home){background:#1E3A5F}
  nav .it:has(.home):hover{background:#1E3A5F}
  nav .home{margin-top:0;box-shadow:none;background:rgba(255,255,255,.14)}
  nav .badge{top:2px;right:6px}
  #toast{bottom:40px}
}
/* דסקטופ ≥1024: סרגל מלא עם תוויות (בית פעיל נייבי, נכס נולד עם badge) */
@media (min-width:1024px){
  body:has(nav){padding-right:264px}
  body:has(nav) header, body:has(nav) main, body:has(nav) #impBar{max-width:940px}
  #sheet{max-width:640px}
  nav{width:224px;padding:88px 12px 16px;align-items:stretch}
  nav::before{content:'';position:absolute;top:18px;left:14px;right:14px;height:52px;
      background:url(/assets/logo) center/contain no-repeat}
  nav .it{flex-direction:row;justify-content:flex-start;gap:11px;padding:11px 12px;font-size:14px;
      font-weight:600;border-radius:14px;width:auto}
  nav .it:has(.home){color:#fff !important;font-weight:800}
  nav .home{width:36px;height:36px;border-radius:12px}
  nav .badge{position:static;top:auto;right:auto;order:9;margin-inline-start:auto;align-self:center;
      font-size:10.5px;padding:2px 9px;line-height:1.4;flex-shrink:0}
  /* הבית: הבריף כבאנר רוחבי, סטטיסטיקות בשורה, גריד שתי עמודות (§13) */
  body:has(nav) main:has(.briefBar){display:grid;grid-template-columns:1fr 1fr;gap:13px;
      align-items:start;max-width:1000px}
  main:has(.briefBar) > .greet, main:has(.briefBar) > .stats,
  main:has(.briefBar) > .briefBar, main:has(.briefBar) > .care{grid-column:1 / -1}
}
</style>"""

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
  .brand img{height:36px;max-width:150px;object-fit:contain}
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
  .qaBadge{display:none;position:absolute;top:-7px;left:-4px;background:#C29435;color:#fff;font-size:11px;
      font-weight:800;min-width:20px;height:20px;border-radius:999px;padding:0 6px;align-items:center;
      justify-content:center;box-shadow:0 2px 6px rgba(194,148,53,.35)}
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
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer;position:relative}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
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
  #story .ringWrap>div{width:100%;height:100%;border-radius:50%;background:#fff;
      display:flex;align-items:center;justify-content:center;overflow:hidden}
  #story .ringWrap img{width:72%;height:72%;object-fit:contain}
  #story .teasers{display:flex;gap:10px}
  #story .teasers .tz{flex:1;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);
      border-radius:14px;padding:14px 6px;display:flex;flex-direction:column;align-items:center;gap:3px}
  #story .teasers .tz .n{font-size:30px;font-weight:800;color:#E4C56B;font-variant-numeric:tabular-nums}
  #story .teasers .tz .l{font-size:13px;font-weight:700;color:rgba(255,255,255,.85);text-align:center;line-height:1.3}
  #story .teasers .tz .of{font-size:13.5px;font-weight:700;color:rgba(255,255,255,.7);margin-top:3px;
      font-variant-numeric:tabular-nums}
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
  /* ── דסקטופ: עמודה ממורכזת (המובייל הוא המקור; מסך רחב מלא — בשלב הדסקטופ) ── */
  @media (min-width:700px){
    header,main,nav,#impBar{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
    #menu{max-width:340px}
    #story .bars,#story .shead,#story .body,#story .sfoot{width:100%;max-width:600px;
        margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
</style></head><body>

  <div id="impBar" style="display:none;position:sticky;top:0;z-index:75;background:#C29435;color:#fff;
       padding:calc(env(safe-area-inset-top,0px) + 8px) 14px 8px;align-items:center;justify-content:center;gap:10px;
       font-size:12.5px;font-weight:700">
    <span id="impTx"></span>
    <button onclick="impBack()" style="background:#fff;color:#B8902F;border:0;border-radius:999px;
        padding:5px 12px;font-size:11.5px;font-weight:800;font-family:inherit;cursor:pointer">חזרה למנהל</button>
  </div>

  <header>
    <div class="avatar" onclick="openMe()" style="cursor:pointer"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img id="brandLogo" src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
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
    <a href="/v2/updates" style="display:flex;align-items:center;gap:11px;padding:12px 4px;text-decoration:none;
       color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><path d="M4 14V9a7 7 0 0 1 14 0v5l1.5 2.5H2.5z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 18.5a2 2 0 0 0 4 0" fill="none" stroke="#1E3A5F" stroke-width="1.7"/></svg>
      עדכונים למשרד</a>
    <a id="menuActivity" href="/v2/activity" style="display:none;align-items:center;gap:11px;padding:12px 4px;
       text-decoration:none;color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><circle cx="11" cy="11" r="8" fill="none" stroke="#1E3A5F" stroke-width="1.7"/><path d="M11 6.5V11l3 2" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linecap="round"/></svg>
      יומן שימוש</a>
    <a href="/v2/reports" style="display:flex;align-items:center;gap:11px;padding:12px 4px;text-decoration:none;
       color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 22 22"><path d="M3.5 18.5v-5M8.5 18.5v-9M13.5 18.5V5.5M18.5 18.5v-7" stroke="#1E3A5F" stroke-width="2" stroke-linecap="round"/></svg>
      דוחות</a>
    <a href="/v2/deals" style="display:flex;align-items:center;gap:11px;padding:12px 4px;text-decoration:none;
       color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#1E3A5F" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#1E3A5F" stroke-width="1.5" stroke-linecap="round"/></svg>
      תהליכים ועסקאות</a>
    <a href="/v2/map" style="display:flex;align-items:center;gap:11px;padding:12px 4px;text-decoration:none;
       color:#1E3A5F;font-size:14px;font-weight:700;min-height:44px">
      <svg width="18" height="18" viewBox="0 0 16 16"><path d="M8 14s-5-4.2-5-8a5 5 0 0 1 10 0c0 3.8-5 8-5 8z" fill="none" stroke="#1E3A5F" stroke-width="1.5"/><circle cx="8" cy="6" r="1.8" fill="none" stroke="#1E3A5F" stroke-width="1.5"/></svg>
      נכסים במפה</a>
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
    <button onclick="inviteWa()" style="display:flex;align-items:center;gap:11px;padding:12px 4px;border:0;
       background:none;color:#1E3A5F;font-size:14px;font-weight:700;font-family:inherit;cursor:pointer;min-height:44px;text-align:right">
      <svg width="18" height="18" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#1FAF5E" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      הזמנה לאפליקציה בוואטסאפ</button>
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
      <div class="stat"><div class="n" style="color:#1FAF5E" id="stSigs">—</div><div class="l">גויסו השבוע</div></div>
      <div class="stat"><div class="n" style="color:#B8902F" id="stBuyers">—</div><div class="l">קונים חדשים</div></div>
    </div>

    <div class="briefBar" onclick="openStory()">
      <div class="ic"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
      <div style="flex:1;display:flex;flex-direction:column;gap:1px">
        <div class="t" id="briefTitle">סטורי נכסים חמים</div>
        <div class="s" id="briefSum">הנכסים החמים של המשרד + הסיכום שלך</div>
      </div>
      <button class="cta" id="briefCta">צפה</button>
    </div>

    <div class="qa">
      <div class="a blue" onclick="location.href='/v2/buyers?add=1'">
        <div class="ic"><svg width="15" height="15" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg></div>
        <div class="l">הוסף קונה</div>
      </div>
      <div class="a gold" onclick="location.href='/v2/sigs'">
        <div class="ic"><svg width="15" height="15" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg></div>
        <div class="l">חתימות</div>
      </div>
      <div class="a lite" onclick="location.href='/v2/props'">
        <div class="ic" style="background:#EAF0FA"><svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5" fill="none" stroke="#2E6BD6" stroke-width="1.8"/><path d="M10.5 10.5l3 3" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round"/></svg></div>
        <div class="l">חיפוש נכס</div>
      </div>
      <div class="a lite" style="position:relative" onclick="location.href='/v2/deals'">
        <div class="ic" style="background:#F6EEDB"><svg width="15" height="15" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#B8902F" stroke-width="1.6"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#B8902F" stroke-width="1.6" stroke-linecap="round"/></svg></div>
        <div class="l">תהליכים</div>
        <div class="qaBadge" id="dealsBadge"></div>
      </div>
    </div>

    <div style="display:flex;gap:10px">
      <div class="strip" style="flex:1;min-width:0;cursor:pointer" onclick="location.href = (M.role === 'admin') ? '/v2/props' : '/v2/props?mine=1'">
        <div class="ic"><svg width="17" height="17" viewBox="0 0 16 16"><path d="M2 8L8 3l6 5v5a.8.8 0 0 1-.8.8H9.8V10H6.2v3.8H2.8A.8.8 0 0 1 2 13z" fill="none" stroke="#2E6BD6" stroke-width="1.6" stroke-linejoin="round"/></svg></div>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:1px">
          <div class="t" id="propsT">הנכסים שלי</div>
          <div class="s" id="propsSum" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">מתעדכן…</div>
        </div>
      </div>
      <div class="strip" style="flex:1;min-width:0;cursor:pointer" onclick="location.href='/v2/meets'">
        <div class="ic" style="background:#F6EEDB"><svg width="17" height="17" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#B8902F" stroke-width="1.6"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#B8902F" stroke-width="1.6" stroke-linecap="round"/></svg></div>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:1px">
          <div class="t">יומן</div>
          <div class="s" id="meetsSum" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">פגישות ופולו-אפ</div>
        </div>
      </div>
    </div>

    <div class="care">
      <div class="hd"><div class="t">דורש טיפול</div><div class="all" onclick="location.href='/v2/meets'">הכל</div></div>
      <div id="careList"><div class="careEmpty" style="padding:6px 0"><div class="s">מתעדכן…</div></div></div>
    </div>
  </main>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" style="color:#1E3A5F;font-weight:700"><div class="home"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg></div>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><div class="badge" id="nbBadge"></div><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <!-- ── בריף הבוקר — סטורי ── -->
  <div id="story">
    <div class="bars" id="storyBars"><i><b></b></i></div>
    <div class="shead">
      <div style="display:flex;align-items:center;gap:10px">
        <div class="lg"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
        <div><div class="t">נכסים חמים</div><div class="s" id="storyDate"></div></div>
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
  <div id="ovl" onclick="closeSheet()" style="position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:60"></div>
  <div id="meSheet" style="position:fixed;left:0;right:0;bottom:0;z-index:61;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:14px 18px calc(env(safe-area-inset-bottom,0px) + 18px);
      display:none;flex-direction:column;gap:12px;max-height:82vh;overflow:auto;max-width:600px;margin:0 auto"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
    try{ localStorage.removeItem('v2who'); }catch(e){}
    localStorage.removeItem('fbTokAdmin');
  }catch(e){}
  location.href = '/v2/admin';
}
function openSheet(html){
  el('meSheet').innerHTML = '<div style="width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center"></div>' + html;
  el('meSheet').style.display = 'flex'; el('ovl').style.display = 'block';
  document.documentElement.style.overflow = 'hidden'; document.body.style.overflow = 'hidden';
}
function closeSheet(){
  el('meSheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.documentElement.style.overflow = ''; document.body.style.overflow = '';
}
function POST(u, d){
  return fetch(u, {method:'POST', headers:{'X-Auth-Token': TOK, 'Content-Type':'application/json'},
    body: JSON.stringify(d)}).then(function(r){ return r.json(); });
}
var ME = {phone: '', name: '', role: ''};
function openMe(){
  var avUrl = '/v2/api/avatar?p=' + ME.phone + '&t=' + Date.now();
  openSheet('<div style="display:flex;align-items:center;justify-content:space-between">' +
    '<h3 style="margin:0">אזור אישי</h3>' +
    '<button onclick="closeSheet()" aria-label="סגירה" style="width:36px;height:36px;border-radius:50%;background:#EFEBDD;border:none;display:flex;align-items:center;justify-content:center;cursor:pointer">' +
    '<svg width="12" height="12" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round"/></svg></button></div>' +
    '<div style="display:flex;align-items:center;gap:14px">' +
    '<div style="position:relative;width:72px;height:72px;border-radius:50%;background:#1E3A5F;color:#fff;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;overflow:hidden;flex-shrink:0">' +
    '<img id="meAv" src="' + avUrl + '" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display=\'none\'">' +
    '<span style="position:absolute">' + esc((ME.name || ' ')[0]) + '</span></div>' +
    '<div><div style="font-size:16.5px;font-weight:800">' + esc(ME.name) + '</div>' +
    '<div style="font-size:12.5px;color:#8B8F99">' + esc(ME.role) + (ME.phone ? ' · 0' + esc(ME.phone) : '') + '</div></div></div>' +
    '<input type="file" id="meFile" accept="image/*" style="display:none" onchange="meUpload(this)">' +
    '<button style="display:flex;align-items:center;justify-content:center;width:100%;padding:13px 0;border-radius:13px;font-size:14.5px;font-weight:700;font-family:inherit;cursor:pointer;background:#fff;color:#1E3A5F;border:1.5px solid #DCD6C8" onclick="el(\'meFile\').click()">החלפת תמונת פרופיל</button>' +
    '<button style="display:flex;align-items:center;justify-content:center;width:100%;padding:13px 0;border-radius:13px;font-size:14.5px;font-weight:700;font-family:inherit;cursor:pointer;background:#fff;color:#1E3A5F;border:1.5px solid #DCD6C8" ' +
    'onclick="location.href=\'/auth/google/login?\' + (window.Capacitor ? \'native=1\' : \'next=v2\')">' +
    'סנכרון יומן Google (גם אחרי כניסה ב-SMS)</button>' +
    '<button style="display:flex;align-items:center;justify-content:center;width:100%;padding:13px 0;border-radius:13px;font-size:14.5px;font-weight:700;font-family:inherit;cursor:pointer;background:#EFEBDD;color:#5B6472;border:0" onclick="closeSheet()">סגירה</button>');
  // תמונה קיימת מכסה את האות
  var im = el('meAv');
  if (im) im.onload = function(){ var sp = im.parentNode.querySelector('span'); if (sp) sp.style.display = 'none'; };
}
function meUpload(inp){
  var f = inp.files && inp.files[0];
  if (!f) return;
  var img = new Image();
  img.onload = function(){
    var c = document.createElement('canvas');
    var s = Math.min(img.width, img.height);
    c.width = 144; c.height = 144;
    c.getContext('2d').drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, 144, 144);
    var data = c.toDataURL('image/jpeg', 0.82);
    POST('/v2/api/avatar', {img: data}).then(function(j){
      if (!j.ok){ toast('שגיאה בשמירת התמונה'); return; }
      toast('התמונה נשמרה');
      openMe();
      setHeaderAvatar();
    });
  };
  img.src = URL.createObjectURL(f);
}
function setHeaderAvatar(){
  if (!ME.phone) return;
  var c = el('avatarTx');
  if (!c) return;
  c.innerHTML = '<img src="/v2/api/avatar?p=' + ME.phone + '&t=' + Date.now() + '" ' +
    'style="width:100%;height:100%;object-fit:cover;border-radius:50%" onerror="this.remove()">' +
    '<span>' + esc((ME.name || ' ')[0]) + '</span>';
}
function inviteWa(){
  // הזמנת עמית לאפליקציה — קישור הכניסה + שם המשרד (white-label)
  var nm = (document.title && document.title !== 'בית') ? document.title : 'המשרד';
  var msg = 'היי, מזמין אותך לאפליקציה של ' + nm + ' — שיחות, קונים, נכסים וחתימות דיגיטליות במקום אחד:\n' +
    location.origin + '/v2';
  window.open('https://wa.me/?text=' + encodeURIComponent(msg), '_blank');
}
function logout(){
  try{
    ['fbTok','fbRole','fbDrole','fbName','fbDev','fbPhone','fbTabs','v2who'].forEach(function(k){ localStorage.removeItem(k); });
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
    GET('/api/my/properties').catch(function(){ return {}; }),
    GET('/api/signatures').catch(function(){ return {}; }),
    GET('/api/newborn/meetings').catch(function(){ return {}; })
  ]).then(function(rs){
    // גיוסים ב-7 הימים האחרונים — כל החתמת בעל נכס (בלעדיות או מוכר), בלי כפילויות
    var wk7 = Math.floor(Date.now() / 1000) - 7 * 86400;
    var seen = {};
    M.exclWeek = (((rs[3] || {}).signatures) || []).filter(function(g){
      var t = g.type || '';
      if (!((t.indexOf('בלעדיות') >= 0 || t.indexOf('מוכר') >= 0) && (g.ts || 0) >= wk7)) return false;
      var k = (g.address || '') + '|' + (g.client || '');
      if (seen[k]) return false;
      seen[k] = 1;
      return true;
    });
    var rep = rs[0] || {}, sm = rep.summary || {};
    M.calls = (sm.calls || {}).total || 0;
    M.sigs = (sm.sigs || {}).total || 0;
    M.sigSample = (sm.sigsList && sm.sigsList[0]) || null;
    M.excl = (sm.exclusives || []).length;   // נכסים שגויסו בבלעדיות בתקופת הדוח
    M.repLabel = rep.label || 'השבוע';
    M.listings = rep.listings || 0;
    // אותו סינון של מסך היומן — לדוח יש סקופ אחר למתאמת (כל המשרד) והבריף היה מציג יותר מדי
    M.meets = ((rs[4] || {}).results) || rep.meetings || [];
    var _ms = el('meetsSum');
    if (_ms) _ms.textContent = M.meets.length ? (M.meets.length + ' פגישות ופולו-אפ פתוחים') : 'אין משימות פתוחות';
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
  el('stSigs').textContent = (M.exclWeek || []).length;   // גויס בשבוע האחרון (החתמות בעלי נכס)
  el('stBuyers').textContent = M.buyersNew || M.buyersTot;
  var open = M.meetLate + M.meetToday;
  el('dateTx').textContent = 'יום ' + HDAYS[new Date().getDay()] + ', ' + new Date().getDate() +
      ' ב' + HMON[new Date().getMonth()] + (open ? ' · ' + open + ' משימות פתוחות' : '');
  // הבאנר מציג "סטורי נכסים חמים" (#33b) — הכותרת מתעדכנת עם מספר הסוכנים כשה-brief נטען.
  // מנהל: נכסי כל המשרד; סוכן: שלו. "בבלעדיות" הישן היה למעשה גיוסי התקופה — עכשיו מפורש
  if (M.role === 'admin') el('propsT').textContent = 'נכסי המשרד';
  el('propsSum').textContent = ((M.role === 'admin' && M.listings) ? M.listings : M.props) + ' פעילים' +
      (M.excl ? ' · ' + M.excl + ' גויסו בבלעדיות ' + (M.repLabel || 'השבוע') : '');
  var care = [];
  M.meets.slice().sort(function(a, b){
    return (parseDMY(a.date) || 0) - (parseDMY(b.date) || 0);
  }).forEach(function(m){
    var d = parseDMY(m.date);
    var dd = d ? dayDiff(d) : 99;
    var chipTx = dd < 0 ? 'באיחור' : dd === 0 ? 'היום' : dd === 1 ? 'מחר'
               : (d ? ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) : '');
    care.push({t: (m.label || (m.status === 'meeting' ? 'פגישה' : 'פולו-אפ')) + ': ' + (m.addr || ''),
               s: 'נכס נולד · ' + (m.agent || '') + (m.date ? ' · ' + String(m.date).replace('T', ' ') : ''),
               chip: dd < 0 ? 'late' : dd === 0 ? 'today' : 'soon',
               chipTx: chipTx,
               ord: dd < 0 ? -1000 + dd : dd,   // באיחור קודם, אחר כך לפי קרבה
               meeting: m.status === 'meeting'});
  });
  care.sort(function(a, b){ return a.ord - b.ord; });
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
var B = {buyersMe:null, buyersAll:null, sigBMe:null, sigBAll:null, exclMe:null, exclAll:null};
GET('/v2/api/brief').then(function(j){
  if (!j.ok) return;
  B = j;
  var np = (B.hotProps || []).length;
  var bt = el('briefTitle'); if (bt) bt.textContent = 'סטורי נכסים חמים' + (np ? ' · ' + np + (np === 1 ? ' נכס' : ' נכסים') : '');
  if (STORY.open && STORY.i === 0) renderCard(0);
}).catch(function(){});
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
function total(){ return 1 + ((B.hotProps && B.hotProps.length) || 0); }   // סיכום + נכסים חמים
function nextCard(){ (STORY.i < total() - 1) ? go(STORY.i + 1) : closeStory(); }
function prevCard(){ if (STORY.i > 0) go(STORY.i - 1); }
function go(i){ STORY.i = i; renderCard(i); }
function setBars(i){
  var T = total(), wrap = el('storyBars');
  if (wrap.children.length !== T){
    var hh = ''; for (var k = 0; k < T; k++) hh += '<i><b></b></i>';
    wrap.innerHTML = hh;
  }
  var bars = wrap.querySelectorAll('i b');
  for (var k = 0; k < T; k++){
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
  STORY.paused = false;
  el('storyHint').textContent = 'הקש להמשך · החלק למטה לסגירה';
  setBars(i);
  el('storyDate').textContent = 'יום ' + HDAYS[new Date().getDay()] + ', ' + new Date().getDate() +
      ' ב' + HMON[new Date().getMonth()] + ' · ' + (i + 1) + ' מתוך ' + total();
  var b = el('storyBody'), q = function(v){ return M.ready ? v : '…'; };
  var timeAgo = function(iso){ try{ var s=(Date.now()-new Date(iso).getTime())/1000;
    if(s<3600) return 'לפני '+Math.max(1,Math.round(s/60))+' דק׳';
    if(s<86400) return 'לפני '+Math.round(s/3600)+' שעות'; return 'לפני '+Math.round(s/86400)+' ימים'; }catch(e){ return ''; } };
  var statCard = function(n,label,col){ return '<div style="background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:2px">'+
    '<div style="font-size:30px;font-weight:800;color:'+col+'">'+n+'</div><div style="font-size:12.5px;color:rgba(255,255,255,.6)">'+label+'</div></div>'; };
  var hlRow = function(icon,label,val){ return '<div style="display:flex;align-items:center;gap:11px;background:rgba(255,255,255,.06);border-radius:14px;padding:12px 14px">'+
    '<div style="width:34px;height:34px;border-radius:10px;background:rgba(228,197,107,.16);display:flex;align-items:center;justify-content:center;flex-shrink:0">'+icon+'</div>'+
    '<div style="flex:1;display:flex;flex-direction:column;gap:1px"><div style="font-size:11px;color:rgba(255,255,255,.5)">'+label+'</div>'+
    '<div style="font-size:13.5px;font-weight:700;color:#fff">'+val+'</div></div></div>'; };
  if (i === 0){
    var hpArr = B.hotProps || [];
    var byA = {}; hpArr.forEach(function(x){ if(x.agent) byA[x.agent]=(byA[x.agent]||0)+1; });
    var tA='', tN=0; for (var a in byA) if (byA[a]>tN){ tN=byA[a]; tA=a; }
    var sigsTot = (B.sigBAll||0) + (B.exclAll||0);
    var pinSvg = '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M8 14s-5-4.2-5-8a5 5 0 0 1 10 0c0 3.8-5 8-5 8z" fill="none" stroke="#E4C56B" stroke-width="1.5"></path><circle cx="8" cy="6" r="1.6" fill="none" stroke="#E4C56B" stroke-width="1.5"></circle></svg>';
    var usrSvg = '<svg width="15" height="15" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#E4C56B" stroke-width="1.7"></circle><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#E4C56B" stroke-width="1.7" stroke-linecap="round"></path></svg>';
    b.innerHTML =
      '<div style="display:flex;flex-direction:column;gap:2px;margin-bottom:2px">'+
        '<div style="font-size:12px;font-weight:700;color:#E4C56B;letter-spacing:.12em">'+greetWord()+', '+esc(M.name)+'</div>'+
        '<div style="font-size:21px;font-weight:800;color:#fff">המשרד מתחילת השנה</div></div>'+
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:11px">'+
        statCard(q(B.dealsYear), 'עסקאות', '#5FD08C')+
        statCard(q(B.exclAll), 'בלעדיות', '#E4C56B')+
        statCard(q(B.callsAll), 'שיחות נכנסו', '#fff')+
        statCard(q(B.buyersTotal), 'קונים במערכת', '#E4C56B')+
      '</div>'+
      '<div style="display:flex;flex-direction:column;gap:9px;margin-top:14px">'+
        (hpArr[0] ? hlRow(pinSvg, 'הנכס החם המוביל', esc(hpArr[0].title||'')) : '')+
      '</div>'+
      // באנר הישג — דירוג המשרד ברשת רימקס ישראל מתחילת השנה (טקסט קבוע)
      '<div style="margin-top:12px;background:linear-gradient(135deg,rgba(228,197,107,.14),rgba(228,197,107,.05));border:1px solid rgba(228,197,107,.35);border-radius:16px;padding:14px 15px">'+
        '<div style="font-size:11px;font-weight:700;color:#E4C56B;letter-spacing:.06em;margin-bottom:10px">רימקס פמילי קריות · רשת רימקס ישראל</div>'+
        '<div style="display:flex;align-items:center;gap:11px;margin-bottom:9px">'+
          '<svg width="17" height="17" viewBox="0 0 16 16"><path d="M4.5 2h7v3a3.5 3.5 0 0 1-7 0V2z" fill="none" stroke="#E4C56B" stroke-width="1.2"/><path d="M4.5 3H2.8v1.2A2 2 0 0 0 4.8 6.2M11.5 3h1.7v1.2a2 2 0 0 1-2 2M6.5 9.7h3M5.7 13.2h4.6M8 9.7v3.5" fill="none" stroke="#E4C56B" stroke-width="1.2" stroke-linecap="round"/></svg>'+
          '<div style="font-size:13.5px;color:#fff;line-height:1.35"><b style="color:#E4C56B">מקום 2</b> בעסקאות מתחילת השנה</div>'+
        '</div>'+
        '<div style="display:flex;align-items:center;gap:11px">'+
          '<svg width="17" height="17" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="none" stroke="#E4C56B" stroke-width="1.2"/><path d="M8 4.4v7.2M6.2 6.2c0-1 .8-1.5 1.8-1.5s1.8.6 1.8 1.4c0 1.9-3.6 1-3.6 2.9 0 .9.8 1.5 1.8 1.5s1.8-.6 1.8-1.6" fill="none" stroke="#E4C56B" stroke-width="1.2" stroke-linecap="round"/></svg>'+
          '<div style="font-size:13.5px;color:#fff;line-height:1.35"><b style="color:#E4C56B">מקום 4</b> בעמלות משרדים מתחילת השנה</div>'+
        '</div>'+
      '</div>'+
      '<div class="btns" style="margin-top:auto;align-items:center">'+
        '<button class="bMain" style="width:100%" onclick="'+(total()>1?'nextCard()':'closeStory()')+'">'+(total()>1?'המשך לנכסים החמים ←':'בוא נתחיל את היום')+'</button>'+
        '<button class="skip" onclick="closeStory()">דלג לדשבורד</button></div>';
  } else {
    var hp = (B.hotProps || [])[i - 1] || {};
    var isLast = (i >= total() - 1);
    var prNum = String(hp.price || '').replace(/[^0-9]/g, '');
    var prTxt = prNum ? '₪' + Number(prNum).toLocaleString() : esc(hp.price || '');
    var wa = String(hp.agentPhone || '').replace(/^0/, ''); if (wa) wa = '972' + wa;
    var ini = esc((String(hp.agent || '?').trim().charAt(0)) || '?');
    b.innerHTML =
      '<div style="display:flex;flex-direction:column;align-items:center;gap:8px;margin-top:2px">'+
        '<div style="width:80px;height:80px;border-radius:50%;border:3px solid #E4C56B;padding:4px;box-sizing:border-box;animation:chickGlow 2.6s ease-out infinite">'+
          '<div style="width:100%;height:100%;border-radius:50%;background:rgba(228,197,107,.15);display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;color:#E4C56B">'+ini+'</div></div>'+
        '<div style="text-align:center"><div style="font-size:17px;font-weight:800;color:#fff">'+esc(hp.agent||'')+'</div>'+
          '<div style="font-size:11.5px;font-weight:600;color:#E4C56B">משתפת נכס חם'+(hp.ts?' · '+timeAgo(hp.ts):'')+'</div></div></div>'+
      '<div style="display:flex;justify-content:center;margin-top:2px"><div style="background:rgba(228,197,107,.16);border:1px solid rgba(228,197,107,.4);color:#E4C56B;border-radius:999px;padding:6px 15px;font-size:12px;font-weight:800">נכס חם</div></div>'+
      '<div style="display:flex;flex-direction:column;gap:6px;align-items:center;text-align:center;margin-top:2px">'+
        '<div style="font-size:22px;font-weight:800;color:#fff;line-height:1.25">'+esc(hp.title||'נכס')+'</div>'+
        (hp.details?'<div style="font-size:13.5px;color:rgba(255,255,255,.72)">'+esc(hp.details)+'</div>':'')+
        (hp.desc?'<div style="font-size:13px;color:rgba(255,255,255,.58);line-height:1.6;max-width:300px">'+esc(hp.desc)+'</div>':'')+
        (prTxt?'<div style="font-size:30px;font-weight:800;color:#E4C56B;margin-top:6px">'+prTxt+'</div>':'')+
      '</div>'+
      '<div style="margin-top:auto;display:flex;flex-direction:column;gap:9px">'+

        (wa?'<a href="https://wa.me/'+wa+'" class="bSec" style="margin:0;text-decoration:none;display:block;text-align:center">שאל את '+esc(hp.agent||'הסוכן')+'</a>':'')+
        '<button class="bSec" style="margin:0" onclick="'+(isLast?'closeStory()':'nextCard()')+'">'+(isLast?'בוא נתחיל את היום':'הנכס הבא ←')+'</button>'+
      '</div>';
  }
    STORY.timer = setTimeout(nextCard, STORY.DUR);
}
/* ניווט בהקשה: שמאל=הבא (RTL), ימין=הקודם; החלקה למטה=סגירה */
function pauseStory(){
  STORY.paused = true;
  clearTimeout(STORY.timer);
  var b = el('story').querySelectorAll('.bars i b')[STORY.i];
  if (b){ b.style.width = getComputedStyle(b).width; b.style.transition = 'none'; }
  el('storyHint').textContent = 'מושהה — הקש באמצע להמשך';
}
function resumeStory(){
  STORY.paused = false;
  var b = el('story').querySelectorAll('.bars i b')[STORY.i];
  var remain = STORY.DUR;
  if (b){
    var w = parseFloat(getComputedStyle(b).width) || 0;
    var total = b.parentNode.getBoundingClientRect().width || 1;
    remain = Math.max(400, (1 - w / total) * STORY.DUR);
    b.style.transition = 'width ' + remain + 'ms linear';
    b.style.width = '100%';
  }
  clearTimeout(STORY.timer);
  STORY.timer = setTimeout(nextCard, remain);
  el('storyHint').textContent = 'הקש להמשך · החלק למטה לסגירה';
}
el('story').addEventListener('click', function(e){
  if (e.target.closest('button')) return;
  var x = e.clientX, w = window.innerWidth;
  if (x > w * 0.33 && x < w * 0.66){   // אמצע המסך — השהיה/המשך
    STORY.paused ? resumeStory() : pauseStory();
    return;
  }
  STORY.paused = false;
  (x < w * 0.33) ? nextCard() : prevCard();
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
    M.role = j.role || '';
    ME = {phone: j.phone || '', name: j.name || '',
          role: j.dev ? 'בעל המשרד' : (j.role === 'admin') ? 'מנהל' : (j.role === 'coordinator') ? 'מתאמת' : 'סוכן'};
    setHeaderAvatar();
    el('greetTx').textContent = greetWord() + ', ' + M.name;
    el('avatarTx').textContent = M.name ? M.name.trim()[0] : '';
    el('menuAv').textContent = el('avatarTx').textContent;
    el('menuNm').textContent = M.name;
    el('menuRole').textContent = j.dev ? 'בעל המשרד' :
        (j.role === 'admin') ? 'מנהל' : (j.role === 'coordinator') ? 'מתאמת' : 'סוכן';
    if (j.dev) el('menuAdmin').style.display = 'flex';
    if (j.role === 'admin') el('menuActivity').style.display = 'flex';
    var impTok = null;
    try{ impTok = localStorage.getItem('fbTokAdmin'); }catch(e){}
    if (impTok && !j.dev){   // מצב "כניסה כסוכן (בדיקה)" — פס חזרה למנהל
      el('impTx').textContent = 'מצב בדיקה — אתה צופה כ' + (j.name || 'סוכן');
      el('impBar').style.display = 'flex';
    }
    var seenSess = null;
    try{ seenSess = sessionStorage.getItem('v2BriefSess'); }catch(e){}
    if (!seenSess){   // כל כניסה לאפליקציה (סשן חדש) — לא בכל רענון או חזרה לבית
      try{ sessionStorage.setItem('v2BriefSess', '1'); localStorage.setItem(seenKey(), todayStr()); }catch(e){}
      openStory();   // הסטורי הוא מסך הפתיחה
    } else el('briefCta').textContent = 'צפה שוב';
    loadData();
    GET('/api/deals').then(function(d){
      var n = ((d && d.items) || []).filter(function(x){ return !x.deal; }).length;
      var b = el('dealsBadge');
      if (b && n > 0){ b.textContent = n; b.style.display = 'flex'; }
    }).catch(function(){});
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
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;font-weight:600;color:#9AA0AB}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
            box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  /* bottom sheet */
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
       box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 16px;
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
  /* ── דסקטופ: עמודה ממורכזת (המובייל הוא המקור; מסך רחב מלא — בשלב הדסקטופ) ── */
  @media (min-width:700px){
    header,main,nav,#impBar{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
    #menu{max-width:340px}
    #story .bars,#story .shead,#story .body,#story .sfoot{width:100%;max-width:600px;
        margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
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
      <div style="display:flex;align-items:center;gap:9px;background:#F5F3EC;border:1px solid #E9E4D8;border-radius:14px;padding:0 14px">
        <svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M11 11l3.4 3.4" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>
        <input id="teamQ" placeholder="חיפוש סוכן לפי שם או טלפון" oninput="renderTeam()"
          style="flex:1;border:0;background:none;font-size:13.5px;font-family:inherit;outline:none;color:#1E3A5F;padding:11px 0">
      </div>
      <div id="teamList"></div>
    </div>

    <!-- שמות לא משויכים — מניעת כפילויות איות (מפתח בלבד) -->
    <div class="card" id="unmCard" style="display:none">
      <div class="cardTitle">שמות לא משויכים · מניעת כפילויות</div>
      <div style="font-size:12px;color:#8B8F99;line-height:1.5">שמות שמופיעים בחתימות או בנכסים ולא מזוהים
        לאף חבר צוות — שיוך לסוכן הופך אותם לכינוי שלו, וכל הנתונים (חתימות, השהיות, התראות) מתאחדים.</div>
      <div id="unmList"></div>
    </div>

    <!-- הגדרות המשרד -->
    <div class="card">
      <div class="cardTitle">הגדרות המשרד</div>
      <div class="setRow" onclick="location.href='/v2/onboard'">
        <div class="setIc" style="background:#EAF0FA"><svg width="18" height="18" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round"/></svg></div>
        <div class="mid"><div class="nm">חיבור משרד חדש</div><div class="sb">צ'קליסט המקורות המלא — עתידי</div></div>
        <svg width="8" height="12" viewBox="0 0 8 12"><path d="M6 1L2 6l4 5" fill="none" stroke="#9AA0AB" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="sep"></div>
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
      <div class="sep"></div>
      <div class="swRow"><div><div class="lb">וואטסאפ אוטומטי מהמערכת</div><div class="sb">התראות שיחה/חתימה לקבוצות ולסוכנים — מושהה עד מעבר ל-API רשמי</div></div>
        <div class="tg" id="tgWaAuto" onclick="togglePolicy('wa_auto', this)"></div></div>
    </div>
  </main>

  <div id="blocked">
    <div class="ic"><svg width="30" height="30" viewBox="0 0 22 22"><rect x="4" y="9" width="14" height="9" rx="2" fill="none" stroke="#C29435" stroke-width="1.7"/><path d="M7 9V6.5a4 4 0 0 1 8 0V9" fill="none" stroke="#C29435" stroke-width="1.7"/></svg></div>
    <div style="font-size:17px;font-weight:800">המסך למנהל המשרד בלבד</div>
    <div style="font-size:13px;color:#5B6472;max-width:250px;line-height:1.6">אין לחשבון שלך הרשאת ניהול. אם זו טעות — פנה למנהל המשרד.</div>
    <button class="btn btn-sec" style="max-width:220px" onclick="location.href='/v2/home'">חזרה לבית</button>
  </div>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
        UNMATCHED = ((rs[1] && rs[1].unmatchedSignings) || []).map(function(u){ return {n: u.name, c: u.count, w: 'חתימות'}; })
          .concat(((rs[1] && rs[1].unmatchedListings) || []).map(function(u){ return {n: u.name, c: u.count, w: 'נכסים'}; }));
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
  ['transcribe','shtaf_sharing','require_followup','who_contacted_admins_only','wa_auto']
    .forEach(function(k){ setTg(k, OV.policies[k]); });
  renderTeam();
  renderTeams();
  renderUnmatched();
}
var UNMATCHED = [];
var SHOW_ALL = false;
function renderUnmatched(){
  var card = el('unmCard');
  if (!card) return;
  if (!UNMATCHED.length){ card.style.display = 'none'; return; }
  card.style.display = 'flex';
  var opts = PEOPLE.map(function(p){ return '<option value="' + esc(p.name) + '">' + esc(p.name) + '</option>'; }).join('');
  el('unmList').innerHTML = UNMATCHED.map(function(u, i){
    return '<div style="display:flex;align-items:center;gap:8px;padding:9px 0;border-top:1px solid #F0EDE3">' +
      '<div style="flex:1;min-width:0"><div style="font-size:13.5px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(u.n) + '</div>' +
      '<div style="font-size:11px;color:#8B8F99">' + u.c + ' רשומות · ' + u.w + '</div></div>' +
      '<select id="unmSel' + i + '" style="max-width:130px;padding:9px 10px;border:1.5px solid #DCD6C8;border-radius:11px;' +
      'font-size:12.5px;font-family:inherit;background:#fff;color:#1E3A5F"><option value="">— שייך לסוכן —</option>' + opts + '</select>' +
      '<button onclick="assignAlias(' + i + ')" style="padding:9px 14px;border:none;border-radius:11px;background:#C29435;' +
      'color:#fff;font-size:12.5px;font-weight:700;font-family:inherit;cursor:pointer">שייך</button>' +
      '<button onclick="delUnmatched(' + i + ')" aria-label="מחיקת שם" style="width:38px;height:38px;border:none;' +
      'border-radius:11px;background:#FBEDED;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0">' +
      '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.6a1 1 0 0 0 1 .9h3.6a1 1 0 0 0 1-.9l.7-8.6M6.7 7v4M9.3 7v4" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>';
  }).join('');
}
function delUnmatched(i){
  var u = UNMATCHED[i]; if (!u) return;
  if (!confirm('למחוק את השם "' + u.n + '"? הוא לא יוצג יותר — לא בספרייה ולא ברשימה הזו.')) return;
  POST('/api/dev/agent_delete', {name: u.n}).then(function(j){
    if (!j.ok){ toast('שגיאה במחיקה'); return; }
    toast('השם נמחק'); boot();
  });
}
function assignAlias(i){
  var u = UNMATCHED[i]; if (!u) return;
  var ag = el('unmSel' + i).value;
  if (!ag){ toast('בחר סוכן'); return; }
  if (!confirm('לשייך את "' + u.n + '" כאיות נוסף של ' + ag + '?')) return;
  POST('/api/dev/alias', {alias: u.n, agent: ag}).then(function(j){
    if (!j.ok){ toast(j.reason === 'forbidden' ? 'למפתח בלבד' : 'שגיאה בשיוך'); return; }
    toast('שויך — הנתונים יתאחדו'); boot();
  });
}
var TG_IDS = {transcribe:'tgTranscribe', shtaf_sharing:'tgShtaf',
              require_followup:'tgFollowup', who_contacted_admins_only:'tgWho', wa_auto:'tgWaAuto'};
function setTg(key, on){ el(TG_IDS[key]).classList.toggle('on', !!on); }

function renderTeam(){
  var tq = (el('teamQ') ? el('teamQ').value : '').trim().toLowerCase();
  var list = PEOPLE.filter(function(p){
    if (!tq) return true;
    return ((p.name || '') + ' ' + (p.phone || '') + ' ' + (p.vphone || '')).toLowerCase().indexOf(tq) >= 0;
  }).sort(function(a, b){
    var r = {developer:0, manager:1, accountant:1, secretary:1, coordinator:2, agent:3};
    var ra = (a.role in r) ? r[a.role] : 3, rb = (b.role in r) ? r[b.role] : 3;
    return (ra - rb) || a.name.localeCompare(b.name, 'he');
  });
  el('teamTitle').textContent = 'הצוות · ' + (tq ? list.length + ' מתוך ' + PEOPLE.length : list.length);
  var full = list.length;
  if (!tq && !SHOW_ALL) list = list.slice(0, 5);   // ברירת מחדל: 5 בלבד — "הצג את כולם" או חיפוש פותחים הכל
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
  if (!tq && !SHOW_ALL && full > 5)
    html += '<div onclick="SHOW_ALL=true;renderTeam()" style="text-align:center;font-size:12.5px;font-weight:800;' +
      'color:#2E6BD6;padding:12px 0 4px;cursor:pointer">הצג את כל ' + full + ' חברי הצוות</div>';
  else if (!tq && SHOW_ALL && full > 5)
    html += '<div onclick="SHOW_ALL=false;renderTeam()" style="text-align:center;font-size:12.5px;font-weight:800;' +
      'color:#8B8F99;padding:12px 0 4px;cursor:pointer">הצג פחות</div>';
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
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }

var SEL_ROLE = 'agent';
function openInvite(){
  SEL_ROLE = 'agent';
  openSheet(
    '<h3>הזמן חבר צוות</h3>' +
    '<div class="fld"><span>שם מלא</span><input id="invNm" placeholder="שם החבר החדש"></div>' +
    '<div class="fld"><span>נייד</span><input id="invPh" type="tel" inputmode="numeric" placeholder="05X-XXXXXXX"></div>' +
    '<div class="fld"><span>תפקיד</span><div class="segs">' +
      seg('agent', 'סוכן') + seg('coordinator', 'מתאמת') + seg('manager', 'מנהל') + '</div></div>' +
    '<div style="font-size:11.5px;color:#8B8F99;line-height:1.5">ההזמנה נשלחת ב-SMS עם קישור כניסה. ' +
      'ההצטרפות למשרד היא בהזמנה בלבד — אין הרשמה פתוחה.</div>' +
    '<button class="btn btn-green" onclick="sendInvite(\'sms\')">' +
      '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M2.5 3h11a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H8l-3 2.5V11H2.5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" fill="none" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>' +
      'שלח הזמנה ב-SMS</button>' +
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
  var cw = el('coordWrap');   // בורר הסוכנים של המתאמת — מוצג מיד עם בחירת התפקיד
  if (cw) cw.style.display = (SEL_ROLE === 'coordinator') ? 'flex' : 'none';
}
function sendInvite(){
  var nm = el('invNm').value.trim(), ph = el('invPh').value.replace(/\D/g, '');
  if (!nm || ph.length < 9){ toast('שם ונייד תקין — חובה'); return; }
  POST('/v2/api/admin/invite', {name: nm, phone: ph, role: SEL_ROLE, via: 'sms'}).then(function(j){
    if (!j.ok){ toast('שגיאה בשמירה'); return; }
    closeSheet(); boot();
    toast(j.sms ? 'ההזמנה נשלחה ב-SMS' : 'נשמר — אך שליחת ה-SMS נכשלה');
  });
}
function resend(phone){
  POST('/v2/api/admin/invite', {phone: phone, resend: true, via: 'sms'}).then(function(j){
    if (!j.ok){ toast('שגיאה'); return; }
    toast(j.sms ? 'ההזמנה נשלחה שוב ב-SMS' : 'שליחת ה-SMS נכשלה');
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
  var mine = coordAgentsOf(p.name);
  var opts = PEOPLE.filter(function(x){
    return x.name !== p.name && (x.role === 'agent' || !x.role);
  });
  var agentsHtml = '<div class="fld" id="coordWrap" style="display:' +
    (SEL_ROLE === 'coordinator' ? 'flex' : 'none') + '"><span>הסוכנים המשויכים למתאמת</span><div id="coordAgents">' +
    opts.map(function(a){
      var on = mine.indexOf(a.name) >= 0;
      return '<div class="chk' + (on ? ' on' : '') + '" data-n="' + esc(a.name) + '" onclick="this.classList.toggle(\'on\')">' +
        '<div class="box"><svg width="11" height="9" viewBox="0 0 12 10"><path d="M1.5 5l3 3 6-6.5" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg></div>' +
        esc(a.name) + '</div>';
    }).join('') + '</div></div>';
  var phDisp = p.phone ? '0' + p.phone.slice(0, 2) + '-' + p.phone.slice(2) : '—';
  openSheet(
    '<div style="display:flex;align-items:center;justify-content:space-between"><h3>' + esc(p.name) + '</h3>' +
    (isDev ? '' : '<button class="trashBtn" onclick="delMember(' + i + ')" aria-label="מחיקת סוכן">' +
      '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M2.5 4h11M6.5 2h3M5.5 4v9a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1V4M6.8 6.5v5M9.2 6.5v5" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round"/></svg></button>') +
    '</div>' +
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
      try{ localStorage.removeItem('v2who'); }catch(e){}
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
  if (el('coordAgents') && SEL_ROLE === 'coordinator'){
    var names = _pickedNames('coordAgents');
    var next = COORDS.filter(function(c){ return c.coordinator !== p.name; });
    if (names.length) next.push({coordinator: p.name, agents: names});
    jobs.push(POST('/api/dev/coordinators', {coordinators: next}));
  } else if (SEL_ROLE !== 'coordinator' && coordAgentsOf(p.name).length){
    jobs.push(POST('/api/dev/coordinators',
      {coordinators: COORDS.filter(function(c){ return c.coordinator !== p.name; })}));
  }
  Promise.all(jobs).then(function(){ closeSheet(); toast('נשמר'); boot(); });
}

function delMember(i){
  var p = el('teamList')._list[i];
  openSheet('<h3>מחיקת ' + esc(p.name) + '</h3>' +
    '<div style="font-size:13px;color:#5B6472;line-height:1.7">המחיקה מסירה את הסוכן מהצוות, מהצוותים ' +
    'ומהשיוכים למתאמת, וחוסמת את הכניסה שלו למערכת. הנתונים ההיסטוריים (שיחות, חתימות, קונים) נשארים.</div>' +
    '<button class="btn" style="background:#fff;color:#C24040;border:1.5px solid #C24040" onclick="delMemberGo(' + i + ')">' +
    'מחק את ' + esc(p.name) + '</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function delMemberGo(i){
  var p = el('teamList')._list[i];
  POST('/api/dev/agent_delete', {name: p.name}).then(function(j){
    if (!j.ok){ toast('שגיאה במחיקה'); return; }
    closeSheet(); toast(p.name + ' הוסר מהמערכת'); boot();
  });
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


# ── מסך השיחות (עיצוב 15a) — משפך, פילטרים, סיכום חכם, הוסף כקונה, מוסתרות ──
V2_CALLS_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>שיחות</title>
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
  .brand img{height:36px;max-width:150px;object-fit:contain}
  .brand .nm{font-size:16px;font-weight:800;letter-spacing:.02em}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 14px;display:flex;flex-direction:column;gap:13px;overflow:auto}
  .card{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:16px 18px 14px;
      display:flex;flex-direction:column;gap:12px}
  .hd{display:flex;align-items:center;justify-content:space-between}
  .hd .tt{display:flex;align-items:center;gap:10px}
  .hd .ic{width:36px;height:36px;border-radius:11px;background:#E7F7EE;display:flex;align-items:center;justify-content:center}
  .hd h1{font-size:21px;font-weight:800}
  .live{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:700}
  .live i{width:8px;height:8px;border-radius:50%;background:#1FAF5E;display:block}
  @media (prefers-reduced-motion:no-preference){
    @keyframes pulseDot{0%,100%{opacity:1}50%{opacity:.35}}
    .live i{animation:pulseDot 2s infinite}
  }
  .funnel{display:flex;align-items:center;gap:0;background:#F7F5EE;border-radius:14px;padding:11px 8px}
  .funnel .st{flex:1;display:flex;flex-direction:column;align-items:center;gap:1px}
  .funnel .st .n{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}
  .funnel .st .l{font-size:10.5px;font-weight:600;color:#8B8F99}
  .vp{display:flex;align-items:center;justify-content:space-between;background:#F5F3EC;border:1px solid #E9E4D8;
      border-radius:13px;padding:10px 14px;cursor:pointer}
  .vp .r{display:flex;align-items:center;gap:8px}
  .vp .num{font-size:14px;font-weight:700;letter-spacing:.03em}
  .vp .sub{font-size:11px;color:#8B8F99}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px}
  .segs .sg{flex:1;text-align:center;padding:7px 0;font-size:12.5px;font-weight:700;color:#5B6472;
      border-radius:10px;cursor:pointer}
  .segs .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .call{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:10px}
  .call .top{display:flex;align-items:center;gap:11px}
  .call .tile{width:40px;height:40px;border-radius:13px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .call .mid{flex:1;display:flex;flex-direction:column;gap:1px;min-width:0}
  .call .num{font-size:16px;font-weight:800;letter-spacing:.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .call .sub{font-size:12px;color:#8B8F99;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .chip{font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:999px;white-space:nowrap;flex-shrink:0}
  .chip.hot{color:#1FAF5E;background:#E7F7EE}
  .chip.back{color:#C24040;background:#FBEDED}
  .ai{background:#F7F5EE;border-radius:13px;padding:10px 13px;display:flex;flex-direction:column;gap:4px;cursor:pointer}
  .ai .t{display:flex;align-items:center;gap:6px;font-size:10.5px;font-weight:800;color:#B8902F;letter-spacing:.05em}
  .ai .x{font-size:12.5px;color:#5B6472;line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .acts{display:flex;gap:9px;align-items:center}
  .acts .main{flex:1;display:flex;align-items:center;justify-content:center;gap:7px;border-radius:12px;
      padding:10px 0;font-size:13px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:40px}
  .acts .blue{background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .acts .green{background:#1FAF5E;color:#fff;box-shadow:0 4px 12px rgba(31,175,94,.25)}
  .acts .sec{background:#fff;color:#1E3A5F;border:1.5px solid #DCD6C8}
  .acts .sq{width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;
      flex-shrink:0;border:0;cursor:pointer}
  .hiddenBar{display:flex;align-items:center;justify-content:center;gap:8px;padding:2px 0 6px;
      font-size:13px;font-weight:700;color:#8B8F99}
  .hiddenBar b{color:#2E6BD6;cursor:pointer;font-weight:700}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .t{font-size:15px;font-weight:800}
  .empty .s{font-size:12.5px;color:#5B6472;line-height:1.6;max-width:250px}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer;position:relative}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 16px;
      display:none;flex-direction:column;gap:12px;max-height:82vh;overflow:auto}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center}
  #sheet h3{font-size:19px;font-weight:800}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld span{font-size:11.5px;font-weight:700;color:#5B6472}
  .fld input,.fld textarea{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:11px;padding:11px 13px;
      font-size:14px;font-weight:700;color:#1E3A5F;font-family:inherit;outline:none;width:100%;resize:vertical}
  .btn{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:13px;padding:13px 0;width:100%;
      font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:46px}
  .btn-blue{background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .btn-sec{background:#fff;color:#5B6472;border:1.5px solid #DCD6C8}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  /* ── דסקטופ: עמודה ממורכזת (המובייל הוא המקור; מסך רחב מלא — בשלב הדסקטופ) ── */
  @media (min-width:700px){
    header,main,nav,#impBar{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
    #menu{max-width:340px}
    #story .bars,#story .shead,#story .body,#story .sfoot{width:100%;max-width:600px;
        margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
</style></head><body>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
    <button class="menuBtn" onclick="location.href='/v2/home'" aria-label="לבית">
      <svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
    </button>
  </header>

  <main>
    <div class="card">
      <div class="hd">
        <div class="tt">
          <div class="ic"><svg width="16" height="16" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#1FAF5E" stroke-width="1.7" stroke-linejoin="round"/></svg></div>
          <h1 id="pgTitle">שיחות</h1>
        </div>
        <div class="live"><i></i><span id="weekN">—</span></div>
      </div>
      <div class="funnel">
        <div class="st"><div class="n" style="color:#1E3A5F" id="fAll">—</div><div class="l">שיחות</div></div>
        <svg width="13" height="11" viewBox="0 0 14 12"><path d="M11 2L4 6l7 4" fill="none" stroke="#C9CDD4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <div class="st"><div class="n" style="color:#1FAF5E" id="fAns">—</div><div class="l">נענו</div></div>
        <svg width="13" height="11" viewBox="0 0 14 12"><path d="M11 2L4 6l7 4" fill="none" stroke="#C9CDD4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <div class="st"><div class="n" style="color:#B8902F" id="fBuy">—</div><div class="l">הפכו לקונים</div></div>
      </div>
      <div class="vp" onclick="copyVp()" id="vpRow" style="display:none">
        <div class="r">
          <svg width="14" height="14" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#B8902F" stroke-width="1.7" stroke-linejoin="round"/></svg>
          <span class="num" id="vpNum"></span>
          <span class="sub">· המספר הווירטואלי</span>
        </div>
        <svg width="15" height="15" viewBox="0 0 16 16"><rect x="5" y="5" width="9" height="9" rx="2" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><path d="M11 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h1" fill="none" stroke="#2E6BD6" stroke-width="1.6"/></svg>
      </div>
      <div class="segs" id="filters">
        <div class="sg on" data-f="all" onclick="setFilter(this)">הכל</div>
        <div class="sg" data-f="ans" onclick="setFilter(this)">נענו</div>
        <div class="sg" data-f="miss" onclick="setFilter(this)">לא נענו</div>
        <div class="sg" data-f="hot" onclick="setFilter(this)">חמים</div>
      </div>
    </div>

    <div id="list"><div class="card empty"><div class="s" style="padding:10px 0">טוען שיחות…</div></div></div>
    <div class="hiddenBar" id="hiddenBar" style="display:none">
      <svg width="14" height="14" viewBox="0 0 16 16"><path d="M2 2l12 12M6.7 6.8a2 2 0 0 0 2.6 2.6M4.4 4.5C3 5.4 2 6.6 1.5 8c1 2.8 3.5 4.5 6.5 4.5 1.1 0 2.1-.2 3-.6M7 3.6c.3 0 .7-.1 1-.1 3 0 5.5 1.7 6.5 4.5-.3.9-.8 1.7-1.5 2.4" fill="none" stroke="#8B8F99" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span id="hiddenN"></span><b id="hiddenGo" onclick="toggleHidden()">הצג</b>
    </div>
  </main>

  <nav>
    <div class="it" style="color:#1E3A5F;font-weight:700"><div class="home"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg></div>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
function openSheet(html){
  el('sheet').innerHTML = '<div class="grip"></div>' + html;
  el('sheet').style.display = 'flex'; el('ovl').style.display = 'block';
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }
function last9(s){ return String(s || '').replace(/\D/g, '').slice(-9); }

var CALLS = [], HIDDEN = [], FILTER = 'all', VIEW = 'main';
var BUYER_BY_PHONE = {};   // last9 -> שם קונה קיים (זיהוי חוזר)
var OFFICE = '';

var EYE_SVG = '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M2 2l12 12M6.7 6.8a2 2 0 0 0 2.6 2.6M4.4 4.5C3 5.4 2 6.6 1.5 8c1 2.8 3.5 4.5 6.5 4.5 1.1 0 2.1-.2 3-.6M7 3.6c.3 0 .7-.1 1-.1 3 0 5.5 1.7 6.5 4.5-.3.9-.8 1.7-1.5 2.4" fill="none" stroke="#5B6472" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
var PHONE_SVG = function(color){
  return '<svg width="16" height="16" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="' + color + '" stroke-width="1.7" stroke-linejoin="round"/></svg>';
};
var WA_SVG = function(color){
  return '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="' + color + '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
};

function isHot(c){   // ליד חם: יש סיכום ממשי עם פרטי לקוח / סיכום עשיר
  return c.status === 'ANSWER' && !!c.summary && (!!c.clientDetails || c.summary.length > 60);
}
function stLabel(st){
  return st === 'ANSWER' ? 'נענתה' : st === 'BUSY' ? 'תפוס' : st === 'CALLER_CANCEL' ? 'נותקה' : 'לא נענתה';
}
function fmtDur(d){
  d = parseInt(d, 10);
  if (!d) return '';
  return Math.floor(d / 60) + ':' + ('0' + (d % 60)).slice(-2) + ' דק׳';
}
function weekStart(){
  var d = new Date(); d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - d.getDay());   // יום ראשון
  return d.getTime() / 1000;
}

function load(){
  // מהיר: מציירים מיד מהבקשה הראשית; מוסתרות וקונים נטענים ברקע (בלי לחסום)
  var p = GET('/api/history').then(function(j){
    CALLS = (j && j.calls) || [];
    if (j && j.vphone){ el('vpNum').textContent = j.vphone; el('vpRow').style.display = 'flex'; }
    try{ localStorage.setItem('v2c:calls', JSON.stringify({calls: CALLS.slice(0, 120), vphone: j.vphone || ''})); }catch(e){}
    render();
  }).catch(function(){});
  GET('/api/my/buyers').then(function(j){
    BUYER_BY_PHONE = {};
    ((j && j.results) || []).forEach(function(b){
      var pp = last9(b.tel || b.phone);
      if (pp) BUYER_BY_PHONE[pp] = b.name || '';
    });
    render();   // רענון לזיהוי "קונה קיים" ולמשפך ההמרה
  }).catch(function(){});
  loadHidden();
  return p;
}
function loadHidden(){
  GET('/api/history?hidden=1').then(function(j){
    HIDDEN = (j && j.calls) || [];
    el('hiddenN').textContent = 'שיחות שהוסתרו · ' + HIDDEN.length;
    el('hiddenBar').style.display = HIDDEN.length || VIEW === 'hidden' ? 'flex' : 'none';
    if (VIEW === 'hidden') render();
  }).catch(function(){});
}

function render(){
  var ws = weekStart();
  var wk = CALLS.filter(function(c){ return (c.ts || 0) >= ws; });
  var ans = wk.filter(function(c){ return c.status === 'ANSWER'; }).length;
  var became = {};
  wk.forEach(function(c){
    var p = last9(c.tel || c.caller);
    if (p && BUYER_BY_PHONE[p] !== undefined) became[p] = 1;
  });
  el('weekN').textContent = wk.length + ' השבוע';
  el('fAll').textContent = wk.length;
  el('fAns').textContent = ans;
  el('fBuy').textContent = Object.keys(became).length;
  el('hiddenN').textContent = 'שיחות שהוסתרו · ' + HIDDEN.length;
  el('hiddenBar').style.display = HIDDEN.length || VIEW === 'hidden' ? 'flex' : 'none';
  el('hiddenGo').textContent = VIEW === 'hidden' ? 'חזרה לשיחות' : 'הצג';
  el('pgTitle').textContent = VIEW === 'hidden' ? 'שיחות שהוסתרו' : 'שיחות';
  el('filters').style.display = VIEW === 'hidden' ? 'none' : 'flex';

  var src = VIEW === 'hidden' ? HIDDEN : CALLS.filter(function(c){
    if (FILTER === 'ans') return c.status === 'ANSWER';
    if (FILTER === 'miss') return c.status !== 'ANSWER';
    if (FILTER === 'hot') return isHot(c);
    return true;
  });
  var h = '';
  src.slice(0, 100).forEach(function(c, i){ h += callCard(c, i, VIEW === 'hidden'); });
  el('list').innerHTML = h ||
    '<div class="card empty"><div class="ic"><svg width="28" height="28" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#C29435" stroke-width="1.7" stroke-linejoin="round"/></svg></div>' +
    '<div class="t">' + (VIEW === 'hidden' ? 'אין שיחות מוסתרות' : 'אין שיחות להצגה') + '</div>' +
    '<div class="s">' + (VIEW === 'hidden' ? 'שיחות שתסתיר מהרשימה יופיעו כאן' : 'כששיחה תגיע למספר הווירטואלי — היא תופיע כאן עם סיכום חכם') + '</div></div>';
  el('list')._src = src;
}

function callCard(c, i, hidden){
  var ok = c.status === 'ANSWER';
  var p = last9(c.tel || c.caller);
  var known = BUYER_BY_PHONE[p];
  var title = known ? known : (c.caller || '');
  var subParts = [stLabel(c.status), c.time, fmtDur(c.duration), c.agent].filter(Boolean);
  if (known && c.caller) subParts.unshift(c.caller);
  var chip = hidden ? '' :
    known ? '<div class="chip hot">קונה קיים</div>' :
    isHot(c) ? '<div class="chip hot">ליד חם</div>' :
    !ok ? '<div class="chip back">לחזור</div>' : '';
  var ai = c.summary ?
    '<div class="ai" onclick="showSummary(' + i + ')"><div class="t">' +
    '<svg width="14" height="13" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>' +
    'סיכום חכם</div><div class="x">' + esc(c.summary) + '</div></div>' : '';
  var acts;
  if (hidden){
    acts = '<div class="acts"><button class="main sec" onclick="unhide(\'' + esc(c.id) + '\')">שחזר לרשימה</button></div>';
  } else if (ok){
    acts = '<div class="acts">' +
      '<button class="main blue" onclick="addBuyer(' + i + ')">' +
      '<svg width="12" height="12" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>הוסף כקונה</button>' +
      '<button class="sq" style="background:#E7F7EE" onclick="openWa(' + i + ')">' + WA_SVG('#1FAF5E') + '</button>' +
      (c.summary ? '<button class="sq" style="background:#F5F3EC" onclick="showSummary(' + i + ')">' +
      '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M12 3L8 7M12 3v4M12 3H8M4 13l4-4M4 13v-4M4 13h4" stroke="#5B6472" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' : '') +
      '<button class="sq" style="background:#F5F3EC" onclick="hide(\'' + esc(c.id) + '\')">' + EYE_SVG + '</button></div>';
  } else {
    acts = '<div class="acts">' +
      '<button class="main green" onclick="openWa(' + i + ')">' + WA_SVG('#fff') + 'שלח וואטסאפ</button>' +
      '<button class="main sec" onclick="location.href=\'tel:' + esc(c.tel || '') + '\'">' + PHONE_SVG('#1E3A5F') + 'חייג חזרה</button>' +
      '<button class="sq" style="background:#EAF0FA" onclick="addBuyer(' + i + ')">' +
      '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#2E6BD6" stroke-width="2" stroke-linecap="round"/></svg></button>' +
      '<button class="sq" style="background:#F5F3EC" onclick="hide(\'' + esc(c.id) + '\')">' + EYE_SVG + '</button></div>';
  }
  return '<div class="call" style="margin-bottom:13px">' +
    '<div class="top"><div class="tile" style="background:' + (ok ? '#E7F7EE' : '#FBEDED') + '">' +
    PHONE_SVG(ok ? '#1FAF5E' : '#C24040') + '</div>' +
    '<div class="mid"><div class="num">' +
    (c.tel ? '<a href="tel:' + esc(c.tel) + '" style="color:inherit;text-decoration:none">' + esc(title) + '</a>' : esc(title)) +
    '</div><div class="sub">' + esc(subParts.join(' · ')) + '</div></div>' +
    chip + '</div>' + ai + acts + '</div>';
}

function setFilter(node){
  FILTER = node.getAttribute('data-f');
  var sgs = node.parentNode.children;
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i] === node);
  render();
}
function toggleHidden(){ VIEW = (VIEW === 'hidden') ? 'main' : 'hidden'; render(); window.scrollTo(0, 0); }
function copyVp(){
  var v = el('vpNum').textContent;
  try{ navigator.clipboard.writeText(v).then(function(){ toast('המספר הועתק'); }); }
  catch(e){ toast(v); }
}
function hide(id){
  POST('/api/calls/hide', {id: id}).then(function(j){
    if (!j.ok){ toast('שגיאה בהסתרה'); return; }
    toast('השיחה הוסתרה'); load();
  });
}
function unhide(id){
  POST('/api/calls/unhide', {id: id}).then(function(j){
    if (!j.ok){ toast('שגיאה בשחזור'); return; }
    toast('השיחה שוחזרה'); load();
  });
}
function openWa(i){
  var c = el('list')._src[i];
  var msg = 'היי, ראינו שהתקשרת ל' + (OFFICE || 'משרד') + ' — איך נוכל לעזור?';
  window.open('https://wa.me/' + (c.wa || '') + '?text=' + encodeURIComponent(msg), '_blank');
}
function showSummary(i){
  var c = el('list')._src[i];
  openSheet('<h3>סיכום חכם</h3>' +
    '<div style="font-size:12px;color:#8B8F99">' + esc((c.caller || '') + ' · ' + (c.time || '')) + '</div>' +
    '<div style="background:#fff;border-radius:13px;padding:13px 15px;font-size:13.5px;color:#1E3A5F;line-height:1.7">' + esc(c.summary) + '</div>' +
    (c.clientDetails ? '<div style="background:#F6EEDB;border-radius:13px;padding:13px 15px;font-size:13px;color:#5B6472;line-height:1.7">' + esc(c.clientDetails) + '</div>' : '') +
    '<button class="btn btn-blue" onclick="closeSheet();addBuyer(' + i + ')">הוסף כקונה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">סגירה</button>');
}
function addBuyer(i){
  var c = el('list')._src[i];
  openSheet('<h3>הוסף כקונה</h3>' +
    '<div class="fld"><span>שם</span><input id="abNm" placeholder="שם הקונה" value="' + esc(BUYER_BY_PHONE[last9(c.tel)] || '') + '"></div>' +
    '<div class="fld"><span>טלפון</span><input id="abPh" type="tel" value="' + esc(c.caller || '') + '"></div>' +
    '<div class="fld"><span>תקציב</span><input id="abBd" inputmode="numeric" placeholder="₪" oninput="var d=this.value.replace(/[^0-9]/g,\'\');this.value=d?Number(d).toLocaleString():\'\'"></div>' +
    '<div class="fld"><span>מה מחפש</span><textarea id="abSm" rows="3">' + esc(c.summary || '') + '</textarea></div>' +
    '<button class="btn btn-blue" onclick="saveBuyer()">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function saveBuyer(force){
  if (window._svBusy) return;   // מניעת לחיצה כפולה — קונה נוסף פעמיים
  window._svBusy = true;
  POST('/api/buyers/add', {name: el('abNm').value.trim(), phone: el('abPh').value.trim(),
                           budget: el('abBd').value.trim(), summary: el('abSm').value.trim(),
                           force: !!force})
    .then(function(j){
      window._svBusy = false;
      if (!j.ok){
        if (j.dup){   // כבר קיים — מאשרים במפורש אם באמת רוצים כפול
          if (confirm(j.reason + '. להוסיף בכל זאת?')) saveBuyer(true);
          return;
        }
        toast('שגיאה בשמירה'); return;
      }
      closeSheet(); toast('הקונה נוסף'); load();
    }).catch(function(){ window._svBusy = false; toast('שגיאה בשמירה'); });
}


/* זיכרון מצב הטאב — פילטר/חיפוש/גלילה נשמרים וחוזרים בכניסה הבאה */
var _restY = 0;
function saveSt(){
  try{
    var m = document.querySelector('main');
    localStorage.setItem('v2st:calls', JSON.stringify({f:FILTER, v:VIEW, y:(m ? m.scrollTop : 0)}));
  }catch(e){}
}
(function(){
  try{
    var s = JSON.parse(localStorage.getItem('v2st:calls') || 'null');
    if (s){
      FILTER = s.f || FILTER; VIEW = s.v || 'main'; _restY = s.y || 0;
    }
  }catch(e){}
  var sg = document.querySelector('#filters .sg[data-f="' + FILTER + '"]');
  if (sg){ var cs = sg.parentNode.children;
    for (var i = 0; i < cs.length; i++) cs[i].classList.toggle('on', cs[i] === sg); }
})();
var _renderBase = render;
render = function(){
  _renderBase();
  if (_restY){
    var m = document.querySelector('main');
    if (m){ m.scrollTop = _restY; if (m.scrollTop >= _restY - 4) _restY = 0; }
  }
  if (!_restY) saveSt();
};
(function(){
  var m = document.querySelector('main');
  if (m) m.addEventListener('scroll', function(){
    if (window._svScrolled) _restY = 0; window._svScrolled = true;
    clearTimeout(window._svt); window._svt = setTimeout(saveSt, 300);
  }, {passive:true});
  window.addEventListener('pagehide', function(){ if (!_restY) saveSt(); });
})();

(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    el('avatarTx').textContent = (j.name || ' ').trim()[0] || '';
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    OFFICE = o.name || '';
    document.title = 'שיחות · ' + OFFICE;
  }).catch(function(){});
  try{   // פתיחה מיידית מהעותק האחרון — הרענון מהשרת רץ ברקע
    var c = JSON.parse(localStorage.getItem('v2c:calls') || 'null');
    if (c && c.calls && c.calls.length){
      CALLS = c.calls;
      if (c.vphone){ el('vpNum').textContent = c.vphone; el('vpRow').style.display = 'flex'; }
      render();
    }
  }catch(e){}
  load();
  setInterval(function(){   // רענון עדין לראשי בלבד — Realtime מלא כשעוברים ל-Supabase
    GET('/api/history').then(function(j){
      CALLS = (j && j.calls) || [];
      render();
    }).catch(function(){});
  }, 90000);
})();
</script></body></html>'''


# ── מסך הקונים (עיצוב 16a) + התאמת נכסים (16b) ──────────────────────────────
V2_BUYERS_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>קונים</title>
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
  .brand img{height:36px;max-width:150px;object-fit:contain}
  .brand .nm{font-size:16px;font-weight:800;letter-spacing:.02em}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 14px;display:flex;flex-direction:column;gap:13px;overflow:auto}
  .card{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:16px 18px 14px;
      display:flex;flex-direction:column;gap:12px}
  .hd{display:flex;align-items:center;justify-content:space-between}
  .hd .tt{display:flex;align-items:center;gap:10px}
  .hd .ic{width:36px;height:36px;border-radius:11px;background:#EAF0FA;display:flex;align-items:center;justify-content:center}
  .hd h1{font-size:21px;font-weight:800}
  .cnt{font-size:13px;font-weight:700;color:#2E6BD6;background:#EAF0FA;padding:4px 11px;border-radius:999px}
  .srchRow{display:flex;gap:7px}
  .srch{flex:1;min-width:0;display:flex;align-items:center;gap:8px;background:#F5F3EC;border:1px solid #E9E4D8;
      border-radius:14px;padding:0 12px}
  .srch input{flex:1;min-width:0;border:0;background:none;font-size:13.5px;font-family:inherit;outline:none;
      color:#1E3A5F;padding:11px 0}
  .addBtn{display:flex;align-items:center;justify-content:center;gap:5px;background:#2E6BD6;color:#fff;
      border-radius:14px;padding:0 11px;font-size:13px;font-weight:700;border:0;cursor:pointer;
      font-family:inherit;box-shadow:0 4px 12px rgba(46,107,214,.25);white-space:nowrap;flex-shrink:0}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px}
  .segs .sg{flex:1;text-align:center;padding:7px 0;font-size:12.5px;font-weight:700;color:#5B6472;
      border-radius:10px;cursor:pointer}
  .segs .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .buyer{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:10px;margin-bottom:13px;border:2px solid transparent}
  .buyer.hot{border-color:#C29435}
  .buyer .top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  .buyer .nm{font-size:16.5px;font-weight:800;display:flex;align-items:center;gap:7px}
  .buyer .tag{font-size:10.5px;font-weight:800;color:#fff;background:#C29435;padding:2px 8px;border-radius:999px}
  .buyer .sb{font-size:12px;color:#8B8F99}
  .buyer .bdg{font-size:11.5px;font-weight:700;color:#B8902F;background:#F6EEDB;padding:3px 9px;
      border-radius:999px;white-space:nowrap;cursor:pointer}
  .buyer .req{font-size:11px;color:#8B8F99;text-align:left}
  .ai{background:#F7F5EE;border-radius:13px;padding:10px 13px;display:flex;flex-direction:column;gap:4px}
  .ai .t{display:flex;align-items:center;gap:6px;font-size:10.5px;font-weight:800;color:#B8902F;letter-spacing:.05em}
  .ai .x{font-size:12.5px;color:#5B6472;line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .acts{display:flex;gap:9px;align-items:center}
  .acts .main{flex:1;display:flex;align-items:center;justify-content:center;gap:7px;border-radius:12px;
      padding:10px 0;font-size:13px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:40px;
      background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .acts .sq{width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;
      flex-shrink:0;border:0;cursor:pointer}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .t{font-size:15px;font-weight:800}
  .empty .s{font-size:12.5px;color:#5B6472;line-height:1.6;max-width:250px}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);top:70px;z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 16px;
      display:none;flex-direction:column;gap:12px;overflow:auto}
  #sheet.small{top:auto;max-height:82vh}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center;flex-shrink:0}
  #sheet h3{font-size:19px;font-weight:800}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld span{font-size:11.5px;font-weight:700;color:#5B6472}
  .fld input,.fld textarea{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:11px;padding:11px 13px;
      font-size:14px;font-weight:700;color:#1E3A5F;font-family:inherit;outline:none;width:100%;resize:vertical}
  .btn{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:13px;padding:13px 0;width:100%;
      font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:46px;flex-shrink:0}
  .btn-blue{background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .btn-sec{background:#fff;color:#5B6472;border:1.5px solid #DCD6C8}
  .stChoice{display:flex;align-items:center;gap:9px;padding:12px 4px;font-size:14px;font-weight:700;cursor:pointer;min-height:44px}
  .stChoice .d{width:9px;height:9px;border-radius:50%}
  /* תוצאות התאמה */
  .grpTitle{font-size:13px;font-weight:800;color:#B8902F;letter-spacing:.05em;padding:2px 2px 0}
  .prop{background:#fff;border-radius:18px;box-shadow:0 4px 14px rgba(30,58,95,.05);padding:13px 15px;
      display:flex;flex-direction:column;gap:8px;flex-shrink:0}
  .prop.shtaf{background:#F7F5EE;border:1.5px dashed #DCD6C8;box-shadow:none}
  .prop .r1{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  .prop .ad{font-size:14.5px;font-weight:800}
  .prop .dt{font-size:11.5px;color:#8B8F99;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  .prop .pr{font-size:15px;font-weight:800;white-space:nowrap}
  .prop .dxBtn{width:30px;height:30px;border-radius:9px;background:#F5F3EC;border:none;padding:0;
      display:flex;align-items:center;justify-content:center;flex-shrink:0;align-self:center;cursor:pointer}
  .prop.shtaf .dxBtn{background:#EFEBDD}
  .prop .dx{font-size:12.5px;color:#5B6472;line-height:1.55;background:#FAF8F2;border-radius:12px;
      padding:10px 12px;white-space:pre-wrap}
  .prop.shtaf .dx{background:#F1EDE0}
  .score{font-size:11px;font-weight:800;padding:3px 9px;border-radius:999px;white-space:nowrap}
  .score.hi{color:#157A43;background:#E7F7EE}
  .score.md{color:#B8902F;background:#F6EEDB}
  .prop .acts2{display:flex;gap:8px}
  .prop .sel{flex:0 0 40px;width:40px;border-radius:12px;border:1.5px solid #DCD6C8;background:#fff;color:#C9C4B6;
      display:flex;align-items:center;justify-content:center;cursor:pointer;min-height:40px}
  .prop .sel.on{background:#1FAF5E;border-color:#1FAF5E;color:#fff}
  .prop .a1{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;background:#1FAF5E;color:#fff;
      border-radius:11px;padding:9px 0;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(31,175,94,.25)}
  .prop .a2{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;background:#C29435;color:#fff;
      border-radius:11px;padding:9px 0;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(194,148,53,.25)}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  /* ── דסקטופ: עמודה ממורכזת (המובייל הוא המקור; מסך רחב מלא — בשלב הדסקטופ) ── */
  @media (min-width:700px){
    header,main,nav,#impBar{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
    #menu{max-width:340px}
    #story .bars,#story .shead,#story .body,#story .sfoot{width:100%;max-width:600px;
        margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
</style></head><body>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
    <button class="menuBtn" onclick="location.href='/v2/home'" aria-label="לבית">
      <svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
    </button>
  </header>

  <main>
    <div class="card">
      <div class="hd">
        <div class="tt">
          <div class="ic"><svg width="16" height="16" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#2E6BD6" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round"/></svg></div>
          <h1>הקונים שלי</h1>
        </div>
        <div class="cnt" id="cnt">—</div>
      </div>
      <div class="srchRow">
        <div class="srch">
          <svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M11 11l3.4 3.4" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>
          <input id="q" placeholder="שם, טלפון או חיפוש חופשי (Enter לחיפוש חכם)" oninput="qChanged()"
                 onkeydown="if(event.key==='Enter')smartSearch()">
        </div>
        <button class="addBtn" onclick="openAdd()">
          <svg width="12" height="12" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>
          קונה
        </button>
      </div>
      <div class="segs" id="filters">
        <div class="sg on" data-f="active" onclick="setFilter(this)">פעילים</div>
        <div class="sg" data-f="hot" onclick="setFilter(this)">חמים</div>
        <div class="sg" data-f="frozen" onclick="setFilter(this)">בהקפאה</div>
        <div class="sg" data-f="closed" onclick="setFilter(this)">סגרו</div>
      </div>
    </div>
    <div id="list"></div>
  </main>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" style="color:#1E3A5F;font-weight:700"><div class="home"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#fff" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg></div>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
function openSheet(html, small){
  var s = el('sheet');
  s.className = small ? 'small' : '';
  s.innerHTML = '<div class="grip"></div>' + html;
  s.style.display = 'flex'; el('ovl').style.display = 'block';
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }

var BUYERS = [], STATUSES = {}, FILTER = 'active', OFFICE = '', MULTI = false, SMART = null;
function qChanged(){ if (SMART) SMART = null; render(); }
function smartSearch(){
  var q = el('q').value.trim();
  if (!q){ toast('כתוב מה לחפש — למשל "קונה בתקציב 3 מיליון בגושן"'); return; }
  el('list').innerHTML = '<div class="card empty"><div class="s" style="padding:10px 0">מחפש בשיחות שנענו…</div></div>';
  POST('/api/search/buyers', {q: q}).then(function(j){
    SMART = (j && j.results) || [];
    render();
  }).catch(function(){ SMART = []; render(); });
}
function renderSmart(){
  el('cnt').textContent = SMART.length;
  var h = '<div style="display:flex;align-items:center;justify-content:space-between;padding:2px 4px 10px">' +
    '<div style="font-size:13px;font-weight:800;color:#B8902F">חיפוש חכם · מהשיחות שנענו</div>' +
    '<div style="font-size:12.5px;font-weight:700;color:#2E6BD6;cursor:pointer" onclick="SMART=null;el(\'q\').value=\'\';render()">נקה חיפוש</div></div>';
  SMART.slice(0, 15).forEach(function(b, i){
    h += '<div class="buyer">' +
      '<div class="top"><div><div class="nm">' + esc(b.phone || '') + '</div>' +
      '<div class="sb">' + esc([b.agent, b.date].filter(Boolean).join(' · ')) + '</div></div>' +
      (b.budget ? '<div class="bdg">' + esc(b.budget) + '</div>' : '') + '</div>' +
      (b.summary ? '<div class="ai"><div class="t">' +
        '<svg width="14" height="13" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>' +
        'סיכום חכם</div><div class="x">' + esc(b.summary) + '</div></div>' : '') +
      '<div class="acts">' +
      '<button class="main" onclick="smartAdd(' + i + ')">' +
      '<svg width="12" height="12" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>' +
      'הוסף כקונה</button>' +
      (b.wa ? '<button class="sq" style="background:#E7F7EE" onclick="window.open(\'https://wa.me/' + esc(b.wa) + '\',\'_blank\')">' +
      '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#1FAF5E" stroke-width="1.5"/></svg></button>' : '') +
      (b.tel ? '<button class="sq" style="background:#EAF0FA" onclick="location.href=\'tel:' + esc(b.tel) + '\'">' +
      '<svg width="14" height="14" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#2E6BD6" stroke-width="1.7"/></svg></button>' : '') +
      '</div></div>';
  });
  if (!SMART.length)
    h += '<div class="card empty"><div class="t">לא נמצאו קונים מתאימים</div>' +
      '<div class="s">חיפשנו בשיחות שנענו לפי תקציב ומילות מפתח — נסה ניסוח אחר</div></div>';
  el('list').innerHTML = h;
  el('list')._smart = SMART;
}
function smartAdd(i){
  var b = el('list')._smart[i];
  openAdd();
  setTimeout(function(){
    el('abPh').value = b.phone || '';
    el('abBd').value = (b.budget || '').replace(/[^\d,]/g, '');
    el('abSm').value = b.summary || '';
  }, 50);
}
var ST_LABEL = {active:'פעיל', hot:'חם', frozen:'בהקפאה', closed:'סגר'};
var ST_COLOR = {active:'#2E6BD6', hot:'#C29435', frozen:'#5B6472', closed:'#1FAF5E'};

function bKey(b){
  var d = String(b.phone || '').replace(/[^0-9]/g, '').slice(-9);
  return d || ('r' + b.row);
}
function stOf(b){ return STATUSES[bKey(b)] || STATUSES[b.row] || 'active'; }

function load(){
  return Promise.all([
    GET('/api/my/buyers').catch(function(){ return {}; }),
    GET('/v2/api/buyers/statuses').catch(function(){ return {}; })
  ]).then(function(rs){
    BUYERS = (rs[0] && rs[0].results) || [];
    MULTI = !!(rs[0] && rs[0].multi);
    STATUSES = (rs[1] && rs[1].statuses) || {};
    try{ localStorage.setItem('v2c:buyers', JSON.stringify({b: BUYERS.slice(0, 200), m: MULTI, s: STATUSES})); }catch(e){}
    render();
  });
}
(function(){   // פתיחה מיידית מהעותק האחרון
  try{
    var c = JSON.parse(localStorage.getItem('v2c:buyers') || 'null');
    if (c && c.b){ BUYERS = c.b; MULTI = !!c.m; STATUSES = c.s || {}; }
  }catch(e){}
})();

function render(){
  if (SMART){ renderSmart(); return; }
  var q = el('q').value.trim().toLowerCase();
  var src = BUYERS.filter(function(b){
    var st = stOf(b);
    if (FILTER === 'hot' && st !== 'hot') return false;
    if (FILTER === 'frozen' && st !== 'frozen') return false;
    if (FILTER === 'closed' && st !== 'closed') return false;
    if (FILTER === 'active' && (st === 'frozen' || st === 'closed')) return false;   // פעילים כולל חמים
    if (q && ((b.name || '') + ' ' + (b.phone || '') + ' ' + (b.summary || '') + ' ' + (b.search || ''))
        .toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  el('cnt').textContent = src.length;
  var h = '';
  src.forEach(function(b, i){
    var st = stOf(b);
    var hot = st === 'hot';
    var sub = [b.phone, MULTI ? b.agent : '', b.date].filter(Boolean).join(' · ');
    h += '<div class="buyer' + (hot ? ' hot' : '') + '">' +
      '<div class="top"><div>' +
      '<div class="nm">' + esc(b.name || b.phone || 'ללא שם') + (hot ? '<span class="tag">חם</span>' : '') + '</div>' +
      '<div class="sb">' + esc(sub) + '</div></div>' +
      '<div style="display:flex;flex-direction:column;align-items:flex-start;gap:4px">' +
      (b.budget ? '<div class="bdg" onclick="pickStatus(' + i + ')">עד ' + esc(b.budget) + '</div>' :
        '<div class="bdg" onclick="pickStatus(' + i + ')">' + ST_LABEL[st] + '</div>') +
      (b.search ? '<div class="req">' + esc(b.search.slice(0, 30)) + '</div>' : '') + '</div></div>' +
      (b.summary ? '<div class="ai"><div class="t">' +
        '<svg width="14" height="13" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>' +
        'סיכום חכם</div><div class="x">' + esc(b.summary) + '</div></div>' : '') +
      '<div class="acts">' +
      '<button class="main" onclick="matchProps(' + i + ')">' +
      '<svg width="13" height="13" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5" fill="none" stroke="#fff" stroke-width="1.8"/><path d="M10.5 10.5l3 3" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>' +
      'התאם</button>' +
      '<button class="sq" style="background:' + (hot ? '#C29435' : '#F6EEDB') + '" onclick="toggleHot(' + i + ')" aria-label="קונה חם">' +
      '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M8 1.5c.4 2.2-.8 3.2-1.8 4.4C5 7.3 4.3 8.6 4.5 10.3c.3 2.3 2 3.9 3.7 4.2-.8-.9-1-2-.5-3 .4-.8 1.1-1.3 1.4-2.2 1 .8 1.7 2 1.5 3.3-.1.7-.4 1.3-.9 1.8 2-.5 3.6-2.2 3.8-4.5.2-3.2-2.3-4.6-3.1-6.9-.3-.6-.4-1.1-.4-1.5z" fill="' + (hot ? '#fff' : 'none') + '" stroke="' + (hot ? '#fff' : '#B8902F') + '" stroke-width="1.3" stroke-linejoin="round"/></svg></button>' +
      '<button class="sq" style="background:#F5F3EC" onclick="openEdit(' + i + ')" aria-label="עריכה">' +
      '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#5B6472" stroke-width="1.5" stroke-linejoin="round"/></svg></button>' +
      '<button class="sq" style="background:#E7F7EE" onclick="window.open(\'https://wa.me/' + esc(b.wa || '') + '\',\'_blank\')">' +
      '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#1FAF5E" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
      '<button class="sq" style="background:#EAF0FA" onclick="location.href=\'tel:' + esc(b.tel || '') + '\'">' +
      '<svg width="14" height="14" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#2E6BD6" stroke-width="1.7" stroke-linejoin="round"/></svg></button>' +
      '</div></div>';
  });
  el('list').innerHTML = h ||
    '<div class="card empty"><div class="ic"><svg width="28" height="28" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#C29435" stroke-width="1.7"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#C29435" stroke-width="1.7" stroke-linecap="round"/></svg></div>' +
    '<div class="t">אין קונים להצגה</div>' +
    '<div class="s">קונים חדשים נוספים מהשיחות ("הוסף כקונה") או מכפתור "+ קונה" למעלה</div>' +
    '<button class="btn btn-blue" style="max-width:220px" onclick="openAdd()">+ הוסף קונה</button></div>';
  el('list')._src = src;
}
function setFilter(node){
  FILTER = node.getAttribute('data-f');
  var sgs = node.parentNode.children;
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i] === node);
  render();
}

/* ── סטטוס קונה (buyers.status ב-Supabase) ── */
function pickStatus(i){
  var b = el('list')._src[i];
  var cur = stOf(b);
  var opts = ['active','hot','frozen','closed'].map(function(st){
    return '<div class="stChoice" onclick="setStatusIdx(' + i + ',\'' + st + '\')">' +
      '<div class="d" style="background:' + ST_COLOR[st] + '"></div>' + ST_LABEL[st] +
      (st === cur ? ' <span style="color:#8B8F99;font-size:11px">· נוכחי</span>' : '') + '</div>';
  }).join('<div style="height:1px;background:#F0EDE3"></div>');
  openSheet('<h3>' + esc(b.name || 'קונה') + ' — סטטוס</h3>' + opts +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>', true);
}
function setStatus(b, st){
  POST('/v2/api/buyers/status', {row: b.row, phone: b.phone || '', status: st}).then(function(j){
    if (!j.ok){ toast('שגיאה בשמירה'); closeSheet(); return; }
    if (st === 'active') delete STATUSES[bKey(b)]; else STATUSES[bKey(b)] = st;
    delete STATUSES[b.row];
    closeSheet(); toast('הסטטוס עודכן'); render();
  });
}

function setStatusIdx(i, st){ setStatus(el('list')._src[i], st); }
function toggleHot(i){
  var b = el('list')._src[i];
  setStatus(b, stOf(b) === 'hot' ? 'active' : 'hot');
}
/* ── עריכת קונה: דרישות + סטטוס (שאר השדות ייפתחו עם המעבר ל-Supabase) ── */
function openEdit(i){
  var b = el('list')._src[i];
  var cur = stOf(b);
  openSheet('<div style="display:flex;align-items:center;justify-content:space-between">' +
    '<h3>עריכת קונה · ' + esc(b.name || '') + '</h3>' +
    '<button class="trashBtn" style="width:42px;height:42px;border-radius:11px;background:#FBEDED;border:0;cursor:pointer;display:flex;align-items:center;justify-content:center" onclick="delBuyer(' + i + ')" aria-label="מחיקת קונה">' +
    '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M2.5 4h11M6.5 2h3M5.5 4v9a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1V4M6.8 6.5v5M9.2 6.5v5" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round"/></svg></button></div>' +
    '<div style="display:flex;gap:8px;align-items:flex-end">' +
    '<div class="fld" style="flex:1"><span>טלפון הקונה</span><input id="edPhone" type="tel" value="' + esc(b.phone || '') + '"></div>' +
    (b.budget ? '<div style="background:#F6EEDB;border:1px solid #E4C56B;border-radius:10px;padding:10px 11px;font-size:12px;font-weight:700;color:#B8902F;white-space:nowrap">' + esc(b.budget) + '</div>' : '') +
    '</div>' +
    '<div class="fld"><span>סטטוס</span><div style="display:flex;gap:8px" id="edSt">' +
    ['active','hot','frozen','closed'].map(function(st){
      return '<div data-st="' + st + '" onclick="pickEdSt(this)" ' +
        'style="flex:1;text-align:center;padding:9px 0;border-radius:11px;font-size:12.5px;font-weight:700;cursor:pointer;' +
        (st === cur ? 'background:#2E6BD6;color:#fff' : 'background:#F5F3EC;border:1px solid #E9E4D8;color:#5B6472') + '">' +
        ST_LABEL[st] + '</div>';
    }).join('') + '</div></div>' +
    '<div class="fld"><span>מה מחפש (דרישות) — זה הטקסט שמופיע בכרטיס ומשמש את ההתאמה</span><textarea id="edSearch" rows="3" placeholder="לדוגמה: 4 חדרים בקריות עד 1.5M, קומה נמוכה, מעלית">' + esc(b.search || '') + '</textarea></div>' +
    '<div style="font-size:11px;color:#8B8F99;line-height:1.5">שם ותקציב נערכים בינתיים בגיליון — ייפתחו לעריכה מלאה עם המעבר ל-Supabase.</div>' +
    '<button class="btn btn-blue" onclick="saveEdit(' + i + ')">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>', true);
  el('sheet')._st = cur;
}
function pickEdSt(node){
  el('sheet')._st = node.getAttribute('data-st');
  var cs = node.parentNode.children;
  for (var i = 0; i < cs.length; i++){
    var on = cs[i] === node;
    cs[i].style.cssText = 'flex:1;text-align:center;padding:9px 0;border-radius:11px;font-size:12.5px;font-weight:700;cursor:pointer;' +
      (on ? 'background:#2E6BD6;color:#fff' : 'background:#F5F3EC;border:1px solid #E9E4D8;color:#5B6472');
  }
}
function saveEdit(i){
  var b = el('list')._src[i];
  var jobs = [];
  var q = el('edSearch').value.trim();
  if (q !== (b.search || ''))
    jobs.push(POST('/api/buyers/update', {row: b.row, search: q, phone: (el('edPhone') && el('edPhone').value.trim()) || ''}).then(function(j){
      if (j.ok) b.search = q;
      return j;
    }));
  var st = el('sheet')._st;
  if (st !== stOf(b))
    jobs.push(POST('/v2/api/buyers/status', {row: b.row, phone: b.phone || '', status: st}).then(function(j){
      if (j.ok){ if (st === 'active') delete STATUSES[bKey(b)]; else STATUSES[bKey(b)] = st; delete STATUSES[b.row]; }
      return j;
    }));
  if (!jobs.length){ closeSheet(); return; }
  Promise.all(jobs).then(function(rs){
    closeSheet();
    toast(rs.every(function(j){ return j.ok; }) ? 'נשמר' : 'חלק מהשינויים לא נשמרו');
    load();   // רענון מהשרת — העדכון מופיע מיד בכרטיס ובחיפוש
  });
}
function delBuyer(i){
  var b = el('list')._src[i];
  if (!confirm('למחוק את ' + (b.name || 'הקונה') + '? הפעולה מסירה אותו מהגיליון.')) return;
  POST('/api/buyers/delete', {row: b.row}).then(function(j){
    if (!j.ok){ toast('שגיאה במחיקה'); return; }
    closeSheet(); toast('הקונה נמחק'); load();
  });
}
/* ── הוספת קונה ── */
function openAdd(){
  // מנהל/מתאמת: שיוך הקונה לסוכן כבר בהוספה (מתאמת — הסוכנים שלה בלבד, נאכף בשרת)
  var agRow = MULTI
    ? '<div class="fld"><span>שייך לסוכן</span><select id="abAg" style="background:#fff;border:1.5px solid #DCD6C8;' +
      'border-radius:13px;padding:12px 13px;font-size:14px;font-family:inherit;color:#1E3A5F;width:100%">' +
      '<option value="">עליי</option></select></div>'
    : '';
  openSheet('<h3>קונה חדש</h3>' +
    '<div class="fld"><span>שם</span><input id="abNm" placeholder="שם הקונה"></div>' +
    '<div class="fld"><span>טלפון</span><input id="abPh" type="tel" placeholder="05X-XXXXXXX"></div>' +
    agRow +
    '<div class="fld"><span>תקציב</span><input id="abBd" inputmode="numeric" placeholder="₪" oninput="var d=this.value.replace(/[^0-9]/g,\'\');this.value=d?Number(d).toLocaleString():\'\'"></div>' +
    '<div class="fld"><span>מה מחפש</span><textarea id="abSm" rows="3" placeholder="4 חדרים בקריות, קומה נמוכה..."></textarea></div>' +
    '<div id="abHot" onclick="this._on=!this._on;this.style.background=this._on?\'#F6EEDB\':\'#fff\';this.style.borderColor=this._on?\'#C29435\':\'#DCD6C8\'" ' +
    'style="display:flex;align-items:center;gap:9px;background:#fff;border:1.5px solid #DCD6C8;border-radius:13px;padding:12px 13px;cursor:pointer">' +
    '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M8 1.5c1 2-.5 3-.5 4.5a2.6 2.6 0 0 0 5-1c1.5 2 2 3.5 2 5a6.5 6.5 0 1 1-13 0c0-3 2.5-4.5 3.5-7 .6 1 .8 1.8.7 2.8C7 4.3 7.3 2.8 8 1.5z" fill="none" stroke="#C29435" stroke-width="1.5" stroke-linejoin="round"/></svg>' +
    '<span style="font-size:14px;font-weight:700">קונה חם</span></div>' +
    '<button class="btn btn-blue" onclick="saveBuyer()">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>', true);
  if (MULTI) GET('/api/my/agents').then(function(d){
    var sel = el('abAg'); if (!sel) return;
    sel.innerHTML = '<option value="">עליי</option>' + (((d && d.agents) || []).map(function(a){
      return '<option value="' + esc(a.name) + '">' + esc(a.name) + '</option>'; }).join(''));
  }).catch(function(){});
}
function saveBuyer(){
  if (window._svBusy) return;   // מניעת לחיצה כפולה — קונה נוסף פעמיים
  window._svBusy = true;
  var nm = el('abNm').value.trim(), ph = el('abPh').value.trim();
  var hot = !!(el('abHot') && el('abHot')._on);
  POST('/api/buyers/add', {name: nm, phone: ph,
                           budget: el('abBd').value.trim(), summary: el('abSm').value.trim(),
                           as: (el('abAg') && el('abAg').value) || '', force: !!window._svForce})
    .then(function(j){
      window._svBusy = false;
      if (!j.ok){
        if (j.dup){
          if (confirm(j.reason + '. להוסיף בכל זאת?')){ window._svForce = true; saveBuyer(); window._svForce = false; }
          return;
        }
        toast('שגיאה בשמירה'); return;
      }
      closeSheet(); toast('הקונה נוסף');
      // חוזרים לפילטר שמציג אותו — קונה חדש לא ייעלם מאחורי "חמים"/"בהקפאה" שנשארו מסומנים
      FILTER = 'active';
      var sg = document.querySelector('.sg[data-f="active"]');
      if (sg){ var cs = sg.parentNode.children;
        for (var i2 = 0; i2 < cs.length; i2++) cs[i2].classList.toggle('on', cs[i2] === sg); }
      load().then(function(){
        if (!hot) return;
        // מאתרים את הקונה שנוסף (לפי טלפון, ואם אין — שם) ומסמנים חם
        var dg = ph.replace(/\D/g, ''), b = null;
        BUYERS.forEach(function(x){
          if (b) return;
          var xd = String(x.phone || '').replace(/\D/g, '');
          if ((dg && xd === dg) || (!dg && nm && (x.name || '').trim() === nm)) b = x;
        });
        if (b && b.row != null) setStatus(b, 'hot');
        else toast('הקונה נוסף — סמן חם מהכרטיס');
      });
    }).catch(function(){ window._svBusy = false; toast('שגיאה בשמירה'); });
}

/* ── התאמת נכסים (16b): משרד + שת"פ, אחוז התאמה, שלח לקונה / החתם מתעניין ── */
function matchQuery(b){
  // הדרישות: "מה מחפש" של הקונה, ואם ריק — סיכום השיחה; התקציב מצטרף תמיד
  var base = (b.search || '').trim() || (b.summary || '').trim().slice(0, 90);
  return {q: [base, b.budget ? 'עד ' + b.budget : ''].filter(Boolean).join(' ').slice(0, 160),
          hasNeeds: !!base};
}
function matchProps(i){
  var b = el('list')._src[i];
  var mq = matchQuery(b);
  MQ_NEEDS = mq.hasNeeds;
  openSheet('<div style="display:flex;align-items:flex-start;gap:10px;position:sticky;top:-12px;z-index:2;' +
    'background:#F7F5EE;margin:0 -18px;padding:10px 18px 8px;box-shadow:0 8px 14px -10px rgba(30,58,95,.22)">' +
    '<div style="flex:1"><h3 style="margin:0">התאמת נכסים · ' + esc(b.name || '') + '</h3>' +
    '<div style="font-size:12px;color:#8B8F99;margin-top:3px">מחפש: ' + esc(mq.q || '—') + '</div>' +
    (mq.hasNeeds ? '' : '<div style="font-size:11.5px;color:#B8902F;font-weight:700;margin-top:2px">אין דרישות לקונה — ההתאמה לפי תקציב בלבד. הוסף "מה מחפש" בעריכת הקונה לדיוק</div>') +
    '</div>' +
    '<button onclick="closeSheet()" aria-label="סגירה" style="width:36px;height:36px;border-radius:50%;background:#F5F3EC;' +
    'border:none;display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer">' +
    '<svg width="12" height="12" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round"/></svg></button></div>' +
    '<div id="mRes" style="display:flex;flex-direction:column;gap:10px">' +
    '<div style="text-align:center;color:#8B8F99;font-size:13px;padding:20px 0">מחפש התאמות…</div></div>' +
    '<button class="btn btn-sec" onclick="closeSheet()">סגירה</button>');
  Promise.all([
    POST('/api/search/properties', {q: mq.q, nosave: true}).catch(function(){ return {}; }),
    POST('/api/search/exclusives', {q: mq.q, nosave: true}).catch(function(){ return {}; })
  ]).then(function(rs){
    var bySc = function(a, c){ return (c.score || 0) - (a.score || 0); };
    renderMatches(b, ((rs[0] && rs[0].results) || []).sort(bySc),
                     ((rs[1] && rs[1].results) || []).sort(bySc));
  });
}
function scoreChip(sc){
  if (sc == null) return '';
  return '<span class="score ' + (sc >= 90 ? 'hi' : 'md') + '">' + sc + '% התאמה</span>';
}
var DXN = 0;
function toggleDx(id, btn){
  var d = el(id); if (!d) return;
  var open = d.style.display !== 'none';
  d.style.display = open ? 'none' : 'block';
  var sv = btn && btn.querySelector('svg');
  if (sv) sv.style.transform = open ? '' : 'rotate(180deg)';
}
var MITEMS = [], MSEL = {};
function msgLine(p, shtaf){
  // שורת נכס להודעת הוואטסאפ — בלי שם הסוכן/המשרד המקורי (בקשת אייל)
  var where = [(p.address || p.street), p.neighborhood, p.city].filter(Boolean).join(', ');
  var dt = shtaf
    ? (p.dest || '')
    : [p.type, p.rooms ? p.rooms + ' חד׳' : '', p.floor ? 'קומה ' + p.floor : '',
       p.size ? p.size + ' מ"ר' : ''].filter(Boolean).join(' · ');
  return where + (dt ? '\n' + dt : '') + (p.price ? '\nמחיר: ₪' + p.price : '');
}
function propCard(p, b, shtaf){
  var mi = MITEMS.length;
  MITEMS.push({p: p, shtaf: shtaf});
  // שת"פ באותו פורמט של המשרד: שורת פרטים קצרה; התיאור המלא נפתח באייקון "הרחב לתיאור"
  var dt = shtaf
    ? [(p.dest || ''), p.date ? 'פורסם ' + p.date : '', p.office || 'משרד שותף'].filter(Boolean).join(' · ')
    : [p.type, p.rooms ? p.rooms + ' חד׳' : '', p.floor ? 'קומה ' + p.floor : '',
       p.size ? p.size + ' מ"ר' : '', p.agent || ''].filter(Boolean).join(' · ');
  var where = [(p.address || p.street), p.neighborhood, p.city].filter(Boolean).join(', ');
  var desc = String(p.desc || '').trim();
  var did = 'dx' + (DXN++);
  return '<div class="prop' + (shtaf ? ' shtaf' : '') + '">' +
    '<div class="r1"><div><div class="ad">' + esc(where) + '</div>' +
    '<div class="dt">' + esc(dt) + '</div></div>' +
    '<div style="display:flex;flex-direction:column;align-items:flex-start;gap:4px">' +
    '<div class="pr">' + esc(p.price ? '₪' + p.price : '') + '</div>' + scoreChip(p.score) + '</div>' +
    (desc ? '<button class="dxBtn" onclick="toggleDx(\'' + did + '\', this)" aria-label="הרחב לתיאור">' +
      '<svg width="13" height="13" viewBox="0 0 16 16" style="transition:transform .18s"><path d="M3.5 6l4.5 4.5L12.5 6" fill="none" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' : '') +
    '</div>' +
    (desc ? '<div class="dx" id="' + did + '" style="display:none;margin-top:2px">' + esc(desc) + '</div>' : '') +
    // שת"פ: קישור למודעה המקורית (נדל"ן וואן)
    (shtaf && p.link ? '<a href="' + esc(p.link) + '" target="_blank" rel="noopener" style="display:flex;align-items:center;' +
      'justify-content:center;gap:6px;background:#fff;border:1.5px solid #DCD6C8;border-radius:12px;padding:9px 0;' +
      'font-size:12.5px;font-weight:700;color:#1E3A5F;text-decoration:none">' +
      '<svg width="12" height="12" viewBox="0 0 16 16"><path d="M6.5 9.5l6-6M9 2.5h4.5V7M13 9.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h3.5" fill="none" stroke="#1E3A5F" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      'צפייה במודעה בנדל"ן וואן</a>' : '') +
    '<div class="acts2">' +
    '<button class="sel' + (MSEL[mi] ? ' on' : '') + '" onclick="toggleSel(' + mi + ')" aria-label="בחירה לשליחה">' +
    '<svg width="13" height="13" viewBox="0 0 14 14"><path d="M2 7.5l3.5 3.5L12 3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
    '<button class="a1" onclick="sendOne(' + mi + ')">' +
    '<svg width="13" height="13" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
    'שלח לקונה</button>' +
    '<button class="a2" onclick=\'signBuyer(' + JSON.stringify(JSON.stringify({w: where, pr: p.price || ''})) + ')\'>' +
    '<svg width="12" height="12" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg>' +
    'החתם מתעניין</button></div></div>';
}
var CUR_BUYER = null;
function signBuyer(js){
  var p = JSON.parse(js);
  try{ localStorage.setItem('v2signPre', JSON.stringify({
    client: (CUR_BUYER && CUR_BUYER.name) || '', phone: (CUR_BUYER && CUR_BUYER.phone) || '',
    addr: p.w || '', price: p.pr || ''})); }catch(e){}
  location.href = '/v2/sign?type=buyer';
}
var MQ_NEEDS = true;
function _streetKey(s){
  var m = /([א-ת"'\.\- ]+?\s?\d+[א-ת]?)/.exec(String(s || ''));
  return (m ? m[1] : String(s || '')).replace(/[^א-ת0-9]/g, '');
}
function _priceNum(p){
  var n = parseInt(String(p || '').replace(/[^0-9]/g, ''), 10);
  return isNaN(n) ? 0 : n;
}
function _budgetNum(s){
  // תקציב כטקסט חופשי: "2,000,000" / "2 מיליון" / "800 אלף" / "1.5-2 מיליון" — לוקחים את הגבוה
  s = String(s || '');
  var mil = /מי?ליון/.test(s), elf = /אלף/.test(s);
  var best = 0;
  (s.match(/\d[\d,\.]*/g) || []).forEach(function(t){
    var n = parseFloat(t.replace(/,/g, ''));
    if (isNaN(n)) return;
    if (mil && n < 100) n *= 1000000;
    else if (elf && n < 10000) n *= 1000;
    if (n > best) best = n;
  });
  return best;
}
function dedupeShtaf(office, shtaf){
  // אותו נכס גם במשרד וגם בשת"פ (כתובת זהה + מחיר בהפרש עד 100 אלף) — משאירים את של המשרד
  return shtaf.filter(function(s){
    var sk = _streetKey(s.street || s.address), sp = _priceNum(s.price);
    if (!sk) return true;
    return !office.some(function(o){
      var ok = _streetKey(o.address || o.street);
      return ok && ok === sk && Math.abs(_priceNum(o.price) - sp) <= 100000;
    });
  });
}
function renderMatches(b, office, shtaf){
  CUR_BUYER = b;
  MITEMS = []; MSEL = {};
  // תקציב 2 מיליון לא מקבל נכס של 1.35/2.6 מיליון — עד 20% הפרש; נכס בלי מחיר לא נפסל
  var bd = _budgetNum(b.budget);
  if (bd >= 10000){
    var bok = function(p){ var pr = _priceNum(p.price); return !pr || Math.abs(pr - bd) <= bd * 0.2; };
    office = office.filter(bok); shtaf = shtaf.filter(bok);
  }
  shtaf = dedupeShtaf(office, shtaf);
  // חזקות (60%+) קודם; כל השאר תחת "התאמות נוספות" — שום דבר לא נחתך ל-5
  var strong = function(p){ return (p.score || 0) >= 60; };
  var oS = office, oW = [], sS = shtaf, sW = [];
  if (MQ_NEEDS){
    oS = office.filter(strong); oW = office.filter(function(p){ return !strong(p); });
    sS = shtaf.filter(strong);  sW = shtaf.filter(function(p){ return !strong(p); });
  }
  var h = '';
  if (oS.length){
    h += '<div class="grpTitle">המשרד שלנו · ' + oS.length + '</div>';
    oS.slice(0, 25).forEach(function(p){ h += propCard(p, b, false); });
  }
  if (sS.length){
    h += '<div class="grpTitle">שת"פ · ' + sS.length + '</div>';
    sS.slice(0, 15).forEach(function(p){ h += propCard(p, b, true); });
  }
  if (oW.length || sW.length){
    h += '<div class="grpTitle" style="color:#8B8F99">התאמות נוספות · ' + (oW.length + sW.length) + '</div>';
    oW.slice(0, 15).forEach(function(p){ h += propCard(p, b, false); });
    sW.slice(0, 10).forEach(function(p){ h += propCard(p, b, true); });
  }
  el('mRes').innerHTML = (h ||
    '<div style="text-align:center;color:#8B8F99;font-size:13px;padding:16px 0">' +
    'לא נמצאו התאמות — נסה לעדכן את הדרישות של הקונה</div>') +
    '<div id="selBar" style="display:none;position:sticky;bottom:0;padding:8px 0">' +
    '<button class="btn" style="background:#1FAF5E;color:#fff;box-shadow:0 4px 14px rgba(31,175,94,.3)" ' +
    'onclick="sendSelected()"><span id="selN"></span></button></div>';
  updateSelBar();
}
function toggleSel(mi){
  if (MSEL[mi]) delete MSEL[mi]; else MSEL[mi] = 1;
  document.querySelectorAll('#mRes .sel').forEach(function(btn){
    var m = /toggleSel\((\d+)\)/.exec(btn.getAttribute('onclick') || '');
    if (m) btn.classList.toggle('on', !!MSEL[m[1]]);
  });
  updateSelBar();
}
function updateSelBar(){
  var n = Object.keys(MSEL).length;
  var bar = el('selBar');
  if (!bar) return;
  bar.style.display = n ? 'block' : 'none';
  if (n) el('selN').textContent = 'שלח ' + n + ' נכסים לקונה בוואטסאפ';
}
function waToBuyer(msg){
  // וואטסאפ ללקוח — גם כשאין מספר שמור נפתח וואטסאפ עם ההודעה לבחירת איש קשר
  var wa = (CUR_BUYER && CUR_BUYER.wa) || '';
  window.open('https://wa.me/' + wa + '?text=' + encodeURIComponent(msg), '_blank');
}
function sendOne(mi){
  var it = MITEMS[mi]; if (!it) return;
  var msg = 'היי' + (CUR_BUYER && CUR_BUYER.name ? ' ' + CUR_BUYER.name : '') +
    ', מצאתי נכס שיכול להתאים לך:\n\n' + msgLine(it.p, it.shtaf) + '\n\nמעניין אותך לשמוע עוד?';
  waToBuyer(msg);
}
function sendSelected(){
  var ks = Object.keys(MSEL);
  if (!ks.length) return;
  var lines = ks.map(function(k, i){
    var it = MITEMS[k];
    return (i + 1) + '. ' + msgLine(it.p, it.shtaf);
  });
  var msg = 'היי' + (CUR_BUYER && CUR_BUYER.name ? ' ' + CUR_BUYER.name : '') +
    ', מצאתי ' + ks.length + ' נכסים שיכולים להתאים לך:\n\n' + lines.join('\n\n') + '\n\nמעניין אותך לשמוע עוד?';
  waToBuyer(msg);
}



/* זיכרון מצב הטאב — פילטר/חיפוש/גלילה נשמרים וחוזרים בכניסה הבאה */
var _restY = 0;
function saveSt(){
  try{
    var m = document.querySelector('main');
    localStorage.setItem('v2st:buyers', JSON.stringify({f:FILTER, q:el('q').value, y:(m ? m.scrollTop : 0)}));
  }catch(e){}
}
(function(){
  try{
    var s = JSON.parse(localStorage.getItem('v2st:buyers') || 'null');
    if (s){
      FILTER = s.f || FILTER; el('q').value = s.q || ''; _restY = s.y || 0;
    }
  }catch(e){}
  var sg = document.querySelector('#filters .sg[data-f="' + FILTER + '"]');
  if (sg){ var cs = sg.parentNode.children;
    for (var i = 0; i < cs.length; i++) cs[i].classList.toggle('on', cs[i] === sg); }
})();
var _renderBase = render;
render = function(){
  _renderBase();
  if (_restY){
    var m = document.querySelector('main');
    if (m){ m.scrollTop = _restY; if (m.scrollTop >= _restY - 4) _restY = 0; }
  }
  if (!_restY) saveSt();
};
(function(){
  var m = document.querySelector('main');
  if (m) m.addEventListener('scroll', function(){
    if (window._svScrolled) _restY = 0; window._svScrolled = true;
    clearTimeout(window._svt); window._svt = setTimeout(saveSt, 300);
  }, {passive:true});
  window.addEventListener('pagehide', function(){ if (!_restY) saveSt(); });
})();

(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    el('avatarTx').textContent = (j.name || ' ').trim()[0] || '';
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    OFFICE = o.name || '';
    document.title = 'קונים · ' + OFFICE;
  }).catch(function(){});
  load().then(function(){
    if (location.search.indexOf('add=1') >= 0) openAdd();
  });
})();
</script></body></html>'''


# ── מסך החתימות (עיצוב 17a) — רשימה, פילטרים, צפייה במסמך; הטפסים בסשן הבא ──
V2_SIGS_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>חתימות</title>
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
  .brand img{height:36px;max-width:150px;object-fit:contain}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 14px;display:flex;flex-direction:column;gap:13px;overflow:auto}
  .card{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:16px 18px 14px;
      display:flex;flex-direction:column;gap:12px}
  .hd{display:flex;align-items:center;justify-content:space-between}
  .hd .tt{display:flex;align-items:center;gap:10px}
  .hd .ic{width:36px;height:36px;border-radius:11px;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .hd h1{font-size:21px;font-weight:800}
  .live{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:700}
  .live i{width:8px;height:8px;border-radius:50%;background:#1FAF5E;display:block}
  @media (prefers-reduced-motion:no-preference){
    @keyframes pulseDot{0%,100%{opacity:1}50%{opacity:.35}}
    .live i{animation:pulseDot 2s infinite}
  }
  .ctaRow{display:flex;gap:10px}
  .ctaRow .b1{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;background:#C29435;color:#fff;
      border-radius:14px;padding:13px 0;font-size:14px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(194,148,53,.25)}
  .ctaRow .b2{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;background:#fff;color:#1E3A5F;
      border:1.5px solid #DCD6C8;border-radius:14px;padding:13px 0;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px}
  .segs .sg{flex:1;text-align:center;padding:7px 0;font-size:12.5px;font-weight:700;color:#5B6472;
      border-radius:10px;cursor:pointer}
  .segs .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .sig{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:10px;margin-bottom:13px}
  .sig .top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  .sig .ad{font-size:15.5px;font-weight:700}
  .sig .sb{font-size:12px;color:#8B8F99}
  .chip{font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:999px;white-space:nowrap;flex-shrink:0}
  .chip.owner{color:#C24040;background:#FBEDED}
  .chip.buyer{color:#2E6BD6;background:#EAF0FA}
  .chip.other{color:#5B6472;background:#F0EDE3}
  .st{display:flex;align-items:center;gap:7px;font-size:12.5px;font-weight:600}
  .st i{width:7px;height:7px;border-radius:50%;display:block;flex-shrink:0}
  .st.signed{color:#1FAF5E}.st.signed i{background:#1FAF5E}
  .st.wait{color:#B8902F}.st.wait i{background:#C29435}
  .acts{display:flex;gap:9px;align-items:center}
  .acts .a{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;border-radius:12px;
      padding:10px 0;font-size:13px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:40px}
  .acts .sec{background:#fff;color:#1E3A5F;border:1.5px solid #DCD6C8}
  .acts .del{flex:0 0 42px;width:42px;background:#FBEDED}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .t{font-size:15px;font-weight:800}
  .empty .s{font-size:12.5px;color:#5B6472;line-height:1.6;max-width:260px}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 16px;
      display:none;flex-direction:column;gap:12px;max-height:82vh;overflow:auto}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center}
  #sheet h3{font-size:19px;font-weight:800}
  .btn{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:13px;padding:13px 0;width:100%;
      font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:46px}
  .btn-gold{background:#C29435;color:#fff;box-shadow:0 4px 12px rgba(194,148,53,.25)}
  .btn-sec{background:#fff;color:#5B6472;border:1.5px solid #DCD6C8}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  /* ── דסקטופ: עמודה ממורכזת ── */
  @media (min-width:700px){
    header,main,nav{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
</style></head><body>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
    <button class="menuBtn" onclick="location.href='/v2/home'" aria-label="לבית">
      <svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
    </button>
  </header>

  <main>
    <div class="card">
      <div class="hd">
        <div class="tt">
          <div class="ic"><svg width="16" height="16" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#B8902F" stroke-width="1.7" stroke-linejoin="round"/></svg></div>
          <h1>חתימות</h1>
        </div>
        <div class="live"><i></i><span id="weekN">—</span></div>
      </div>
      <div class="ctaRow">
        <button class="b1" onclick="openSignInfo('owner')">
          <svg width="14" height="14" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg>
          החתם בעל נכס
        </button>
        <button class="b2" onclick="openSignInfo('buyer')">החתם מתעניין</button>
      </div>
      <div class="segs" id="filters">
        <div class="sg on" data-f="buyer" onclick="setFilter(this)">קונים</div>
        <div class="sg" data-f="excl" onclick="setFilter(this)">בלעדיות</div>
        <div class="sg" data-f="all" onclick="setFilter(this)">הכל</div>
      </div>
    </div>
    <div id="list"></div>
  </main>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" style="color:#1E3A5F;font-weight:700"><div class="home"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg></div>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
function openSheet(html){
  el('sheet').innerHTML = '<div class="grip"></div>' + html;
  el('sheet').style.display = 'flex'; el('ovl').style.display = 'block';
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }
function POST(u, d){
  return fetch(u, {method:'POST', headers:{'X-Auth-Token': TOK, 'Content-Type':'application/json'},
    body: JSON.stringify(d)}).then(function(r){ return r.json(); });
}

var SIGS = [], FILTER = 'buyer', MULTI = false, ROLE = '';   // ברירת מחדל: קונים (מימין); שכירות/מוכר וכו' — תחת "הכל"
function kindOf(g){   // תוויות _deal_label בשרת: "קונים" / "בלעדיות" / "שכירות" / "מוכר"
  var t = g.type || '';
  if (t.indexOf('בלעדיות') >= 0) return 'excl';
  if (t.indexOf('קונים') >= 0 || t.indexOf('מתעניין') >= 0) return 'buyer';
  return 'other';
}
function weekStart(){
  var d = new Date(); d.setHours(0,0,0,0);
  d.setDate(d.getDate() - d.getDay());
  return d.getTime() / 1000;
}
function load(){
  return GET('/api/signatures').then(function(j){
    SIGS = (j && j.signatures) || [];
    MULTI = (j && j.role) !== 'agent';
    ROLE = (j && j.role) || '';
    try{ localStorage.setItem('v2c:sigs', JSON.stringify({g: SIGS.slice(0, 150), m: MULTI, r: ROLE})); }catch(e){}
    render();
  }).catch(function(){});
}
(function(){
  try{
    var c = JSON.parse(localStorage.getItem('v2c:sigs') || 'null');
    if (c && c.g){ SIGS = c.g; MULTI = !!c.m; ROLE = c.r || ''; }
  }catch(e){}
})();
function render(){
  var ws = weekStart();
  el('weekN').textContent = SIGS.filter(function(g){ return (g.ts || 0) >= ws; }).length + ' השבוע';
  var src = SIGS.filter(function(g){
    if (FILTER === 'all') return true;
    return kindOf(g) === FILTER;
  });
  var h = '';
  var shown = src.slice(0, 100);
  shown.forEach(function(g, gi){
    var k = kindOf(g);
    var chip = (k === 'buyer') ? '<div class="chip buyer">קונים</div>'
      : (k === 'excl') ? '<div class="chip owner">בלעדיות</div>'
      : '<div class="chip other">' + esc(g.type || 'חתימה') + '</div>';
    var signed = !!(g.link || g.pct);
    var sub = [g.client, MULTI ? g.agent : '', g.type].filter(Boolean).join(' · ');
    var vw = (signed && g.link)
      ? '<button class="a sec" onclick="window.open(\'' + esc(g.link) + '\',\'_blank\')">' +
        '<svg width="13" height="13" viewBox="0 0 16 16"><path d="M3 2.5h7l3 3V13a.9.9 0 0 1-.9.9H3.9A.9.9 0 0 1 3 13z" fill="none" stroke="#1E3A5F" stroke-width="1.5" stroke-linejoin="round"/><path d="M10 2.5v3h3" fill="none" stroke="#1E3A5F" stroke-width="1.5" stroke-linejoin="round"/></svg>' +
        'צפייה במסמך החתום</button>'
      : '';
    // מחיקת חתימה דיגיטלית — מנהל בלבד (רק לרשומות מהאפליקציה, עם eid)
    var dl = (ROLE === 'admin' && g.eid)
      ? '<button class="a del" onclick="delSig(' + gi + ')" aria-label="מחיקת חתימה">' +
        '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.6a1 1 0 0 0 1 .9h3.6a1 1 0 0 0 1-.9l.7-8.6M6.7 7v4M9.3 7v4" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></button>'
      : '';
    var acts = (vw || dl) ? '<div class="acts">' + vw + dl + '</div>' : '';
    h += '<div class="sig">' +
      '<div class="top"><div><div class="ad">' + esc(g.address || g.client || '') + '</div>' +
      '<div class="sb">' + esc(sub) + '</div></div>' + chip + '</div>' +
      '<div class="st ' + (signed ? 'signed' : 'wait') + '"><i></i>' +
      (signed ? 'נחתם' : 'ממתין לחתימה') + (g.time ? ' · ' + esc(g.time) : '') +
      (signed && g.pct ? ' · עמלה ' + esc(String(g.pct)) + '%' : '') + '</div>' + acts + '</div>';
  });
  el('list').innerHTML = h ||
    '<div class="card empty"><div class="ic"><svg width="28" height="28" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#C29435" stroke-width="1.7" stroke-linejoin="round"/></svg></div>' +
    '<div class="t">אין חתימות להצגה</div>' +
    '<div class="s">כל החתמה דיגיטלית — בעל נכס או מתעניין — תופיע כאן עם המסמך החתום</div></div>';
  el('list')._shown = shown;
}
function delSig(i){
  var g = (el('list')._shown || [])[i]; if (!g) return;
  if (!confirm('למחוק את החתימה של ' + (g.client || 'הלקוח') + '? הפעולה אינה הפיכה.')) return;
  POST('/api/sign/delete', {eid: g.eid || '', received: g.raw || '', client: g.client || ''}).then(function(j){
    if (!j.ok){ toast('שגיאה במחיקה'); return; }
    toast('החתימה נמחקה'); load();
  });
}
function setFilter(node){
  FILTER = node.getAttribute('data-f');
  var sgs = node.parentNode.children;
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i] === node);
  render();
}
function openSignInfo(kind){
  location.href = '/v2/sign?type=' + (kind === 'owner' ? 'owner' : 'buyer');
}

/* זיכרון מצב הטאב — פילטר/חיפוש/גלילה נשמרים וחוזרים בכניסה הבאה */
var _restY = 0;
function saveSt(){
  try{
    var m = document.querySelector('main');
    localStorage.setItem('v2st:sigs', JSON.stringify({f:FILTER, y:(m ? m.scrollTop : 0)}));
  }catch(e){}
}
(function(){
  try{
    var s = JSON.parse(localStorage.getItem('v2st:sigs') || 'null');
    if (s){
      FILTER = s.f || FILTER; _restY = s.y || 0;
    }
  }catch(e){}
  var sg = document.querySelector('#filters .sg[data-f="' + FILTER + '"]');
  if (sg){ var cs = sg.parentNode.children;
    for (var i = 0; i < cs.length; i++) cs[i].classList.toggle('on', cs[i] === sg); }
})();
var _renderBase = render;
render = function(){
  _renderBase();
  if (_restY){
    var m = document.querySelector('main');
    if (m){ m.scrollTop = _restY; if (m.scrollTop >= _restY - 4) _restY = 0; }
  }
  if (!_restY) saveSt();
};
(function(){
  var m = document.querySelector('main');
  if (m) m.addEventListener('scroll', function(){
    if (window._svScrolled) _restY = 0; window._svScrolled = true;
    clearTimeout(window._svt); window._svt = setTimeout(saveSt, 300);
  }, {passive:true});
  window.addEventListener('pagehide', function(){ if (!_restY) saveSt(); });
})();

(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    el('avatarTx').textContent = (j.name || ' ').trim()[0] || '';
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    document.title = 'חתימות · ' + (o.name || '');
  }).catch(function(){});
  load();
  setInterval(load, 90000);
})();
</script></body></html>'''


# ── מסך נכס נולד (עיצוב 19a) — מונה חי, צ'יפי ותק, בעל הנכס, סטטוסים, פגישות ──
V2_NB_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>נכס נולד</title>
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
  .brand img{height:36px;max-width:150px;object-fit:contain}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 14px;display:flex;flex-direction:column;gap:12px;overflow:auto}
  .card{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px 13px;
      display:flex;flex-direction:column;gap:11px}
  .hd{display:flex;align-items:center;justify-content:space-between}
  .hd .tt{display:flex;align-items:center;gap:10px}
  .hd h1{font-size:21px;font-weight:800}
  .live{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:700}
  .live i{width:8px;height:8px;border-radius:50%;background:#1FAF5E;display:block}
  @media (prefers-reduced-motion:no-preference){
    @keyframes pulseDot{0%,100%{opacity:1}50%{opacity:.35}}
    .live i{animation:pulseDot 2s infinite}
  }
  .meetChip{display:flex;align-items:center;gap:6px;background:#EAF0FA;color:#2E6BD6;border-radius:999px;
      padding:5px 12px;font-size:12px;font-weight:700;border:0;cursor:pointer;font-family:inherit;align-self:flex-start}
  .ageHead{display:flex;align-items:center;justify-content:space-between}
  .ageHead .l{font-size:11.5px;font-weight:700;color:#8B8F99}
  .ageHead .r{font-size:11.5px;font-weight:700;color:#B8902F}
  .ages{display:flex;gap:7px;overflow-x:auto;scrollbar-width:none;
      mask-image:linear-gradient(to left, black 88%, transparent)}
  .ages::-webkit-scrollbar{display:none}
  .age{display:flex;flex-direction:column;align-items:center;background:#fff;border:1.5px solid #E9E4D8;
      border-radius:12px;padding:7px 14px;flex-shrink:0;cursor:pointer}
  .age .t{font-size:12.5px;font-weight:700;color:#1E3A5F}
  .age .n{font-size:10.5px;font-weight:600;color:#9AA0AB}
  .age.on{background:#C29435;border-color:#C29435;box-shadow:0 4px 12px rgba(194,148,53,.25)}
  .age.on .t,.age.on .n{color:#fff}
  .srch{display:flex;align-items:center;gap:9px;background:#F5F3EC;border:1px solid #E9E4D8;
      border-radius:13px;padding:0 14px}
  .srch input{flex:1;border:0;background:none;font-size:13.5px;font-family:inherit;outline:none;
      color:#1E3A5F;padding:11px 0}
  .nb{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:9px;margin-bottom:12px}
  .nb .top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  .nb .ad{font-size:16px;font-weight:700;line-height:1.3}
  .nb .dt{font-size:12.5px;color:#8B8F99}
  .chip{font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:999px;white-space:nowrap;flex-shrink:0}
  .chip.new{color:#B8902F;background:#F6EEDB}
  .chip.age{color:#8B8F99;background:#F0EDE3}
  .nb .pr{font-size:21px;font-weight:800}
  .owner{display:flex;align-items:center;gap:10px;background:#F7F5EE;border-radius:12px;padding:9px 12px}
  .owner .ic{width:30px;height:30px;border-radius:50%;background:#EAF0FA;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .owner .nm{font-size:13.5px;font-weight:800}
  .owner .sb{font-size:10.5px;color:#8B8F99}
  .oActs{display:flex;gap:8px}
  .oActs .a{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;border-radius:11px;
      padding:10px 0;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;text-decoration:none}
  .oActs .call{background:#EAF0FA;color:#2E6BD6}
  .oActs .wa{background:#E7F7EE;color:#1FAF5E}
  .oActs .view{flex:1.2;background:#1E3A5F;color:#fff}
  .contacted{display:flex;align-items:center;gap:6px;background:#E7F7EE;border-radius:999px;
      padding:5px 12px;align-self:flex-start;font-size:11.5px;font-weight:700;color:#1FAF5E}
  .stActs{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:7px}
  .stActs .s{display:flex;align-items:center;justify-content:center;background:#fff;border:1.5px solid #DCD6C8;
      border-radius:11px;padding:9px 0;font-size:11px;font-weight:700;color:#1E3A5F;cursor:pointer;font-family:inherit}
  .stActs .s.red{color:#C24040}
  .stActs .s.on{background:#C29435;border-color:#C29435;color:#fff;box-shadow:0 3px 10px rgba(194,148,53,.25)}
  .stActs .s.red.on{background:#C24040;border-color:#C24040;color:#fff;box-shadow:0 3px 10px rgba(194,64,64,.25)}
  .stLine{display:flex;align-items:center;gap:6px;font-size:11.5px;color:#8B8F99}
  .stLine i{width:6px;height:6px;border-radius:50%;background:#C29435;display:block;flex-shrink:0}
  .notes{font-size:11.5px;color:#5B6472;background:#F7F5EE;border-radius:10px;padding:7px 11px;line-height:1.5}
  .more{display:flex;align-items:center;justify-content:center;padding:12px 0;font-size:13px;font-weight:700;
      color:#2E6BD6;cursor:pointer}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .t{font-size:15px;font-weight:800}
  .empty .s{font-size:12.5px;color:#5B6472;line-height:1.6;max-width:260px}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer;position:relative}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  nav .badge{position:absolute;top:-13px;z-index:2;background:#C29435;color:#fff;font-size:10px;font-weight:800;
      padding:1px 8px;border-radius:999px;display:none}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 16px;
      display:none;flex-direction:column;gap:12px;max-height:82vh;overflow:auto}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center}
  #sheet h3{font-size:19px;font-weight:800}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld span{font-size:11.5px;font-weight:700;color:#5B6472}
  .fld input,.fld textarea{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:11px;padding:11px 13px;
      font-size:14px;font-weight:700;color:#1E3A5F;font-family:inherit;outline:none;width:100%;resize:vertical}
  .btn{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:13px;padding:13px 0;width:100%;
      font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:46px}
  .btn-gold{background:#C29435;color:#fff;box-shadow:0 4px 12px rgba(194,148,53,.25)}
  .btn-blue{background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .btn-sec{background:#fff;color:#5B6472;border:1.5px solid #DCD6C8}
  .mRow{display:flex;align-items:center;gap:10px;background:#fff;border-radius:14px;padding:11px 13px}
  .mRow .mid{flex:1;min-width:0}
  .mRow .t{font-size:13.5px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mRow .s{font-size:11.5px;color:#8B8F99}
  .mRow .sq{width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;
      flex-shrink:0;border:0;cursor:pointer;text-decoration:none}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  @media (min-width:700px){
    header,main,nav{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
</style></head><body>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
    <button class="menuBtn" onclick="location.href='/v2/home'" aria-label="לבית">
      <svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
    </button>
  </header>

  <main>
    <div class="card">
      <div class="hd">
        <div class="tt">
          <svg width="26" height="23" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>
          <h1>נכס נולד</h1>
        </div>
        <div class="live"><i></i><span id="liveN">—</span></div>
      </div>
      <button class="meetChip" onclick="location.href='/v2/meets'">
        <svg width="12" height="12" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#2E6BD6" stroke-width="1.6" stroke-linecap="round"/></svg>
        <span id="meetN">פגישות ופולו-אפ</span>
      </button>
      <div class="ageHead"><span class="l">ותק בפרסום · גלול לצדדים</span><span class="r" id="ageSum"></span></div>
      <div class="ages" id="ages"></div>
      <div class="srch">
        <svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M11 11l3.4 3.4" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>
        <input id="q" placeholder="רחוב, שכונה או בעל הנכס" oninput="render();qClearBtn()">
        <button id="qClear" onclick="el('q').value='';qClearBtn();render()" aria-label="ניקוי חיפוש"
          style="display:none;width:26px;height:26px;border-radius:50%;background:#EBE8DD;border:none;flex-shrink:0;
          align-items:center;justify-content:center;cursor:pointer;padding:0">
          <svg width="10" height="10" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round"/></svg>
        </button>
      </div>
    </div>
    <div id="list"></div>
  </main>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" style="color:#1E3A5F;font-weight:700"><div class="home"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#fff"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg></div>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
function openSheet(html){
  el('sheet').innerHTML = '<div class="grip"></div>' + html;
  el('sheet').style.display = 'flex'; el('ovl').style.display = 'block';
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }

var ROWS = [], BUCKETS = [], TOTAL = 0, AGE = -1, MGR = false, MEETS = [];
var BUCKET_RANGES = [[0,30],[30,60],[60,90],[90,120],[120,150],[150,180],[180,99999]];
var ST_LABEL = {meeting:'פגישה', followup:'פולו-אפ', not_interested:'לא מעוניין'};

function load(){
  return Promise.all([
    GET('/api/newborn').catch(function(){ return {}; }),
    GET('/api/newborn/meetings').catch(function(){ return {}; })
  ]).then(function(rs){
    ROWS = (rs[0] && rs[0].results) || [];
    BUCKETS = (rs[0] && rs[0].bucketCounts) || [];
    TOTAL = (rs[0] && rs[0].total) || ROWS.length;
    MEETS = (rs[1] && (rs[1].results || rs[1].meetings)) || [];
    try{ localStorage.setItem('v2c:nb', JSON.stringify(
      {r: ROWS.slice(0, 150), b: BUCKETS, t: TOTAL, m: MEETS.slice(0, 40)})); }catch(e){}
    render();
  });
}
(function(){
  try{
    var c = JSON.parse(localStorage.getItem('v2c:nb') || 'null');
    if (c && c.r){ ROWS = c.r; BUCKETS = c.b || []; TOTAL = c.t || 0; MEETS = c.m || []; }
  }catch(e){}
})();
function qClearBtn(){
  var b = el('qClear');
  if (b) b.style.display = el('q').value ? 'flex' : 'none';
}
function fmtPrice(p){
  p = String(p || '').trim();
  if (!p) return '';
  return (/^[\d,.]+$/.test(p) ? '₪' : '') + p;
}
function render(){
  el('liveN').textContent = TOTAL.toLocaleString() + ' · חי';
  var bd = el('nbBadge');
  if (bd && TOTAL){ bd.textContent = TOTAL.toLocaleString(); bd.style.display = 'block'; }
  el('meetN').textContent = 'פגישות ופולו-אפ' + (MEETS.length ? ' · ' + MEETS.length : '');
  // צ'יפי ותק
  var ah = '';
  BUCKET_RANGES.forEach(function(r, i){
    var label = (i < 6) ? 'חודש ' + (i + 1) : '7+';
    ah += '<div class="age' + (AGE === i ? ' on' : '') + '" onclick="setAge(' + i + ')">' +
      '<span class="t">' + label + '</span><span class="n">' + (BUCKETS[i] || 0) + '</span></div>';
  });
  el('ages').innerHTML = ah;
  el('ageSum').textContent = AGE < 0 ? 'כל הנכסים · ' + TOTAL.toLocaleString()
    : ((AGE < 6 ? 'חודש ' + (AGE + 1) : '7+') + ' · ' + (BUCKETS[AGE] || 0) + ' נכסים');
  // רשימה
  var q = el('q').value.trim().toLowerCase();
  var src = ROWS.filter(function(r){
    if (AGE >= 0){
      var rg = BUCKET_RANGES[AGE];
      if (!(r.ageDays >= rg[0] && r.ageDays < rg[1])) return false;
    }
    if (q && ((r.address || '') + ' ' + (r.city || '') + ' ' + (r.owner || '') + ' ' + (r.desc || ''))
        .toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  var h = '';
  src.slice(0, 30).forEach(function(r, i){
    try{ h += nbCard(r, i); }catch(e){}   // שורה בעייתית לא מפילה את המסך
  });
  if (src.length > 30) h += '<div class="more">מוצגים 30 מתוך ' + src.length + ' — חדד עם חיפוש או ותק</div>';
  el('list').innerHTML = h ||
    '<div class="card empty"><div class="ic"><svg width="30" height="27" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg></div>' +
    '<div class="t">אין נכסים להצגה</div><div class="s">נסה ותק אחר או חיפוש שונה — מודעות חדשות עולות כל היום</div></div>';
  el('list')._src = src;
}
function nbCard(r, i){
  var chip = (r.ageDays === 0) ? '<div class="chip new">חדש היום</div>'
    : '<div class="chip age">' + (r.ageDays < 180 ? 'חודש ' + (Math.floor(r.ageDays / 30) + 1) : '7+ חודשים') + '</div>';
  var st = r.stat;
  var owner = (r.owner || r.phone)
    ? '<div class="owner"><div class="ic"><svg width="13" height="13" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#2E6BD6" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round"/></svg></div>' +
      '<div style="flex:1"><div class="nm">' + esc([r.owner, r.phone].filter(Boolean).join(' · ')) + '</div>' +
      '<div class="sb">בעל הנכס · מתעדכן יומית</div></div></div>' +
      '<div class="oActs">' +
      '<a class="a call" href="tel:' + esc((r.phone || '').replace(/\D/g, '')) + '" onclick="markContact(' + i + ')">' +
      '<svg width="13" height="13" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#2E6BD6" stroke-width="1.7"/></svg>חייג</a>' +
      '<button class="a wa" onclick="waOwner(' + i + ')">' +
      '<svg width="13" height="13" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#1FAF5E" stroke-width="1.5"/></svg>וואטסאפ</button>' +
      (r.link ? '<a class="a view" target="_blank" rel="noopener" href="' + esc(r.link) + '">צפייה במודעה</a>' : '') +
      '</div>'
    // אין שם/טלפון של בעל הנכס — עדיין מציגים את הקישור למודעה
    : (r.link ? '<div class="oActs"><a class="a view" target="_blank" rel="noopener" href="' + esc(r.link) + '">צפייה במודעה</a></div>' : '');
  var contacted = (MGR && r.contacted && r.contacted.length)
    ? '<div class="contacted">כבר פנו: ' + esc(r.contacted[0]) +
      (r.contacted.length > 1 ? ' +' + (r.contacted.length - 1) : '') + ' · ' + r.contacted.length + ' פניות</div>'
    : '';
  var stLine = st ? '<div class="stLine"><i></i>' + esc((ST_LABEL[st.status] || st.status) +
      (st.date ? ' · ' + st.date.replace('T', ' ') : '') + (st.agent ? ' · ' + st.agent : '')) + '</div>' : '';
  var notes = (r.unotes && r.unotes.length)
    ? '<div class="notes">' + esc(r.unotes[r.unotes.length - 1].name + ': ' + r.unotes[r.unotes.length - 1].text) + '</div>' : '';
  return '<div class="nb">' +
    '<div class="top"><div><div class="ad">' + esc([r.address, r.city].filter(Boolean).join(', ')) + '</div>' +
    '<div class="dt">' + esc((r.desc || '').slice(0, 90)) + '</div></div>' + chip + '</div>' +
    '<div style="display:flex;align-items:center;justify-content:space-between">' +
    '<div class="pr">' + esc(fmtPrice(r.price)) + '</div>' +
    '<div style="font-size:11.5px;color:#8B8F99">' + esc(r.date || '') + '</div></div>' +
    owner + contacted +
    '<div class="stActs">' +
    '<button class="s' + (st && st.status === 'meeting' ? ' on' : '') + '" onclick="stDate(' + i + ',\'meeting\')">פגישה</button>' +
    '<button class="s' + (st && st.status === 'followup' ? ' on' : '') + '" onclick="stDate(' + i + ',\'followup\')">פולו-אפ</button>' +
    '<button class="s red' + (st && st.status === 'not_interested' ? ' on' : '') + '" onclick="stToggleNI(' + i + ')">לא מעוניין</button>' +
    '<button class="s" onclick="noteSheet(' + i + ')">הערה</button></div>' +
    stLine + notes + '</div>';
}
function setAge(i){ AGE = (AGE === i) ? -1 : i; render(); }
function markContact(i){
  var r = el('list')._src[i];
  POST('/api/newborn/contact', {key: r.key, addr: r.address}).catch(function(){});
}
function waOwner(i){
  var r = el('list')._src[i];
  markContact(i);
  window.open('https://wa.me/' + (r.wa || '') + '?text=' +
    encodeURIComponent('שלום' + (r.owner ? ' ' + r.owner : '') + ', ראיתי את המודעה שלך ב' +
    ((r.address || '') + (r.city ? ', ' + r.city : '')) + '. אשמח לדבר איתך לגבי הנכס.'), '_blank');
}
var MYNAME = '';
var AG_OPTS = [];      // מתאמת: הסוכנים שלה (מהשרת); מנהל: כל סוכני המשרד
var IS_COORD = false;  // למתאמת נוספת אופציית "אחר במשרד…" — כל סוכני המשרד
var OFFICE_AG = [];
function agOpts(list, withMore){
  return '<option value="">עליי (' + esc(MYNAME || '') + ')</option>' +
    list.map(function(a){ return '<option value="' + esc(a) + '">' + esc(a) + '</option>'; }).join('') +
    (withMore ? '<option value="__more">אחר במשרד…</option>' : '');
}
function agOther(sel){
  if (sel.value !== '__more') return;
  var fill = function(){
    var mine = {};
    AG_OPTS.forEach(function(a){ mine[a] = 1; });
    var rest = OFFICE_AG.filter(function(a){ return !mine[a] && a !== MYNAME; });
    sel.innerHTML = agOpts(AG_OPTS.concat(rest), false);
    sel.value = '';
    sel.focus();
  };
  if (OFFICE_AG.length){ fill(); return; }
  GET('/api/agents').then(function(d){   // רשימת המשרד הקנונית — בלי כפילויות איות
    OFFICE_AG = ((d && d.agents) || []).map(function(a){ return a.name; });
    fill();
  }).catch(function(){ sel.value = ''; });
}
function dt15Opts(sel){
  var ts = [], h, m;
  for (h = 0; h < 24; h++) for (m = 0; m < 60; m += 15)
    ts.push(('0' + h).slice(-2) + ':' + ('0' + m).slice(-2));
  if (sel && ts.indexOf(sel) < 0){ ts.push(sel); ts.sort(); }   // מועד קיים שאינו על רבע שעה — נשמר
  return ts.map(function(t){
    return '<option value="' + t + '"' + (t === sel ? ' selected' : '') + '>' + t + '</option>';
  }).join('');
}
function dtNextQ(){
  var d = new Date();
  d.setMinutes(d.getMinutes() + ((15 - d.getMinutes() % 15) % 15), 0, 0);
  return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
}
function dtJoin(dId, tId){
  var dv = el(dId).value;
  return dv ? dv + 'T' + (el(tId).value || '10:00') : '';
}
function stDate(i, status){
  var r = el('list')._src[i];
  var agSel = AG_OPTS.length
    ? '<div class="fld"><span>עבור סוכן</span><select id="stAg" onchange="agOther(this)" style="width:100%;padding:12px 13px;' +
      'border:1.5px solid #DCD6C8;border-radius:13px;font-size:14px;font-family:inherit;background:#fff;color:#1E3A5F">' +
      agOpts(AG_OPTS, IS_COORD) +
      '</select></div>'
    : '';
  openSheet('<h3>' + (status === 'meeting' ? 'קביעת פגישה' : 'קביעת פולו-אפ') + '</h3>' +
    '<div style="font-size:12px;color:#8B8F99">' + esc([r.address, r.city].filter(Boolean).join(', ')) + '</div>' +
    agSel +
    '<div class="fld"><span>מועד</span><div style="display:flex;gap:8px">' +
    '<input id="stDtD" type="date" style="flex:1.2;min-width:0;-webkit-appearance:none;appearance:none;display:block;min-height:44px;text-align:right">' +
    '<select id="stDtT" style="flex:1;min-width:0;background:#F5F3EC;border:1px solid #E9E4D8;border-radius:11px;padding:11px 13px;' +
    'font-size:14px;font-weight:700;color:#1E3A5F;font-family:inherit;outline:none">' + dt15Opts(dtNextQ()) + '</select>' +
    '</div></div>' +
    '<div class="fld"><span>הערה</span><textarea id="stNote" rows="2" placeholder="הערה במלל חופשי (אופציונלי)" ' +
    'style="background:#fff;border:1.5px solid #DCD6C8;border-radius:13px;padding:12px 13px;font-size:14px;' +
    'font-family:inherit;outline:none;color:#1E3A5F;width:100%;resize:vertical"></textarea></div>' +
    '<div style="font-size:11.5px;color:#8B8F99">נשמר גם ביומן Google שלך (אם מחובר)</div>' +
    '<button class="btn btn-gold" onclick="stSave(' + i + ',\'' + status + '\')">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function stSave(i, status){
  stSet(i, status, dtJoin('stDtD', 'stDtT'));
}
function stToggleNI(i){
  var r = el('list')._src[i];
  if (r.stat && r.stat.status === 'not_interested'){
    // לחיצה נוספת — מחזירה למצב רגיל (מסיר את הסטטוס)
    POST('/api/newborn/status/delete', {key: r.key}).then(function(j){
      if (!j.ok){ toast('שגיאה בהסרה'); return; }
      toast('הסטטוס הוסר'); load();
    });
  } else stSet(i, 'not_interested', '');
}
function stSet(i, status, date){
  var r = el('list')._src[i];
  if ((status === 'meeting' || status === 'followup') && !date){ toast('בחר מועד'); return; }
  var forAg = (el('stAg') && el('stAg').value) || '';   // מתאמת/מנהל — הפגישה נרשמת על הסוכן הנבחר
  if (forAg === '__more') forAg = '';
  POST('/api/newborn/status', {key: r.key, addr: [r.address, r.city].filter(Boolean).join(', '),
    price: r.price || '', phone: r.phone || '', owner: r.owner || '', status: status, date: date || '',
    agent: forAg, note: (el('stNote') && el('stNote').value.trim()) || ''})
    .then(function(j){
      if (!j.ok){ toast('שגיאה בשמירה'); return; }
      closeSheet();
      toast(status === 'not_interested' ? 'סומן: לא מעוניין' :
        (ST_LABEL[status] + ' נקבע' + (j.calendar ? ' + נשמר ביומן' : '')));
      load();
    });
}
function noteSheet(i){
  var r = el('list')._src[i];
  var prev = (r.unotes || []).map(function(n){
    return '<div class="notes">' + esc(n.name + ': ' + n.text) + '</div>';
  }).join('');
  openSheet('<h3>הערות · ' + esc(r.address || '') + '</h3>' + prev +
    '<div class="fld"><span>הערה חדשה (כולם רואים)</span><textarea id="ntTx" rows="3"></textarea></div>' +
    '<button class="btn btn-blue" onclick="noteSave(' + i + ')">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
}
function noteSave(i){
  var r = el('list')._src[i];
  var tx = el('ntTx').value.trim();
  if (!tx){ toast('כתוב הערה'); return; }
  POST('/api/newborn/note', {key: r.key, addr: r.address || '', text: tx}).then(function(j){
    if (!j.ok){ toast('שגיאה בשמירה'); return; }
    closeSheet(); toast('ההערה נשמרה'); load();
  });
}
function openMeetings(){
  var h = MEETS.map(function(m){
    var d = String(m.date || '').replace('T', ' ');
    return '<div class="mRow">' +
      '<div class="mid"><div class="t">' + esc((m.label || '') + ': ' + (m.addr || '')) + '</div>' +
      '<div class="s">' + esc([d, m.agent, m.owner].filter(Boolean).join(' · ')) + '</div></div>' +
      (m.ophone ? '<a class="sq" style="background:#EAF0FA" href="tel:' + esc(m.ophone.replace(/\D/g, '')) + '">' +
        '<svg width="14" height="14" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#2E6BD6" stroke-width="1.7"/></svg></a>' : '') +
      (m.wa ? '<a class="sq" style="background:#E7F7EE" target="_blank" rel="noopener" href="https://wa.me/' + esc(m.wa) + '">' +
        '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#1FAF5E" stroke-width="1.5"/></svg></a>' : '') +
      '</div>';
  }).join('');
  openSheet('<h3>פגישות ופולו-אפ · ' + MEETS.length + '</h3>' +
    (h || '<div style="text-align:center;color:#8B8F99;font-size:13px;padding:16px 0">אין פגישות או פולו-אפים פתוחים</div>') +
    '<button class="btn btn-sec" onclick="closeSheet()">סגירה</button>');
}

/* זיכרון מצב הטאב — פילטר/חיפוש/גלילה נשמרים וחוזרים בכניסה הבאה */
var _restY = 0;
/* זיכרון גלילה מדויק — אגנוסטי לגולל (החלון או main, לפי הדף/רוחב).
   נשבר בעבר כי נקרא main.scrollTop בזמן שהחלון הוא הגולל. */
var _userScrolled = false, _restoring = false;
function _scrEls(){ var m = document.querySelector('main'); return {win: (document.scrollingElement || document.documentElement), main: m}; }
function _scrY(){
  var e = _scrEls();
  return Math.max(window.pageYOffset || 0, e.win ? e.win.scrollTop : 0, (e.main && e.main.scrollTop) || 0);
}
function _scrTo(y){
  _restoring = true;
  var e = _scrEls();
  try{ window.scrollTo(0, y); }catch(x){}
  if (e.win) e.win.scrollTop = y;
  if (e.main && e.main.scrollHeight > e.main.clientHeight + 2) e.main.scrollTop = y;   // אם main הוא הגולל
  setTimeout(function(){ _restoring = false; }, 80);
}
function saveSt(){
  try{
    localStorage.setItem('v2st:newborn', JSON.stringify({a:AGE, q:el('q').value, y: Math.round(_scrY())}));
  }catch(e){}
}
(function(){
  try{
    var s = JSON.parse(localStorage.getItem('v2st:newborn') || 'null');
    if (s){
      AGE = (typeof s.a === 'number') ? s.a : -1; el('q').value = s.q || ''; _restY = s.y || 0;
      qClearBtn();
    }
  }catch(e){}
})();
var _renderBase = render;
var _restDeadline = Date.now() + 2500;   // חלון שחזור: 2.5ש' מהטעינה — מכסה cache-render + load()
render = function(){
  _renderBase();
  // שחזור סינכרוני מיד אחרי בניית הרשימה (כמו המקור שעבד — הגדרת scroll מאלצת layout).
  // מיושם בכל render בתוך החלון (load עלול לרנדר מחדש ולאפס) עד שהמשתמש גולל;
  // אחרי החלון _restY מתעלם כדי ששינוי פילטר/חיפוש לא יקפיץ למיקום ישן.
  if (_restY && !_userScrolled && Date.now() < _restDeadline) _scrTo(_restY);
};
(function(){
  function onScroll(){
    if (_restoring) return;             // גלילת-שחזור תכנותית — לא לספור כגלילת משתמש
    _userScrolled = true; _restY = 0;
    clearTimeout(window._svt); window._svt = setTimeout(saveSt, 250);
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  var m = document.querySelector('main');
  if (m) m.addEventListener('scroll', onScroll, {passive:true});
  var flush = function(){ if (_userScrolled || !_restY) saveSt(); };
  window.addEventListener('pagehide', flush);
  document.addEventListener('visibilitychange', function(){ if (document.visibilityState === 'hidden') flush(); });
})();

(function(){
  GET('/api/auth/whoami').then(function(j){
    MYNAME = j.name || '';
    if (j.role === 'coordinator' || j.role === 'admin'){
      IS_COORD = j.role === 'coordinator';
      // רשימה קנונית (בלי כפילויות איות) — מתאמת: הסוכנים שלה; מנהל: כל המשרד
      GET('/api/my/agents').then(function(d){
        AG_OPTS = ((d && d.agents) || []).map(function(a){ return a.name; })
          .filter(function(a){ return a && a !== j.name; });
      }).catch(function(){});
    }
    if (!j.ok){ location.replace('/v2'); return; }
    el('avatarTx').textContent = (j.name || ' ').trim()[0] || '';
    MGR = (j.role === 'admin' || j.role === 'coordinator');
    render();
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    document.title = 'נכס נולד · ' + (o.name || '');
  }).catch(function(){});
  load();
  setInterval(load, 60000);   // מונה חי — Realtime מלא כשעוברים ל-Supabase
})();
</script></body></html>'''


# ── טאב הנכסים המאוחד (עיצוב 20a) — משרד / שת"פ / שלי + קונים מתאימים ──────
V2_PROPS_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>נכסים</title>
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
  .brand img{height:36px;max-width:150px;object-fit:contain}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 14px;display:flex;flex-direction:column;gap:12px;overflow:auto}
  .card{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px 13px;
      display:flex;flex-direction:column;gap:11px}
  .hd{display:flex;align-items:center;justify-content:space-between}
  .hd .tt{display:flex;align-items:center;gap:10px}
  .hd .ic{width:36px;height:36px;border-radius:11px;background:#EAF0FA;display:flex;align-items:center;justify-content:center}
  .hd h1{font-size:21px;font-weight:800}
  .mapChip{display:flex;align-items:center;gap:6px;background:#EAF0FA;color:#2E6BD6;border-radius:999px;
      padding:6px 13px;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px}
  .segs .sg{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:9px 0;
      font-size:13px;font-weight:600;color:#8B8F99;border-radius:10px;cursor:pointer;white-space:nowrap}
  .segs .sg b{font-size:11px;font-weight:700}
  .segs .sg.on{color:#fff;font-weight:700;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .segs .sg.on b{background:rgba(255,255,255,.22);padding:1px 8px;border-radius:999px;font-weight:800}
  .srch{display:flex;align-items:center;gap:9px;background:#F5F3EC;border:1px solid #E9E4D8;
      border-radius:13px;padding:0 14px}
  .srch input{flex:1;border:0;background:none;font-size:13.5px;font-family:inherit;outline:none;
      color:#1E3A5F;padding:11px 0}
  .prop{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:8px;margin-bottom:12px}
  .prop.shtaf{background:#F7F5EE;border:1.5px dashed #DCD6C8;box-shadow:none}
  .prop.mine{border:2px solid #C29435;box-shadow:0 6px 20px rgba(194,148,53,.1)}
  .prop .top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  .prop .ad{font-size:15.5px;font-weight:700}
  .prop.shtaf .ad{color:#3D5273}
  .prop .dt{font-size:12.5px;color:#8B8F99}
  .prop .dt b{color:#1E3A5F}
  .chip{font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;white-space:nowrap;flex-shrink:0}
  .chip.office{color:#2E6BD6;background:#EAF0FA}
  .chip.shtaf{color:#8B8F99;background:#EBE8DD}
  .chip.mine{color:#B8902F;background:#F6EEDB}
  .chip.pend{color:#B8902F;background:#F6EEDB;border:1px dashed #C29435}
  .reqRow{display:flex;gap:8px;margin-top:8px}
  .reqRow .rq{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;border-radius:12px;
      padding:10px 0;font-size:12.5px;font-weight:700;border:1.5px solid #DCD6C8;background:#fff;color:#1E3A5F;
      cursor:pointer;font-family:inherit;min-height:40px}
  .reqRow .tr{flex:0 0 42px;width:42px;background:#FBEDED;border:none;border-radius:12px;display:flex;
      align-items:center;justify-content:center;cursor:pointer;min-height:40px}
  .reqRow .dn{flex:1;background:#E7F7EE;border:none;color:#157A43;border-radius:12px;font-size:12.5px;
      font-weight:700;cursor:pointer;font-family:inherit;min-height:40px}
  .prop .pr{font-size:21px;font-weight:800}
  .prop.shtaf .pr{font-size:19px;color:#3D5273}
  .prop .acts{display:flex;gap:8px}
  .prop .a1{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;background:#2E6BD6;color:#fff;
      border-radius:11px;padding:10px 0;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit}
  .prop .a2{flex:1;display:flex;align-items:center;justify-content:center;background:#fff;color:#1E3A5F;
      border:1.5px solid #DCD6C8;border-radius:11px;padding:10px 0;font-size:12.5px;font-weight:700;border-style:solid;cursor:pointer;font-family:inherit}
  .more{display:flex;align-items:center;justify-content:center;padding:12px 0;font-size:13px;font-weight:700;color:#2E6BD6}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .t{font-size:15px;font-weight:800}
  .empty .s{font-size:12.5px;color:#5B6472;line-height:1.6;max-width:260px}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 16px;
      display:none;flex-direction:column;gap:12px;max-height:82vh;overflow:auto}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center;flex-shrink:0}
  #sheet h3{font-size:19px;font-weight:800}
  .btn{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:13px;padding:13px 0;width:100%;
      font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:46px;flex-shrink:0}
  .btn-sec{background:#fff;color:#5B6472;border:1.5px solid #DCD6C8}
  .bRow{background:#fff;border-radius:14px;padding:11px 13px;display:flex;flex-direction:column;gap:6px}
  .bRow .t{font-size:13.5px;font-weight:700}
  .bRow .s{font-size:12px;color:#5B6472;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .bRow .acts{display:flex;gap:8px}
  .bRow .wa{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;background:#E7F7EE;color:#1FAF5E;
      border-radius:10px;padding:8px 0;font-size:12px;font-weight:700;border:0;cursor:pointer;font-family:inherit;text-decoration:none}
  .bRow .tel{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;background:#EAF0FA;color:#2E6BD6;
      border-radius:10px;padding:8px 0;font-size:12px;font-weight:700;text-decoration:none}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  @media (min-width:700px){
    header,main,nav{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
  }
  main{padding-bottom:124px}
</style></head><body>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
    <button class="menuBtn" onclick="location.href='/v2/home'" aria-label="לבית">
      <svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
    </button>
  </header>

  <main>
    <div class="card">
      <div class="hd">
        <div class="tt">
          <div class="ic"><svg width="16" height="16" viewBox="0 0 16 16"><path d="M2 8L8 3l6 5v5a.8.8 0 0 1-.8.8H9.8V10H6.2v3.8H2.8A.8.8 0 0 1 2 13z" fill="none" stroke="#2E6BD6" stroke-width="1.6" stroke-linejoin="round"/></svg></div>
          <h1>נכסים</h1>
        </div>
        <button class="mapChip" onclick="location.href='/v2/map'">
          <svg width="12" height="12" viewBox="0 0 16 16"><path d="M8 14s-5-4.2-5-8a5 5 0 0 1 10 0c0 3.8-5 8-5 8z" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><circle cx="8" cy="6" r="1.8" fill="none" stroke="#2E6BD6" stroke-width="1.6"/></svg>
          מפה
        </button>
      </div>
      <div class="segs" id="modes">
        <div class="sg on" data-m="office" onclick="setMode(this)">המשרד שלנו <b id="cOffice"></b></div>
        <div class="sg" data-m="shtaf" onclick="setMode(this)">שת"פ <b id="cShtaf"></b></div>
        <div class="sg" data-m="mine" onclick="setMode(this)">שלי <b id="cMine"></b></div>
      </div>
      <div class="srch">
        <svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M11 11l3.4 3.4" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>
        <input id="q" placeholder="דירת 4 חדרים בקרית ביאליק עד 2 מיליון" oninput="qChanged();qClearBtn()">
        <button id="qClear" onclick="el('q').value='';qClearBtn();qChanged()" aria-label="ניקוי חיפוש"
          style="display:none;width:26px;height:26px;border-radius:50%;background:#EBE8DD;border:none;flex-shrink:0;align-items:center;justify-content:center;cursor:pointer;padding:0">
          <svg width="10" height="10" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round"/></svg>
        </button>
      </div>
      <div style="font-size:11.5px;color:#8B8F99" id="sumLine"></div>
    </div>
    <div id="list"></div>
  </main>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
function openSheet(html){
  el('sheet').innerHTML = '<div class="grip"></div>' + html;
  el('sheet').style.display = 'flex'; el('ovl').style.display = 'block';
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }
function fmtPrice(p){
  p = String(p || '').trim();
  if (!p) return '';
  if (/^\d+$/.test(p)) p = Number(p).toLocaleString();
  return (/^[\d,.]+$/.test(p) ? '₪' : '') + p;
}

var MODE = 'office', OFFICE = [], SHTAF = [], MINE = [], MINE_MULTI = false, SUM = {office:'', shtaf:''};
var HOT = {};   // property_key → true עבור הנכסים החמים של הסוכן (עד 2)
function toggleHot(i){
  var p = el('list')._src[i]; if (!p) return;
  var hk = String(p.id || p.address || ''); if (!hk) return;
  var on = !HOT[hk];
  if (on){ var c = 0; for (var k in HOT) if (HOT[k]) c++; if (c >= 2){ toast('אפשר לסמן עד 2 נכסים חמים — הסר אחד קודם'); return; } }
  HOT[hk] = on; if (!on) delete HOT[hk]; render();   // אופטימי
  var det = [p.type, p.rooms ? p.rooms + ' חד׳' : '', p.size ? p.size + ' מ"ר' : ''].filter(Boolean).join(' · ');
  POST('/v2/api/hot', {property_key: hk, on: on, title: [p.address, p.city].filter(Boolean).join(', '), details: det, price: String(p.price || ''), description: String(p.desc || '')}).then(function(j){
    if (!j || !j.ok){ if (on) delete HOT[hk]; else HOT[hk] = true; render();
      toast(j && j.reason === 'limit' ? 'אפשר עד 2 נכסים חמים' : 'השמירה נכשלה'); return; }
    toast(on ? 'הנכס סומן כחם — יופיע בבריף' : 'הוסר מהבריף');
  }).catch(function(){ if (on) delete HOT[hk]; else HOT[hk] = true; render(); toast('שגיאה'); });
}
function loadHot(){ GET('/v2/api/hot').then(function(j){ if (j && j.ok && j.keys){ HOT = {}; j.keys.forEach(function(k){ HOT[String(k)] = true; }); render(); } }).catch(function(){}); }

var _loadSeq = 0;
function load(q){
  var seq = ++_loadSeq;   // שומר רצף: תשובה של חיפוש ישן שהגיעה באיחור לא דורסת את החדש
  return Promise.all([
    POST('/api/search/properties', {q: q || '', nosave: true}).catch(function(){ return {}; }),
    POST('/api/search/exclusives', {q: q || '', nosave: true}).catch(function(){ return {}; }),
    GET('/api/my/properties').catch(function(){ return {}; })
  ]).then(function(rs){
    if (seq !== _loadSeq) return;   // כבר יצא חיפוש חדש יותר — מתעלמים מהתשובה הישנה
    OFFICE = (rs[0] && rs[0].results) || [];
    SUM.office = (rs[0] && rs[0].summary) || '';
    SHTAF = (rs[1] && rs[1].results) || [];
    SUM.shtaf = (rs[1] && rs[1].summary) || '';
    MINE = (rs[2] && rs[2].results) || [];
    MINE_MULTI = !!(rs[2] && rs[2].multi);   // מתאמת/מנהל/צוות — "שלי" מכיל כמה סוכנים
    if (!q) try{ localStorage.setItem('v2c:props', JSON.stringify(
      {o: OFFICE.slice(0, 80), so: SUM.office, s: SHTAF.slice(0, 60), ss: SUM.shtaf, m: MINE.slice(0, 60), mm: MINE_MULTI})); }catch(e){}
    render();
    loadHot();   // טעינת הנכסים החמים של הסוכן (מצב הכפתורים)
  });
}
(function(){
  try{
    var c = JSON.parse(localStorage.getItem('v2c:props') || 'null');
    if (c && c.o){ OFFICE = c.o; SUM.office = c.so || ''; SHTAF = c.s || []; SUM.shtaf = c.ss || ''; MINE = c.m || []; MINE_MULTI = !!c.mm; }
  }catch(e){}
})();
function render(){
  el('cOffice').textContent = OFFICE.length;
  el('cShtaf').textContent = SHTAF.length;
  el('cMine').textContent = MINE.length;
  var q = el('q').value.trim().toLowerCase();
  var src, h = '';
  if (MODE === 'office') src = OFFICE;
  else if (MODE === 'shtaf') src = SHTAF.filter(function(s){   // נכס שקיים גם במשרד — מציגים רק את של המשרד
    var sk = pStreetKey(s.street || s.address), sp = pPriceNum(s.price);
    if (!sk) return true;
    return !OFFICE.some(function(o){
      var ok = pStreetKey(o.address || o.street);
      return ok && ok === sk && Math.abs(pPriceNum(o.price) - sp) <= 100000;
    });
  });
  else src = MINE.filter(function(p){
    return !q || ((p.address || '') + ' ' + (p.city || '') + ' ' + (p.desc || '')).toLowerCase().indexOf(q) >= 0;
  });
  el('sumLine').textContent = (MODE === 'office' ? SUM.office : MODE === 'shtaf' ? SUM.shtaf : '') || '';
  src.slice(0, 40).forEach(function(p, i){ h += propCard(p, i); });
  if (src.length > 40) h += '<div class="more">מוצגים 40 מתוך ' + src.length + ' — חדד את החיפוש</div>';
  el('list').innerHTML = h ||
    '<div class="card empty"><div class="ic"><svg width="28" height="28" viewBox="0 0 16 16"><path d="M2 8L8 3l6 5v5a.8.8 0 0 1-.8.8H9.8V10H6.2v3.8H2.8A.8.8 0 0 1 2 13z" fill="none" stroke="#C29435" stroke-width="1.4" stroke-linejoin="round"/></svg></div>' +
    '<div class="t">' + (MODE === 'mine' ? 'אין לך נכסים פעילים' : 'לא נמצאו נכסים') + '</div>' +
    '<div class="s">' + (MODE === 'mine' ? 'נכסים שמשויכים אליך בגיליון המשרד יופיעו כאן' : 'נסה ניסוח אחר — החיפוש מבין תקציב, חדרים ואזור') + '</div></div>';
  el('list')._src = src;
}
function propCard(p, i){
  var isShtaf = MODE === 'shtaf';
  var isMine = MODE === 'mine';
  var dt = isShtaf ? (p.desc || p.dest || '')
    : [p.type, p.rooms ? p.rooms + ' חד׳' : '', p.floor ? 'קומה ' + p.floor : '',
       p.size ? p.size + ' מ"ר' : ''].filter(Boolean).join(' · ');
  // מתאמת/מנהל רואים את שם הסוכן של כל נכס; סוכן רגיל — "שלך"
  var whoRaw = isShtaf ? (p.office || 'משרד שותף')
    : (isMine ? ((MINE_MULTI && p.agent) ? p.agent : 'שלך') : (p.agent || ''));
  var sameNet = isShtaf && whoRaw.indexOf('רימקס') >= 0;   // אותה רשת — הדגשה בנייבי (network מ-offices בהמשך)
  var who = sameNet ? '<b>' + esc(whoRaw) + '</b>' : esc(whoRaw);
  var where = isShtaf ? [p.street || p.address, p.city].filter(Boolean).join(', ')
                      : [p.address, p.neighborhood, p.city].filter(Boolean).join(', ');
  var chip = isShtaf ? '<div class="chip shtaf">שת"פ</div>'
    : isMine ? (p.pending ? '<div class="chip pend">בטיפול אצל המזכירה</div>' : '<div class="chip mine">הנכס שלי</div>')
    : '<div class="chip office">המשרד שלנו</div>';
  var acts = isShtaf
    ? '<div class="acts"><button class="a1" onclick="matchBuyers(' + i + ')">' +
      '<svg width="12" height="12" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#fff" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>' +
      'קונים מתאימים</button>' +
      (p.link ? '<button class="a2" onclick="window.open(\'' + esc(p.link) + '\',\'_blank\')">למודעה</button>' : '') + '</div>'
    :
    '<div class="acts"><button class="a1" onclick="matchBuyers(' + i + ')">' +
    '<svg width="12" height="12" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#fff" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>' +
    'קונים מתאימים</button>' +
    '<button class="a2" onclick="propDetails(' + i + ')">פרטי הנכס</button></div>' +
    // בקשות למזכירה — עדכון מחיר / הסרת מודעה (רק בנכס שלי, עם מספר מודעה)
    (isMine && p.own && p.id ? (p.pending
      ? '<div class="reqRow"><button class="dn" onclick="doneListing(' + i + ')">הטיפול בוצע — הסר את הסימון</button></div>'
      : '<div class="reqRow"><button class="rq" onclick="reqPrice(' + i + ')">' +
        '<svg width="13" height="13" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#1E3A5F" stroke-width="1.6" stroke-linejoin="round"/></svg>' +
        'עדכן מחיר</button>' +
        '<button class="tr" onclick="reqRemove(' + i + ')" aria-label="בקשת הסרת מודעה">' +
        '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.6a1 1 0 0 0 1 .9h3.6a1 1 0 0 0 1-.9l.7-8.6M6.7 7v4M9.3 7v4" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>') : '');
  // כפתור "נכס חם" — רק בנכסי הסוכן ("שלי"). סימון עד 2 → רצים בבריף הבוקר הכלל-משרדי.
  var _hk = String(p.id || p.address || '');
  var _hot = !!HOT[_hk];
  var hotRow = isMine ? ('<div style="margin-top:8px"><button onclick="toggleHot(' + i + ')" ' +
    'style="width:100%;padding:11px 0;border-radius:12px;font-size:14px;font-weight:800;font-family:inherit;' +
    'cursor:pointer;border:' + (_hot ? 'none' : '1.5px solid #C29435') + ';background:' + (_hot ? '#C29435' : '#fff') +
    ';color:' + (_hot ? '#fff' : '#C29435') + '">' + (_hot ? 'נכס חם · בבריף' : 'סמן כנכס חם') + '</button></div>') : '';
  return '<div class="prop' + (isShtaf ? ' shtaf' : isMine ? ' mine' : '') + '">' +
    '<div class="top"><div><div class="ad">' + esc(where) + '</div>' +
    '<div class="dt">' + [esc(dt), who].filter(Boolean).join(' · ') + '</div></div>' + chip + '</div>' +
    '<div style="display:flex;align-items:center;justify-content:space-between">' +
    '<div class="pr">' + esc(fmtPrice(p.price)) + '</div>' +
    (p.score != null ? '<div style="font-size:11.5px;font-weight:700;color:' + (p.score >= 90 ? '#157A43' : '#B8902F') + '">' + p.score + '% התאמה</div>' : '') +
    '</div>' + acts + hotRow + '</div>';
}
function setMode(node){
  MODE = node.getAttribute('data-m');
  var sgs = node.parentNode.children;
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i] === node);
  render();
}
var _qT = null;
function qChanged(){
  clearTimeout(_qT);
  if (MODE === 'mine'){ render(); return; }
  _qT = setTimeout(function(){ load(el('q').value.trim()); }, 500);
}
function qClearBtn(){ var b = el('qClear'); if (b) b.style.display = el('q').value ? 'flex' : 'none'; }
function pStreetKey(s){
  var m = /([א-ת"'\.\- ]+?\s?\d+[א-ת]?)/.exec(String(s || ''));
  return (m ? m[1] : String(s || '')).replace(/[^א-ת0-9]/g, '');
}
function pPriceNum(p){
  var n = parseInt(String(p || '').replace(/[^0-9]/g, ''), 10);
  return isNaN(n) ? 0 : n;
}
function propText(p){
  return [p.type, p.rooms ? p.rooms + ' חדרים' : '', p.address, p.city,
          p.price ? 'עד ' + p.price : ''].filter(Boolean).join(' ');
}
function matchBuyers(i){
  var p = el('list')._src[i];
  openSheet('<h3>קונים מתאימים</h3>' +
    '<div style="font-size:12px;color:#8B8F99">' + esc([p.address || p.street, p.city].filter(Boolean).join(', ')) + '</div>' +
    '<div id="bRes" style="display:flex;flex-direction:column;gap:10px">' +
    '<div style="text-align:center;color:#8B8F99;font-size:13px;padding:16px 0">מחפש בקונים השמורים…</div></div>' +
    '<button class="btn btn-sec" onclick="closeSheet()">סגירה</button>');
  // חיפוש בקונים השמורים בלבד (לא בשיחות) — בהיקף של המשתמש (סוכן=שלו)
  GET('/api/my/buyers').then(function(j){
    var price = parseInt(String(p.price || '').replace(/[^0-9]/g, ''), 10) || 0;
    var city = String(p.city || '').replace('קריית', 'קרית').trim();
    var rooms = String(p.rooms || '').trim();
    var scored = ((j && j.results) || []).map(function(b){
      var sc = 0, why = [];
      var bud = parseInt(String(b.budget || '').replace(/[^0-9]/g, ''), 10) || 0;
      var tx = ((b.search || '') + ' ' + (b.summary || '')).replace(/קריית/g, 'קרית');
      if (price && bud && bud >= price * 0.85){ sc += 2; why.push('תקציב מתאים'); }
      if (city && tx.indexOf(city) >= 0){ sc += 2; why.push('אזור'); }
      if (rooms && new RegExp('(^|[^0-9])' + rooms + "\\s*חד").test(tx)){ sc += 1; why.push('חדרים'); }
      return {b: b, sc: sc, why: why};
    }).filter(function(x){ return x.sc > 0; }).sort(function(a, c){ return c.sc - a.sc; });
    var h = scored.slice(0, 10).map(function(x){
      var b = x.b;
      return '<div class="bRow"><div class="t">' + esc(b.name || b.phone || '') +
        (b.phone && b.name ? ' · ' + esc(b.phone) : '') +
        (b.budget ? ' · ' + esc(b.budget) : '') + '</div>' +
        '<div class="s" style="color:#157A43;font-weight:700">' + esc(x.why.join(' · ')) + '</div>' +
        (b.summary || b.search ? '<div class="s">' + esc((b.search || b.summary).slice(0, 120)) + '</div>' : '') +
        '<div class="acts">' +
        (b.wa ? '<a class="wa" target="_blank" rel="noopener" href="https://wa.me/' + esc(b.wa) + '">וואטסאפ</a>' : '') +
        (b.tel ? '<a class="tel" href="tel:' + esc(b.tel) + '">חייג</a>' : '') + '</div></div>';
    }).join('');
    el('bRes').innerHTML = h ||
      '<div style="text-align:center;color:#8B8F99;font-size:13px;padding:12px 0">אין קונים שמורים שמתאימים לנכס הזה</div>';
  }).catch(function(){});
}
function propDetails(i){
  var p = el('list')._src[i];
  openSheet('<h3>' + esc([p.address, p.city].filter(Boolean).join(', ')) + '</h3>' +
    '<div style="font-size:13px;color:#5B6472">' +
    esc([p.type, p.rooms ? p.rooms + ' חד׳' : '', p.floor ? 'קומה ' + p.floor : '', p.size ? p.size + ' מ"ר' : '',
         p.agent].filter(Boolean).join(' · ')) + '</div>' +
    '<div style="font-size:22px;font-weight:800">' + esc(fmtPrice(p.price)) + '</div>' +
    (p.desc ? '<div style="background:#fff;border-radius:13px;padding:13px 15px;font-size:13px;color:#5B6472;line-height:1.7">' + esc(p.desc) + '</div>' : '') +
    (p.wa ? '<a class="btn" style="background:#1FAF5E;color:#fff;text-decoration:none;box-shadow:0 4px 12px rgba(31,175,94,.25)" target="_blank" rel="noopener" href="https://wa.me/' + esc(p.wa) + '">וואטסאפ לסוכן המטפל</a>' : '') +
    '<button class="btn btn-sec" onclick="closeSheet()">סגירה</button>');
}

/* בקשות למזכירה — עדכון מחיר / הסרת מודעה (זהה לזרימה באפליקציה הקיימת: requestchange) */
function reqPrice(i){
  var p = el('list')._src[i]; if (!p) return;
  openSheet('<h3>עדכון מחיר</h3>' +
    '<div style="font-size:12.5px;color:#8B8F99">' + esc([p.address, p.city].filter(Boolean).join(', ')) +
    ' · מחיר נוכחי: ' + esc(fmtPrice(p.price)) + '</div>' +
    '<input id="npr" type="text" inputmode="numeric" placeholder="המחיר החדש" style="width:100%;padding:13px 14px;' +
    'border:1.5px solid #DCD6C8;border-radius:13px;font-size:15px;font-family:inherit;outline:none;background:#fff">' +
    '<button class="btn" style="background:#2E6BD6;color:#fff;box-shadow:0 4px 12px rgba(46,107,214,.25)" ' +
    'onclick="sendPrice(' + i + ')">שלח בקשה למזכירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
  setTimeout(function(){ var n = el('npr'); if (n) n.focus(); }, 150);
}
function sendPrice(i){
  var p = el('list')._src[i]; if (!p) return;
  var np = (el('npr') && el('npr').value || '').trim();
  if (!np){ toast('כתוב את המחיר החדש'); return; }
  POST('/api/listing/request', {kind:'price', id: p.id, address: p.address || '', new_price: np}).then(function(j){
    if (!j.ok){ toast('השליחה נכשלה'); return; }
    closeSheet(); toast('הבקשה נשלחה למזכירה'); load(el('q').value.trim());
  });
}
function reqRemove(i){
  var p = el('list')._src[i]; if (!p) return;
  if (!confirm('לשלוח בקשה למזכירה להסיר את המודעה?\n' + [p.address, p.city].filter(Boolean).join(', '))) return;
  POST('/api/listing/request', {kind:'remove', id: p.id, address: p.address || ''}).then(function(j){
    if (!j.ok){ toast('השליחה נכשלה'); return; }
    toast('הבקשה נשלחה למזכירה'); load(el('q').value.trim());
  });
}
function doneListing(i){
  var p = el('list')._src[i]; if (!p) return;
  if (!confirm('לסמן שהטיפול בוצע? הנכס לא יסומן יותר כ"בטיפול אצל המזכירה".')) return;
  POST('/api/listing/done', {id: p.id}).then(function(j){
    if (!j.ok){ toast('שגיאה'); return; }
    toast('הסימון הוסר'); load(el('q').value.trim());
  });
}

/* זיכרון מצב הטאב */
var _restY = 0;
function saveSt(){
  try{
    var m = document.querySelector('main');
    localStorage.setItem('v2st:props', JSON.stringify({m:MODE, q:el('q').value, y:(m ? m.scrollTop : 0)}));
  }catch(e){}
}
(function(){
  try{
    var s = JSON.parse(localStorage.getItem('v2st:props') || 'null');
    if (s){
      MODE = s.m || MODE; el('q').value = s.q || ''; _restY = s.y || 0;
      var sg = document.querySelector('#modes .sg[data-m="' + MODE + '"]');
      if (sg){ var cs = sg.parentNode.children;
        for (var i = 0; i < cs.length; i++) cs[i].classList.toggle('on', cs[i] === sg); }
    }
  }catch(e){}
})();
var _renderBase = render;
render = function(){
  _renderBase();
  qClearBtn();
  if (_restY){
    var m = document.querySelector('main');
    if (m){ m.scrollTop = _restY; if (m.scrollTop >= _restY - 4) _restY = 0; }
  }
  if (!_restY) saveSt();
};
(function(){
  var m = document.querySelector('main');
  if (m) m.addEventListener('scroll', function(){
    if (window._svScrolled) _restY = 0; window._svScrolled = true;
    clearTimeout(window._svt); window._svt = setTimeout(saveSt, 300);
  }, {passive:true});
  window.addEventListener('pagehide', function(){ if (!_restY) saveSt(); });
})();

(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    el('avatarTx').textContent = (j.name || ' ').trim()[0] || '';
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    document.title = 'נכסים · ' + (o.name || '');
  }).catch(function(){});
  if (location.search.indexOf('mine=1') >= 0){
    MODE = 'mine';
    var sg = document.querySelector('#modes .sg[data-m="mine"]');
    if (sg){ var cs = sg.parentNode.children;
      for (var i = 0; i < cs.length; i++) cs[i].classList.toggle('on', cs[i] === sg); }
  }
  load(el('q').value.trim());
})();
</script></body></html>'''


# ── מפת הנכסים (עיצוב 21a) — Leaflet, קלאסטרים נייבי, פיני מחיר, כרטיס צף ──
V2_MAP_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>מפה</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;height:100vh;height:100dvh;overflow:hidden;color:#1E3A5F}
  #map{position:absolute;inset:0}
  .topBar{position:absolute;top:calc(env(safe-area-inset-top,0px) + 10px);left:14px;right:14px;z-index:500;
      display:flex;flex-direction:column;gap:8px}
  .row1{display:flex;gap:8px;align-items:center}
  .backBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 4px 14px rgba(30,58,95,.18);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer;flex-shrink:0}
  .srch{flex:1;display:flex;align-items:center;gap:9px;background:#fff;border-radius:14px;
      box-shadow:0 4px 14px rgba(30,58,95,.18);padding:0 14px}
  .srch input{flex:1;border:0;background:none;font-size:13.5px;font-family:inherit;outline:none;
      color:#1E3A5F;padding:12px 0}
  .filters{display:flex;gap:7px}
  .fchip{display:flex;align-items:center;gap:6px;background:#fff;border-radius:999px;padding:7px 14px;
      font-size:12.5px;font-weight:700;color:#5B6472;box-shadow:0 4px 14px rgba(30,58,95,.14);
      border:0;cursor:pointer;font-family:inherit}
  .fchip.on{background:#1E3A5F;color:#fff}
  .fchip.on.coop{background:#2E6BD6}
  .locBtn{position:absolute;bottom:calc(env(safe-area-inset-bottom,0px) + 170px);left:16px;z-index:500;
      width:48px;height:48px;border-radius:50%;background:#fff;box-shadow:0 6px 18px rgba(30,58,95,.22);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  /* פיני מחיר */
  .pin{background:#1E3A5F;color:#fff;border-radius:999px;padding:4px 10px;font-size:11.5px;font-weight:800;
      font-family:'Heebo',sans-serif;box-shadow:0 3px 10px rgba(30,58,95,.35);white-space:nowrap;
      border:2px solid #fff;direction:ltr}
  .pin.coop{background:#2E6BD6}
  .pin.sel{background:#C29435;box-shadow:0 4px 14px rgba(194,148,53,.5)}
  .marker-cluster{background:rgba(30,58,95,.25)!important;border-radius:50%!important}
  .marker-cluster div{background:#1E3A5F!important;color:#fff!important;font-family:'Heebo',sans-serif!important;
      font-weight:800!important;border-radius:50%!important}
  /* כרטיס נכס צף */
  #propCard{position:absolute;bottom:calc(env(safe-area-inset-bottom,0px) + 16px);left:14px;right:14px;z-index:600;
      background:#fff;border-radius:20px;box-shadow:0 12px 36px rgba(14,29,51,.3);padding:15px 18px;
      display:none;flex-direction:column;gap:8px}
  #propCard .top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  #propCard .ad{font-size:15.5px;font-weight:800}
  #propCard .dt{font-size:12.5px;color:#8B8F99}
  #propCard .x{width:30px;height:30px;border-radius:50%;background:#F5F3EC;display:flex;align-items:center;
      justify-content:center;border:0;cursor:pointer;flex-shrink:0}
  .feats{display:flex;gap:6px;flex-wrap:wrap}
  .feat{font-size:11px;font-weight:700;color:#5B6472;background:#F0EDE3;padding:3px 9px;border-radius:999px}
  #propCard .pr{display:flex;align-items:baseline;gap:8px}
  #propCard .pr b{font-size:20px;font-weight:800}
  #propCard .pr span{font-size:11.5px;color:#8B8F99}
  #propCard .cta{display:flex;align-items:center;justify-content:center;background:#2E6BD6;color:#fff;
      border-radius:12px;padding:11px 0;font-size:13.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(46,107,214,.25)}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:800;white-space:nowrap}
  @media (min-width:700px){
    .topBar,#propCard{max-width:600px;margin-left:auto;margin-right:auto}
  }
</style></head><body>

  <div id="map"></div>
  <div class="topBar">
    <div class="row1">
      <button class="backBtn" onclick="location.href='/v2/props'" aria-label="חזרה">
        <svg width="15" height="15" viewBox="0 0 14 14"><path d="M5 2L10 7l-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <div class="srch">
        <svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M11 11l3.4 3.4" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>
        <input id="q" placeholder="רחוב או עיר" oninput="qChanged()">
      </div>
    </div>
    <div class="filters">
      <button class="fchip on" id="fOffice" onclick="toggleF('office')">המשרד <span id="nOffice"></span></button>
      <button class="fchip coop" id="fCoop" onclick="toggleF('coop')">שת"פ <span id="nCoop"></span></button>
    </div>
  </div>
  <button class="locBtn" onclick="myLoc()" aria-label="המיקום שלי">
    <svg width="20" height="20" viewBox="0 0 22 22"><circle cx="11" cy="11" r="3" fill="none" stroke="#2E6BD6" stroke-width="1.8"/><circle cx="11" cy="11" r="7.5" fill="none" stroke="#2E6BD6" stroke-width="1.8"/><path d="M11 1v3M11 18v3M1 11h3M18 11h3" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round"/></svg>
  </button>

  <div id="propCard">
    <div class="top"><div><div class="ad" id="pcAd"></div><div class="dt" id="pcDt"></div></div>
      <button class="x" onclick="hideCard()"><svg width="11" height="11" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round"/></svg></button></div>
    <div class="feats" id="pcFeats"></div>
    <div class="pr"><b id="pcPr"></b><span id="pcSqm"></span></div>
    <button class="cta" id="pcCta">לכרטיס הנכס</button>
  </div>
  <div id="toast"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
function priceNum(p){
  var n = parseInt(String(p || '').replace(/[^\d]/g, ''), 10);
  return isNaN(n) ? 0 : n;
}
function priceShort(p){
  var n = priceNum(p);
  if (!n) return '—';
  return n >= 1000000 ? (n / 1000000).toFixed(n % 1000000 ? 2 : 0).replace(/\.?0+$/, '') + 'M'
       : Math.round(n / 1000) + 'K';
}

var MAP, CLUSTER, ITEMS = [], MARKERS = [], SEL = null;
var SHOW = {office: true, coop: true};

MAP = L.map('map', {zoomControl: false}).setView([32.83, 35.08], 12);   // הקריות
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(MAP);
CLUSTER = L.markerClusterGroup({maxClusterRadius: 46, showCoverageOnHover: false});
MAP.addLayer(CLUSTER);
// סיכות המשרדים (זהב, תמיד מעל הקלאסטרים): מוצקין — שושנה דמארי 4; ביאליק (אפק) — יגאל בשן 2
[[32.85042, 35.08606, 'המשרד · מוצקין'], [32.85012, 35.10338, 'המשרד · ביאליק']].forEach(function(o){
  L.marker([o[0], o[1]], {zIndexOffset: 1000, icon: L.divIcon({className: '',
    html: '<div class="pin sel" style="background:#C29435">' + o[2] + '</div>', iconSize: null, iconAnchor: [40, 14]})}).addTo(MAP);
});

function pinIcon(it, sel){
  return L.divIcon({className: '', html: '<div class="pin' + (it.t === 'coop' ? ' coop' : '') +
    (sel ? ' sel' : '') + '">₪' + priceShort(it.p) + '</div>', iconSize: null, iconAnchor: [24, 14]});
}
function render(){
  CLUSTER.clearLayers();
  MARKERS = [];
  var q = el('q').value.trim().toLowerCase();
  var counts = {office: 0, coop: 0};
  ITEMS.forEach(function(it, idx){
    counts[it.t] = (counts[it.t] || 0) + 1;
    if (!SHOW[it.t]) return;
    if (q && ((it.a || '') + ' ' + (it.c || '')).toLowerCase().indexOf(q) < 0) return;
    var mk = L.marker([it.lat, it.lng], {icon: pinIcon(it, SEL === idx)});
    mk.on('click', function(){ selectItem(idx, mk); });
    mk._idx = idx;
    CLUSTER.addLayer(mk);
    MARKERS.push(mk);
  });
  el('nOffice').textContent = counts.office || '';
  el('nCoop').textContent = counts.coop || '';
}
function selectItem(idx, mk){
  SEL = idx;
  MARKERS.forEach(function(m){ m.setIcon(pinIcon(ITEMS[m._idx], m._idx === idx)); });
  var it = ITEMS[idx];
  el('pcAd').textContent = [it.a, it.c].filter(Boolean).join(', ');
  el('pcDt').textContent = [it.t === 'coop' ? (it.g || 'משרד שותף') : '',
    it.r ? it.r + ' חד׳' : '', it.fl ? 'קומה ' + it.fl : '', it.z ? it.z + ' מ"ר' : '',
    it.t === 'office' ? it.g : ''].filter(Boolean).join(' · ');
  // צ'יפי מאפיינים מהתיאור
  var d = (it.d || '');
  var feats = [];
  [['מעלית','מעלית'],['חניה','חניה'],['מרפסת','מרפסת'],['ממ"ד','ממ"ד'],['ממ״ד','ממ"ד']].forEach(function(f){
    if (d.indexOf(f[0]) >= 0 && feats.indexOf(f[1]) < 0) feats.push(f[1]);
  });
  el('pcFeats').innerHTML = feats.map(function(f){ return '<span class="feat">' + esc(f) + '</span>'; }).join('');
  el('pcFeats').style.display = feats.length ? 'flex' : 'none';
  var n = priceNum(it.p), sq = parseInt(it.z, 10);
  el('pcPr').textContent = n ? '₪' + n.toLocaleString() : (it.p || '');
  el('pcSqm').textContent = (n && sq) ? '₪' + Math.round(n / sq).toLocaleString() + ' למ"ר' : '';
  el('pcCta').onclick = function(){
    try{ localStorage.setItem('v2st:props', JSON.stringify(
      {m: it.t === 'coop' ? 'shtaf' : 'office', q: it.a || '', y: 0})); }catch(e){}
    location.href = '/v2/props';
  };
  el('propCard').style.display = 'flex';
}
function hideCard(){
  el('propCard').style.display = 'none';
  var old = SEL; SEL = null;
  MARKERS.forEach(function(m){ if (m._idx === old) m.setIcon(pinIcon(ITEMS[old], false)); });
}
function toggleF(t){
  SHOW[t] = !SHOW[t];
  el(t === 'office' ? 'fOffice' : 'fCoop').classList.toggle('on', SHOW[t]);
  hideCard(); render();
}
var _qT = null;
function qChanged(){ clearTimeout(_qT); _qT = setTimeout(render, 300); }
function myLoc(){
  if (!navigator.geolocation){ toast('אין הרשאת מיקום'); return; }
  navigator.geolocation.getCurrentPosition(function(pos){
    var ll = [pos.coords.latitude, pos.coords.longitude];
    MAP.setView(ll, 15);
    L.circleMarker(ll, {radius: 8, color: '#2E6BD6', fillColor: '#2E6BD6', fillOpacity: .9,
      weight: 3, opacity: .35}).addTo(MAP);
  }, function(){ toast('לא הצלחנו לאתר את המיקום'); });
}
/* מיקוד על האזור עם רוב הנכסים: חציון → 80% הקרובים אליו — נכס חריג רחוק לא מרחיק את הזום */
function focusDense(){
  var pts = ITEMS.filter(function(it){ return it.lat && it.lng; });
  if (!pts.length) return;
  var lats = pts.map(function(x){ return x.lat; }).sort(function(a, b){ return a - b; });
  var lngs = pts.map(function(x){ return x.lng; }).sort(function(a, b){ return a - b; });
  var cLat = lats[Math.floor(lats.length / 2)], cLng = lngs[Math.floor(lngs.length / 2)];
  var byDist = pts.slice().sort(function(a, b){
    return (Math.pow(a.lat - cLat, 2) + Math.pow(a.lng - cLng, 2)) -
           (Math.pow(b.lat - cLat, 2) + Math.pow(b.lng - cLng, 2));
  });
  var core = byDist.slice(0, Math.max(3, Math.ceil(byDist.length * 0.8)));
  var b = L.latLngBounds(core.map(function(it){ return [it.lat, it.lng]; }));
  MAP.fitBounds(b, {padding: [46, 46], maxZoom: 15});
}
(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
  }).catch(function(){ location.replace('/v2'); });
  GET('/api/map/properties').then(function(j){
    ITEMS = (j && j.items) || [];
    render();
    focusDense();
  }).catch(function(){ toast('שגיאה בטעינת הנכסים'); });
})();
</script></body></html>'''


# ── תהליכים ועסקאות (עיצוב 22a + טפסים 24a/27a) — על /api/deals הקיים ────────
V2_DEALS_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>תהליכים ועסקאות</title>
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
  .brand img{height:36px;max-width:150px;object-fit:contain}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 124px;display:flex;flex-direction:column;gap:12px;overflow:auto}
  .card{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px 13px;
      display:flex;flex-direction:column;gap:11px}
  .hd{display:flex;align-items:center;justify-content:space-between}
  .hd .tt{display:flex;align-items:center;gap:10px}
  .hd .ic{width:36px;height:36px;border-radius:11px;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .hd h1{font-size:21px;font-weight:800}
  .cnt{font-size:13px;font-weight:700;color:#B8902F;background:#F6EEDB;padding:4px 11px;border-radius:999px}
  .ctaRow{display:flex;gap:10px}
  .ctaRow .b1{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;background:#2E6BD6;color:#fff;
      border-radius:14px;padding:13px 0;font-size:14px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .ctaRow .b2{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;background:#fff;color:#1E3A5F;
      border:1.5px solid #DCD6C8;border-radius:14px;padding:13px 0;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit}
  .srch{display:flex;align-items:center;gap:9px;background:#F5F3EC;border:1px solid #E9E4D8;
      border-radius:13px;padding:0 14px}
  .srch input{flex:1;border:0;background:none;font-size:13.5px;font-family:inherit;outline:none;
      color:#1E3A5F;padding:11px 0}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px}
  .segs .sg{flex:1;text-align:center;padding:7px 0;font-size:12.5px;font-weight:700;color:#5B6472;
      border-radius:10px;cursor:pointer}
  .segs .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .deal{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:9px;margin-bottom:12px;border:2px solid transparent}
  .deal.closed{border-color:#1FAF5E}
  .deal .top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  .deal .ad{font-size:15.5px;font-weight:700}
  .deal .sb{font-size:12.5px;color:#8B8F99}
  .chip{font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:999px;white-space:nowrap;flex-shrink:0}
  .chip.stage{color:#B8902F;background:#F6EEDB}
  .chip.open{color:#2E6BD6;background:#EAF0FA}
  .chip.closed{color:#1FAF5E;background:#E7F7EE}
  .deal .pr{font-size:20px;font-weight:800}
  .deal .pr s{color:#9AA0AB;font-weight:600;font-size:14px;margin-right:8px}
  .deal .acts{display:flex;gap:8px;align-items:center}
  .deal .gold{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;background:#C29435;color:#fff;
      border-radius:11px;padding:10px 0;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(194,148,53,.25)}
  .deal .sec{flex:1;display:flex;align-items:center;justify-content:center;background:#fff;color:#1E3A5F;
      border:1.5px solid #DCD6C8;border-radius:11px;padding:10px 0;font-size:12.5px;font-weight:700;cursor:pointer;font-family:inherit}
  .trash{width:42px;height:42px;border-radius:11px;background:#FBEDED;border:0;cursor:pointer;
      display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .t{font-size:15px;font-weight:800}
  .empty .s{font-size:12.5px;color:#5B6472;line-height:1.6;max-width:260px}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;
      padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);top:70px;z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);display:none;flex-direction:column;overflow:hidden}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center;margin:10px 0 2px;flex-shrink:0}
  #sheet .body{flex:1;overflow:auto;padding:8px 18px 14px;display:flex;flex-direction:column;gap:12px}
  #sheet .foot{background:#fff;border-top:1px solid #F0EDE3;padding:12px 18px 14px;
      display:flex;gap:10px;flex-shrink:0}
  #sheet h3{font-size:19px;font-weight:800}
  .sec2{background:#fff;border-radius:18px;box-shadow:0 4px 14px rgba(30,58,95,.05);padding:14px 16px;
      display:flex;flex-direction:column;gap:11px}
  .sec2 .st{font-size:12px;font-weight:800;color:#B8902F;letter-spacing:.06em}
  .fld{display:flex;flex-direction:column;gap:5px;flex:1;min-width:0}
  .fld span{font-size:11.5px;font-weight:700;color:#5B6472}
  .fld input,.fld select{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:11px;padding:10px 13px;
      font-size:13.5px;font-weight:700;color:#1E3A5F;font-family:inherit;outline:none;width:100%;
      appearance:none;-webkit-appearance:none}
  .fld input.gold{background:#F6EEDB;border-color:#E4C56B;color:#B8902F;font-size:15px;font-weight:800}
  .frow{display:flex;gap:9px}
  .btnMain{flex:1.6;display:flex;align-items:center;justify-content:center;background:#2E6BD6;color:#fff;
      border-radius:13px;padding:13px 0;font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .btnMain.gold{background:#C29435;box-shadow:0 4px 12px rgba(194,148,53,.25)}
  .btnSec{flex:1;display:flex;align-items:center;justify-content:center;background:#fff;color:#5B6472;
      border:1.5px solid #DCD6C8;border-radius:13px;padding:13px 0;font-size:14.5px;font-weight:700;cursor:pointer;font-family:inherit}
  .comRow{display:flex;align-items:center;gap:9px}
  .comRow .pencil{width:40px;height:40px;border-radius:11px;background:#F6EEDB;border:0;cursor:pointer;
      display:flex;align-items:center;justify-content:center;flex-shrink:0}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  @media (min-width:700px){
    header,main,nav{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
  }
</style></head><body>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
    <button class="menuBtn" onclick="location.href='/v2/home'" aria-label="לבית">
      <svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
    </button>
  </header>

  <main>
    <div class="card">
      <div class="hd">
        <div class="tt">
          <div class="ic"><svg width="16" height="16" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#B8902F" stroke-width="1.6"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#B8902F" stroke-width="1.6" stroke-linecap="round"/></svg></div>
          <h1>תהליכים ועסקאות</h1>
          <span style="font-size:11px;font-weight:700;color:#8B8F99;align-self:flex-start;margin-top:2px">בס"ד</span>
        </div>
        <div class="cnt" id="cnt">—</div>
      </div>
      <div class="ctaRow">
        <button class="b1" onclick="openForm(null, false)">
          <svg width="12" height="12" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>
          תהליך חדש
        </button>
        <button class="b2" onclick="openForm(null, true)">+ עסקה</button>
      </div>
      <div class="srch">
        <svg width="15" height="15" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M11 11l3.4 3.4" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>
        <input id="q" placeholder="כתובת, סוכן או עו&quot;ד" oninput="render()">
      </div>
      <div class="segs" id="filters">
        <div class="sg on" data-f="open" onclick="setFilter(this)">תהליכים פתוחים</div>
        <div class="sg" data-f="closed" onclick="setFilter(this)">נסגרו</div>
        <div class="sg" data-f="all" onclick="setFilter(this)">הכל</div>
      </div>
    </div>
    <div id="list"></div>
  </main>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }
function fmtPrice(p){
  p = String(p || '').trim();
  if (!p) return '';
  var n = parseInt(p.replace(/[^\d]/g, ''), 10);
  return n ? '₪' + n.toLocaleString() : p;
}

var ITEMS = [], AGENTS = [], FILTER = 'open', MY = '';
var SIDES = ['מוכר','קונה','מוכר וקונה','משכיר','שוכר'];
var STAGES = ['ליווי ראשוני','משא ומתן','אצל עו"ד','לקראת חתימה'];
var VAT = 0.18;
function nfmt(v){ var d = String(v == null ? '' : v).replace(/[^0-9]/g, ''); return d ? Number(d).toLocaleString() : ''; }
function nfix(el){ var p = el.selectionStart; el.value = nfmt(el.value); try{ el.setSelectionRange(el.value.length, el.value.length); }catch(e){} }

function load(){
  return GET('/api/deals').then(function(j){
    ITEMS = (j && j.items) || [];
    AGENTS = (j && j.agents) || [];
    try{ localStorage.setItem('v2c:deals', JSON.stringify({i: ITEMS.slice(0, 150), a: AGENTS})); }catch(e){}
    render();
  }).catch(function(){});
}
(function(){
  try{
    var c = JSON.parse(localStorage.getItem('v2c:deals') || 'null');
    if (c && c.i){ ITEMS = c.i; AGENTS = c.a || []; }
  }catch(e){}
})();
function render(){
  var q = el('q').value.trim().toLowerCase();
  var src = ITEMS.filter(function(it){
    if (FILTER === 'open' && it.deal) return false;
    if (FILTER === 'closed' && !it.deal) return false;
    if (q && ((it.notes || '') + ' ' + (it.agents || []).join(' ') + ' ' + (it.lawyers || ''))
        .toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  el('cnt').textContent = src.length;
  var h = '';
  src.slice(0, 60).forEach(function(it, i){ h += dealCard(it, i); });
  el('list').innerHTML = h ||
    '<div class="card empty"><div class="ic"><svg width="26" height="26" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#C29435" stroke-width="1.4"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#C29435" stroke-width="1.4" stroke-linecap="round"/></svg></div>' +
    '<div class="t">' + (FILTER === 'closed' ? 'עוד לא נסגרו עסקאות' : 'אין תהליכים פתוחים') + '</div>' +
    '<div class="s">כל תהליך מכירה שתפתח יופיע כאן, ומ"נמכר" הוא הופך לעסקה</div>' +
    '<button class="btnMain" style="max-width:220px;flex:none;padding:13px 26px" onclick="openForm(null,false)">+ תהליך חדש</button></div>';
  el('list')._src = src;
}
function dealCard(it, i){
  var agentsLine = (it.agents || []).map(function(a, k){
    var side = k === 0 ? it.side1 : it.side2;
    return a + (side ? ' (' + side + ')' : '');
  }).join(' + ');
  var chip = it.deal ? '<div class="chip closed">נסגרה' + (it.close_date ? ' · ' + esc(it.close_date) : '') + '</div>'
    : (it.stage ? '<div class="chip stage">' + esc(it.stage) + '</div>' : '<div class="chip open">תהליך פתוח</div>');
  var pr = it.deal
    ? '<div class="pr">' + esc(fmtPrice(it.sale_price || it.price)) +
      (it.sale_price && it.price && it.price !== it.sale_price ? '<s>' + esc(fmtPrice(it.price)) + '</s>' : '') + '</div>'
    : (it.price ? '<div class="pr">' + esc(fmtPrice(it.price)) + '</div>' : '');
  var com = it.deal && it.commission ? '<div class="sb">עמלה' +
      (it.commission2 ? ' סוכן 1' : '') + ': ' + esc(fmtPrice(it.commission)) +
      (it.commission_manual ? ' (ידני)' : '') +
      (it.commission2 ? ' · סוכן 2: ' + esc(fmtPrice(it.commission2)) : '') + '</div>' : '';
  var acts = it.deal
    ? '<div class="acts"><button class="sec" onclick="openForm(' + i + ', true)">עריכה</button>' + trashBtn(i) + '</div>'
    : '<div class="acts"><button class="gold" onclick="openForm(' + i + ', true)">' +
      '<svg width="12" height="12" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg>' +
      'נמכר ← עסקה</button>' +
      '<button class="sec" onclick="openForm(' + i + ', false)">עריכה</button>' + trashBtn(i) + '</div>';
  return '<div class="deal' + (it.deal ? ' closed' : '') + '">' +
    '<div class="top"><div><div class="ad">' + esc(it.notes || '') + '</div>' +
    '<div class="sb">' + esc(agentsLine) + (it.lawyers ? ' · עו"ד ' + esc(it.lawyers) : '') + '</div></div>' +
    chip + '</div>' + pr + com + acts + '</div>';
}
function trashBtn(i){
  return '<button class="trash" onclick="delDeal(' + i + ')" aria-label="מחיקה">' +
    '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M2.5 4h11M6.5 2h3M5.5 4v9a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1V4M6.8 6.5v5M9.2 6.5v5" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round"/></svg></button>';
}
function setFilter(node){
  FILTER = node.getAttribute('data-f');
  var sgs = node.parentNode.children;
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i] === node);
  render();
}
function delDeal(i){
  var it = el('list')._src[i];
  if (!confirm('למחוק את "' + (it.notes || 'התהליך') + '"?')) return;
  POST('/api/deals/delete', {id: it.id}).then(function(j){
    if (!j.ok){ toast('שגיאה במחיקה'); return; }
    toast('נמחק'); load();
  });
}

/* ── טופס תהליך/עסקה (24a/27a) ── */
function agentSel(id, val){
  // מלל חופשי עם השלמה אוטומטית מרשימת הסוכנים (datalist agentsDL מוזרק בטופס)
  return '<input id="' + id + '" list="agentsDL" autocomplete="off" value="' + esc(val || '') + '" placeholder="הקלד או בחר סוכן">';
}
function agentsDatalist(){
  return '<datalist id="agentsDL">' + AGENTS.map(function(a){
    return '<option value="' + esc(a) + '"></option>'; }).join('') + '</datalist>';
}
function sideSel(id, val){
  return '<select id="' + id + '">' + SIDES.map(function(s){
    return '<option' + (s === val ? ' selected' : '') + '>' + esc(s) + '</option>';
  }).join('') + '</select>';
}
function calcCom(){
  var sp = parseInt((el('fSale').value || '').replace(/[^\d]/g, ''), 10) || 0;
  if (!el('fCom')._manual){
    el('fCom').value = sp ? Math.round(sp * 0.02 * (1 + VAT)).toLocaleString() : '';
  }
  var c2 = el('fCom2');
  if (c2 && !c2._manual){
    c2.value = (sp && el('fAg2') && el('fAg2').value) ? Math.round(sp * 0.02 * (1 + VAT)).toLocaleString() : '';
  }
}
function comEdit(id){
  var f = el(id || 'fCom');
  f._manual = true;
  f.removeAttribute('readonly');
  f.focus();
  toast('עמלה ידנית — דורסת את החישוב');
}
function openForm(i, asDeal){
  var it = (i === null) ? {} : el('list')._src[i];
  var isDeal = asDeal || !!it.deal;
  var title = (i === null) ? (isDeal ? 'עסקה חדשה' : 'תהליך חדש')
            : (isDeal && !it.deal) ? 'סגירת עסקה' : (isDeal ? 'עסקה — עריכה' : 'תהליך — עריכה');
  var s = el('sheet');
  s.innerHTML = '<div class="grip"></div><div class="body">' +
    '<h3>' + title + (it.notes ? ' · ' + esc(it.notes) : '') + '</h3>' + agentsDatalist() +
    (isDeal ?
      '<div class="sec2"><div class="st">פרטי הסגירה</div>' +
      '<div class="frow">' +
      '<div class="fld"><span>מחיר מבוקש</span><input id="fPrice" inputmode="numeric" style="text-decoration:line-through;color:#9AA0AB" value="' + esc(nfmt(it.price)) + '" oninput="nfix(this)"></div>' +
      '<div class="fld"><span>מחיר מכירה *</span><input id="fSale" class="gold" inputmode="numeric" value="' + esc(nfmt(it.sale_price || it.price || '')) + '" oninput="nfix(this);calcCom()"></div></div>' +
      '<div class="frow">' +
      '<div class="fld"><span>תאריך סגירה</span><input id="fDate" placeholder="ריק = היום" value="' + esc(it.close_date || '') + '"></div>' +
      '<div class="fld"><span>כתובת *</span><input id="fAddr" value="' + esc(it.notes || '') + '"></div></div></div>'
    :
      '<div class="sec2"><div class="st">הנכס והמחיר</div>' +
      '<div class="fld"><span>כתובת *</span><input id="fAddr" value="' + esc(it.notes || '') + '"></div>' +
      '<div class="frow">' +
      '<div class="fld"><span>מחיר</span><input id="fPrice" inputmode="numeric" value="' + esc(nfmt(it.price)) + '" oninput="nfix(this)"></div>' +
      '<div class="fld"><span>שלב בתהליך</span><select id="fStage">' + STAGES.map(function(st){
        return '<option' + (st === it.stage ? ' selected' : '') + '>' + esc(st) + '</option>';
      }).join('') + '</select></div></div></div>') +
    '<div class="sec2"><div class="st">סוכנים' + (isDeal ? ' ועמלה' : '') + '</div>' +
    '<div class="frow">' +
    '<div class="fld" style="flex:1.3"><span>סוכן</span>' + agentSel('fAg1', (it.agents || [])[0] || MY) + '</div>' +
    '<div class="fld"><span>מייצג</span>' + sideSel('fSide1', it.side1 || 'מוכר') + '</div></div>' +
    '<div class="frow">' +
    '<div class="fld" style="flex:1.3"><span>סוכן 2 · אופציונלי</span>' + agentSel('fAg2', (it.agents || [])[1] || '') + '</div>' +
    '<div class="fld"><span>מייצג</span>' + sideSel('fSide2', it.side2 || 'קונה') + '</div></div>' +
    (isDeal ? '' :
      '<label class="offRow" style="display:flex;align-items:center;gap:9px;cursor:pointer;padding:4px 2px">' +
      '<input type="checkbox" id="fOffer"' + (it.offer ? ' checked' : '') + ' onchange="el(\'offerWrap\').style.display=this.checked?\'flex\':\'none\'" style="width:20px;height:20px;accent-color:#2E6BD6">' +
      '<span style="font-size:13.5px;font-weight:700">הוגשה הצעה על הנכס</span></label>' +
      '<div class="frow" id="offerWrap" style="display:' + (it.offer ? 'flex' : 'none') + '">' +
      '<div class="fld"><span>הצעת מוכר</span><input id="fOfferS" inputmode="numeric" value="' + esc(nfmt(it.offer_seller)) + '" oninput="nfix(this)"></div>' +
      '<div class="fld"><span>הצעת קונה</span><input id="fOfferB" inputmode="numeric" value="' + esc(nfmt(it.offer_buyer)) + '" oninput="nfix(this)"></div></div>') +
    (isDeal ?
      '<div class="fld"><span>עמלה סוכן 1 (2% + מע"מ — עיפרון לעריכה ידנית)</span>' +
      '<div class="comRow"><input id="fCom" readonly value="' + esc(it.commission || '') + '">' +
      '<button class="pencil" onclick="comEdit(\'fCom\')">' +
      '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#B8902F" stroke-width="1.6" stroke-linejoin="round"/></svg>' +
      '</button></div></div>' +
      '<div class="fld" id="com2Wrap" style="display:none"><span>עמלה סוכן 2</span>' +
      '<div class="comRow"><input id="fCom2" readonly value="' + esc(it.commission2 || '') + '">' +
      '<button class="pencil" onclick="comEdit(\'fCom2\')">' +
      '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#B8902F" stroke-width="1.6" stroke-linejoin="round"/></svg>' +
      '</button></div></div>' : '') +
    '</div>' +
    '<div class="sec2"><div class="st">עו"ד · אופציונלי</div>' +
    '<div class="frow">' +
    '<div class="fld"><span>עו"ד קונה</span><input id="fLaw" placeholder="שם / משרד" value="' + esc(it.lawyers || '') + '"></div>' +
    '<div class="fld"><span>עו"ד מוכר</span><input id="fLaw2" placeholder="שם / משרד" value="' + esc(it.lawyers2 || '') + '"></div></div></div>' +
    '</div>' +
    '<div class="foot">' +
    '<button class="btnMain' + (isDeal ? ' gold' : '') + '" onclick="saveForm(' + (i === null ? 'null' : i) + ',' + isDeal + ')">' +
    (isDeal ? 'סגור עסקה' : 'שמירה') + '</button>' +
    '<button class="btnSec" onclick="closeSheet()">ביטול</button></div>';
  s.style.display = 'flex'; el('ovl').style.display = 'block';
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
  if (isDeal){
    el('fCom')._manual = !!it.commission_manual;
    el('fCom2')._manual = !!it.commission2_manual;
    if (it.commission2_manual) el('fCom2').removeAttribute('readonly');
    var _syncC2 = function(){
      el('com2Wrap').style.display = el('fAg2').value ? '' : 'none';
      calcCom();
    };
    el('fAg2').addEventListener('change', _syncC2);
    el('fAg2').addEventListener('input', _syncC2);
    _syncC2();
    if (!it.commission_manual) calcCom();
    else el('fCom').removeAttribute('readonly');
  }
}
function saveForm(i, isDeal){
  var it = (i === null) ? {} : el('list')._src[i];
  var agents = [el('fAg1').value, el('fAg2').value].filter(Boolean);
  var addr = el('fAddr').value.trim();
  if (!addr){ toast('כתובת — חובה'); return; }
  var body = {
    id: it.id || '',
    agents: agents,
    notes: addr,
    side1: el('fSide1').value,
    side2: el('fAg2').value ? el('fSide2').value : '',
    lawyers: el('fLaw').value.trim(),
    lawyers2: el('fLaw2') ? el('fLaw2').value.trim() : (it.lawyers2 || ''),
    offer: (!isDeal && el('fOffer')) ? el('fOffer').checked : !!it.offer,
    offer_seller: (!isDeal && el('fOfferS')) ? el('fOfferS').value.trim() : (it.offer_seller || ''),
    offer_buyer: (!isDeal && el('fOfferB')) ? el('fOfferB').value.trim() : (it.offer_buyer || ''),
    price: el('fPrice') ? el('fPrice').value.trim() : (it.price || ''),
    deal: isDeal,
    sale_price: isDeal ? el('fSale').value.trim() : (it.sale_price || ''),
    close_date: isDeal ? el('fDate').value.trim() : (it.close_date || ''),
    stage: (!isDeal && el('fStage')) ? el('fStage').value : (it.stage || ''),
    commission: isDeal ? el('fCom').value.trim() : (it.commission || ''),
    commission_manual: isDeal ? !!el('fCom')._manual : !!it.commission_manual,
    commission2: isDeal ? (el('fAg2').value ? el('fCom2').value.trim() : '') : (it.commission2 || ''),
    commission2_manual: isDeal ? !!el('fCom2')._manual : !!it.commission2_manual
  };
  if (isDeal && !body.sale_price){
    toast('מחיר מכירה — חובה'); return;   // תאריך סגירה לא חובה (ריק = היום)
  }
  POST('/api/deals/save', body).then(function(j){
    if (!j.ok){ toast(j.reason || 'שגיאה בשמירה'); return; }
    closeSheet();
    toast(isDeal ? 'העסקה נסגרה 🎉'.replace(' 🎉','') : 'נשמר');
    load();
  });
}

/* זיכרון מצב הטאב */
var _restY = 0;
function saveSt(){
  try{
    var m = document.querySelector('main');
    localStorage.setItem('v2st:deals', JSON.stringify({f:FILTER, q:el('q').value, y:(m ? m.scrollTop : 0)}));
  }catch(e){}
}
(function(){
  try{
    var s = JSON.parse(localStorage.getItem('v2st:deals') || 'null');
    if (s){
      FILTER = s.f || FILTER; el('q').value = s.q || ''; _restY = s.y || 0;
      var sg = document.querySelector('#filters .sg[data-f="' + FILTER + '"]');
      if (sg){ var cs = sg.parentNode.children;
        for (var i = 0; i < cs.length; i++) cs[i].classList.toggle('on', cs[i] === sg); }
    }
  }catch(e){}
})();
var _renderBase = render;
render = function(){
  _renderBase();
  if (_restY){
    var m = document.querySelector('main');
    if (m){ m.scrollTop = _restY; if (m.scrollTop >= _restY - 4) _restY = 0; }
  }
  if (!_restY) saveSt();
};
(function(){
  var m = document.querySelector('main');
  if (m) m.addEventListener('scroll', function(){
    if (window._svScrolled) _restY = 0; window._svScrolled = true;
    clearTimeout(window._svt); window._svt = setTimeout(saveSt, 300);
  }, {passive:true});
  window.addEventListener('pagehide', function(){ if (!_restY) saveSt(); });
})();

(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    MY = j.name || '';
    el('avatarTx').textContent = (MY || ' ').trim()[0] || '';
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    document.title = 'תהליכים ועסקאות · ' + (o.name || '');
  }).catch(function(){});
  load();
})();
</script></body></html>'''


# ── דוחות (עיצוב 30a) — KPI, מובילים, שת"פ, נכס נולד לפי ערים, ייצוא ─────────
V2_REPORTS_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>דוחות</title>
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
  .brand img{height:36px;max-width:150px;object-fit:contain}
  .menuBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  main{flex:1;padding:4px 16px 124px;display:flex;flex-direction:column;gap:12px;overflow:auto}
  .card{background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 18px;
      display:flex;flex-direction:column;gap:12px}
  .hd{display:flex;align-items:center;justify-content:space-between}
  .hd .tt{display:flex;align-items:center;gap:10px}
  .hd .ic{width:36px;height:36px;border-radius:11px;background:#EAF0FA;display:flex;align-items:center;justify-content:center}
  .hd h1{font-size:21px;font-weight:800}
  .scope{font-size:12px;color:#8B8F99}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px}
  .segs .sg{flex:1;text-align:center;padding:7px 0;font-size:12px;font-weight:700;color:#5B6472;
      border-radius:10px;cursor:pointer;white-space:nowrap}
  .segs .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}
  .kpi{background:#F7F5EE;border-radius:14px;padding:11px 6px;display:flex;flex-direction:column;align-items:center;gap:1px}
  .kpi .n{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}
  .kpi .l{font-size:10px;font-weight:600;color:#8B8F99;text-align:center}
  .kpi .s{font-size:9.5px;color:#B8902F;font-weight:700}
  .secT{font-size:15.5px;font-weight:800}
  .chips{display:flex;gap:7px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
  .chips::-webkit-scrollbar{display:none}
  .lchip{flex-shrink:0;background:#F5F3EC;border:1.5px solid #E9E4D8;border-radius:999px;padding:7px 14px;
      font-size:12px;font-weight:700;color:#5B6472;cursor:pointer;font-family:inherit}
  .lchip.on{background:#C29435;border-color:#C29435;color:#fff;box-shadow:0 3px 10px rgba(194,148,53,.25)}
  .leadRow{display:flex;align-items:center;gap:11px;min-height:40px}
  .leadRow .rank{width:26px;height:26px;border-radius:50%;background:#F0EDE3;color:#5B6472;display:flex;
      align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0}
  .leadRow.first .rank{background:#C29435;color:#fff}
  .leadRow .nm{flex:1;font-size:13.5px;font-weight:700;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .leadRow .val{font-size:14px;font-weight:800;font-variant-numeric:tabular-nums}
  .bar{height:6px;border-radius:999px;background:#F0EDE3;overflow:hidden;margin:2px 37px 6px 0}
  .bar i{display:block;height:100%;background:linear-gradient(90deg,#E4C56B,#C29435);border-radius:999px}
  .sideSplit{display:flex;gap:7px;flex-wrap:wrap}
  .sideSplit .sp{font-size:11.5px;font-weight:700;color:#5B6472;background:#F0EDE3;padding:4px 11px;border-radius:999px}
  .expand{font-size:12.5px;font-weight:700;color:#2E6BD6;cursor:pointer;text-align:center;padding:4px 0}
  .tRow{display:flex;align-items:center;justify-content:space-between;padding:7px 2px;font-size:13px}
  .tRow .n{font-weight:700}
  .tRow .v{font-weight:800;font-variant-numeric:tabular-nums}
  .tRow.our .n{color:#B8902F}
  .sep{height:1px;background:#F0EDE3}
  .exports{display:flex;gap:9px}
  .exports .e{flex:1;display:flex;align-items:center;justify-content:center;gap:7px;border-radius:12px;
      padding:11px 0;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit}
  .exports .wa{background:#1FAF5E;color:#fff;box-shadow:0 4px 12px rgba(31,175,94,.25)}
  .exports .pdf{background:#1E3A5F;color:#fff;box-shadow:0 4px 12px rgba(30,58,95,.25)}
  .exports .cp{background:#fff;color:#1E3A5F;border:1.5px solid #DCD6C8}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;
      padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  @media (min-width:700px){
    header,main,nav{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
  }
  @media print{
    header,nav,.segs,.exports,#toast{display:none !important}
    body{background:#fff}
    main{padding:0}
    .card{box-shadow:none;border:1px solid #E9E4D8;page-break-inside:avoid}
  }
</style></head><body>

  <header>
    <div class="avatar"><div class="c" id="avatarTx"></div><div class="dot"></div></div>
    <div class="brand"><img src="/assets/logo" alt="" onerror="this.style.display='none'"></div>
    <button class="menuBtn" onclick="location.href='/v2/home'" aria-label="לבית">
      <svg width="19" height="19" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#1E3A5F" stroke-width="1.7" stroke-linejoin="round"/></svg>
    </button>
  </header>

  <main>
    <div class="card">
      <div class="hd">
        <div class="tt">
          <div class="ic"><svg width="16" height="16" viewBox="0 0 16 16"><path d="M2.5 13.5v-4M6.5 13.5v-7M10.5 13.5V4M14 13.5V7.5" stroke="#2E6BD6" stroke-width="2" stroke-linecap="round"/></svg></div>
          <h1 id="pgT">דוחות</h1>
        </div>
        <div class="scope" id="scope"></div>
      </div>
      <div class="segs" id="periods">
        <div class="sg" data-p="day" onclick="setPeriod(this)">היום</div>
        <div class="sg" data-p="lastweek" onclick="setPeriod(this)">שבוע שעבר</div>
        <div class="sg on" data-p="week" onclick="setPeriod(this)">השבוע</div>
        <div class="sg" data-p="month" onclick="setPeriod(this)">החודש</div>
        <div class="sg" data-p="year" onclick="setPeriod(this)">השנה</div>
      </div>
      <div class="chips" id="months" style="display:none"></div>
      <div class="kpis" id="kpis"></div>
      <div class="exports">
        <button class="e wa" onclick="sendWa()">
          <svg width="14" height="14" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#fff" stroke-width="1.5"/></svg>
          שלח בוואטסאפ</button>
        <button class="e pdf" onclick="window.print()">דוח PDF</button>
        <button class="e cp" onclick="copyTxt()">העתק</button>
      </div>
    </div>

    <div class="card" id="leadersCard" style="display:none">
      <div class="secT">המובילים במשרד</div>
      <div class="chips" id="leadChips"></div>
      <div id="leadList"></div>
      <div class="sideSplit" id="sideSplit" style="display:none"></div>
      <div class="expand" id="leadMore" style="display:none" onclick="LEAD_ALL=!LEAD_ALL;renderLeaders()">כל 10 המובילים</div>
    </div>

    <div class="card" id="shtafCard" style="display:none">
      <div class="secT" id="shtafT">גיוס נכסים בשת"פ</div>
      <div id="shtafList"></div>
    </div>

    <div class="card" id="nbCard" style="display:none">
      <div class="secT" id="nbT">נכס נולד לפי ערים</div>
      <div id="nbList"></div>
    </div>
    <div class="card" id="meetsCard" style="display:none">
      <div class="secT" id="meetsT">פגישות ופולו-אפ</div>
      <div id="meetsList"></div>
    </div>
  </main>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
/* מקלדת פתוחה: מסתירים את הניווט התחתון כדי שלא "יקפוץ" מעל המקלדת */
document.addEventListener('focusin', function(e){
  var t = e.target;
  if (window.innerWidth < 768) if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')){
    var nv = document.querySelector('nav'); if (nv) nv.style.display = 'none';
  }
});
document.addEventListener('focusout', function(){
  setTimeout(function(){
    var a = document.activeElement;
    if (!a || (a.tagName !== 'INPUT' && a.tagName !== 'TEXTAREA')){
      var nv = document.querySelector('nav'); if (nv) nv.style.display = '';
    }
  }, 150);
});
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

var PERIOD = 'week', MONTH = 0, R = null, DEALS = [], LEAD_TAB = 'gius', LEAD_ALL = false, IS_MGR = false;
var HMON = ['ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר'];

function setPeriod(node){
  PERIOD = node.getAttribute('data-p');
  var sgs = node.parentNode.children;
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i] === node);
  if (PERIOD === 'month'){
    MONTH = new Date().getMonth() + 1;   // ברירת מחדל: החודש הנוכחי
    renderMonths();
    el('months').style.display = 'flex';
  } else {
    MONTH = 0;
    el('months').style.display = 'none';
  }
  load();
}
function renderMonths(){
  var cur = new Date().getMonth() + 1;
  var h = '';
  for (var m = cur; m >= 1; m--)
    h += '<button class="lchip' + (m === MONTH ? ' on' : '') + '" onclick="pickMonth(' + m + ')">' +
         HMON[m - 1] + '</button>';
  el('months').innerHTML = h;
}
function pickMonth(m){
  MONTH = m;
  renderMonths();
  load();
}
function parseDMY(s){
  var m = /(\d{1,2})[\/.](\d{1,2})[\/.](\d{2,4})/.exec(String(s || ''));
  if (!m) return null;
  var y = +m[3]; if (y < 100) y += 2000;
  return new Date(y, +m[2] - 1, +m[1]);
}
function dealsInRange(){
  if (!R) return [];
  var f = parseDMY(R.from), t = parseDMY(R.to);
  if (t) t.setHours(23, 59, 59);
  return DEALS.filter(function(d){
    if (!d.deal) return false;
    var cd = parseDMY(d.close_date);
    return cd && (!f || cd >= f) && (!t || cd <= t);
  });
}
function load(){
  el('kpis').innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#8B8F99;font-size:12.5px;padding:14px 0">טוען את הדוח…</div>';
  return Promise.all([
    GET('/api/report?period=' + PERIOD + (PERIOD === 'month' && MONTH ? '&month=' + MONTH : ''))
      .catch(function(){ return {}; }),
    GET('/api/deals').catch(function(){ return {}; })
  ]).then(function(rs){
    R = rs[0] || {};
    DEALS = (rs[1] && rs[1].items) || [];
    render();
  });
}
function kpi(n, l, sub, color){
  return '<div class="kpi"><div class="n" style="color:' + (color || '#1E3A5F') + '">' + n + '</div>' +
    '<div class="l">' + l + '</div>' + (sub ? '<div class="s">' + sub + '</div>' : '') + '</div>';
}
function render(){
  if (!R || !R.ok){ el('kpis').innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#8B8F99;font-size:12.5px;padding:14px 0">שגיאה בטעינת הדוח</div>'; return; }
  var sm = R.summary || {}, c = sm.calls || {}, g = sm.sigs || {};
  el('scope').textContent = (R.label || '') + ' · ' + (R.scope || '');
  var dr = dealsInRange();
  el('kpis').innerHTML =
    kpi(c.total || 0, 'שיחות') +
    kpi(c.answered || 0, 'נענו', (c.rate || 0) + '%', '#1FAF5E') +
    kpi(g.total || 0, 'חתימות') +
    kpi(g.bladiut || 0, 'בלעדיות', '', '#B8902F') +
    kpi(dr.length, 'עסקאות בתקופה', '', '#1FAF5E') +
    kpi((R.meetings || []).length, 'פגישות ופולו-אפ') +
    kpi(DEALS.filter(function(d){ return !d.deal; }).length, 'תהליכים פתוחים', 'לרגע זה', '#B8902F') +
    kpi(DEALS.filter(function(d){
      if (!d.deal) return false;
      var cd = parseDMY(d.close_date);
      return cd && cd.getFullYear() === new Date().getFullYear();
    }).length, 'עסקאות השנה', '', '#1FAF5E');
  renderLeaders();
  renderShtaf();
  renderNb();
  renderMeets();
}
var LEADS = {gius: 'גיוס נכסים', konim: 'החתמת קונים', deals: 'עסקאות', calls: 'שיחות'};
var REP_NAME = '';
function leadData(){
  var sm = R.summary || {};
  if (LEAD_TAB === 'gius') return (sm.topGius || []).map(function(x){ return {n: x.name, v: x.n}; });
  if (LEAD_TAB === 'konim') return (sm.topKonim || []).map(function(x){ return {n: x.name, v: x.n}; });
  if (LEAD_TAB === 'deals') return (R.top_deals || []).map(function(x){ return {n: x.name, v: x.n}; });
  return (sm.agents || []).map(function(x){ return {n: x.name, v: x.total}; });
}
function renderLeaders(){
  var sm = R.summary || {};
  var any = (sm.topGius || []).length || (sm.topKonim || []).length || (R.top_deals || []).length || (sm.agents || []).length;
  el('leadersCard').style.display = any ? 'flex' : 'none';
  if (!any) return;
  el('leadChips').innerHTML = Object.keys(LEADS).map(function(k){
    return '<button class="lchip' + (k === LEAD_TAB ? ' on' : '') + '" onclick="LEAD_TAB=\'' + k + '\';LEAD_ALL=false;renderLeaders()">' + LEADS[k] + '</button>';
  }).join('');
  var data = leadData();
  var max = data.length ? data[0].v : 0;
  var shown = LEAD_ALL ? data.slice(0, 10) : data.slice(0, 3);
  // סוכן: רואה את הדירוג — שמות לפי סדר, בלי מספרי העסקאות של האחרים (בקשת אייל)
  var rankLine = '';
  if (!IS_MGR){
    var mr = (R.summary && R.summary.myRank) || {};
    var r = (LEAD_TAB === 'gius') ? mr.gius : (LEAD_TAB === 'konim') ? mr.konim : null;
    if (LEAD_TAB === 'deals' && REP_NAME){
      var pos = -1;
      (R.top_deals || []).forEach(function(x, i2){ if (pos < 0 && x.name === REP_NAME) pos = i2 + 1; });
      r = pos > 0 ? {pos: pos, of: (R.top_deals || []).length} : null;
    }
    if (r && r.pos) rankLine = '<div style="background:#F6EEDB;border:1px solid #E4C56B;border-radius:12px;' +
      'padding:9px 13px;font-size:13px;font-weight:800;color:#B8902F;margin-bottom:4px">' +
      'הדירוג שלך: מקום ' + r.pos + (r.of ? ' מתוך ' + r.of : '') + '</div>';
  }
  el('leadList').innerHTML = rankLine + (shown.map(function(d, i){
    var mine = !IS_MGR && REP_NAME && d.n === REP_NAME;
    return '<div class="leadRow' + (i === 0 ? ' first' : '') + '"' + (mine ? ' style="color:#B8902F"' : '') + '>' +
      '<div class="rank">' + (i + 1) + '</div><div class="nm"' + (mine ? ' style="font-weight:800"' : '') + '>' + esc(d.n) + (mine ? ' · אתה' : '') + '</div>' +
      (IS_MGR ? '<div class="val">' + d.v + '</div>' : '') + '</div>' +
      (IS_MGR && i === 0 && max ? '<div class="bar"><i style="width:' + Math.round(d.v / max * 100) + '%"></i></div>' : '');
  }).join('') || '<div style="font-size:12px;color:#8B8F99;padding:6px 0">אין נתונים בתקופה</div>');
  el('leadMore').style.display = data.length > 3 ? 'block' : 'none';
  el('leadMore').textContent = LEAD_ALL ? 'הצג פחות' : 'כל 10 המובילים';
  // פילוח עסקאות לפי צד — מתחת לצ'יפ עסקאות
  if (LEAD_TAB === 'deals'){
    var split = {'מוכר': 0, 'קונה': 0, 'משכיר': 0, 'שוכר': 0};
    dealsInRange().forEach(function(d){
      [d.side1, d.side2].forEach(function(s){
        if (s === 'מוכר וקונה'){ split['מוכר']++; split['קונה']++; }
        else if (split[s] !== undefined) split[s]++;
      });
    });
    el('sideSplit').innerHTML = Object.keys(split).map(function(k){
      return '<span class="sp">' + k + ' · ' + split[k] + '</span>';
    }).join('');
    el('sideSplit').style.display = 'flex';
  } else el('sideSplit').style.display = 'none';
}
function renderShtaf(){
  var list = R.shtaf || [];
  el('shtafCard').style.display = list.length ? 'flex' : 'none';
  if (!list.length) return;
  el('shtafT').textContent = 'גיוס נכסים בשת"פ · ' + (R.shtaf_total || 0) + ' נכסים · ' + (R.shtaf_offices || 0) + ' משרדים';
  el('shtafList').innerHTML = list.map(function(o, i){
    var our = /פמילי|family/i.test(o.office || '');
    return (i ? '<div class="sep"></div>' : '') +
      '<div class="tRow' + (our ? ' our' : '') + '"><span class="n">' + esc(o.office) + '</span>' +
      '<span class="v">' + o.count + '</span></div>';
  }).join('');
}
function renderMeets(){
  var ms = (R.meetings || []).slice();
  el('meetsCard').style.display = ms.length ? 'flex' : 'none';
  if (!ms.length) return;
  var nMeet = ms.filter(function(m){ return m.status === 'meeting'; }).length;
  var nFu = ms.length - nMeet;
  el('meetsT').textContent = 'פגישות ופולו-אפ · ' + ms.length +
    ' (' + nMeet + ' פגישות · ' + nFu + ' פולו-אפ)';
  ms.sort(function(a, b){ return String(a.date || '').localeCompare(String(b.date || '')); });
  el('meetsList').innerHTML = ms.slice(0, 40).map(function(m, i){
    var lbl = m.label || (m.status === 'meeting' ? 'פגישה' : 'פולו-אפ');
    var when = String(m.date || '').replace('T', ' ');
    return (i ? '<div class="sep"></div>' : '') +
      '<div class="tRow"><span class="n">' + esc(lbl + ': ' + (m.addr || '')) +
      (m.agent ? ' · ' + esc(m.agent) : '') + '</span>' +
      '<span class="v" style="font-size:12px;white-space:nowrap">' + esc(when) + '</span></div>';
  }).join('');
}
function renderNb(){
  var list = R.nbCities || [];
  el('nbCard').style.display = list.length ? 'flex' : 'none';
  if (!list.length) return;
  el('nbT').textContent = 'נכס נולד לפי ערים · ' + (R.nbTotal || 0);
  el('nbList').innerHTML = list.slice(0, 12).map(function(cx, i){
    return (i ? '<div class="sep"></div>' : '') +
      '<div class="tRow"><span class="n">' + esc(cx.city) + '</span><span class="v">' + cx.n + '</span></div>';
  }).join('');
}
function sendWa(){
  if (!R || !R.wa_text){ toast('הדוח עוד נטען'); return; }
  window.open('https://wa.me/?text=' + encodeURIComponent(R.wa_text), '_blank');
}
function copyTxt(){
  if (!R || !R.wa_text){ toast('הדוח עוד נטען'); return; }
  try{ navigator.clipboard.writeText(R.wa_text).then(function(){ toast('הדוח הועתק'); }); }
  catch(e){ toast('לא ניתן להעתיק'); }
}
(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    IS_MGR = (j.role === 'admin' || j.role === 'coordinator');
    REP_NAME = j.name || '';
    el('avatarTx').textContent = (j.name || ' ').trim()[0] || '';
    el('pgT').textContent = IS_MGR ? 'דוחות מנהל' : 'הדוחות שלי';
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    document.title = 'דוחות · ' + (o.name || '');
  }).catch(function(){});
  load();
})();
</script></body></html>'''


# ── עדכונים למשרד (31b) — Supabase announcements + אישורי קריאה ─────────────
V2_UPDATES_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>עדכונים למשרד</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;min-height:100vh;min-height:100dvh;
       display:flex;flex-direction:column;color:#1E3A5F}
  header{padding:calc(env(safe-area-inset-top,0px) + 10px) 18px 12px;display:flex;align-items:center;justify-content:space-between}
  .backBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  .t{font-size:17px;font-weight:800}
  main{flex:1;padding:4px 16px 30px;display:flex;flex-direction:column;gap:12px;overflow:auto}
  .card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:14px 16px;
      display:flex;flex-direction:column;gap:9px;border:2px solid transparent}
  .card.pinned{border-color:#C29435}
  .hd{display:flex;align-items:center;gap:9px}
  .hd .av{width:34px;height:34px;border-radius:50%;background:#1E3A5F;color:#fff;display:flex;
      align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}
  .hd .nm{font-size:13px;font-weight:800}
  .hd .sb{font-size:11px;color:#8B8F99}
  .pin{margin-right:auto;display:flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:#B8902F}
  .body{font-size:13.5px;line-height:1.7;color:#1E3A5F;white-space:pre-wrap}
  .foot{display:flex;align-items:center;gap:8px}
  .ok{display:flex;align-items:center;justify-content:center;gap:6px;background:#2E6BD6;color:#fff;
      border-radius:11px;padding:9px 16px;font-size:12.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit}
  .okd{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:700;color:#1FAF5E}
  .cnt{font-size:11.5px;font-weight:700;color:#5B6472;background:#F0EDE3;padding:4px 11px;border-radius:999px}
  .trash{width:36px;height:36px;border-radius:10px;background:#FBEDED;border:0;cursor:pointer;
      display:flex;align-items:center;justify-content:center;margin-right:auto}
  .waSh{width:36px;height:36px;border-radius:11px;background:#E7F7EE;border:none;display:flex;align-items:center;justify-content:center;cursor:pointer}
  .composer{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:14px 16px;
      display:flex;flex-direction:column;gap:9px}
  .composer textarea{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:12px;padding:11px 13px;
      font-size:13.5px;font-family:inherit;outline:none;resize:vertical;min-height:64px;color:#1E3A5F}
  .composer .row{display:flex;align-items:center;gap:10px}
  .composer .pub{display:flex;align-items:center;justify-content:center;gap:7px;background:#2E6BD6;color:#fff;
      border-radius:12px;padding:11px 20px;font-size:13px;font-weight:700;border:0;cursor:pointer;font-family:inherit;
      box-shadow:0 4px 12px rgba(46,107,214,.25)}
  .pinTg{display:flex;align-items:center;gap:7px;font-size:12.5px;font-weight:700;color:#5B6472;cursor:pointer}
  .pinTg .bx{width:18px;height:18px;border-radius:5px;border:1.5px solid #DCD6C8;background:#fff;
      display:flex;align-items:center;justify-content:center}
  .pinTg.on .bx{background:#C29435;border-color:#C29435}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .tt{font-size:15px;font-weight:800}
  .empty .ss{font-size:12.5px;color:#5B6472;line-height:1.6;max-width:260px}
  #toast{position:fixed;bottom:40px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  @media (min-width:700px){ header,main{width:100%;max-width:600px;margin-left:auto;margin-right:auto} }
</style></head><body>
  <header>
    <button class="backBtn" onclick="location.href='/v2/home'">
      <svg width="15" height="15" viewBox="0 0 14 14"><path d="M5 2L10 7l-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="t">עדכונים למשרד</div>
    <div style="width:44px"></div>
  </header>
  <main>
    <div class="composer" id="composer" style="display:none">
      <textarea id="annTx" placeholder="עדכון לצוות — נכס חדש, נוהל, ברכה..."></textarea>
      <div class="row">
        <div class="pinTg" id="pinTg" onclick="this.classList.toggle('on')">
          <div class="bx"><svg width="10" height="8" viewBox="0 0 12 10"><path d="M1.5 5l3 3 6-6.5" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg></div>
          נעוץ למעלה
        </div>
        <button class="pub" style="margin-right:auto" onclick="publish()">פרסם</button>
      </div>
    </div>
    <div id="list"><div class="card empty"><div class="ss">טוען עדכונים…</div></div></div>
  </main>
  <div id="toast"></div>
<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function GET(u){ return fetch(u, {headers:{'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function POST(u, d){
  return fetch(u, {method:'POST', headers:{'X-Auth-Token': TOK, 'Content-Type': 'application/json'},
    body: JSON.stringify(d || {})}).then(function(r){ return r.json(); });
}
function el(id){ return document.getElementById(id); }
function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function toast(m){
  var t = el('toast'); t.textContent = m; t.style.opacity = '1';
  clearTimeout(t._h); t._h = setTimeout(function(){ t.style.opacity = '0'; }, 1800);
}
var ANN = [], ME = {}, CAN_POST = false, IS_ADMIN = false;
function load(){
  return GET('/v2/api/ann').then(function(j){
    if (!j.ok){
      el('list').innerHTML = '<div class="card empty"><div class="tt">העדכונים עוד לא זמינים</div>' +
        '<div class="ss">' + (j.reason === 'no_supabase' ? 'החיבור ל-Supabase לא מוגדר בסביבה הזו' : 'שגיאה בטעינה') + '</div></div>';
      return;
    }
    ANN = j.items || [];
    render();
  });
}
function fmtTs(iso){
  try{
    var d = new Date(iso);
    return ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + ' ' +
           ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }catch(e){ return ''; }
}
function render(){
  var h = '';
  ANN.forEach(function(a){
    var mine = a.my_read;
    h += '<div class="card' + (a.pinned ? ' pinned' : '') + '">' +
      '<div class="hd"><div class="av">' + esc((a.author_name || ' ')[0]) + '</div>' +
      '<div><div class="nm">' + esc(a.author_name || '') + '</div>' +
      '<div class="sb">' + esc((a.author_role === 'coordinator' ? 'מתאמת' : 'מנהל') + ' · ' + fmtTs(a.created_at)) + '</div></div>' +
      (a.pinned ? '<div class="pin"><svg width="12" height="12" viewBox="0 0 16 16"><path d="M9.5 1.5l5 5-3 1-2.5 5.5-2-4-4.5 4 4-4.5-4-2L8 4z" fill="#C29435"/></svg>נעוץ</div>' : '') +
      '</div>' +
      '<div class="body">' + esc(a.body || '') + '</div>' +
      '<div class="foot">' +
      (mine ? '<div class="okd"><svg width="13" height="13" viewBox="0 0 16 16"><path d="M2.5 8.5l3.5 3.5 7-8" fill="none" stroke="#1FAF5E" stroke-width="2" stroke-linecap="round"/></svg>אישרת</div>'
            : '<button class="ok" onclick="markRead(\'' + esc(a.id) + '\')">אישרתי · קראתי</button>') +
      (IS_ADMIN ? '<div class="cnt">אישרו ' + (a.reads || 0) + '</div>' : '') +
      '<button class="waSh" onclick="waAnn(\'' + esc(a.id) + '\')" aria-label="שליחה בוואטסאפ">' +
        '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#1FAF5E" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
      (IS_ADMIN ? '<button class="trash" onclick="delAnn(\'' + esc(a.id) + '\')">' +
        '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M2.5 4h11M6.5 2h3M5.5 4v9a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1V4" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round"/></svg></button>' : '') +
      '</div></div>';
  });
  el('list').innerHTML = h ||
    '<div class="card empty"><div class="ic"><svg width="26" height="26" viewBox="0 0 22 22"><path d="M4 14V9a7 7 0 0 1 14 0v5l1.5 2.5H2.5z" fill="none" stroke="#C29435" stroke-width="1.6" stroke-linejoin="round"/></svg></div>' +
    '<div class="tt">אין עדכונים עדיין</div><div class="ss">' + (CAN_POST ? 'פרסם את העדכון הראשון לצוות למעלה' : 'עדכונים מהמשרד יופיעו כאן') + '</div></div>';
}
function waAnn(id){
  var a = null;
  ANN.forEach(function(x){ if (String(x.id) === String(id)) a = x; });
  if (!a) return;
  var tx = 'עדכון מהמשרד' + (a.author_name ? ' (' + a.author_name + ')' : '') + ':\n' + (a.body || '');
  window.open('https://wa.me/?text=' + encodeURIComponent(tx), '_blank');
}
function publish(){
  var tx = el('annTx').value.trim();
  if (!tx){ toast('כתוב עדכון'); return; }
  POST('/v2/api/ann', {body: tx, pinned: el('pinTg').classList.contains('on')}).then(function(j){
    if (!j.ok){ toast(j.reason === 'no_supabase' ? 'אין חיבור Supabase' : 'שגיאה בפרסום'); return; }
    el('annTx').value = ''; el('pinTg').classList.remove('on');
    toast('פורסם'); load();
  });
}
function markRead(id){
  POST('/v2/api/ann/read', {id: id}).then(function(j){
    if (!j.ok){ toast('שגיאה'); return; }
    load();
  });
}
function delAnn(id){
  if (!confirm('למחוק את העדכון?')) return;
  POST('/v2/api/ann/del', {id: id}).then(function(j){
    if (!j.ok){ toast('שגיאה'); return; }
    toast('נמחק'); load();
  });
}
(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    ME = j;
    IS_ADMIN = j.role === 'admin';
    CAN_POST = j.role === 'admin' || j.role === 'coordinator';
    el('composer').style.display = CAN_POST ? 'flex' : 'none';
    load();
  }).catch(function(){ location.replace('/v2'); });
})();
</script></body></html>'''

# ── יומן שימוש — דשבורד כניסות ופעולות (9ו, למנהל) ──────────────────────────
V2_ACTIVITY_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>יומן שימוש</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;min-height:100vh;min-height:100dvh;
       display:flex;flex-direction:column;color:#1E3A5F}
  header{padding:calc(env(safe-area-inset-top,0px) + 10px) 18px 12px;display:flex;align-items:center;justify-content:space-between}
  .backBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  .t{font-size:17px;font-weight:800}
  .live{display:flex;align-items:center;gap:6px;font-size:11.5px;font-weight:700;color:#1FAF5E}
  .live i{width:8px;height:8px;border-radius:50%;background:#1FAF5E;display:block}
  @media (prefers-reduced-motion:no-preference){
    @keyframes pulseDot{0%,100%{opacity:1}50%{opacity:.35}}
    .live i{animation:pulseDot 2s infinite}
  }
  main{flex:1;padding:4px 16px 30px;display:flex;flex-direction:column;gap:10px;overflow:auto}
  .card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:6px 16px}
  .row{display:flex;align-items:center;gap:11px;padding:10px 0;border-bottom:1px solid #F0EDE3;min-height:44px}
  .row:last-child{border-bottom:0}
  .row .av{width:32px;height:32px;border-radius:50%;background:#EAF0FA;color:#2E6BD6;display:flex;
      align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0}
  .row .av.login{background:#E7F7EE;color:#1FAF5E}
  .row .mid{flex:1;min-width:0}
  .row .a{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .row .d{font-size:11.5px;color:#8B8F99;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .row .tm{font-size:11.5px;font-weight:700;color:#8B8F99;flex-shrink:0;font-variant-numeric:tabular-nums}
  .empty{text-align:center;color:#8B8F99;font-size:13px;padding:24px 0}
  @media (min-width:700px){ header,main{width:100%;max-width:600px;margin-left:auto;margin-right:auto} }
</style></head><body>
  <header>
    <button class="backBtn" onclick="location.href='/v2/home'">
      <svg width="15" height="15" viewBox="0 0 14 14"><path d="M5 2L10 7l-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="t">יומן שימוש</div>
    <div class="live"><i></i>חי</div>
  </header>
  <main>
  <div class="card" id="useDash" style="display:none"></div>
  <div class="card" id="list"><div class="empty">טוען…</div></div>
</main>
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
function fmt(ts){
  var d = new Date((parseFloat(ts) || 0) * 1000);
  var today = new Date();
  var hm = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  return (d.toDateString() === today.toDateString()) ? hm
    : ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + ' ' + hm;
}
function load(){
  GET('/api/activity').then(function(j){
    if (!j.ok){
      el('list').innerHTML = '<div class="empty">' + (j.reason === 'forbidden' ? 'המסך למנהל בלבד' : 'שגיאה בטעינה') + '</div>';
      return;
    }
    var items = j.items || [];
    renderUsage(items);
    el('list').innerHTML = items.slice(0, 120).map(function(it){
      var isLogin = (it.action || '').indexOf('כניסה') >= 0;
      return '<div class="row"><div class="av' + (isLogin ? ' login' : '') + '">' + esc((it.name || ' ')[0]) + '</div>' +
        '<div class="mid"><div class="a">' + esc((it.name || '') + ' · ' + (it.action || '')) + '</div>' +
        (it.detail ? '<div class="d">' + esc(it.detail) + '</div>' : '') + '</div>' +
        '<div class="tm">' + fmt(it.ts) + '</div></div>';
    }).join('') || '<div class="empty">אין פעילות עדיין היום</div>';
  }).catch(function(){});
}
/* זמן שימוש לפי סוכן — נגזר מיומן הפעילות: פעולות ברצף (פער עד 10 דק') = סשן אחד */
function fmtMin(m){
  if (m >= 60) return Math.floor(m / 60) + ' ש\'' + (m % 60 ? ' ' + (m % 60) + ' דק\'' : '');
  return m + ' דק\'';
}
function renderUsage(items){
  var by = {};
  items.forEach(function(it){
    var n = (it.name || '').trim(), t = parseFloat(it.ts) || 0;
    if (!n || !t) return;
    (by[n] = by[n] || []).push(t);
  });
  var rows = [];
  Object.keys(by).forEach(function(n){
    var ts = by[n].sort(function(a, b){ return a - b; });
    var mins = 0, start = ts[0], prev = ts[0];
    for (var i = 1; i <= ts.length; i++){
      if (i === ts.length || ts[i] - prev > 600){
        mins += Math.max((prev - start) / 60, 1);   // סשן עם פעולה בודדת = דקה
        if (i < ts.length) start = ts[i];
      }
      if (i < ts.length) prev = ts[i];
    }
    rows.push({n: n, m: Math.round(mins), c: ts.length});
  });
  if (!rows.length){ el('useDash').style.display = 'none'; return; }
  rows.sort(function(a, b){ return b.m - a.m; });
  var mx = rows[0].m || 1;
  el('useDash').style.display = 'block';
  el('useDash').innerHTML =
    '<div style="font-size:14.5px;font-weight:800;padding:2px 2px 10px">זמן באפליקציה היום</div>' +
    rows.slice(0, 12).map(function(r){
      return '<div style="display:flex;align-items:center;gap:10px;padding:5px 2px">' +
        '<div style="width:92px;font-size:12.5px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(r.n) + '</div>' +
        '<div style="flex:1;height:9px;border-radius:999px;background:#F0EDE3;overflow:hidden">' +
        '<div style="height:100%;width:' + Math.max(4, Math.round(r.m / mx * 100)) + '%;border-radius:999px;background:#2E6BD6"></div></div>' +
        '<div style="font-size:11.5px;color:#5B6472;font-weight:700;white-space:nowrap">' + fmtMin(r.m) + ' · ' + r.c + ' פעולות</div></div>';
    }).join('') +
    '<div style="font-size:10.5px;color:#8B8F99;padding:8px 2px 2px">הערכה לפי יומן הפעילות — פעולות ברצף נספרות כסשן אחד</div>';
}
(function(){
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    load();
    setInterval(load, 45000);
  }).catch(function(){ location.replace('/v2'); });
})();
</script></body></html>'''


# ── טופס החתמה (18a/18b) — מתעניין/בעל נכס: מרחוק (SMS+וואטסאפ) או במקום ──
V2_SIGN_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>החתמה</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;min-height:100vh;min-height:100dvh;
       display:flex;flex-direction:column;color:#1E3A5F}
  header{padding:calc(env(safe-area-inset-top,0px) + 10px) 18px 10px;display:flex;align-items:center;justify-content:space-between}
  .backBtn{width:40px;height:40px;border-radius:13px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);
      display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  header .mid{display:flex;flex-direction:column;align-items:center}
  header .t{font-size:17px;font-weight:800}
  header .s{font-size:11px;color:#8B8F99}
  main{flex:1;padding:0 16px 130px;display:flex;flex-direction:column;gap:11px;overflow:auto}
  .sec{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:14px 16px;
      display:flex;flex-direction:column;gap:11px}
  .sec .hd{display:flex;align-items:center;gap:8px}
  .sec .ic{width:28px;height:28px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .sec .tt{font-size:14px;font-weight:800}
  .sec .note{font-size:11px;color:#8B8F99;margin-right:auto}
  .dRow{display:flex;align-items:center;justify-content:space-between;gap:8px}
  .dRow.off{opacity:.55}
  .dRow .r{display:flex;align-items:center;gap:9px;cursor:pointer}
  .cb{width:22px;height:22px;border-radius:7px;border:1.5px solid #DCD6C8;background:#fff;display:flex;
      align-items:center;justify-content:center;flex-shrink:0}
  .dRow.on .cb{background:#C29435;border-color:#C29435}
  .dRow .lb{font-size:14px;font-weight:700}
  .dRow .in{display:flex;align-items:center;gap:6px}
  .dRow input{width:56px;text-align:center;background:#F5F3EC;border:1px solid #E9E4D8;border-radius:10px;
      padding:8px 0;font-size:14px;font-weight:800;color:#1E3A5F;font-family:inherit;outline:none}
  .dRow .un{font-size:12px;font-weight:600;color:#8B8F99}
  .moChip{border:1.5px solid #DCD6C8;background:#fff;color:#5B6472;border-radius:999px;padding:5px 11px;
      font-size:12px;font-weight:700;font-family:inherit;cursor:pointer}
  .moChip.on{background:#C29435;border-color:#C29435;color:#fff}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld span{font-size:11.5px;font-weight:700;color:#5B6472}
  .fld input{background:#F5F3EC;border:1px solid #E9E4D8;border-radius:12px;padding:11px 13px;
      font-size:14px;font-weight:700;color:#1E3A5F;font-family:inherit;outline:none;width:100%}
  .preChip{background:#EAF0FA;border:1.5px solid #2E6BD6;border-radius:12px;padding:10px 13px;
      display:flex;align-items:center;justify-content:space-between}
  .preChip b{font-size:13.5px;font-weight:700}
  .preChip i{font-size:10.5px;font-weight:800;color:#2E6BD6;font-style:normal}
  #idMsg{font-size:11.5px;font-weight:700;min-height:15px}
  .propRow{background:#F7F5EE;border-radius:12px;padding:10px 13px;display:flex;align-items:center;gap:8px}
  .propRow .mid2{flex:1;min-width:0}
  .propRow .a{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .propRow .p{font-size:11.5px;color:#8B8F99}
  .propRow .x{width:28px;height:28px;border-radius:50%;background:#FBEDED;border:0;cursor:pointer;
      display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .pBtns{display:flex;gap:8px}
  .pBtns .b{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;background:#fff;
      border-radius:12px;padding:10px 0;font-size:12.5px;font-weight:700;cursor:pointer;font-family:inherit}
  .pBtns .dash{border:1.5px dashed #DCD6C8;color:#5B6472}
  .pBtns .sol{border:1.5px solid #DCD6C8;color:#1E3A5F}
  .radio{display:flex;align-items:center;gap:9px;cursor:pointer;min-height:36px}
  .radio .dot{width:20px;height:20px;border-radius:50%;border:1.5px solid #DCD6C8;background:#fff;flex-shrink:0}
  .radio.on .dot{border:6px solid #C29435}
  .radio .lb{font-size:13.5px;font-weight:700}
  .radio:not(.on){opacity:.6}
  .hint{background:#EAF0FA;border-radius:11px;padding:9px 12px;font-size:11.5px;color:#3D5273;line-height:1.55}
  #padWrap{display:none;flex-direction:column;gap:8px}
  #pad{width:100%;height:160px;background:#fff;border:1.5px dashed #C9CDD4;border-radius:14px;touch-action:none}
  .padClear{align-self:flex-start;font-size:12px;font-weight:700;color:#2E6BD6;background:none;border:0;
      cursor:pointer;font-family:inherit}
  .cta{position:fixed;left:0;right:0;bottom:0;z-index:40;
      padding:12px 16px calc(env(safe-area-inset-bottom,0px) + 18px);
      background:linear-gradient(to top, #F2EFE7 75%, transparent)}
  .cta button{display:flex;align-items:center;justify-content:center;gap:9px;width:100%;background:#C29435;
      color:#fff;border-radius:15px;padding:15px 0;font-size:15.5px;font-weight:800;border:0;cursor:pointer;
      font-family:inherit;box-shadow:0 8px 22px rgba(194,148,53,.32)}
  .cta button:disabled{opacity:.6}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:50}
  #sheet{position:fixed;left:0;right:0;bottom:0;z-index:51;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 20px;display:none;flex-direction:column;
      gap:10px;max-height:75vh;overflow:auto}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center}
  #sheet h3{font-size:18px;font-weight:800}
  .pick{background:#fff;border-radius:13px;padding:11px 13px;display:flex;align-items:center;
      justify-content:space-between;gap:8px;cursor:pointer}
  .pick .a{font-size:13px;font-weight:700}
  .pick .p{font-size:11.5px;color:#8B8F99}
  .btnSec{display:flex;align-items:center;justify-content:center;background:#fff;color:#5B6472;
      border:1.5px solid #DCD6C8;border-radius:13px;padding:12px 0;font-size:14px;font-weight:700;
      cursor:pointer;font-family:inherit}
  #toast{position:fixed;bottom:120px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:80;white-space:nowrap}
  @media (min-width:700px){
    header,main,.cta{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    #sheet{max-width:600px;margin-left:auto;margin-right:auto}
  }
</style></head><body>

  <header>
    <button class="backBtn" onclick="location.href='/v2/sigs'">
      <svg width="15" height="15" viewBox="0 0 14 14"><path d="M5 2L10 7l-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="mid"><div class="t" id="pgT">החתמה</div><div class="s" id="pgS"></div></div>
    <div style="width:40px"></div>
  </header>

  <main>
    <div class="sec" id="secDeal">
      <div class="hd"><div class="ic" style="background:#F6EEDB">
        <svg width="13" height="13" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#B8902F" stroke-width="1.6" stroke-linejoin="round"/></svg></div>
        <span class="tt">סוג עסקה ועמלה</span></div>
      <div id="dealRows"></div>
    </div>

    <div class="sec">
      <div class="hd"><div class="ic" style="background:#EAF0FA">
        <svg width="13" height="13" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#2E6BD6" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#2E6BD6" stroke-width="1.8" stroke-linecap="round"/></svg></div>
        <span class="tt">פרטי הלקוח</span></div>
      <div class="preChip" id="preChip" style="display:none"><b id="preTx"></b><i>הועבר מהמסך הקודם</i></div>
      <div class="fld"><span>שם מלא *</span><input id="cName"></div>
      <div class="fld"><span>טלפון *</span><input id="cPhone" type="tel" inputmode="numeric"></div>
      <div class="fld"><span>תעודת זהות <span id="idReq" style="color:#C24040;display:none">*</span></span>
        <input id="cId" inputmode="numeric" oninput="checkId()">
        <div id="idMsg"></div></div>
    </div>

    <div class="sec">
      <div class="hd"><div class="ic" style="background:#F6EEDB">
        <svg width="13" height="13" viewBox="0 0 16 16"><path d="M2 8L8 3l6 5v5a.8.8 0 0 1-.8.8H9.8V10H6.2v3.8H2.8A.8.8 0 0 1 2 13z" fill="none" stroke="#B8902F" stroke-width="1.5" stroke-linejoin="round"/></svg></div>
        <span class="tt">פרטי הנכס</span><span class="note" id="propNote">אפשר יותר מנכס אחד</span></div>
      <div id="propList"></div>
      <div class="pBtns">
        <button class="b dash" onclick="addPropFree()">+ הוסף נכס</button>
        <button class="b sol" onclick="pickProp()">בחר מהנכסים שלי</button>
      </div>
    </div>

    <div class="sec">
      <span class="tt">אופן ההחתמה</span>
      <div class="radio on" id="rRemote" onclick="setMode('remote')">
        <div class="dot"></div><span class="lb">שליחה לחתימה ב-SMS ו-WhatsApp</span></div>
      <div class="radio" id="rLocal" onclick="setMode('local')">
        <div class="dot"></div><span class="lb">חתימה במקום (על המכשיר הזה)</span></div>
      <div class="hint" id="modeHint">הלקוח יקבל קישור, ימלא ת"ז ויחתום במכשירו. המסמך החתום יתווסף לשורת החתימה.</div>
      <div id="padWrap">
        <canvas id="pad"></canvas>
        <button class="padClear" onclick="clearPad()">נקה חתימה</button>
      </div>
    </div>
  </main>

  <div class="cta"><button id="go" onclick="submitSign()">שלח לחתימה בוואטסאפ וב-SMS</button></div>
  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function GET(u){ return fetch(u, {headers:{'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function POST(u, d){
  return fetch(u, {method:'POST', headers:{'X-Auth-Token': TOK, 'Content-Type': 'application/json'},
    body: JSON.stringify(d || {})}).then(function(r){ return r.json(); });
}
function el(id){ return document.getElementById(id); }
function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function toast(m){
  var t = el('toast'); t.textContent = m; t.style.opacity = '1';
  clearTimeout(t._h); t._h = setTimeout(function(){ t.style.opacity = '0'; }, 2200);
}
function openSheet(html){
  el('sheet').innerHTML = '<div class="grip"></div>' + html;
  el('sheet').style.display = 'flex'; el('ovl').style.display = 'block';
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none'; }

var KIND = (location.search.indexOf('type=owner') >= 0 || location.search.indexOf('type=seller') >= 0) ? 'owner' : 'buyer';
var AGENT = '', MODE = 'remote', PROPS = [], BUSY = false;
var DEALS_DEF = KIND === 'buyer'
  ? [{k: 'buy', lb: 'קניה — עמלה', on: true, val: '2', un: '%'},
     {k: 'rent', lb: 'שכירות — עמלה', on: false, val: '1', un: 'חודשים'}]
  : [{k: 'sale', lb: 'מכירה — עמלה', on: true, val: '2', un: '%'},
     {k: 'rent', lb: 'השכרה — עמלה', on: false, val: '1', un: 'חודשים'},
     {k: 'excl', lb: 'בלעדיות — תקופה', on: true, val: '', un: '', from: '', to: '', mo: 6}];

function dstr(d){
  return ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + '/' + d.getFullYear();
}
function exclPeriod(i, months){
  var f = new Date(), t = new Date();
  t.setMonth(t.getMonth() + months);
  DEALS_DEF[i].from = dstr(f); DEALS_DEF[i].to = dstr(t); DEALS_DEF[i].mo = months;
  renderDeals();
}
// ברירת מחדל לבלעדיות: 6 חודשים מהיום (העריכה הידנית של התאריכים נשארת פתוחה)
(function(){
  DEALS_DEF.forEach(function(d, i){ if (d.k === 'excl') exclPeriod._init = i; });
  if (exclPeriod._init != null){
    var i = exclPeriod._init, f = new Date(), t = new Date();
    t.setMonth(t.getMonth() + 6);
    DEALS_DEF[i].from = dstr(f); DEALS_DEF[i].to = dstr(t);
  }
})();

function renderDeals(){
  el('dealRows').innerHTML = DEALS_DEF.map(function(d, i){
    var inputs = d.k === 'excl'
      ? '<div class="in" style="flex-direction:column;align-items:flex-end;gap:6px">' +
        '<div style="display:flex;gap:5px">' + [3, 6].map(function(m){
          return '<button type="button" class="moChip' + (d.mo === m ? ' on' : '') + '" onclick="exclPeriod(' + i + ',' + m + ')">' + m + ' ח׳</button>';
        }).join('') + '</div>' +
        '<div style="display:flex;gap:6px">' +
        '<input style="width:88px" placeholder="מ- 07/07/26" value="' + esc(d.from) + '" onchange="DEALS_DEF[' + i + '].from=this.value;DEALS_DEF[' + i + '].mo=0">' +
        '<input style="width:88px" placeholder="עד 07/01/27" value="' + esc(d.to) + '" onchange="DEALS_DEF[' + i + '].to=this.value;DEALS_DEF[' + i + '].mo=0"></div></div>'
      : '<div class="in"><input inputmode="decimal" value="' + esc(d.val) + '" onchange="DEALS_DEF[' + i + '].val=this.value">' +
        '<span class="un">' + d.un + '</span></div>';
    return '<div class="dRow' + (d.on ? ' on' : ' off') + '" style="' + (i ? 'margin-top:9px' : '') + '">' +
      '<div class="r" onclick="DEALS_DEF[' + i + '].on=!DEALS_DEF[' + i + '].on;renderDeals()">' +
      '<div class="cb"><svg width="12" height="10" viewBox="0 0 12 10"><path d="M1.5 5l3 3 6-6.5" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg></div>' +
      '<span class="lb">' + d.lb + '</span></div>' + inputs + '</div>';
  }).join('');
}
function renderProps(){
  el('propList').innerHTML = PROPS.map(function(p, i){
    return '<div class="propRow" style="' + (i ? 'margin-top:8px' : '') + '"><div class="mid2"><div class="a">' + esc(p.addr) + '</div>' +
      (p.price ? '<div class="p">₪' + esc(p.price) + '</div>' : '') + '</div>' +
      '<button class="x" onclick="PROPS.splice(' + i + ',1);renderProps()">' +
      '<svg width="10" height="10" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#C24040" stroke-width="1.8" stroke-linecap="round"/></svg></button></div>';
  }).join('') || '<div style="font-size:12px;color:#8B8F99">עוד לא נבחר נכס</div>';
}
function addPropFree(){
  openSheet('<h3>הוספת נכס</h3>' +
    '<div class="fld"><span>כתובת (רחוב, עיר) *</span><input id="npAddr"></div>' +
    '<div class="fld"><span>מחיר מבוקש</span><input id="npPrice" inputmode="numeric"></div>' +
    '<button class="btnSec" style="background:#2E6BD6;color:#fff;border:0" onclick="addPropGo()">הוסף</button>' +
    '<button class="btnSec" onclick="closeSheet()">ביטול</button>');
}
function addPropGo(){
  var a = el('npAddr').value.trim();
  if (!a){ toast('כתובת — חובה'); return; }
  PROPS.push({addr: a, price: el('npPrice').value.trim()});
  closeSheet(); renderProps();
}
function pickProp(){
  openSheet('<h3>הנכסים שלי</h3><div id="pkList" style="display:flex;flex-direction:column;gap:8px">' +
    '<div style="text-align:center;color:#8B8F99;font-size:13px;padding:12px 0">טוען…</div></div>' +
    '<button class="btnSec" onclick="closeSheet()">ביטול</button>');
  GET('/api/sign/properties').then(function(j){
    var rows = (j && (j.properties || j.items || j.results)) || [];
    el('pkList').innerHTML = rows.slice(0, 40).map(function(p){
      var addr = p.address || p.addr || '';
      var price = String(p.price || '');
      return '<div class="pick" onclick=\'pickGo(' + JSON.stringify(JSON.stringify({a: addr, p: price})) + ')\'>' +
        '<span class="a">' + esc(addr) + '</span><span class="p">' + esc(price ? '₪' + price : '') + '</span></div>';
    }).join('') || '<div style="text-align:center;color:#8B8F99;font-size:13px;padding:10px 0">אין מודעות משויכות אליך — הוסף נכס ידנית</div>';
  }).catch(function(){});
}
function pickGo(js){
  var p = JSON.parse(js);
  PROPS.push({addr: p.a, price: p.p});
  closeSheet(); renderProps();
}
function validILID(v){
  var s = (v || '').replace(/\D/g, '');
  if (!s || s.length > 9) return false;
  s = ('000000000' + s).slice(-9);
  var t = 0;
  for (var i = 0; i < 9; i++){
    var d = parseInt(s[i], 10) * (i % 2 === 0 ? 1 : 2);
    t += d > 9 ? d - 9 : d;
  }
  return t % 10 === 0;
}
function checkId(){
  var v = el('cId').value.trim(), m = el('idMsg');
  if (!v){ m.textContent = ''; return; }
  var ok = validILID(v);
  m.textContent = ok ? '✓ תעודת זהות תקינה' : '✗ תעודת זהות לא תקינה';
  m.style.color = ok ? '#1FAF5E' : '#C24040';
}
function setMode(m){
  MODE = m;
  el('rRemote').classList.toggle('on', m === 'remote');
  el('rLocal').classList.toggle('on', m === 'local');
  el('padWrap').style.display = m === 'local' ? 'flex' : 'none';
  el('idReq').style.display = m === 'local' ? 'inline' : 'none';
  el('modeHint').textContent = m === 'local'
    ? 'הלקוח מזין ת"ז וחותם באצבע על המסך — המסמך נשמר מיד עם קישור לצפייה.'
    : 'הלקוח יקבל קישור, ימלא ת"ז ויחתום במכשירו. המסמך החתום יתווסף לשורת החתימה.';
  el('go').textContent = m === 'local' ? 'החתם עכשיו' : 'שלח לחתימה בוואטסאפ וב-SMS';
  if (m === 'local') initPad();
}
var padInit = false;
function initPad(){
  if (padInit) return;
  padInit = true;
  var c = el('pad'), r = c.getBoundingClientRect();
  c.width = r.width || 340; c.height = 160;
  var x = c.getContext('2d');
  x.lineWidth = 2.2; x.lineCap = 'round'; x.lineJoin = 'round'; x.strokeStyle = '#1E3A5F';
  var down = false;
  function pos(e){
    var b = c.getBoundingClientRect(), t = (e.touches && e.touches[0]) || e;
    return {x: t.clientX - b.left, y: t.clientY - b.top};
  }
  function st(e){ down = true; var p = pos(e); x.beginPath(); x.moveTo(p.x, p.y); e.preventDefault(); }
  function mv(e){ if (!down) return; var p = pos(e); x.lineTo(p.x, p.y); x.stroke(); c.dataset.signed = '1'; e.preventDefault(); }
  c.onmousedown = st; c.onmousemove = mv; c.onmouseup = c.onmouseleave = function(){ down = false; };
  c.ontouchstart = st; c.ontouchmove = mv; c.ontouchend = function(){ down = false; };
}
function clearPad(){
  var c = el('pad');
  c.getContext('2d').clearRect(0, 0, c.width, c.height);
  c.dataset.signed = '';
}
function todayStr(){
  var d = new Date();
  return ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + '/' + d.getFullYear();
}
/* החלפות בתבנית ההסכם — זהה לאפליקציה הקיימת */
function fill(body, v){
  var addr = PROPS.map(function(p){ return p.addr; }).join(', ');
  var price = PROPS.map(function(p){ return p.price; }).filter(Boolean).join(' / ');
  var map = {
    'SALE_FEE': v.fee ? v.fee + '%' : '____',
    'RENT_FEE': v.months ? v.months + ' חודשי שכירות' : '____',
    'EXCLUSIVE_FROM': v.exfrom || '____', 'EXCLUSIVE_TO': v.exto || '____',
    'CON_REF_ID': '____', 'CON_REF_DATE': todayStr(),
    '{תאריך}': todayStr(), '{שם_הסוכן}': AGENT, '{שם_הלקוח}': v.cname,
    '{טלפון_הלקוח}': v.cphone, '{תז_הלקוח}': v.cid || '____',
    '{כתובת_הנכס}': addr, '{מחיר_מבוקש}': price,
    '{עמלת_קניה}': v.fee || '', '{עמלת_שכירות}': v.months || ''
  };
  var out = String(body || '');
  Object.keys(map).forEach(function(k){ out = out.split(k).join(map[k]); });
  return out;
}
function selectedDocs(){
  var on = {};
  DEALS_DEF.forEach(function(d){ if (d.on) on[d.k] = d; });
  var picks = [];
  if (KIND === 'buyer'){
    if (on.buy && on.rent) picks.push(['buyer_both', 'CLIENT_SALE']);
    else if (on.buy) picks.push(['buyer_buy', 'CLIENT_SALE']);
    else if (on.rent) picks.push(['buyer_rent', 'CLIENT_RENT']);
  } else {
    if (on.excl) picks.push(['exclusive', 'OWNER_EXCLUSIVE']);
    else if (on.sale && on.rent) picks.push(['seller_both', 'OWNER_SALE']);
    else if (on.sale) picks.push(['seller_sell', 'OWNER_SALE']);
    else if (on.rent) picks.push(['seller_both', 'OWNER_RENT']);
  }
  return picks;
}
function submitSign(){
  if (BUSY) return;
  var cname = el('cName').value.trim(), cphone = el('cPhone').value.trim(), cid = el('cId').value.trim();
  if (!cname || !cphone){ toast('שם וטלפון — חובה'); return; }
  if (!PROPS.length){ toast('הוסף לפחות נכס אחד'); return; }
  var picks = selectedDocs();
  if (!picks.length){ toast('בחר סוג עסקה'); return; }
  var exclRow = null, feeRow = null, mRow = null;
  DEALS_DEF.forEach(function(d){
    if (!d.on) return;
    if (d.k === 'excl') exclRow = d;
    else if (d.k === 'rent') mRow = d;
    else feeRow = d;
  });
  if (exclRow && (!exclRow.from || !exclRow.to)){ toast('בבלעדיות — מלא תקופה (מ/עד)'); return; }
  if (MODE === 'local'){
    if (!validILID(cid)){ toast('ת"ז לא תקינה — חובה בחתימה במקום'); return; }
    if (!el('pad').dataset.signed){ toast('חסרה חתימה על המסך'); return; }
  }
  var v = {cname: cname, cphone: cphone, cid: cid,
           fee: feeRow ? feeRow.val : '', months: mRow ? mRow.val : '',
           exfrom: exclRow ? exclRow.from : '', exto: exclRow ? exclRow.to : ''};
  BUSY = true; el('go').disabled = true;
  Promise.all(picks.map(function(pk){
    return GET('/api/sign/contract?type=' + pk[0]);
  })).then(function(cons){
    var docs = picks.map(function(pk, i){
      return {deal_type: pk[1], title: (cons[i] && cons[i].title) || '',
              body: fill((cons[i] && cons[i].body) || '', v)};
    });
    var addr = PROPS.map(function(p){ return p.addr; }).join(PROPS.length > 1 ? ' | ' : '');
    var header = 'פרטי הלקוח: ' + cname + (cid ? ' · ת"ז ' + cid : '') + ' · ' + cphone +
      ' | סוכן: ' + AGENT + ' · ' + todayStr() +
      ' | נכס: ' + PROPS.map(function(p){ return p.addr + (p.price ? ' (₪' + p.price + ')' : ''); }).join(' | ');
    var done = function(j, txt){
      BUSY = false; el('go').disabled = false;
      if (!j.ok){ toast('שגיאה — נסה שוב'); return; }
      toast(txt);
      setTimeout(function(){ location.href = '/v2/sigs'; }, 1200);
    };
    if (MODE === 'remote')
      return POST('/api/sign/send_remote', {docs: docs, client: cname, phone: cphone,
        address: addr, notes: '', header: header}).then(function(j){
          done(j, 'נשלח לחתימה' + (j.wa ? ' · וואטסאפ' : '') + (j.sms ? ' · SMS' : ''));
        });
    var sig = el('pad').toDataURL('image/png');
    return POST('/api/sign/submit', {docs: docs, client: cname, cid: cid, phone: cphone,
      address: addr, notes: '', signature: sig, header: header}).then(function(j){
        done(j, 'נחתם ונשמר');
      });
  }).catch(function(){ BUSY = false; el('go').disabled = false; toast('שגיאה'); });
}
(function(){
  el('pgT').textContent = KIND === 'buyer' ? 'החתמת מתעניין' : 'החתמת בעל נכס';
  el('propNote').textContent = KIND === 'buyer' ? 'אפשר יותר מנכס אחד' : 'הנכס של בעל הנכס';
  renderDeals(); renderProps();
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    AGENT = j.name || '';
  }).catch(function(){ location.replace('/v2'); });
  try{
    var pre = JSON.parse(localStorage.getItem('v2signPre') || 'null');
    localStorage.removeItem('v2signPre');
    if (pre){
      if (pre.client) el('cName').value = pre.client;
      if (pre.phone) el('cPhone').value = pre.phone;
      if (pre.addr){ PROPS.push({addr: pre.addr, price: pre.price || ''}); renderProps(); }
      if (pre.client){
        el('preTx').textContent = pre.client + (pre.phone ? ' · ' + pre.phone : '');
        el('preChip').style.display = 'flex';
        el('pgS').textContent = pre.client;
      }
    }
  }catch(e){}
})();
</script></body></html>'''



# ── פגישות ופולו-אפ (עיצוב 21a) — על /api/newborn/meetings הקיים ────────────────
V2_MEETS_HTML = r"""<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>פגישות ופולו-אפ</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{height:100%;overflow-x:hidden}
  /* דסקטופ: חזרה לגלילת חלון (המובייל נשאר עם נעילת iOS: main גולל) */
  @media(min-width:768px){html,body{height:auto}body{min-height:100vh}main{overflow:visible}}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;color:#1E3A5F;display:flex;flex-direction:column;max-width:100vw}
  header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 6px}
  header .av{width:42px;height:42px;border-radius:50%;background:#1E3A5F;color:#fff;display:flex;
      align-items:center;justify-content:center;font-size:16px;font-weight:700}
  header .lg{height:44px;max-width:150px;object-fit:contain}
  header .bk{width:42px;height:42px;border-radius:14px;background:#fff;border:1px solid #E9E4D8;display:flex;
      align-items:center;justify-content:center;cursor:pointer}
  @media (min-width:700px){
    header,main,nav,#impBar{width:100%;max-width:600px;margin-left:auto;margin-right:auto}
    nav{border:1px solid #E9E4D8;border-bottom:0;border-radius:22px 22px 0 0}
  }
  /* main הוא הגולל כאן — גלילה מרוכבת ב-GPU כדי שהניווט הקבוע לא ירצד ב-iOS (בטוח: אין חלון להתחרות) */
  main{flex:1;padding:4px 16px 14px;display:flex;flex-direction:column;gap:13px;overflow:auto;padding-bottom:124px;-webkit-overflow-scrolling:touch}
  .hd2{display:flex;align-items:center;gap:10px}
  .hd2 .ic{width:36px;height:36px;border-radius:11px;background:#EAF0FA;display:flex;align-items:center;justify-content:center}
  .hd2 h1{font-size:19px;font-weight:800}
  .hd2 .cnt{font-size:12.5px;font-weight:700;color:#2E6BD6;background:#EAF0FA;padding:3px 10px;border-radius:999px}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px}
  .sg{flex:1;text-align:center;padding:8px 0;font-size:13px;font-weight:700;color:#5B6472;border-radius:10px;cursor:pointer}
  .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .sync{display:flex;align-items:center;gap:7px}
  .sync i{width:7px;height:7px;border-radius:50%;background:#1FAF5E;display:block}
  .sync span{font-size:11.5px;font-weight:600;color:#8B8F99}
  .card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:6px 15px;display:flex;flex-direction:column}
  .mt{display:flex;align-items:center;gap:11px;padding:11px 0}
  .mt + .mt{border-top:1px solid #F0EDE3}
  .mt .tile{width:40px;height:40px;border-radius:13px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .mt .tt{font-size:14px;font-weight:700;line-height:1.3}
  .mt .sb{font-size:12px;color:#8B8F99;margin-top:1px}
  .mt .when{font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;white-space:nowrap}
  .mt .acts{display:flex;gap:6px;margin-top:6px}
  .mt .sq{width:32px;height:32px;border-radius:10px;border:none;display:flex;align-items:center;justify-content:center;
      cursor:pointer;padding:0}
  .late{background:#FBEDED;border-radius:14px;padding:2px 13px;display:flex;flex-direction:column}
  .late .mt + .mt{border-top:1px solid rgba(194,64,64,.12)}
  .late .tile{background:#fff}
  .late .sb{color:#C24040;font-weight:700}
  .grpT{font-size:13px;font-weight:800;color:#B8902F;letter-spacing:.05em;padding:2px 2px 0}
  .empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:30px 18px;
      background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06)}
  .empty .ic{width:72px;height:72px;border-radius:50%;background:#F6EEDB;display:flex;align-items:center;justify-content:center}
  .empty .t{font-size:15px;font-weight:800}
  .empty .s{font-size:12.5px;color:#8B8F99;line-height:1.5;max-width:280px}
  .addB{position:fixed;bottom:calc(env(safe-area-inset-bottom,0px) + 92px);left:18px;z-index:35;width:52px;height:52px;
      border-radius:50%;background:#2E6BD6;border:none;box-shadow:0 8px 20px rgba(46,107,214,.35);display:flex;
      align-items:center;justify-content:center;cursor:pointer}
  nav{position:fixed;bottom:0;left:0;right:0;z-index:40;background:#fff;border-top:1px solid #E9E4D8;padding:10px 6px calc(env(safe-area-inset-bottom,0px) + 12px);
      display:flex;justify-content:space-around;align-items:flex-end}
  nav .it{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;font-size:10.5px;
      font-weight:600;color:#9AA0AB;cursor:pointer;position:relative}
  nav .home{width:44px;height:44px;margin-top:-18px;border-radius:15px;background:#1E3A5F;
      box-shadow:0 6px 14px rgba(30,58,95,.3);display:flex;align-items:center;justify-content:center}
  nav .badge{position:absolute;top:-13px;z-index:2;background:#C29435;color:#fff;font-size:10px;font-weight:800;
      padding:1px 8px;border-radius:999px;display:none}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:30}
  #sheet{position:fixed;left:0;right:0;bottom:calc(env(safe-area-inset-bottom,0px) + 74px);z-index:31;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:12px 18px 16px;
      display:none;flex-direction:column;gap:12px;max-height:82vh;overflow:auto}
  #sheet .grip{width:44px;height:5px;border-radius:999px;background:#E2DDD0;align-self:center}
  #sheet h3{font-size:19px;font-weight:800}
  @media (min-width:700px){ #sheet{max-width:600px;margin-left:auto;margin-right:auto} }
  .btn{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:13px;padding:13px 0;width:100%;
      font-size:14.5px;font-weight:700;border:0;cursor:pointer;font-family:inherit;min-height:46px}
  .btn-gold{background:#C29435;color:#fff;box-shadow:0 4px 12px rgba(194,148,53,.25)}
  .btn-sec{background:#fff;color:#5B6472;border:1.5px solid #DCD6C8}
  .fld2{display:flex;flex-direction:column;gap:5px;min-width:0}
  .fld2 span{font-size:11.5px;font-weight:700;color:#5B6472}
  .fld2 input,.fld2 textarea,.fld2 select{background:#fff;border:1.5px solid #DCD6C8;border-radius:13px;padding:12px 13px;
      font-size:14px;font-family:inherit;outline:none;color:#1E3A5F;width:100%;min-width:0;max-width:100%}
  /* iOS: לשדה datetime-local יש רוחב מינימלי משלו שגורם לגלישה רוחבית — מנטרלים */
  .fld2 input[type="datetime-local"],.fld2 input[type="date"]{-webkit-appearance:none;appearance:none;display:block;min-height:47px;text-align:right}
  #sheet{overflow-x:hidden;overscroll-behavior:contain}
  #ovl{touch-action:none}
  .stSeg{display:flex;background:#EBE8DD;border-radius:12px;padding:4px;gap:4px}
  .stSeg div{flex:1;text-align:center;padding:8px 0;font-size:13px;font-weight:700;color:#5B6472;border-radius:9px;cursor:pointer}
  .stSeg div.on{color:#fff;background:#2E6BD6}
  #toast{position:fixed;bottom:110px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:600;padding:10px 18px;border-radius:12px;opacity:0;transition:opacity .25s;
      pointer-events:none;z-index:100;white-space:nowrap}
</style></head><body>

  <header>
    <div class="bk" onclick="history.length > 1 ? history.back() : location.href='/v2/home'">
      <svg width="16" height="16" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <img class="lg" src="/assets/logo" alt="" onerror="this.style.display='none'">
    <div class="av" id="avatarTx"></div>
  </header>

  <main>
    <div class="hd2">
      <div class="ic"><svg width="16" height="16" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#2E6BD6" stroke-width="1.6" stroke-linecap="round"/></svg></div>
      <h1>פגישות ופולו-אפ</h1>
      <div class="cnt" id="cnt">—</div>
    </div>

    <div class="segs">
      <div class="sg on" data-f="today" onclick="setFilter(this)">היום</div>
      <div class="sg" data-f="week" onclick="setFilter(this)">השבוע</div>
      <div class="sg" data-f="all" onclick="setFilter(this)">הכל</div>
    </div>

    <div class="sync"><i></i><span>כל פגישה שנקבעת נרשמת גם ביומן Google של הסוכן</span></div>

    <div id="list"></div>
  </main>

  <button class="addB" onclick="newMeet()" aria-label="קביעת פגישה חדשה">
    <svg width="20" height="20" viewBox="0 0 16 16"><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>
  </button>

  <nav>
    <div class="it" onclick="location.href='/v2/calls'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>שיחות</div>
    <div class="it" onclick="location.href='/v2/buyers'"><svg width="21" height="21" viewBox="0 0 22 22"><circle cx="11" cy="7.5" r="3.5" fill="none" stroke="#9AA0AB" stroke-width="1.8"/><path d="M4.5 19c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linecap="round"/></svg>קונים</div>
    <div class="it" onclick="location.href='/v2/home'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M3 10.5L11 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H4a1 1 0 0 1-1-1z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>בית</div>
    <div class="it" onclick="location.href='/v2/sigs'"><svg width="21" height="21" viewBox="0 0 22 22"><path d="M14 3l4 4L8 17l-4.8 1L4 13z" fill="none" stroke="#9AA0AB" stroke-width="1.8" stroke-linejoin="round"/></svg>חתימות</div>
    <div class="it" onclick="location.href='/v2/newborn'"><svg width="24" height="21" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>נכס נולד</div>
    <div class="it dk" onclick="location.href='/v2/deals'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="1.5" width="12" height="13" rx="2.5" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M5.5 5.5h5M5.5 8.5h5M5.5 11.5h3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>תהליכים ועסקאות</div>
    <div class="it dk" onclick="location.href='/v2/meets'"><svg width="21" height="21" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#9AA0AB" stroke-width="1.5"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#9AA0AB" stroke-width="1.5" stroke-linecap="round"/></svg>יומן ופולו-אפ</div>
  </nav>

  <div id="ovl" onclick="closeSheet()"></div>
  <div id="sheet"></div>
  <div id="toast"></div>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function GET(u){ return fetch(u, {headers:{'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function POST(u, d){
  return fetch(u, {method:'POST', headers:{'X-Auth-Token': TOK, 'Content-Type':'application/json'},
    body: JSON.stringify(d)}).then(function(r){ return r.json(); });
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

function openSheet(html){
  el('sheet').innerHTML = '<div class="grip"></div>' + html;
  el('sheet').style.display = 'flex'; el('ovl').style.display = 'block';
  document.documentElement.style.overflow = 'hidden';
  document.body.style.overflow = 'hidden';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = 'hidden'; })();
}
function closeSheet(){ el('sheet').style.display = 'none'; el('ovl').style.display = 'none';
  document.documentElement.style.overflow = '';
  document.body.style.overflow = '';
  (function(){ var m = document.querySelector('main'); if (m) m.style.overflow = ''; })(); }

var MEETS = [], FILTER = 'today', MULTI = false;
try{ FILTER = localStorage.getItem('v2st:meets') || 'today'; }catch(e){}

/* תאריכי הפגישות מגיעים בכמה צורות: yyyy-mm-dd / dd/mm/yyyy, עם או בלי שעה, בכל סדר */
function parseWhen(s){
  s = String(s || '').trim();
  var time = '';
  var tm = /(\d{1,2}):(\d{2})/.exec(s);
  if (tm) time = ('0' + tm[1]).slice(-2) + ':' + tm[2];
  var d = null, m;
  if ((m = /(\d{4})-(\d{1,2})-(\d{1,2})/.exec(s))) d = new Date(+m[1], +m[2] - 1, +m[3]);
  else if ((m = /(\d{1,2})[\/.](\d{1,2})[\/.](\d{2,4})/.exec(s))){
    var y = +m[3]; if (y < 100) y += 2000;
    d = new Date(y, +m[2] - 1, +m[1]);
  }
  return {d: d, time: time};
}
function dayDiff(d){
  var t = new Date(); t.setHours(0,0,0,0);
  var x = new Date(d); x.setHours(0,0,0,0);
  return Math.round((x - t) / 86400000);
}

var CAL_SVG = '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="#2E6BD6" stroke-width="1.6"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="#2E6BD6" stroke-width="1.6" stroke-linecap="round"/></svg>';
var FU_SVG = '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M3 6.5a5 5 0 0 1 9-2M13 9.5a5 5 0 0 1-9 2" fill="none" stroke="#B8902F" stroke-width="1.6" stroke-linecap="round"/><path d="M12 1.5v3h-3M4 14.5v-3h3" fill="none" stroke="#B8902F" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
var LATE_SVG = '<svg width="15" height="15" viewBox="0 0 16 16"><path d="M3 6.5a5 5 0 0 1 9-2M13 9.5a5 5 0 0 1-9 2" fill="none" stroke="#C24040" stroke-width="1.6" stroke-linecap="round"/><path d="M12 1.5v3h-3M4 14.5v-3h3" fill="none" stroke="#C24040" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function itemRow(m, i){
  var meet = m.status === 'meeting';
  var w = parseWhen(m.date);
  var dd = w.d ? dayDiff(w.d) : 99;
  var late = w.d && dd < 0;
  var whenTx = late ? ((w.d.getDate()) + '/' + (w.d.getMonth() + 1) + (w.time ? ' ' + w.time : ''))
    : dd === 0 ? (w.time || 'היום') : dd === 1 ? ('מחר' + (w.time ? ' ' + w.time : ''))
    : w.d ? (('0' + w.d.getDate()).slice(-2) + '/' + ('0' + (w.d.getMonth() + 1)).slice(-2) + (w.time ? ' ' + w.time : '')) : '';
  var sb = late ? (['באיחור', m.label || '', whenTx, MULTI ? m.agent : ''].filter(Boolean).join(' · '))
    : ['נכס נולד', m.owner ? ('בעל הנכס: ' + m.owner) : '', MULTI ? m.agent : ''].filter(Boolean).join(' · ');
  var acts = '<div class="acts">' +
    (m.ophone ? '<button class="sq" style="background:#EAF0FA" onclick="location.href=\'tel:' + esc(m.ophone) + '\'" aria-label="חיוג">' +
      '<svg width="13" height="13" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#2E6BD6" stroke-width="1.7" stroke-linejoin="round"/></svg></button>' : '') +
    (m.wa ? '<button class="sq" style="background:#E7F7EE" onclick="window.open(\'https://wa.me/' + esc(m.wa) + '\',\'_blank\')" aria-label="וואטסאפ">' +
      '<svg width="13" height="13" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#1FAF5E" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' : '') +
    '<button class="sq" style="background:#F5F3EC" onclick="editMeet(' + i + ')" aria-label="עריכה">' +
      '<svg width="12" height="12" viewBox="0 0 16 16"><path d="M10.5 2.5l3 3L6 13l-3.7.7L3 10z" fill="none" stroke="#5B6472" stroke-width="1.6" stroke-linejoin="round"/></svg></button>' +
    '<button class="sq" style="background:#E7F7EE" onclick="doneMeet(' + i + ')" aria-label="בוצע">' +
      '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M2.5 8.5l3.5 3.5 7-8" fill="none" stroke="#1FAF5E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>';
  return '<div class="mt">' +
    '<div class="tile" style="background:' + (late ? '#fff' : meet ? '#EAF0FA' : '#F6EEDB') + '">' +
    (late ? LATE_SVG : meet ? CAL_SVG : FU_SVG) + '</div>' +
    '<div style="flex:1;min-width:0"><div class="tt">' + esc((m.label || (meet ? 'פגישה' : 'פולו-אפ')) + ': ' + (m.addr || '')) + '</div>' +
    '<div class="sb">' + esc(sb) + '</div>' + acts + '</div>' +
    (whenTx && !late ? '<div class="when" style="' + (meet ? 'color:#2E6BD6;background:#EAF0FA' : 'color:#B8902F;background:#F6EEDB') + '">' + esc(whenTx) + '</div>' : '') +
    '</div>';
}
function render(){
  var withD = MEETS.map(function(m, i){
    var w = parseWhen(m.date);
    return {m: m, i: i, d: w.d, dd: w.d ? dayDiff(w.d) : 99};
  });
  var late = withD.filter(function(x){ return x.d && x.dd < 0; });
  var rest = withD.filter(function(x){ return !(x.d && x.dd < 0); });
  if (FILTER === 'today') rest = rest.filter(function(x){ return x.dd === 0; });
  else if (FILTER === 'week') rest = rest.filter(function(x){ return x.dd <= 7; });
  rest.sort(function(a, b){ return (a.d || 0) - (b.d || 0); });
  el('cnt').textContent = late.length + rest.length;
  var h = '';
  if (late.length){
    h += '<div class="late" style="margin-bottom:13px">' +
      late.map(function(x){ return itemRow(x.m, x.i); }).join('') + '</div>';
  }
  if (rest.length){
    h += '<div class="card">' + rest.map(function(x){ return itemRow(x.m, x.i); }).join('') + '</div>';
  }
  el('list').innerHTML = h ||
    '<div class="empty"><div class="ic"><svg width="26" height="26" viewBox="0 0 16 16"><path d="M2.5 8.5l3.5 3.5 7-8" fill="none" stroke="#C29435" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>' +
    '<div class="t">' + (FILTER === 'today' ? 'אין פגישות להיום' : 'הכל מטופל') + '</div>' +
    '<div class="s">פגישה או פולו-אפ נקבעים מכרטיס נכס במסך נכס נולד — ויופיעו כאן וביומן</div></div>';
}
function setFilter(node){
  FILTER = node.getAttribute('data-f');
  try{ localStorage.setItem('v2st:meets', FILTER); }catch(e){}
  var sgs = node.parentNode.children;
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i] === node);
  render();
}
var MYNAME = '', AG_OPTS = [];
function dt15Opts(sel){
  var ts = [], h, m;
  for (h = 0; h < 24; h++) for (m = 0; m < 60; m += 15)
    ts.push(('0' + h).slice(-2) + ':' + ('0' + m).slice(-2));
  if (sel && ts.indexOf(sel) < 0){ ts.push(sel); ts.sort(); }   // מועד קיים שאינו על רבע שעה — נשמר
  return ts.map(function(t){
    return '<option value="' + t + '"' + (t === sel ? ' selected' : '') + '>' + t + '</option>';
  }).join('');
}
function dtNextQ(){
  var d = new Date();
  d.setMinutes(d.getMinutes() + ((15 - d.getMinutes() % 15) % 15), 0, 0);
  return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
}
function dtJoin(dId, tId){
  var dv = el(dId).value;
  return dv ? dv + 'T' + (el(tId).value || '10:00') : '';
}
function newMeet(){
  var agSel = AG_OPTS.length
    ? '<div class="fld2"><span>עבור סוכן</span><select id="nmAg" style="background:#fff;border:1.5px solid #DCD6C8;' +
      'border-radius:13px;padding:12px 13px;font-size:14px;font-family:inherit;color:#1E3A5F;width:100%">' +
      '<option value="">עליי (' + esc(MYNAME) + ')</option>' +
      AG_OPTS.map(function(a){ return '<option value="' + esc(a) + '">' + esc(a) + '</option>'; }).join('') +
      '</select></div>'
    : '';
  openSheet('<div style="display:flex;align-items:center;justify-content:space-between">' +
    '<h3 style="margin:0">פגישה / פולו-אפ חדש</h3>' +
    '<button onclick="closeSheet()" aria-label="סגירה" style="width:36px;height:36px;border-radius:50%;background:#EFEBDD;' +
    'border:none;display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer">' +
    '<svg width="12" height="12" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round"/></svg></button></div>' +
    '<div class="stSeg"><div id="nmMeet" class="on" onclick="nmType(\'meeting\')">פגישה</div>' +
    '<div id="nmFu" onclick="nmType(\'followup\')">פולו-אפ</div></div>' +
    '<div class="fld2"><span>כתובת / נושא *</span><input id="nmAddr" placeholder="למשל: יקינטון 18, קרית ביאליק"></div>' +
    '<div style="display:flex;gap:8px">' +
    '<div class="fld2" style="flex:1"><span>שם (אופציונלי)</span><input id="nmOwner" placeholder="בעל הנכס / הלקוח"></div>' +
    '<div class="fld2" style="flex:1"><span>טלפון (אופציונלי)</span><input id="nmPhone" type="tel" placeholder="05X-XXXXXXX"></div></div>' +
    agSel +
    '<div class="fld2"><span>מועד *</span><div style="display:flex;gap:8px">' +
    '<input id="nmDtD" type="date" style="flex:1.2">' +
    '<select id="nmDtT" style="flex:1">' + dt15Opts(dtNextQ()) + '</select></div></div>' +
    '<div class="fld2"><span>הערה</span><textarea id="nmNote" rows="2" placeholder="הערה במלל חופשי (אופציונלי)"></textarea></div>' +
    '<div style="font-size:11.5px;color:#8B8F99">נשמר גם ביומן Google (אם מחובר)</div>' +
    '<button class="btn btn-gold" onclick="saveNewMeet()">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
  el('sheet')._nst = 'meeting';
}
function nmType(st){
  el('sheet')._nst = st;
  el('nmMeet').classList.toggle('on', st === 'meeting');
  el('nmFu').classList.toggle('on', st === 'followup');
}
function saveNewMeet(){
  var addr = el('nmAddr').value.trim(), dt = dtJoin('nmDtD', 'nmDtT');
  if (!addr){ toast('כתובת או נושא — חובה'); return; }
  if (!dt){ toast('בחר מועד'); return; }
  POST('/api/newborn/status', {
    key: 'manual:' + Date.now(), addr: addr, price: '',
    phone: el('nmPhone').value.trim(), owner: el('nmOwner').value.trim(),
    status: el('sheet')._nst || 'meeting', date: dt,
    agent: (el('nmAg') && el('nmAg').value) || '',
    note: el('nmNote').value.trim()
  }).then(function(j){
    if (!j.ok){ toast('שגיאה בשמירה'); return; }
    closeSheet();
    toast((el('sheet')._nst === 'followup' ? 'הפולו-אפ נקבע' : 'הפגישה נקבעה') + (j.calendar ? ' + נשמר ביומן' : ''));
    load();
  });
}
function editMeet(i){
  var m = MEETS[i]; if (!m) return;
  var w = parseWhen(m.date);
  var dVal = '', tVal = '10:00';
  if (w.d){
    dVal = w.d.getFullYear() + '-' + ('0' + (w.d.getMonth() + 1)).slice(-2) + '-' + ('0' + w.d.getDate()).slice(-2);
    tVal = w.time || '10:00';
  }
  var meet = m.status === 'meeting';
  openSheet('<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">' +
    '<h3 style="margin:0;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">עריכה · ' + esc(m.addr || '') + '</h3>' +
    '<button onclick="closeSheet()" aria-label="סגירה" style="width:36px;height:36px;border-radius:50%;background:#EFEBDD;' +
    'border:none;display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer">' +
    '<svg width="12" height="12" viewBox="0 0 14 14"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="#5B6472" stroke-width="1.8" stroke-linecap="round"/></svg></button></div>' +
    '<div class="stSeg"><div id="emMeet" class="' + (meet ? 'on' : '') + '" onclick="emType(this,\'meeting\')">פגישה</div>' +
    '<div id="emFu" class="' + (meet ? '' : 'on') + '" onclick="emType(this,\'followup\')">פולו-אפ</div></div>' +
    '<div class="fld2"><span>מועד</span><div style="display:flex;gap:8px">' +
    '<input id="emDtD" type="date" style="flex:1.2" value="' + dVal + '">' +
    '<select id="emDtT" style="flex:1">' + dt15Opts(tVal) + '</select></div></div>' +
    '<div class="fld2"><span>הערה</span><textarea id="emNote" rows="3" placeholder="הערה לפגישה (אופציונלי)">' + esc(m.note || '') + '</textarea></div>' +
    '<div style="font-size:11.5px;color:#8B8F99">שינוי מועד מעדכן גם את האירוע ביומן Google</div>' +
    '<button class="btn btn-gold" onclick="saveMeet(' + i + ')">שמירה</button>' +
    '<button class="btn btn-sec" onclick="closeSheet()">ביטול</button>');
  el('sheet')._st = m.status;
}
function emType(node, st){
  el('sheet')._st = st;
  el('emMeet').classList.toggle('on', st === 'meeting');
  el('emFu').classList.toggle('on', st === 'followup');
}
function saveMeet(i){
  var m = MEETS[i]; if (!m) return;
  var dt = dtJoin('emDtD', 'emDtT');
  if (!dt){ toast('בחר מועד'); return; }
  POST('/api/newborn/status/edit', {skey: m.skey || '', date: dt,
    status: el('sheet')._st || m.status, note: el('emNote').value.trim()}).then(function(j){
    if (!j.ok){ toast(j.reason === 'forbidden' ? 'אין הרשאה לעריכה' : 'שגיאה בשמירה'); return; }
    closeSheet(); toast('עודכן' + (j.calendar === false ? '' : ' + היומן')); load();
  });
}
function doneMeet(i){
  var m = MEETS[i]; if (!m) return;
  if (!confirm('לסמן כבוצע? ' + (m.label || '') + ' — ' + (m.addr || '') + ' יוסר מהרשימה ומהיומן.')) return;
  POST('/api/newborn/status/delete', {skey: m.skey || ''}).then(function(j){
    if (!j.ok){ toast('שגיאה'); return; }
    toast('סומן כבוצע'); load();
  });
}
function load(){
  return GET('/api/newborn/meetings').then(function(j){
    MEETS = (j && j.results) || [];
    try{ localStorage.setItem('v2c:meets', JSON.stringify(MEETS.slice(0, 100))); }catch(e){}
    render();
  }).catch(function(){});
}
(function(){
  try{
    var c = JSON.parse(localStorage.getItem('v2c:meets') || 'null');
    if (c){ MEETS = c; }
  }catch(e){}
  var sgs = document.querySelectorAll('.sg');
  for (var i = 0; i < sgs.length; i++) sgs[i].classList.toggle('on', sgs[i].getAttribute('data-f') === FILTER);
  if (MEETS.length) render();
  GET('/api/auth/whoami').then(function(j){
    if (!j.ok){ location.replace('/v2'); return; }
    MULTI = j.role !== 'agent';
    MYNAME = j.name || '';
    el('avatarTx').textContent = j.name ? j.name.trim()[0] : '';
    if (MULTI) GET('/api/my/agents').then(function(d){
      AG_OPTS = ((d && d.agents) || []).map(function(a){ return a.name; })
        .filter(function(a){ return a && a !== MYNAME; });
    }).catch(function(){});
    load();
  }).catch(function(){ location.replace('/v2'); });
  fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
    document.title = 'פגישות ופולו-אפ · ' + (o.name || '');
  }).catch(function(){});
})();
</script></body></html>"""



# ── חיבור משרד חדש (עתידי) — צ'קליסט המקורות המלא, עם סטטוס חי למשרד הנוכחי ─────
V2_ONBOARD_HTML = r"""<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>חיבור משרד חדש</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{height:100%}
  /* דסקטופ: חזרה לגלילת חלון (המובייל נשאר עם נעילת iOS: main גולל) */
  @media(min-width:768px){html,body{height:auto}body{min-height:100vh}main{overflow:visible}}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;color:#1E3A5F;display:flex;flex-direction:column}
  header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 6px}
  header .bk{width:42px;height:42px;border-radius:14px;background:#fff;border:1px solid #E9E4D8;display:flex;
      align-items:center;justify-content:center;cursor:pointer}
  header .lg{height:44px;max-width:150px;object-fit:contain}
  @media (min-width:700px){ header,main{width:100%;max-width:600px;margin-left:auto;margin-right:auto} }
  main{flex:1;padding:4px 16px 40px;display:flex;flex-direction:column;gap:13px;overflow:auto;-webkit-overflow-scrolling:touch}
  h1{font-size:19px;font-weight:800}
  .sub{font-size:12.5px;color:#8B8F99;line-height:1.6}
  .card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:15px 17px;
      display:flex;flex-direction:column;gap:2px}
  .card .tt{font-size:14.5px;font-weight:800;padding-bottom:6px}
  .row{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-top:1px solid #F0EDE3}
  .dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;margin-top:5px}
  .dot.ok{background:#1FAF5E}
  .dot.no{background:#C24040}
  .dot.info{background:#C29435}
  .row .nm{font-size:13.5px;font-weight:700}
  .row .ds{font-size:11.5px;color:#8B8F99;line-height:1.55;margin-top:1px}
  .steps{background:#1E3A5F;border-radius:20px;padding:16px 18px;color:#fff;display:flex;flex-direction:column;gap:9px}
  .steps .tt{font-size:14.5px;font-weight:800;color:#E4C56B}
  .steps .st{display:flex;gap:10px;font-size:12.5px;line-height:1.55}
  .steps .n{width:20px;height:20px;border-radius:50%;background:rgba(228,197,107,.2);color:#E4C56B;
      display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;flex-shrink:0;margin-top:1px}
</style></head><body>

  <header>
    <div class="bk" onclick="history.length > 1 ? history.back() : location.href='/v2/admin'">
      <svg width="16" height="16" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <img class="lg" src="/assets/logo" alt="" onerror="this.style.display='none'">
    <div style="width:42px"></div>
  </header>

  <main>
    <div>
      <h1>חיבור משרד חדש</h1>
      <div class="sub">כל המקורות שהאפליקציה צריכה כדי להרים משרד מאפס. הנקודות מציגות את הסטטוס
        של המשרד הנוכחי — למשרד חדש צריך להשיג את אותם פריטים בדיוק.</div>
    </div>
    <div id="list"><div class="card"><div class="sub" style="padding:8px 0">טוען סטטוס…</div></div></div>

    <div class="steps">
      <div class="tt">סדר הפעולות המומלץ</div>
      <div class="st"><div class="n">1</div><div>פותחים משרד ב-Supabase: שורת office חדשה (שם, לוגו, office_id) + משתמשים ראשונים (בעלים/מנהל).</div></div>
      <div class="st"><div class="n">2</div><div>טלפוניה: מספר וירטואלי במרכזיה (Maskyoo) + הפניית webhook השיחות לשרת, וחשבון SMS (sms.deals) עם שם שולח.</div></div>
      <div class="st"><div class="n">3</div><div>וואטסאפ: מופע Maytapi למשרד + קבוצות מנהלים (שיחות/חתימות).</div></div>
      <div class="st"><div class="n">4</div><div>נתונים: גיליון נכסים + Apps Script (או ישר Supabase), מזהה גיליון ומפתח Sheets API.</div></div>
      <div class="st"><div class="n">5</div><div>Google OAuth לכניסה וליומן (אפשר להשתמש באפליקציה הקיימת — רק להוסיף redirect).</div></div>
      <div class="st"><div class="n">6</div><div>פוש: אפליקציית OneSignal (או שימוש בקיימת עם סגמנטים לפי משרד).</div></div>
      <div class="st"><div class="n">7</div><div>תוכן: חוזי החתמה של המשרד, לוגו, אינסטגרם/מדלן, אימייל מזכירה.</div></div>
      <div class="st"><div class="n">8</div><div>צוות: הזמנת סוכנים/מתאמות, תפקידים, צוותי שיתוף והשהיות נכס נולד.</div></div>
    </div>
  </main>

<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function el(id){ return document.getElementById(id); }
function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
var SECTIONS = [
  {t: 'זהות המשרד (white-label)', items: [
    ['name', 'שם המשרד', 'offices.name ב-Supabase — מופיע בכותרות, בוואטסאפ ובמסמכים'],
    ['logo', 'לוגו', 'קובץ הלוגו שמוצג בכל המסכים ובטפסי החתימה'],
    ['office_id', 'מזהה משרד ב-Supabase', 'office_id ייחודי — כל הנתונים מסוננים לפיו (מולטי-טננט)'],
    ['links', 'אינסטגרם + מדלן', 'קישורי המשרד בתפריט הצד — נשמרים בהגדרות המשרד בניהול']]},
  {t: 'טלפוניה', items: [
    ['vphone', 'מספר וירטואלי (מרכזיה)', 'המספר שהלקוחות מחייגים אליו; ה-webhook של המרכזיה שולח את השיחות והתמלולים לשרת'],
    ['sms', 'ספק SMS (sms.deals)', 'טוקן + שם שולח מאושר — קוד כניסה, קישורי חתימה, התראות לסוכן']]},
  {t: 'וואטסאפ', items: [
    ['maytapi', 'חיבור Maytapi', 'מופע וואטסאפ של המשרד — הודעות אוטומטיות לסוכנים וללקוחות'],
    ['wa_groups', 'קבוצות מנהלים', 'קבוצת "שיחות" וקבוצת "חתימות" — עדכונים שוטפים להנהלה']]},
  {t: 'נתונים', items: [
    ['supabase', 'Supabase', 'מסד הנתונים המהיר — שיחות, חתימות, קונים, נכס נולד, קונפיג'],
    ['apps_script', 'Apps Script + גיליון', 'הכתיבות (הוספת קונה, חתימות) והגיליון התפעולי של המזכירה'],
    ['sheets_api', 'Google Sheets API', 'קריאת גיליון הנכסים (עד המעבר המלא ל-Supabase)'],
    ['contracts', 'חוזי החתמה', 'נוסחי ההסכמים (בלעדיות/מכירה/קניה/שכירות) — פר-משרד']]},
  {t: 'Google', items: [
    ['google_oauth', 'כניסה עם Google + יומן', 'OAuth Client — כניסת סוכנים וסנכרון פגישות ליומן']]},
  {t: 'התראות', items: [
    ['onesignal', 'פוש (OneSignal)', 'התראות דחיפה לאפליקציה — חתימות, נכס נולד']]},
  {t: 'צוות והרשאות', items: [
    ['admins', 'מנהלים', 'טלפוני מנהלים — גישה מלאה ודוחות'],
    ['agents', 'סוכנים', 'ספריית הסוכנים (שם, נייד, וירטואלי, תפקיד)'],
    ['coordinators', 'מתאמות', 'שיוך מתאמת ← סוכנים']]},
  {t: 'תשתית', items: [
    ['session_secret', 'סוד חתימת טוקנים', 'SESSION_SECRET ייחודי — כניסות מאובטחות'],
    ['base_url', 'כתובת השרת', 'APP_BASE_URL — קישורי חתימה, דיפ-לינקים לאפליקציה']]}
];
fetch('/v2/api/onboard', {headers:{'X-Auth-Token': TOK}}).then(function(r){ return r.json(); })
  .then(function(j){
    if (!j.ok){ el('list').innerHTML = '<div class="card"><div class="sub" style="padding:8px 0">למפתח בלבד</div></div>'; return; }
    var it = j.items || {};
    el('list').innerHTML = SECTIONS.map(function(sec){
      return '<div class="card"><div class="tt">' + esc(sec.t) + '</div>' +
        sec.items.map(function(x){
          var v = it[x[0]];
          var cls = (v === true || (typeof v === 'number' && v > 0)) ? 'ok' : (v === false || v === 0) ? 'no' : 'info';
          var extra = (typeof v === 'number') ? ' · ' + v : '';
          return '<div class="row"><div class="dot ' + cls + '"></div>' +
            '<div style="flex:1"><div class="nm">' + esc(x[1]) + extra + '</div>' +
            '<div class="ds">' + esc(x[2]) + '</div></div></div>';
        }).join('') + '</div>';
    }).join('');
  }).catch(function(){});
fetch('/v2/api/office').then(function(r){ return r.json(); }).then(function(o){
  document.title = 'חיבור משרד חדש · ' + (o.name || '');
}).catch(function(){});
</script></body></html>"""


# אייקוני הכניסה (בקשת אייל 08/07): לוגו אפי כ-favicon ו-apple-touch-icon בלבד —
# שאר ה-UI נשאר white-label עם לוגו המשרד.
# + meta של PWA standalone: בלעדיהם "הוסף למסך הבית" ב-iOS פותח web-clip של ספארי עם שורת
#   כתובת שמתקפלת בגלילה (מרצדת את הניווט הקבוע, בעיקר ברשימות ארוכות). עם apple-mobile-web-app-capable
#   נפתח במסך מלא בלי שורת כתובת — אין קיפול, אין ריצוד. (דורש הוספה-מחדש למסך הבית אחרי דפלוי.)
_V2_ICON_TAGS = ('<link rel="icon" type="image/png" sizes="64x64" href="/v2/icon-64.png">'
                 '<link rel="apple-touch-icon" sizes="180x180" href="/v2/icon-180.png">'
                 '<meta name="apple-mobile-web-app-capable" content="yes">'
                 '<meta name="mobile-web-app-capable" content="yes">'
                 '<meta name="apple-mobile-web-app-status-bar-style" content="default">')

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
                        "require_followup": False, "who_contacted_admins_only": True,
                        "wa_auto": False}   # שליחות וואטסאפ אוטומטיות — מושהות (בקשת אייל 06/07)
    _POLICY_LABELS = {"transcribe": "תמלול שיחות", "shtaf_sharing": "שת\"פ — שיתוף נכסים",
                      "share_buyers": "שיתוף קונים בין סוכנים",
                      "require_followup": "חיוב פולו-אפ לפני סגירה",
                      "who_contacted_admins_only": "\"מי פנה\" למנהלים בלבד",
                      "wa_auto": "וואטסאפ אוטומטי מהמערכת"}

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
        # שכבת הדסקטופ + שכבת המהירות + אייקוני הכניסה מוזרקים לכל דף
        html = html.replace("</head>", _V2_ICON_TAGS + V2_BOOST + V2_DESKTOP_CSS + "</head>", 1)
        resp = Response(html, mimetype="text/html")
        # קאש קצרצר — מאפשר ל-prefetch מהנגיעה בטאב להיתפס בניווט שמיד אחריה
        resp.headers["Cache-Control"] = "private, max-age=30"
        return resp

    _ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "handoff")

    @app.route("/v2/icon-<int:sz>.png", methods=["GET"])
    def v2_icon(sz):
        """אייקוני הכניסה — לוגו אפי (favicon / apple-touch-icon)."""
        fp = os.path.join(_ICON_DIR, "app-icon-%d.png" % sz)
        if sz not in (64, 180, 1024) or not os.path.exists(fp):
            return Response("", status=404)
        with open(fp, "rb") as f:
            return Response(f.read(), mimetype="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.route("/v2", methods=["GET"])
    def v2_login():
        return _page(V2_LOGIN_HTML)

    @app.route("/v2/home", methods=["GET"])
    def v2_home():
        return _page(V2_HOME_HTML)

    @app.route("/v2/onboard", methods=["GET"])
    def v2_onboard():
        return _page(V2_ONBOARD_HTML)

    @app.route("/v2/api/onboard", methods=["GET"])
    def v2_api_onboard():
        """סטטוס המקורות של המשרד הנוכחי — בוליאנים בלבד, בלי סודות. מפתח בלבד."""
        s = _dev_guard()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        env = os.environ.get
        def _has(*names):
            return all(bool((env(n) or "").strip()) for n in names)
        cfg = _load_config()
        v2o = cfg.get("v2_office") or {}
        try:
            import supabase_db as _sb
            sb_on = bool(_sb.enabled())
            office_id = bool(getattr(_sb, "SB_OFFICE_ID", ""))
        except Exception:
            sb_on = False; office_id = False
        items = {
            "name": bool(_office_name(cfg)),
            "logo": True,   # מוגש מ-/assets/logo
            "office_id": office_id,
            "links": bool(v2o.get("instagram") or v2o.get("madlan")),
            "vphone": bool(v2o.get("vphone") or env("VIRTUAL_PHONE_DISPLAY")),
            "sms": _has("SMS_DEALS_TOKEN", "SMS_DEALS_SENDER"),
            "maytapi": _has("MAYTAPI_TOKEN", "MAYTAPI_PHONE_ID", "MAYTAPI_PRODUCT_ID"),
            "wa_groups": _has("WA_GROUP_CALLS") or _has("WA_GROUP_SIGNATURES"),
            "supabase": sb_on,
            "apps_script": _has("APPS_SCRIPT_URL", "APPS_SCRIPT_TOKEN"),
            "sheets_api": _has("GOOGLE_SHEETS_API_KEY", "PROPERTIES_SHEET_ID"),
            "contracts": bool(cfg.get("contracts")),
            "google_oauth": _has("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
            "onesignal": _has("ONESIGNAL_REST_KEY"),
            "admins": len([p for p in (env("ADMIN_PHONES") or "").split(",") if p.strip()]),
            "agents": len(cfg.get("agents") or []),
            "coordinators": len(cfg.get("coordinators") or {}) or len((env("COORDINATORS") or "").strip()) and 1 or 0,
            "session_secret": _has("SESSION_SECRET"),
            "base_url": _has("APP_BASE_URL"),
        }
        return jsonify({"ok": True, "items": items})

    @app.route("/v2/admin", methods=["GET"])
    def v2_admin():
        return _page(V2_ADMIN_HTML)

    @app.route("/v2/calls", methods=["GET"])
    def v2_calls():
        return _page(V2_CALLS_HTML)

    @app.route("/v2/buyers", methods=["GET"])
    def v2_buyers():
        return _page(V2_BUYERS_HTML)

    @app.route("/v2/sigs", methods=["GET"])
    def v2_sigs():
        return _page(V2_SIGS_HTML)

    @app.route("/v2/sign", methods=["GET"])
    def v2_sign():
        return _page(V2_SIGN_HTML)

    @app.route("/v2/meets", methods=["GET"])
    def v2_meets():
        return _page(V2_MEETS_HTML)

    @app.route("/v2/newborn", methods=["GET"])
    def v2_newborn():
        return _page(V2_NB_HTML)

    @app.route("/v2/props", methods=["GET"])
    def v2_props():
        return _page(V2_PROPS_HTML)

    @app.route("/v2/map", methods=["GET"])
    def v2_map():
        return _page(V2_MAP_HTML)

    @app.route("/v2/deals", methods=["GET"])
    def v2_deals():
        return _page(V2_DEALS_HTML)

    @app.route("/v2/reports", methods=["GET"])
    def v2_reports():
        return _page(V2_REPORTS_HTML)

    @app.route("/v2/updates", methods=["GET"])
    def v2_updates():
        return _page(V2_UPDATES_HTML)

    @app.route("/v2/activity", methods=["GET"])
    def v2_activity():
        return _page(V2_ACTIVITY_HTML)

    # ── עדכונים למשרד — Supabase announcements + announcement_reads (מהמיגרציה) ──
    def _sb_mod():
        import supabase_db as _sb
        return _sb if _sb.enabled() else None

    @app.route("/v2/api/ann", methods=["GET"])
    def v2_api_ann_list():
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        _sb = _sb_mod()
        if not _sb:
            return jsonify({"ok": False, "reason": "no_supabase"})
        try:
            r = _requests.get(_sb.SUPABASE_URL + "/rest/v1/announcements", headers=_sb._headers(),
                              params={"office_id": "eq." + _sb.SB_OFFICE_ID,
                                      "select": "id,author_name,author_role,body,pinned,created_at",
                                      "order": "pinned.desc,created_at.desc", "limit": "50"}, timeout=10)
            r.raise_for_status()
            items = r.json() or []
            ids = [it["id"] for it in items]
            reads = {}
            mine = set()
            my9 = _last9(s.get("phone", ""))
            if ids:
                r2 = _requests.get(_sb.SUPABASE_URL + "/rest/v1/announcement_reads", headers=_sb._headers(),
                                   params={"announcement_id": "in.(" + ",".join(ids) + ")",
                                           "select": "announcement_id,reader_phone", "limit": "5000"}, timeout=10)
                r2.raise_for_status()
                for rec in (r2.json() or []):
                    reads[rec["announcement_id"]] = reads.get(rec["announcement_id"], 0) + 1
                    if rec.get("reader_phone") == my9:
                        mine.add(rec["announcement_id"])
            for it in items:
                it["reads"] = reads.get(it["id"], 0)
                it["my_read"] = it["id"] in mine
            return jsonify({"ok": True, "items": items})
        except Exception as e:
            if log: log.warning(f"effie ann list: {e}")
            return jsonify({"ok": False, "reason": "read_failed"})

    @app.route("/v2/api/ann", methods=["POST"])
    def v2_api_ann_post():
        s = _web_auth()
        if not s or s.get("role") not in ("admin", "coordinator"):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        body = (b.get("body") or "").strip()[:2000]
        if not body:
            return jsonify({"ok": False, "reason": "empty"}), 400
        _sb = _sb_mod()
        if not _sb:
            return jsonify({"ok": False, "reason": "no_supabase"})
        try:
            r = _requests.post(_sb.SUPABASE_URL + "/rest/v1/announcements",
                               headers={**_sb._headers(), "Content-Type": "application/json"},
                               json={"office_id": _sb.SB_OFFICE_ID, "author_name": s.get("name", ""),
                                     "author_role": s.get("role", ""), "body": body,
                                     "pinned": bool(b.get("pinned"))}, timeout=10)
            r.raise_for_status()
            _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                          "עדכון למשרד", body[:60])
            return jsonify({"ok": True})
        except Exception as e:
            if log: log.warning(f"effie ann post: {e}")
            return jsonify({"ok": False, "reason": "write_failed"})

    @app.route("/v2/api/ann/read", methods=["POST"])
    def v2_api_ann_read():
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        aid = ((request.get_json(silent=True) or {}).get("id") or "").strip()
        _sb = _sb_mod()
        if not (_sb and aid):
            return jsonify({"ok": False, "reason": "no_supabase" if not _sb else "bad_id"})
        try:
            r = _requests.post(_sb.SUPABASE_URL + "/rest/v1/announcement_reads?on_conflict=announcement_id,reader_phone",
                               headers={**_sb._headers(), "Content-Type": "application/json",
                                        "Prefer": "resolution=merge-duplicates"},
                               json={"office_id": _sb.SB_OFFICE_ID, "announcement_id": aid,
                                     "reader_phone": _last9(s.get("phone", "")),
                                     "reader_name": s.get("name", "")}, timeout=10)
            r.raise_for_status()
            return jsonify({"ok": True})
        except Exception as e:
            if log: log.warning(f"effie ann read: {e}")
            return jsonify({"ok": False, "reason": "write_failed"})

    @app.route("/v2/api/ann/del", methods=["POST"])
    def v2_api_ann_del():
        s = _web_auth()
        if not s or s.get("role") != "admin":
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        aid = ((request.get_json(silent=True) or {}).get("id") or "").strip()
        _sb = _sb_mod()
        if not (_sb and aid):
            return jsonify({"ok": False, "reason": "no_supabase" if not _sb else "bad_id"})
        try:
            r = _requests.delete(_sb.SUPABASE_URL + "/rest/v1/announcements",
                                 headers=_sb._headers(),
                                 params={"id": "eq." + aid, "office_id": "eq." + _sb.SB_OFFICE_ID}, timeout=10)
            r.raise_for_status()
            return jsonify({"ok": True})
        except Exception as e:
            if log: log.warning(f"effie ann del: {e}")
            return jsonify({"ok": False, "reason": "delete_failed"})

    # ── נכסים חמים (hot_stories) — עד 2 לסוכן, רצים בבריף הבוקר הכלל-משרדי ──
    @app.route("/v2/api/hot", methods=["GET"])
    def v2_api_hot_get():
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        _sb = _sb_mod()
        if not _sb:
            return jsonify({"ok": True, "keys": []})
        try:
            r = _requests.get(_sb.SUPABASE_URL + "/rest/v1/hot_stories", headers=_sb._headers(),
                              params={"office_id": "eq." + _sb.SB_OFFICE_ID,
                                      "agent_phone": "eq." + _last9(s.get("phone", "")),
                                      "active": "eq.true", "select": "property_key"}, timeout=10)
            r.raise_for_status()
            keys = [row.get("property_key") for row in (r.json() or []) if row.get("property_key")]
            return jsonify({"ok": True, "keys": keys})
        except Exception as e:
            if log: log.warning(f"effie hot get: {e}")
            return jsonify({"ok": True, "keys": []})

    @app.route("/v2/api/hot", methods=["POST"])
    def v2_api_hot_post():
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        b = request.get_json(silent=True) or {}
        key = (b.get("property_key") or "").strip()
        if not key:
            return jsonify({"ok": False, "reason": "bad_key"}), 400
        on = bool(b.get("on"))
        _sb = _sb_mod()
        if not _sb:
            return jsonify({"ok": False, "reason": "no_supabase"})
        phone9 = _last9(s.get("phone", ""))
        base = {"office_id": "eq." + _sb.SB_OFFICE_ID, "agent_phone": "eq." + phone9}
        try:
            if not on:
                r = _requests.patch(_sb.SUPABASE_URL + "/rest/v1/hot_stories",
                                    headers={**_sb._headers(), "Content-Type": "application/json"},
                                    params={**base, "property_key": "eq." + key},
                                    json={"active": False}, timeout=10)
                r.raise_for_status()
                _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "הסרת נכס חם", key)
                return jsonify({"ok": True, "on": False})
            # הפעלה — אכיפת "עד 2" (סופרים active אחרים של אותו סוכן)
            rc = _requests.get(_sb.SUPABASE_URL + "/rest/v1/hot_stories",
                               headers={**_sb._headers(), "Prefer": "count=exact"},
                               params={**base, "active": "eq.true", "property_key": "neq." + key,
                                       "select": "id"}, timeout=10)
            cnt = 0
            cr = rc.headers.get("Content-Range", "")
            if "/" in cr:
                try: cnt = int(cr.split("/")[-1])
                except Exception: cnt = 0
            if cnt >= 2:
                return jsonify({"ok": False, "reason": "limit"})
            r = _requests.post(_sb.SUPABASE_URL + "/rest/v1/hot_stories?on_conflict=office_id,agent_phone,property_key",
                               headers={**_sb._headers(), "Content-Type": "application/json",
                                        "Prefer": "resolution=merge-duplicates"},
                               json={"office_id": _sb.SB_OFFICE_ID, "agent_phone": phone9,
                                     "agent_name": s.get("name", ""), "property_key": key,
                                     "title": (b.get("title") or "")[:200], "details": (b.get("details") or "")[:200],
                                     "price": (b.get("price") or "")[:40],
                                     "description": (b.get("description") or "")[:600], "active": True}, timeout=10)
            r.raise_for_status()
            _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "סימון נכס חם", key)
            return jsonify({"ok": True, "on": True})
        except Exception as e:
            if log: log.warning(f"effie hot post: {e}")
            return jsonify({"ok": False, "reason": "write_failed"})

    # ── סטטוס קונה (buyers.status — העמודה מהמיגרציה; כתיבה דרך השרת בלבד) ──
    _BUYER_STATUSES = ("active", "hot", "frozen", "closed")

    @app.route("/v2/api/buyers/statuses", methods=["GET"])
    def v2_api_buyers_statuses():
        if not _web_auth():
            return jsonify({"ok": False, "auth": False}), 401
        try:
            return jsonify({"ok": True, "statuses": _bstat_load()})
        except Exception as e:
            if log: log.warning(f"effie v2: buyers statuses read failed: {e}")
            return jsonify({"ok": True, "statuses": {}})

    @app.route("/v2/api/buyers/status", methods=["POST"])
    def v2_api_buyers_status():
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        b = request.get_json(silent=True) or {}
        status = (b.get("status") or "").strip()
        try:
            row = int(b.get("row"))
        except Exception:
            return jsonify({"ok": False, "reason": "bad_row"}), 400
        if status not in _BUYER_STATUSES:
            return jsonify({"ok": False, "reason": "bad_status"}), 400
        # נשמר בקובץ על הדיסק הקבוע (כמו deals.json) — הסנכרון גיליון→Supabase דרס גם את
        # טבלת buyers וגם מפתחות קונפיג חדשים; לדיסק הזה אין לו גישה.
        # מפתח: טלפון הקונה (עמיד להזזת שורות); בלי טלפון — לפי שורה.
        key = "".join(ch for ch in str(b.get("phone", "") or "") if ch.isdigit())[-9:] or ("r" + str(row))
        try:
            with _BSTAT_LOCK:
                m = _bstat_load()
                if status == "active":
                    m.pop(key, None)   # ברירת המחדל — אין צורך לרשום
                else:
                    m[key] = status
                _bstat_save(m)
            _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                          "עדכון סטטוס קונה", f"{key} → {status}")
            return jsonify({"ok": True})
        except Exception as e:
            if log: log.warning(f"effie v2: buyer status write failed: {e}")
            return jsonify({"ok": False, "reason": "write_failed"})

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

    _AV_DIR = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(os.path.abspath(__file__)), "v2_avatars")
    import threading as _bth
    _BSTAT_LOCK = _bth.Lock()
    _BSTAT_PATH = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(os.path.abspath(__file__)),
                               "v2_buyer_status.json")

    def _bstat_load():
        try:
            with open(_BSTAT_PATH, encoding="utf-8") as f:
                m = _json.load(f)
            return m if isinstance(m, dict) else {}
        except Exception:
            return {}

    def _bstat_save(m):
        with open(_BSTAT_PATH, "w", encoding="utf-8") as f:
            _json.dump(m, f, ensure_ascii=False)

    @app.route("/v2/api/avatar", methods=["GET", "POST"])
    def v2_api_avatar():
        """תמונת פרופיל של סוכן: GET לפי ?p=<טלפון> (ציבורי, כמו הלוגו); POST — המשתמש לעצמו."""
        if request.method == "GET":
            pp = "".join(ch for ch in (request.args.get("p", "") or "") if ch.isdigit())[-9:]
            fp = os.path.join(_AV_DIR, pp + ".jpg") if pp else ""
            if not (pp and os.path.exists(fp)):
                return Response("", status=404)
            with open(fp, "rb") as f:
                return Response(f.read(), mimetype="image/jpeg",
                                headers={"Cache-Control": "private, max-age=300"})
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        img = str((request.get_json(silent=True) or {}).get("img", "") or "")
        m = _re.match(r"data:image/(?:jpeg|jpg|png);base64,(.+)", img)
        if not m:
            return jsonify({"ok": False, "reason": "bad_image"}), 400
        try:
            raw = _b64.b64decode(m.group(1))
        except Exception:
            return jsonify({"ok": False, "reason": "bad_image"}), 400
        if len(raw) > 400000:
            return jsonify({"ok": False, "reason": "too_big"}), 400
        pp = _last9(s.get("phone", ""))
        if not pp:
            return jsonify({"ok": False, "reason": "no_phone"}), 400
        os.makedirs(_AV_DIR, exist_ok=True)
        with open(os.path.join(_AV_DIR, pp + ".jpg"), "wb") as f:
            f.write(raw)
        return jsonify({"ok": True})

    @app.route("/v2/api/brief", methods=["GET"])
    def v2_api_brief():
        """מספרי הבריף (7 ימים): קונים / חתימות קונים / בלעדיות — של הסוכן ושל כל המשרד."""
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        _canon = G["_canon_key"]
        me = _canon(s.get("name", ""))
        week_ago = time.time() - 7 * 86400
        import datetime as _dty
        _yr = _dty.date.today().year
        year_start = time.mktime(_dty.date(_yr, 1, 1).timetuple())   # מתחילת השנה
        buyers_all = buyers_me = buyers_total = 0
        try:
            for r in G["_fetch_manual_buyers"]():
                buyers_total += 1   # סה"כ קונים במערכת (ללא סינון תאריך)
                dt = str(r.get("date", "") or "")
                m = _re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", dt)
                if not m:
                    continue
                import datetime as _dt2
                try:
                    e = _dt2.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).timestamp()
                except Exception:
                    continue
                if e < week_ago:
                    continue
                buyers_all += 1
                if _canon(r.get("agent", "")) == me:
                    buyers_me += 1
        except Exception:
            pass
        calls_all = calls_me = calls_ans_all = 0
        try:
            my_phones = set(G["_last9"](x) for x in G["_phones_for_name"](s.get("name", "")))
            for c in G["web_fetch_raw"]("שיחות"):
                e = G["_epoch_from_iso"](c.get("received_at", ""))
                if not e or e < year_start:   # שיחות מתחילת השנה
                    continue
                calls_all += 1
                st = str(c.get("status", "") or "").upper()
                if "ANSWER" in st and "NOANSWER" not in st and "NO ANSWER" not in st:
                    calls_ans_all += 1
                if _canon(c.get("agent", "")) == me or G["_last9"](c.get("agent_phone", "")) in my_phones:
                    calls_me += 1
        except Exception:
            pass
        sigb_all = sigb_me = excl_all = excl_me = 0
        try:
            import datetime as _dt3
            frm = _dt3.date(_dt3.date.today().year, 1, 1).strftime("%d/%m/%Y")   # מתחילת השנה
            to = _dt3.date.today().strftime("%d/%m/%Y")
            for g in G["get_signings"](frm, to):
                lb = G["_deal_label"](g.get("deal_type", ""))
                mine = _canon(g.get("agent", "")) == me
                if lb == "קונים":
                    sigb_all += 1
                    if mine: sigb_me += 1
                elif lb == "בלעדיות":
                    excl_all += 1
                    if mine: excl_me += 1
        except Exception:
            pass
        # עסקאות שנסגרו מתחילת השנה (מוכר/קונה) — דרך _deals_load של app.py
        deals_year = 0
        try:
            for it in (G["_deals_load"]() or []):
                if not it.get("deal"):
                    continue
                cd = str(it.get("close_date", "") or "")
                m = _re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", cd)
                if m and int(m.group(3)) == _yr:
                    deals_year += 1
        except Exception:
            pass
        # נכסים חמים כלל-משרדיים (כל הסוכנים) — כרטיסי הסטורי אחרי הסיכום
        hot_props = []
        hot_buyers = 0
        try:
            _sb = _sb_mod()
            if _sb:
                rh = _requests.get(_sb.SUPABASE_URL + "/rest/v1/hot_stories", headers=_sb._headers(),
                                   params={"office_id": "eq." + _sb.SB_OFFICE_ID, "active": "eq.true",
                                           "select": "property_key,title,details,price,description,agent_name,agent_phone,created_at",
                                           "order": "created_at.desc"}, timeout=10)
                rh.raise_for_status()
                for r in (rh.json() or []):
                    hot_props.append({"key": r.get("property_key") or "", "title": r.get("title") or "",
                                      "details": r.get("details") or "", "price": r.get("price") or "",
                                      "desc": r.get("description") or "", "agent": r.get("agent_name") or "",
                                      "agentPhone": r.get("agent_phone") or "", "ts": r.get("created_at") or ""})
                # קונים חמים (buyers.status=hot) — לסלייד הסיכום
                try:
                    rb = _requests.get(_sb.SUPABASE_URL + "/rest/v1/buyers",
                                       headers={**_sb._headers(), "Prefer": "count=exact"},
                                       params={"office_id": "eq." + _sb.SB_OFFICE_ID, "status": "eq.hot",
                                               "select": "id"}, timeout=10)
                    _cr = rb.headers.get("Content-Range", "")
                    if "/" in _cr:
                        hot_buyers = int(_cr.split("/")[-1])
                except Exception:
                    pass
        except Exception as e:
            if log: log.warning(f"effie brief hot: {e}")
        return jsonify({"ok": True, "buyersMe": buyers_me, "buyersAll": buyers_all,
                        "sigBMe": sigb_me, "sigBAll": sigb_all,
                        "exclMe": excl_me, "exclAll": excl_all,
                        "callsMe": calls_me, "callsAll": calls_all,
                        "callsAnsAll": calls_ans_all, "hotBuyers": hot_buyers,
                        "buyersTotal": buyers_total,
                        "dealsYear": deals_year,
                        "hotProps": hot_props})

    @app.route("/v2/api/admin/overview", methods=["GET"])
    def v2_api_admin_overview():
        s = _dev_guard()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        cfg = _load_config()
        v2o = cfg.get("v2_office") or {}
        gauth = set()
        try:
            for rec in (G["_gauth_all"]() or {}).values():
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
        if (b.get("via") or "") == "sms":
            # שליחה ישירה מהשרת — אותו ספק SMS של קודי הכניסה
            sent = False
            try:
                fn = G.get("web_send_sms")
                sent = bool(fn and fn(phone, msg))
            except Exception as e:
                if log:
                    log.error(f"v2 invite sms: {e}")
            return jsonify({"ok": True, "sms": sent, "wa": wa})
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
