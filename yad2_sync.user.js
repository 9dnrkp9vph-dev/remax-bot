// ==UserScript==
// @name         Yad2 Plus → Google Sheets Auto-Sync
// @namespace    eyal-yad2-sync
// @updateURL    https://remax-bot.onrender.com/yad2.user.js
// @downloadURL  https://remax-bot.onrender.com/yad2.user.js
// @version      9.6
// @description  Auto-scrape 08:00-23:00 (random edges) + Secretary panel + network JSON recorder + סורק בלעדיות משרדים (2×יום).
// @match        https://plus.yad2.co.il/*
// @match        https://www.yad2.co.il/realestate/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setClipboard
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_openInTab
// @connect      script.google.com
// @connect      script.googleusercontent.com
// @run-at       document-start
// ==/UserScript==

(function(){
'use strict';

const WEBHOOK='https://script.google.com/macros/s/AKfycbxNnLyvMp2YicxUnRhQvcL2R2RC9pQ8L-XnvAL-2LM0BZT8CNEfCgakCHE4dcaxClnW/exec';
const SECRET='yad2-d8DTagQ78wnBzt83xX-AZ3Pa';
const MIN_DELAY_MIN=8, MAX_DELAY_MIN=30, CHECK_MIN=25; // ריענון אוטומטי נדיר יותר = טביעת רגל נמוכה יותר
const FETCH_TIMEOUT_MS=25000;   // בקשה שלא חוזרת (חיבור תקוע) — נכשלת במקום להקפיא את הסריקה
const SCAN_MAX_MIN=15;          // סריקה שנמשכת יותר מזה = תקועה → ריענון דף (מנקה הכול ומתחיל מחדש)
var VER='9.6'; // מוצג בפאנל ונשלח בסימן-החיים — כדי לדעת מרחוק איזו גרסה באמת רצה
var POST_RETRY_WAITS=[20000,45000]; // שמירה שנפלה על תקלת-גוגל רגעית: שני ניסיונות נוספים
const TOKENS_PER_SCAN=40;       // תקרת שליפות token/טלפון בסריקה אחת — חוסמת סריקה שנמשכת שעות
const ITEM_AGENTS_PER_SCAN=12;  // תקרת שליפות "מי הסוכן" מדף המודעה, פר משרד בכל סריקה (מצטבר יום-יום)
const OFFICES_PER_RUN=6;        // כמה משרדים בסריקה אחת — יד2 חוסם (ShieldSquare) כשסורקים הרבה ברצף
const BLOCK_COOLDOWN_MIN=90;    // נחסמנו? מנוחה לפני ניסיון חדש (הסריקה תמשיך מהמשרד שנחסם)
// זיהוי חסימה: יד2/Radware מחזירים עמוד CAPTCHA במקום הדף. חובה להבדיל בין "משרד בלי מודעות" ל"נחסמנו".
function looksBlocked(html){
  var s=String(html||'').slice(0,4000);
  return /ShieldSquare|Radware|_Incapsula_|Incapsula|px-captcha|Request unsuccessful|captcha/i.test(s);
}
var paused=false;
var scanStart=0;                // מתי הסריקה הנוכחית התחילה (0 = לא רצה סריקה) — לשומר-הראש
var lastScanMsg='';             // תמצית מצב אחרונה — נשלחת בסימן-החיים כדי שנראה מרחוק מה קרה
// עוטף פונקציית-סיום כך שתופעל פעם אחת בלבד — חריגה/כשל לא ישאירו את הלופ תקוע ב-paused
function once(fn){var done=false;return function(){if(done)return;done=true;try{if(fn)fn.apply(null,arguments);}catch(e){log('once() error: '+e);}};}
// fetch עם תקרת זמן: חיבור שנתקע (Radware/רשת) נכשל אחרי FETCH_TIMEOUT_MS במקום לתקוע את הסריקה לנצח
function fetchT(W,url,opts){
  return new Promise(function(resolve,reject){
    var ctl=null,timer=null;
    try{ctl=new AbortController();}catch(e){}
    var o=Object.assign({credentials:'include'},opts||{});
    if(ctl)o.signal=ctl.signal;
    timer=setTimeout(function(){try{if(ctl)ctl.abort();}catch(e){}reject(new Error('timeout'));},FETCH_TIMEOUT_MS);
    W.fetch(url,o).then(function(r){return r.text();})
      .then(function(t){clearTimeout(timer);resolve(t);})
      .catch(function(e){clearTimeout(timer);reject(e);});
  });
}

const log=(...a)=>console.log('[yad2-sync]',new Date().toLocaleTimeString(),...a);
function rDelay(){return MIN_DELAY_MIN*60000+Math.random()*(MAX_DELAY_MIN-MIN_DELAY_MIN)*60000;}
function parsePrice(s){return s?s.replace(/[₪,\s]/g,''):'';}

// ===== network recorder (runs at document-start, before the app loads) =====
// תופס כל תשובת JSON שהאתר מקבל — כדי לאתר את ה-API הפנימי של רשימת הנכסים.
var NET=[];         // כללי (אבחון) — 40 אחרונים
var LISTINGS=[];    // תשובות property/table — נשמרות בנפרד, לא נדרסות ע"י שיטפון חשיפות
var ADS={};         // orderId → תשובת office/ads (token+טלפון) — נשמרות פר-מודעה
function tap(url,text){
  try{
    if(!text||text.length<20||text.length>3000000)return;
    var c=text.charAt(0); if(c!=='{'&&c!=='[')return;
    var u=String(url||''), sliced=text.length>500000?text.slice(0,500000):text, now=Date.now();
    // רשימת נכסים — שומרים בנפרד כדי שלא תידרס
    if(u.indexOf('/api/v1/property/table')>-1){ LISTINGS.push({url:u,text:sliced,t:now}); if(LISTINGS.length>20)LISTINGS.shift(); }
    // תשובת מודעה בודדת (token/טלפון) — שומרים פר-orderId
    var m=u.match(/\/office\/\d+\/ads\/(\d+)/);
    if(m && /[Tt]oken|owner_phone|phone1/.test(sliced)){ ADS[m[1]]={url:u,text:sliced,t:now}; }
    NET.push({url:u,text:sliced,t:now});
    if(NET.length>40)NET.shift();
  }catch(e){}
}
function adsArr(){ var a=[]; for(var k in ADS) a.push(ADS[k]); return a; }
var SEEN_TPL=null;  // כתובת property/table האחרונה שנצפתה — נתפסת ברגע הבקשה (חסין לכל תקלת גוף)
function noteUrl(u){ u=String(u||''); if(u.indexOf('/api/v1/property/table')>-1) SEEN_TPL=u; }
try{window.__ysTap=tap;}catch(e){}
// הסוואה: גורם ל-fn.toString() להיראות כמו קוד מקורי, כדי שבדיקות "האם fetch עטוף?" לא יזהו אותנו
function nativeToString(fn,name){
  try{Object.defineProperty(fn,'toString',{value:function(){return 'function '+name+'() { [native code] }';},configurable:true,writable:true});}catch(e){}
  return fn;
}
try{window.__ysNative=nativeToString;}catch(e){}
(function installTap(){
  try{
    var W=(typeof unsafeWindow!=='undefined')?unsafeWindow:window;
    if(W.fetch){
      var of=W.fetch;
      W.fetch=nativeToString(function(){
        var args=arguments;
        try{noteUrl(args[0]&&args[0].url?args[0].url:args[0]);}catch(e){}
        return of.apply(this,args).then(function(res){
          try{res.clone().text().then(function(t){tap(res.url||args[0],t);}).catch(function(){});}catch(e){}
          return res;
        });
      },'fetch');
    }
    if(W.XMLHttpRequest){
      var oo=W.XMLHttpRequest.prototype.open, os=W.XMLHttpRequest.prototype.send;
      W.XMLHttpRequest.prototype.open=nativeToString(function(m,u){this.__ysUrl=u;try{noteUrl(u);}catch(e){}return oo.apply(this,arguments);},'open');
      W.XMLHttpRequest.prototype.send=nativeToString(function(){
        var x=this;
        try{x.addEventListener('load',function(){try{if(typeof x.responseText==='string')tap(x.__ysUrl,x.responseText);}catch(e){}});}catch(e){}
        return os.apply(this,arguments);
      },'send');
    }
    log('network tap installed');
  }catch(e){console.error('[yad2-sync] tap failed',e);}
})();

// מזהה אילו תשובות נראות כמו רשימת נכסים (מפתחות כתובת/מחיר/token וכו')
function scoreListingCandidates(net){
  var KEYS=['address','price','rooms','token','street','city','squaremeter','square_meter','adnumber','ad_number','phone','assetid','orderid','neighborhood','floor'];
  var out=[];
  (net||[]).forEach(function(rec){
    var j; try{j=JSON.parse(rec.text);}catch(e){return;}
    var best=null;
    (function walk(o,depth){
      if(!o||typeof o!=='object'||depth>6)return;
      if(Array.isArray(o)){
        if(o.length>=5&&o[0]&&typeof o[0]==='object'&&!Array.isArray(o[0])){
          var keys=Object.keys(o[0]);
          var low=keys.map(function(k){return k.toLowerCase();});
          var hits=0;
          KEYS.forEach(function(k){if(low.some(function(x){return x.indexOf(k)>-1;}))hits++;});
          if(hits>=2&&(!best||o.length>best.count))best={count:o.length,sample:o[0],keys:keys};
        }
        for(var i=0;i<Math.min(o.length,3);i++)walk(o[i],depth+1);
      }else{
        for(var k in o)walk(o[k],depth+1);
      }
    })(j,0);
    if(best)out.push({url:rec.url,count:best.count,keys:best.keys,sample:best.sample});
  });
  out.sort(function(a,b){return b.count-a.count;});
  return out;
}
// ===== API scrape (v3) — קורא ישירות מה-API הפנימי במקום מהטבלה =====
// תיאור הנכס: מפתחות ידועים, ואם אין — מחרוזת העברית הארוכה ביותר שאינה שדה מבני (כתובת/שכונה/עיר...)
function pickDesc(it){
  it=it||{};
  var known=it.info_text||it.description||it.search_text||it.text_information||it.freeText||it.additionalInfo_txt||it.adDescription||it.about||it.merchant_description||it.remarks;
  if(known&&String(known).trim()&&!looksJunk(known))return String(known).trim();
  var skip={};[it.address,it.neighborhood,it.city,it.HomeTypeText,it.action_title,it.contactPirson,it.owner_fullname,it.street].forEach(function(v){if(v)skip[String(v).trim()]=1;});
  var best='';
  for(var k in it){var v=it[k];if(typeof v==='string'&&v.length>=40&&!looksJunk(v)&&!skip[v.trim()]&&v.length>best.length)best=v;}
  return best.trim();
}
function mapApiRow(it){
  it=it||{};
  var phone=String(it.owner_phone||it.phone1||it.phone2||'').trim();
  var contact=String(it.contactPirson||it.owner_fullname||'').trim();
  var city=String(it.city==null?'':it.city).trim();
  var street=[it.address,it.homeNum].map(function(x){return String(x==null?'':x).trim();}).filter(Boolean).join(' ');
  var addr=[city,street].filter(Boolean).join(' ');
  return{
    deal_type:String(it.action_title||''),address:addr,property_type:String(it.HomeTypeText||''),
    rooms:it.rooms==null?'':it.rooms,floor:it.floor==null?'':it.floor,total_floors:it.totalFloors==null?'':it.totalFloors,
    price:String(it.price==null?'':it.price),contact:contact,phone:phone,price_update:'',
    sqm:it.squareMeter==null?'':it.squareMeter,neighborhood:String(it.neighborhood||''),
    link:'', // פורמט הקישור הציבורי טרם אומת (item/{orderId} נכשל) — יופעל כשנמצא את ה-token
    image:(it.images&&it.images.length)?String(it.images[0]):'',
    listing_date:String(it.modified||''), // תאריך עדכון המודעה ביד2 — התאריך ה"אמיתי" לתצוגה
    city:city, street:street, // עיר ורחוב בנפרד — לתצוגה עשירה כמו ב-CRM
    description:pickDesc(it)  // תיאור הנכס (טקסט חופשי מהמודעה)
  };
}
// בונה כתובות עמודים מתוך ה-URL שנתפס: skip מתקדם + שני סוגי עסקה (מכירה/השכרה)
function buildApiUrls(tpl,pagesPerAction){
  var urls=[];
  [1,2].forEach(function(act){
    var base=tpl.replace(/action_id=\d+(,\d+)*/,'action_id='+act);
    for(var p=0;p<pagesPerAction;p++){
      urls.push(base.replace(/\$skip=\d+/,'$skip='+(p*100)));
    }
  });
  return urls;
}
function latestApiTemplate(){
  for(var i=LISTINGS.length-1;i>=0;i--){ if(LISTINGS[i].url.indexOf('/api/v1/property/table')>-1)return LISTINGS[i].url; }
  for(var i=NET.length-1;i>=0;i--){ if(NET[i].url.indexOf('/api/v1/property/table')>-1)return NET[i].url; }
  return SEEN_TPL; // גיבוי אחרון — הכתובת שנתפסה ברגע הבקשה
}
// ===== פגינציה דרך הממשק של יד2 (v6.9) =====
// יד2 חוסם בעקביות בקשות-עמוד ששולחים בעצמנו (כל סריקה נעצרה על 100 מודעות מ-900/1,866).
// הפתרון: ללחוץ על "העמוד הבא" בממשק — יד2 טוען את העמוד בעצמו, ואת התשובה שלו אנחנו
// אוספים ממילא (הוא לא חוסם את הבקשות של עצמו). נופלים למשיכה הישנה אם אין פגינציה בדף.
var UI_PAGES_MAX=25, UI_PAGE_WAIT_MS=12000, UI_TOTAL_MS=420000;   // 7 דק': 4 לא הספיקו ל-9 עמודים (31/08), ושומר-הראש עדיין ב-15
var UI_PAGER_WAIT_MS=20000;  // כמה לחכות שהטבלה של יד2 תיבנה לפני שמתייאשים מהפגינציה
var PAGER_BACK_KEY='yad2_pager_back_v1';
var PAGER_KEY='yad2_pager_v1';   // זוכרים איזה חץ הוא "הבא" אחרי שהוכח
function lastTableSig(){
  for(var i=LISTINGS.length-1;i>=0;i--){
    if(String(LISTINGS[i].url).indexOf('/api/v1/property/table')>-1)return LISTINGS[i].url+'#'+LISTINGS[i].t;
  }
  return '';
}
// "עמוד X מתוך Y" — ממנו לומדים את המצב ואיפה הפגינציה יושבת
// ⚠️ יד2 מרנדר את מספר העמוד הנוכחי כשדה קלט — ולערך של input אין טקסט ב-DOM.
// לכן הטקסט שנראה בדף הוא "עמוד ‹ריק› מתוך 9", והמספר נשלף בנפרד (v7.7).
var PAGE_RE=/עמוד\s*(\d*)\s*מתוך\s*(\d+)/;
// המספר הנוכחי: קודם שדה קלט/בחירה, אחר כך צאצא שכל תוכנו מספר
function curFromEl(el){
  try{
    var ins=el.querySelectorAll?el.querySelectorAll('input,select'):[];
    for(var i=0;i<ins.length;i++){ var v=String(ins[i].value||'').trim(); if(/^\d+$/.test(v))return parseInt(v,10); }
    var kids=el.querySelectorAll?el.querySelectorAll('*'):[];
    for(var j=0;j<kids.length;j++){ var t=ownText(kids[j]); if(/^\d+$/.test(t))return parseInt(t,10); }
  }catch(e){}
  return 0;
}
// מה יש בתוך המחוון, כשהמספר לא נקרא — נוסע אליי בסימן-החיים
function pagerInside(el){
  try{
    var out=[], kids=el.querySelectorAll?el.querySelectorAll('*'):[];
    for(var i=0;i<kids.length && out.length<6;i++){
      var k=kids[i], tag=String(k.tagName||'?').toLowerCase();
      var val=(tag==='input'||tag==='select')?('='+String(k.value||'').slice(0,6)):'';
      var t=ownText(k).slice(0,8);
      out.push(tag+val+(t?(':'+t):''));
    }
    return out.join(',');
  }catch(e){ return '?'; }
}
// הטקסט הישיר של אלמנט (בלי צאצאים) — "עמוד 1 מתוך 9" יושב לפעמים כטקסט חופשי
// בתוך מכל שיש בו גם את החצים, ואז תנאי "עד 2 צאצאים" פסל אותו (v7.5).
function ownText(el){
  var t='';
  try{ for(var i=0;i<el.childNodes.length;i++){ var n=el.childNodes[i]; if(n.nodeType===3)t+=n.nodeValue; } }catch(e){}
  return t.trim();
}
function mkInfo(m, el){
  var cur = m[1] ? parseInt(m[1],10) : curFromEl(el);        // ריק בטקסט → מהשדה
  return {cur:cur, total:parseInt(m[2],10), el:el, curKnown:!!cur};
}
function pageInfo(){
  try{
    var els=document.querySelectorAll('div,span,p,li,button,nav,section,a');
    var best=null, bestLen=1e9;
    for(var i=0;i<els.length;i++){
      var el=els[i];
      var m=PAGE_RE.exec(ownText(el));                       // 1. טקסט ישיר — הכי מדויק
      if(m)return mkInfo(m,el);
      var tc=(el.textContent||'').trim();                    // 2. אחרת: ההתאמה הקטנה ביותר
      if(tc.length<bestLen){ var m2=PAGE_RE.exec(tc); if(m2){ best=mkInfo(m2,el); bestLen=tc.length; } }
    }
    if(best)return best;
  }catch(e){}
  return null;
}
// מה בכל זאת יש בדף? נוסע אליי בסימן-החיים כשהמחוון לא נמצא — במקום עוד סבב ניחושים.
function pagerHint(){
  try{
    var hits=[], els=document.querySelectorAll('div,span,p,li,button,nav,a');
    for(var i=0;i<els.length && hits.length<3;i++){
      var t=ownText(els[i]);
      if(t && t.length<40 && (t.indexOf('עמוד')>-1 || t.indexOf('מתוך')>-1)) hits.push(t);
    }
    var path=''; try{path=(location.pathname||'')+String(location.search||'').slice(0,40);}catch(e){}
    var body=''; try{body=(document.body.innerText||'').indexOf('מתוך')>-1?'"מתוך" קיים בדף':'"מתוך" לא בדף';}catch(e){}
    return 'נתיב '+path+' · '+body+(hits.length?(' · '+hits.join(' | ')):' · אין טקסט "עמוד"');
  }catch(e){ return 'רמז נכשל'; }
}
// מועמדים לחץ "הבא": אלמנטים לחיצים קטנים סביב טקסט הפגינציה
function pagerButtons(info){
  var out=[],node=info.el;
  for(var up=0;up<3&&node;up++){
    node=node.parentElement||node.parentNode;
    if(!node||!node.querySelectorAll)continue;
    var cands=node.querySelectorAll('button,[role="button"],a');
    for(var i=0;i<cands.length;i++){
      var c=cands[i];
      if(c===info.el)continue;
      if(c.offsetParent===null)continue;
      if((c.textContent||'').trim().length>3)continue;   // חצים בלבד
      if(out.indexOf(c)===-1)out.push(c);
    }
    if(out.length)break;
  }
  return out;
}
// עובר עמוד-עמוד דרך הממשק ומצרף הכול. done(rows, full) · rows=null → אין פגינציה, לגיבוי
// 🐞 סריקה שמתחילה בעמוד האחרון "מסיימת" מיד עם עמוד אחד — ומדווחת כיסוי מלא (תוקן ב-v7.3).
// הסריקה הקודמת משאירה את הטאב על העמוד האחרון, ולכן חייבים לחזור לעמוד 1 לפני שמתחילים.
function uiRewindToFirst(done, deadline){
  done=once(done);
  var tries=0;
  var backIdx=null; try{backIdx=JSON.parse(localStorage.getItem(PAGER_BACK_KEY)||'null');}catch(e){}
  (function back(){
    var cur=pageInfo();
    if(!cur){ done(false); return; }
    if(cur.cur<=1){ done(true); return; }
    if(++tries>UI_PAGES_MAX+2 || Date.now()>deadline){ done(false); return; }
    var btns=pagerButtons(cur);
    if(!btns.length){ done(false); return; }
    var order=[]; if(backIdx!=null&&btns[backIdx])order.push(backIdx);
    var fwd=null; try{fwd=JSON.parse(localStorage.getItem(PAGER_KEY)||'null');}catch(e){}
    for(var i=0;i<btns.length;i++)if(order.indexOf(i)===-1&&i!==fwd)order.push(i);
    if(fwd!=null&&btns[fwd]&&order.indexOf(fwd)===-1)order.push(fwd);
    var oi=0, attemptId=0;
    (function tryBtn(){
      if(oi>=order.length){ done(false); return; }
      var idx=order[oi++], myAttempt=++attemptId;
      var pi0=pageInfo(), pageBefore=pi0?pi0.cur:cur.cur;
      try{btns[idx].click();}catch(e){ tryBtn(); return; }
      var waited=0;
      (function wait(){
        if(myAttempt!==attemptId) return;     // מועמד חדש כבר נוסה — לא מזכים את החץ הלא נכון
        var pi=pageInfo();
        if(pi && pi.cur<pageBefore){                                   // זה חץ ה"אחורה"
          backIdx=idx;
          try{localStorage.setItem(PAGER_BACK_KEY,String(idx));}catch(e){}
          setTimeout(back, 600+Math.random()*600);                     // קצב אנושי
          return;
        }
        waited+=800;
        if(waited>=UI_PAGE_WAIT_MS){ tryBtn(); return; }
        setTimeout(wait,800);
      })();
    })();
  })();
}
// pgDiag — למה הפגינציה נעצרה. נוסע לפאנל ולסימן-החיים כדי שנדע מרחוק בלי גישה ל-DOM.
var pgDiag='';
// שתי פגינציות במקביל (סריקה מתוזמנת שכבר רצה + שמירה ידנית) לוחצות על אותם חצים,
// "לומדות" חצים הפוכים וגונבות זו לזו עמודים. רק אחת רצה בכל רגע (v7.3).
var uiPagingBusy=false;
function uiPaginateAll(onProg, done){
  if(uiPagingBusy){ if(done)done(null,false); return; }
  uiPagingBusy=true;
  var _d=once(done||function(){});
  done=function(rows,full){ uiPagingBusy=false; _d(rows,full); };
  pgDiag='';
  // 🐞 הסריקה מתחילה עם טעינת הדף, כשהטבלה של יד2 עוד לא נבנתה — ואז "אין מחוון עמודים"
  //    והסריקה נופלת לתקרת ה-100. מחכים שהמחוון יופיע לפני שמתייאשים (v7.4).
  var waited=0;
  (function findPager(){
    var info=pageInfo();
    if(!info){
      waited+=1000;
      if(waited<UI_PAGER_WAIT_MS){ setTimeout(findPager,1000); return; }
      pgDiag='אין מחוון עמודים ('+Math.round(UI_PAGER_WAIT_MS/1000)+'ש׳) · '+pagerHint();
      done(null,false); return;
    }
    if(!info.total||info.total<2){ pgDiag='עמוד אחד'; done(null,false); return; }
    if(!info.curKnown){ pgDiag='המחוון נמצא (מתוך '+info.total+') אך מספר העמוד לא נקרא · '+pagerInside(info.el); done(null,false); return; }
    if(onProg)onProg(info.cur, info.total, 0);
    uiWalkPages(info, onProg, done);
  })();
}
// הצעידה עצמה: מעמוד 1 עד האחרון, אוספת לפי orderId
function uiWalkPages(info, onProg, done){
  var acc={}, pages=0, t0=Date.now(), partial=false, startedAt=info.cur, pgPrefix='', stepId=0;
  var learned=null; try{learned=JSON.parse(localStorage.getItem(PAGER_KEY)||'null');}catch(e){}
  function absorb(){
    harvestApiRows().forEach(function(r){ var k=r._orderId||r.link||r.address; if(k&&!acc[k])acc[k]=r; });
  }
  function rows(){ return Object.keys(acc).map(function(k){return acc[k];}); }
  // חוזרים לתחילת הרשימה. אם לא הצלחנו — הסריקה חלקית, ואסור שתדווח כיסוי מלא
  // (דיווח-שווא הוא מה שסימן 796 נכסים פעילים כמועמדים ל"ירד מפרסום").
  uiRewindToFirst(function(rewound){
    var at=pageInfo();
    if(!rewound && at && at.cur>1){ partial=true; pgPrefix='לא הצלחתי לחזור לעמוד 1 (התחלתי ב-'+startedAt+') · '; }
    absorb();
    nextPage();
  }, t0+UI_TOTAL_MS);
  function nextPage(){
    var myStep=++stepId;
    var cur=pageInfo();
    if(!cur){ pgDiag=pgPrefix+'המחוון נעלם בעמוד '+pages; done(rows(), false); return; }
    if(onProg)onProg(cur.cur, cur.total, rows().length);
    var atEnd = cur.cur>=cur.total;
    if(atEnd || ++pages>UI_PAGES_MAX || Date.now()-t0>UI_TOTAL_MS){
      pgDiag = pgPrefix + (atEnd ? ('עמודים 1-'+cur.total+(partial?' (חלקי)':'')) : ('נעצר בעמוד '+cur.cur+'/'+cur.total+' (תקרה)'));
      done(rows(), atEnd && !partial);   // full=true רק אם כיסינו מעמוד 1 עד האחרון
      return;
    }
    var btns=pagerButtons(cur);
    if(!btns.length){ pgDiag=pgPrefix+'אין חצים ליד המחוון (עמוד '+cur.cur+'/'+cur.total+')'; done(rows(), false); return; }
    // סדר הניסיון: החץ שנלמד קודם, אחריו השאר, וחץ ה"אחורה" הידוע — אחרון.
    // בלי זה הצעידה קדימה לוחצת "אחורה" בכל עמוד ומתקוטטת עם עצמה (נתפס ב-v7.3).
    var back=null; try{back=JSON.parse(localStorage.getItem(PAGER_BACK_KEY)||'null');}catch(e){}
    var order=[]; if(learned!=null&&btns[learned])order.push(learned);
    for(var i=0;i<btns.length;i++)if(order.indexOf(i)===-1&&i!==back)order.push(i);
    if(back!=null&&btns[back]&&order.indexOf(back)===-1)order.push(back);
    var oi=0, attemptId=0;
    (function tryBtn(){
      if(myStep!==stepId) return;
      if(oi>=order.length){ pgDiag=pgPrefix+'החץ לא הזיז את העמוד '+cur.cur+'/'+cur.total+' ('+btns.length+' מועמדים)'; done(rows(), false); return; }
      var idx=order[oi++], myAttempt=++attemptId;
      // ⚠️ קוראים את המצב מחדש לפני כל מועמד: מועמד קודם עלול היה להזיז אחורה,
      // ואז השוואה מול מספר מיושן פוסלת גם את החץ הנכון (v7.3).
      var pi0=pageInfo(), pageBefore=pi0?pi0.cur:cur.cur, sigBefore=lastTableSig();
      try{btns[idx].click();}catch(e){ tryBtn(); return; }
      var waited=0;
      (function wait(){
        if(myStep!==stepId || myAttempt!==attemptId) return;  // צעד/מועמד חדש — הלולאה הזו מיושנת
        var pi=pageInfo();
        if(pi && pi.cur>pageBefore && lastTableSig()!==sigBefore){
          learned=idx;                                                   // גם בתוך הריצה, לא רק לפעם הבאה
          try{localStorage.setItem(PAGER_KEY,String(idx));}catch(e){}   // זה החץ הנכון
          absorb();
          setTimeout(nextPage, 900+Math.random()*900);                  // קצב אנושי בין עמודים
          return;
        }
        waited+=800;
        if(waited>=UI_PAGE_WAIT_MS){ tryBtn(); return; }
        setTimeout(wait,800);
      })();
    })();
  }
}
// משיכה אקטיבית של כל עמודי רשימת הנכסים (הפילטר הנוכחי) — לא מסתמך על תפיסה פסיבית.
// done(rows, full) — full=true אם נסרקו כל העמודים בהצלחה (לצורך זיהוי "ירד מפרסום").
function activeFetchAllPages(fetchFn, onProg, done){
  var tpl=latestApiTemplate();
  if(!tpl){ done(harvestApiRows(), false); return; }
  var skip=0, pages=0, ok=true, tries=0;
  (function next(){
    var url = tpl.indexOf('$skip=')>-1 ? tpl.replace(/\$skip=\d+/,'$skip='+skip)
                                       : tpl + (tpl.indexOf('?')>-1?'&':'?') + '$skip='+skip;
    fetchFn(url).then(function(txt){
      tries=0;
      tap(url,txt);
      var items=null; try{items=extractItems(JSON.parse(txt));}catch(e){}
      var n=items?items.length:0; pages++;
      if(onProg)onProg(pages,n);
      // קצב אנושי בין עמודים (1.2-2.6ש') — הקצב המהיר הקודם הוא מה שגרם ליד2 לחסום מעמוד 2
      if(n>=100 && skip<3000){ skip+=100; setTimeout(next, 1200+Math.random()*1400); }
      else { done(harvestApiRows(), ok); }
    }).catch(function(){
      // עמוד שנכשל (חסימה/רשת) — עד 2 נסיונות נוספים בהמתנה ארוכה, במקום לעצור על 100 מודעות
      if(tries<2){ tries++; setTimeout(next, 4000+tries*3000+Math.random()*2000); return; }
      ok=false; done(harvestApiRows(), false);
    });
  })();
}
// מחלץ מערך פריטים מתוך תשובת JSON כלשהי (מחפש מערך עם orderId/action_title)
function extractItems(j){
  var items=null;
  (function walk(o,d){if(!o||typeof o!=='object'||d>4)return;if(Array.isArray(o)&&o.length&&o[0]&&typeof o[0]==='object'&&('orderId'in o[0]||'action_title'in o[0])){if(!items||o.length>items.length)items=o;return;}if(!Array.isArray(o))for(var k in o)walk(o[k],d+1);else for(var x=0;x<Math.min(o.length,2);x++)walk(o[x],d+1);})(j,0);
  return items;
}
// ה-token של מודעה מגיע מ-office/{משרד}/ads/{orderId} — נשלח כשלוחצים על מודעה.
// אוספים אותם מ-NET (בלי בקשות משלנו) וממפים orderId → token.
function harvestTokens(net){
  var map={};
  (net||adsArr()).forEach(function(rec){
    var m=String(rec.url).match(/\/office\/\d+\/ads\/(\d+)/);
    if(!m)return;
    var tm=rec.text.match(/"(?:yad2_ad_token|Token|token)"\s*:\s*"([A-Za-z0-9]{5,14})"/);
    if(tm)map[m[1]]=tm[1];
  });
  return map;
}
// קישור ציבורי בפורמט של כפתור השיתוף של יד2: /realestate/item/{token} — בלי אזור, עובד לכל עיר
function cityArea(city){ return String(city||'').trim() ? 'ok' : ''; } // נשמר לתאימות; כל עיר תקפה
function itemLink(orderId,token,city){
  return token ? ('https://www.yad2.co.il/realestate/item/'+token) : '';
}
// אוסף נכסים מכל תשובות ה-API שכבר נתפסו (בזמן שהמשתמש מדפדף) — מאומת, לא נחסם
function harvestApiRows(net){
  var src=net||LISTINGS;
  var tokens=harvestTokens(net&&src), phones=harvestPhones(net&&src), cache=tokCache();
  var byId={};
  src.forEach(function(rec){
    if(String(rec.url).indexOf('/api/v1/property/table')<0)return;
    var j; try{j=JSON.parse(rec.text);}catch(e){return;}
    var items=extractItems(j); if(!items)return;
    items.forEach(function(it){
      var k=it.orderId||it.id||(it.city+it.address+it.homeNum);
      var row=mapApiRow(it);
      row._orderId=it.orderId; row._city=it.city; // פנימי — לשליפת token והתאמה
      var tok=tokens[it.orderId]||(cache[it.orderId]&&cache[it.orderId].t);
      if(tok) row.link=itemLink(it.orderId,tok,it.city); // קישור ישיר אמיתי
      var ph=phones[it.orderId]||(cache[it.orderId]&&cache[it.orderId].p);
      if(!hasRealPhone(row.phone) && ph) row.phone=ph; // טלפון אמין לפי orderId
      if(!row.description && cache[it.orderId] && cache[it.orderId].d) row.description=cache[it.orderId].d; // תיאור מתשובת המודעה
      byId[k]=row;
    });
  });
  return Object.keys(byId).map(function(k){return byId[k];});
}

// ===== שליפת token+טלפון עדינה מ-office/{משרד}/ads/{orderId} (בחירת אייל: כל המודעות) =====
var OFFICE_DEFAULT='5628636';
function officeId(){
  for(var i=NET.length-1;i>=0;i--){var m=String(NET[i].url).match(/\/office\/(\d+)\/ads\//);if(m)return m[1];}
  return OFFICE_DEFAULT;
}
function tokCache(){try{return JSON.parse(localStorage.getItem('yad2_tokens_v1')||'{}');}catch(e){return {};}}
function tokCacheSave(c){try{localStorage.setItem('yad2_tokens_v1',JSON.stringify(c));}catch(e){}}
// פענוח מחרוזת JSON גולמית (\n, \", \/, \uXXXX) לטקסט קריא
function jsonUnesc(s){ try{ return JSON.parse('"'+String(s)+'"'); }catch(e){ return String(s).replace(/\\n/g,' ').replace(/\\"/g,'"').replace(/\\\//g,'/').replace(/\\t/g,' ').replace(/\\r/g,' ').trim(); } }
// פוסל ערך שאינו תיאור אמיתי: HTML / קונפיג / בלי עברית
// 🧹 v8.5 — התיאור שיד2 מחזיר הוא בלוק אחד משולש (אייל, 25/08):
//   [תקציר SEO: "שם מוכר ... נכס למכירה מסוג ... בכתובת ..."] + "תאור לקוח" + [התיאור האמיתי]
//   + [פרסומת המשרד: "ר/מקס family שמה לה למטרה ... פילוסופיית החברה ..."]
// שמרנו את כולו כי בחרנו את המחרוזת הארוכה ביותר. כאן חותכים לתיאור הנכס בלבד.
var DESC_OFFICE_RE=/ר\/?מקס|re\/?max|שמה לה למטרה|פילוסופיית החברה|יועצי הנדל|לתמוך ולסייע|להוביל את שוק|מעורבות ותרומה לקהילה|סוכנות\s+re/i;
function cleanAdDesc(t){
  var s=String(t||'').replace(/\s+/g,' ').trim();
  if(!s)return '';
  var m=s.match(/תי?אור\s+לקוח\s*[:\-]?\s*/);   // מכאן מתחיל התיאור שהסוכן כתב
  if(m)s=s.slice(m.index+m[0].length);
  var cut=s.search(DESC_OFFICE_RE);
  if(cut===0)return '';                              // הכל פרסומת משרד
  if(cut>0)s=s.slice(0,cut);
  if(/^שם מוכר/.test(s))return '';                   // נשאר רק תקציר ה-SEO — עדיף ריק מזבל
  s=s.replace(/[\s,;·\-]+$/,'').trim();
  return s.length>=12?s:'';                          // שבר קצר מדי אינו תיאור
}
function looksJunk(v){v=String(v||'');return /data-showcond|HomeTypeID|dependencyProp|<[a-zA-Z]/.test(v)||/^\s*[\[{]/.test(v)||!/[֐-׿]/.test(v);}
// תיאור מתשובת המודעה (office/ads): "Remark" מאומת → גיבויים → המחרוזת העברית הארוכה. תמיד פוסל HTML/קונפיג.
function adDesc(text){
  var s=String(text);
  var rm=s.match(/"Remark"\s*:\s*"((?:[^"\\]|\\.){2,4000})"/); // השדה המאומת
  if(rm){var v=jsonUnesc(rm[1]).trim();if(v&&!looksJunk(v))return v;}
  var m=s.match(/"(?:info_text|description|search_text|text_information|additionalInfo_txt|freeText|adDescription|about|remarks)"\s*:\s*"((?:[^"\\]|\\.){2,4000})"/); // גיבוי (בלי body/content שמכילים HTML)
  if(m){var v2=jsonUnesc(m[1]).trim();if(v2&&!looksJunk(v2))return v2;}
  var re=/"((?:[^"\\]|\\.){40,4000})"/g, mm, best='';
  while((mm=re.exec(s))){ var v3=jsonUnesc(mm[1]); if(!looksJunk(v3) && v3.length>best.length) best=v3; }
  return cleanAdDesc(best);
}
function parseAd(text){
  var t=(String(text).match(/"(?:yad2_ad_token|Token|token)"\s*:\s*"([A-Za-z0-9]{5,14})"/)||[])[1]||'';
  var pm=String(text).match(/"(?:owner_phone|phone1|phone)"\s*:\s*"([\d\-+ ]{7,})"/);
  var p=(pm&&pm[1].replace(/\D/g,'').length>=7)?pm[1].trim():'';
  return {t:t,p:p,d:adDesc(text)};
}
// צריך שליפה אם: אין token, או שיש token אבל התיאור עוד לא נוסה (dt) — כדי להשלים תיאור לרשומות ישנות ב-cache
function needTokens(rows){
  var cache=tokCache(),out=[],seen={};
  (rows||[]).forEach(function(r){
    var oid=r._orderId; if(!oid||seen[oid])return; seen[oid]=1;
    if(cache[oid]&&cache[oid].t&&cache[oid].dt)return;  // כבר ב-cache עם תיאור שנוסה
    out.push({orderId:oid,city:r._city});
  });
  return out;
}
// שליפה סדרתית עדינה (fetchFn מוזרק לבדיקות). onProg(i,total,ok). done(cache,ok)
function fetchTokens(list, fetchFn, onProg, done){
  var oid=officeId(), cache=tokCache(), i=0, ok=0;
  (function next(){
    if(i>=list.length){tokCacheSave(cache);done(cache,ok);return;}
    var item=list[i++];
    if(cache[item.orderId]&&cache[item.orderId].t&&cache[item.orderId].dt){onProg(i,list.length,ok);setTimeout(next,0);return;} // כבר ב-cache עם תיאור
    fetchFn('https://plus-api.yad2.co.il/office/'+oid+'/ads/'+item.orderId)
      .then(function(txt){var a=parseAd(txt);if(a.t){a.dt=1;cache[item.orderId]=a;ok++;tokCacheSave(cache);}onProg(i,list.length,ok);setTimeout(next,900+Math.random()*1600);})
      .catch(function(){onProg(i,list.length,ok);setTimeout(next,1200);});
  })();
}
// טלפונים אמינים מ-office/{משרד}/ads/{orderId} (התשובה מכילה owner_phone) — לפי orderId, בלי תלות בכתובת
function harvestPhones(net){
  var map={};
  (net||adsArr()).forEach(function(rec){
    var m=String(rec.url).match(/\/office\/\d+\/ads\/(\d+)/);
    if(!m)return;
    var pm=rec.text.match(/"(?:owner_phone|phone1|phone)"\s*:\s*"([\d\-+ ]{7,})"/);
    if(pm){var d=pm[1].replace(/\D/g,'');if(d.length>=7)map[m[1]]=pm[1].trim();}
  });
  return map;
}
// מיזוג טלפונים שנחשפו במסך (DOM) → נכסי-API. התאמה חסינה: כתובת מדויקת, ואם לא — הכלה של טוקנים (רחוב+מספר ⊆ כתובת מלאה)
function normTokens(a){return String(a||'').trim().split(/[\s,]+/).filter(Boolean).sort();}
function hasRealPhone(x){return String(x||'').replace(/\D/g,'').length>=7;}
function mergeDomPhones(apiRows,domRows){
  var dom=[],exact={};
  (domRows||[]).forEach(function(d){
    if(!hasRealPhone(d.phone))return;
    var t=normTokens(d.address); if(!t.length)return;
    dom.push({toks:t,phone:d.phone}); exact[t.join(' ')]=d.phone;
  });
  (apiRows||[]).forEach(function(r){
    if(hasRealPhone(r.phone))return;
    var toks=normTokens(r.address), key=toks.join(' ');
    if(exact[key]){r.phone=exact[key];return;}
    for(var i=0;i<dom.length;i++){
      var d=dom[i], small=d.toks.length<=toks.length?d.toks:toks, big=d.toks.length<=toks.length?toks:d.toks;
      if(small.length>=2 && small.every(function(t){return big.indexOf(t)>-1;})){r.phone=d.phone;break;}
    }
  });
  return apiRows;
}
// אבחון מבנה הטבלה — כותרות + דגימת שורות (כדי לראות איפה הטלפון החשוף והכתובת יושבים)
function domDump(){
  var f=findHeaders();
  var out={headersFound:!!f};
  if(f){
    out.kind=f.kind; out.headers=f.headers;
    var fd=findDataRows(f.headers.length);
    out.rowCount=fd.rows.length;
    out.sampleRows=Array.prototype.slice.call(fd.rows,0,4).map(function(row){
      var cells=row.querySelectorAll(fd.cellSel);
      return Array.prototype.map.call(cells,function(c){return String(c.textContent||'').trim().slice(0,28);});
    });
  }else{
    out.anyHeaders=Array.prototype.slice.call(document.querySelectorAll('th,[role="columnheader"]')).slice(0,25).map(function(h){return String(h.textContent||'').trim();});
  }
  try{ out.extractRowsCount=extractRows().length; out.extractSample=extractRows().slice(0,3); }catch(e){ out.extractError=String(e); }
  return out;
}
// צייד token-ים: מחפש שדות token קצרים (קישור ציבורי) בכל תשובה שנתפסה
function findTokens(net){
  var out=[];
  (net||[]).forEach(function(rec){
    var re=/"([A-Za-z0-9_]*[Tt]oken[A-Za-z0-9_]*)"\s*:\s*"([A-Za-z0-9]{5,12})"/g,m;
    while((m=re.exec(rec.text))&&out.length<20){out.push({url:String(rec.url).slice(0,140),field:m[1],token:m[2]});}
  });
  return out;
}
// מחפש קישורי מודעה קנוניים (/realestate/item/<area>/<token>) בכל תשובה שנתפסה
function findItemUrls(net){
  var out=[],seen={};
  (net||[]).forEach(function(rec){
    var re=/\/realestate\/item\/([a-z0-9-]+)\/([A-Za-z0-9]{5,14})/g,m;
    while((m=re.exec(rec.text))){var k=m[1]+'/'+m[2];if(!seen[k]){seen[k]=1;out.push({area:m[1],token:m[2],full:m[0]});}}
  });
  return out.slice(0,15);
}
// dump מלא של הפריט הראשון ברשימה — כדי לראות אם ה-token/area מוסתר בשדה כלשהו
function firstItemDump(net){
  for(var i=(net||[]).length-1;i>=0;i--){
    if(net[i].url.indexOf('/api/v1/property/table')<0)continue;
    try{var j=JSON.parse(net[i].text);var items=extractItems(j);if(items&&items[0])return items[0];}catch(e){}
  }
  return null;
}
// תשובות "פרטי מודעה" (אובייקט בודד עם orderId/id) — לא רשימות
function findDetails(net){
  var out=[];
  (net||[]).forEach(function(rec){
    if(rec.text.length>60000)return;
    if(!/"orderId"|"orderId2"/.test(rec.text))return;
    try{var j=JSON.parse(rec.text);}catch(e){return;}
    var hasList=false;
    (function walk(o,d){if(!o||typeof o!=='object'||d>5)return;if(Array.isArray(o)&&o.length>=5&&o[0]&&typeof o[0]==='object'){hasList=true;return;}if(!Array.isArray(o))for(var k in o)walk(o[k],d+1);})(j,0);
    if(!hasList)out.push({url:String(rec.url).slice(0,140),body:rec.text.slice(0,2500)});
  });
  return out.slice(-4);
}
try{window.__ysScore=scoreListingCandidates;window.__ysNet=NET;window.__ysMapApi=mapApiRow;window.__ysPickDesc=pickDesc;window.__ysApiUrls=buildApiUrls;window.__ysTokens=findTokens;window.__ysDetails=findDetails;window.__ysHarvest=harvestApiRows;window.__ysMergePhones=mergeDomPhones;window.__ysItemUrls=findItemUrls;window.__ysFirstItem=firstItemDump;window.__ysHarvestTokens=harvestTokens;window.__ysCityArea=cityArea;window.__ysHarvestPhones=harvestPhones;window.__ysMergePhones=mergeDomPhones;window.__ysParseAd=parseAd;window.__ysAdDesc=adDesc;window.__ysCleanAdDesc=cleanAdDesc;window.__ysDescHunt=descHunt;window.__ysNeedTokens=needTokens;window.__ysFetchTokens=fetchTokens;window.__ysTokCache=tokCache;window.__ysActiveFetch=activeFetchAllPages;window.__ysLatestTpl=latestApiTemplate;}catch(e){} // לדיבוג/בדיקות
// ציד תיאור: כל צמד "שדה":"טקסט עברי ארוך" בכל תשובה שנתפסה — חושף איפה יושב התיאור ובאיזה endpoint
function descHunt(net){
  var out=[],seen={};
  (net||NET).forEach(function(rec){
    var re=/"([A-Za-z0-9_]{2,40})"\s*:\s*"((?:[^"\\]|\\.){45,})"/g,m;
    while((m=re.exec(rec.text))){
      if(/[֐-׿]/.test(m[2])){
        var key=String(rec.url).slice(0,80)+'|'+m[1];
        if(!seen[key]){seen[key]=1;out.push({url:String(rec.url).slice(0,140),field:m[1],sample:m[2].slice(0,140)});}
        if(out.length>=12)return;
      }
    }
  });
  return out.slice(0,12);
}
// דגימת גוף מלא של תשובות office/ads (שם עשוי לשבת התיאור)
function adSampleBodies(net){
  var out=[];
  (net||NET).forEach(function(rec){ if(/\/office\/\d+\/ads\/\d+/.test(String(rec.url))) out.push({url:String(rec.url).slice(0,120),len:rec.text.length,body:rec.text.slice(0,3000)}); });
  return out.slice(-2);
}
function copyNetReport(){
  var cands=scoreListingCandidates(NET);
  var report={note:'yad2 network capture',candidates:cands.slice(0,1),domTable:domDump(),itemUrls:findItemUrls(NET),firstItemFull:firstItemDump(NET),tokens:findTokens(NET),details:findDetails(NET),descHunt:descHunt(NET),adSampleBodies:adSampleBodies(NET)};
  var txt=JSON.stringify(report,null,1);
  if(txt.length>80000)txt=txt.slice(0,80000)+'\n...[קוצץ]';
  try{GM_setClipboard(txt);status('✓ הועתק (אבחון טבלה+API) — הדבק בצ׳אט של קלוד');}
  catch(e){console.log(txt);status('העתקה נכשלה — הדוח בקונסול (F12)');}
}

// ===== schedule: active 08:00-23:00 with random daily edges =====
function edge(now,key,h1,m1,h2,m2){var ck='yad2_'+key+'_'+now.toDateString();var c=localStorage.getItem(ck);if(c)return parseInt(c);var v=(h1*60+m1)+Math.floor(Math.random()*((h2*60+m2)-(h1*60+m1)+1));localStorage.setItem(ck,String(v));return v;}
// חלון שקט יומי אקראי (60-120 דק', בין 09:00 ל-22:00) שבו לא סורקים כלל — הדפוס נראה אנושי, לא מכונתי
function quietWin(now){
  var ck='yad2_quiet_'+now.toDateString();
  var c=localStorage.getItem(ck);
  if(c){var p=c.split(',');return {s:parseInt(p[0]),e:parseInt(p[0])+parseInt(p[1])};}
  var start=540+Math.floor(Math.random()*(1200-540+1)); // 09:00–20:00
  var dur=60+Math.floor(Math.random()*61);               // 60–120 דק'
  localStorage.setItem(ck,start+','+dur);
  return {s:start,e:start+dur};
}
function inQuiet(d){d=d||new Date();var nm=d.getHours()*60+d.getMinutes();var w=quietWin(d);return nm>=w.s&&nm<w.e;}
function isActive(){var now=new Date();var nm=now.getHours()*60+now.getMinutes();return nm>=edge(now,'start',8,0,8,20)&&nm<edge(now,'stop',22,40,23,0)&&!inQuiet(now);}
function nextActive(){var now=new Date();var nm=now.getHours()*60+now.getMinutes();var t=new Date(now);var s=edge(now,'start',8,0,8,20);if(nm<s){t.setHours(0,s,0,0);}else{t.setDate(t.getDate()+1);t.setHours(0,edge(t,'start',8,0,8,20),0,0);}return t;}

// ===== scrape =====
function findHeaders(){
  for(const t of document.querySelectorAll('table')){
    const cells=t.querySelectorAll('thead th, thead td, tr:first-child th, tr:first-child td');
    const headers=Array.from(cells).map(h=>h.textContent.trim());
    if(headers.some(h=>h.includes('כתובת')||h.includes('טלפון')||h.includes('עסקה')))return{headers,kind:'table'};
  }
  const ah=Array.from(document.querySelectorAll('[role="columnheader"]')).map(h=>h.textContent.trim());
  if(ah.some(h=>h.includes('כתובת')||h.includes('טלפון')||h.includes('עסקה')))return{headers:ah,kind:'aria'};
  return null;
}
function findDataRows(N){
  const tr=Array.from(document.querySelectorAll('tr')).filter(r=>{if(r.querySelector('th'))return false;const c=r.querySelectorAll('td').length;return c>=N-1&&c<=N+2;});
  if(tr.length)return{rows:tr,cellSel:'td'};
  const ar=Array.from(document.querySelectorAll('[role="row"]')).filter(r=>{const c=r.querySelectorAll('[role="cell"],[role="gridcell"]');return c.length>=N-1&&c.length<=N+2;});
  if(ar.length)return{rows:ar,cellSel:'[role="cell"],[role="gridcell"]'};
  return{rows:[],cellSel:null};
}
function extractRows(){
  const f=findHeaders();if(!f)return[];
  const H=f.headers;
  const idx={deal_type:H.findIndex(h=>h.includes('עסקה')),address:H.findIndex(h=>h.includes('כתובת')),property_type:H.findIndex(h=>h.includes('סוג נכס')),rooms:H.findIndex(h=>h.includes('חדרים')),floor:H.findIndex(h=>h.trim()==='קומה'),total_floors:H.findIndex(h=>h.includes('מתוך')),price:H.findIndex(h=>h.includes('מחיר')),contact:H.findIndex(h=>h.includes('איש קשר')),phone:H.findIndex(h=>h.includes('טלפון')),date:H.findIndex(h=>h.includes('תאריך'))};
  const N=H.length;const{rows,cellSel}=findDataRows(N);
  if(!rows.length)return[];
  const data=[];
  rows.forEach(row=>{
    const cells=row.querySelectorAll(cellSel);if(!cells.length)return;
    const get=i=>(i>=0&&cells[i])?cells[i].textContent.trim():'';
    const dc=idx.date>=0?cells[idx.date]:null;
    const pu=dc?!!dc.querySelector('svg,img,i,[class*="icon"],[class*="reduced"],[class*="update"],[class*="orange"],[data-icon]'):false;
    const r={deal_type:get(idx.deal_type),address:get(idx.address),property_type:get(idx.property_type),rooms:get(idx.rooms),floor:get(idx.floor),total_floors:get(idx.total_floors),price:parsePrice(get(idx.price)),contact:get(idx.contact),phone:get(idx.phone),price_update:pu?'כן':''};
    if(r.address||r.phone)data.push(r);
  });
  return data;
}
// מזהה המלאי שנסרק — מתוך פרמטרי תבנית ה-API. שני פרופילים = שני מזהים,
// וכך "ירד מפרסום" בשרת לא חוצה בין המלאים.
// מזהה המשרד שנתפס בפועל מקריאות yad2 (לא ברירת המחדל) — משתנה בין פרופילים
function officeIdSeen(){
  for(var i=NET.length-1;i>=0;i--){var m=String(NET[i].url).match(/\/office\/(\d+)\/ads\//);if(m)return m[1];}
  return '';
}
// ⚠️ אסור לזהות את הפרופיל הפעיל לפי מילות-מפתח ("פמילי"/"קריות") — כך זיהינו בטעות
// את הפרופיל *השני* כפעיל, וההחלפה סיננה בדיוק את היעד. במקום זה: ניקוד מועמדים בכותרת.
function profileCandidates(){
  var out=[];
  try{
    var els=document.querySelectorAll('button,[role="button"],a,span,div');
    for(var i=0;i<els.length;i++){
      var el=els[i], t=(el.textContent||'').trim().replace(/\s+/g,' ');
      if(!t||t.length<3||t.length>40)continue;
      if(!/[֐-׿]/.test(t))continue;
      if(notProfile(t))continue;
      if(el.children&&el.children.length>3)continue;
      if(el.offsetParent===null)continue;
      var score=1;
      if(/^[א-ת]{2,}\s+[א-ת]{2,}$/.test(t))score=3;                 // "אייל שמול" — שם אדם
      else if(/רי\/?מקס|פמילי|קריות|נדל/i.test(t))score=2;           // שם משרד
      out.push({el:el,label:t,score:score,i:i});
    }
  }catch(e){}
  out.sort(function(a,b){return b.score-a.score||a.i-b.i;});
  return out;
}
function activeProfile(){ var c=profileCandidates(); return c.length?c[0]:null; }
function profileLabel(){ var a=activeProfile(); return a?a.label:''; }
// מזהה המלאי שנסרק. ⚠️ החלפת פרופיל ביד2 *אינה* משנה את כתובת ה-API (נבדק 03/08),
// ולכן הזהות נשענת קודם על מזהה המשרד שנתפס, ואז על שם הפרופיל בדף.
// ⚠️ המזהה חייב להיות *יציב* בין סריקות. הגרסאות הקודמות שרשרו גם office/profile/action —
// והם משתנים לפי מה שנתפס בכל סריקה, כך שנוצרו 7 מזהים לאותם שני מלאים
// וזיהוי "ירד מפרסום" הושבת בפועל. עכשיו: האזור (area) בלבד — הוא המבדיל בין הפרופילים.
function srcKey(){
  var t=latestApiTemplate()||'';
  var m=t.match(/[?&]area(?:ID|_id)?=([^&]+)/i);
  if(m)return 'area:'+decodeURIComponent(m[1]).trim();
  // אין אזור בכתובת — נופלים לזהות הפרופיל, רק כדי לא לאחד שני מלאים בטעות
  var oid=officeIdSeen(); if(oid)return 'office:'+oid;
  var lbl=profileLabel(); if(lbl)return 'profile:'+lbl;
  return 'default';
}
function postRows(rows,cb,scanFull){
  if(!rows.length){status('אין שורות');if(cb)cb('0');return;}
  var body=new URLSearchParams();body.append('secret',SECRET);body.append('data',JSON.stringify(rows));
  if(scanFull)body.append('scan','full'); // סריקה מלאה → זיהוי "ירד מפרסום" בשרת
  try{body.append('machine',machineId());}catch(e){}   // איזו מכונה סרקה — נוסע גם לאפליקציה
  try{body.append('src',srcKey());}catch(e){}   // מקור המלאי — מגדר את זיהוי הירידות לפרופיל הזה
  cb=once(cb); // גם timeout וגם onerror משחררים את הלופ — לא נשארים תקועים בהמתנה לתשובה
  // ⚠️ נמדד חי (13/08): גוגל מחזיר מדי פעם 404 + "לא ניתן לפתוח את הקובץ כרגע" על הפריסה עצמה —
  // הבקשה לא מגיעה בכלל לקוד בשרת, ולכן ניסיון חוזר בשרת לא יכול לעזור. מנסים שוב מכאן.
  // תשובה תקינה היא תמיד JSON; דף HTML של גוגל = תקלה רגעית ששווה ניסיון נוסף.
  var attempt=0;
  var isJson=function(t){ try{ var j=JSON.parse(t); return !!j && typeof j==='object'; }catch(e){ return false; } };
  var again=function(last){
    // לא מאריכים סריקה שכבר קרובה לתקרת הזמן — עדיף לסיים ולנסות בסריקה הבאה
    var late = scanStart && (Date.now()-scanStart) > (SCAN_MAX_MIN-4)*60000;
    if(attempt>=POST_RETRY_WAITS.length || late){ cb(last); return; }
    var w=POST_RETRY_WAITS[attempt]; attempt++;
    status('השרת לא זמין — ניסיון '+(attempt+1)+'/'+(POST_RETRY_WAITS.length+1)+' בעוד '+Math.round(w/1000)+'ש׳...');
    setTimeout(send,w);
  };
  var send=function(){
    GM_xmlhttpRequest({method:'POST',url:WEBHOOK,data:body.toString(),headers:{'Content-Type':'application/x-www-form-urlencoded'},timeout:60000,
      onload:function(res){
        var t=res&&res.responseText;
        if(isJson(t)){log('POSTed '+rows.length+' → '+t);cb(t);return;}
        console.error('[yad2-sync] POST got HTML instead of JSON');again(t);
      },
      onerror:function(e){console.error('[yad2-sync] POST failed',e);again('שגיאה');},
      ontimeout:function(){console.error('[yad2-sync] POST timeout');again('פסק זמן');}});
  };
  send();
}

// ===== secretary panel =====
function status(t){var s=document.getElementById('ys-status');if(s)s.textContent=t;log(t);}
// בניית הפאנל — עמידה בפני דף שעוד לא נטען ובפני SPA שמוחק אלמנטים.
// ⚠️ אסור שכשל כאן יפיל את הסריקה: מי שקורא לזה עוטף ב-try/catch, וגם אם הפאנל לא נבנה — הכול ממשיך.
function buildPanel(){
  if(!document.body)return false;                     // הדף עוד לא מוכן — ניסיון נוסף בטיק הבא
  if(document.getElementById('ys-panel'))return true; // כבר קיים
  var box=document.createElement('div');box.id='ys-panel';
  box.style.cssText='position:fixed;bottom:16px;left:16px;z-index:2147483647;background:#1e293b;color:#fff;padding:14px;border-radius:12px;box-shadow:0 6px 20px rgba(0,0,0,.35);font-family:-apple-system,Arial,sans-serif;width:215px;direction:rtl';
  var bs='display:block;width:100%;margin:6px 0;padding:12px;border:0;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;color:#fff';
  var mk=function(id,bg,txt,fn,extra){
    var b=document.createElement('button');b.id=id;b.type='button';
    b.style.cssText=bs+';background:'+bg+(extra||'');b.textContent=txt;
    b.addEventListener('click',function(){try{fn();}catch(e){log('כפתור '+id+' נכשל: '+e);}});
    return b;
  };
  var t=document.createElement('div');t.style.cssText='font-weight:800;margin-bottom:6px;font-size:15px';t.textContent='📋 מצב מזכירה · v'+VER;
  box.appendChild(t);
  // מחברים את המאזינים ישירות לאלמנטים שיצרנו — בלי getElementById (שם נפל קודם)
  box.appendChild(mk('ys-reveal','#2563eb','📞 חשוף מספרים',revealAll));
  box.appendChild(mk('ys-save','#16a34a','💾 שמור לגיליון',manualSave));
  box.appendChild(mk('ys-net','#7c3aed','🔎 JSON לניתוח',copyNetReport,';font-size:13px;padding:9px'));
  box.appendChild(mk('ys-fam','#0f766e','🏠 סרוק רימקס פמילי',function(){
    var armed=exclForceArm && (Date.now()-exclForceArm)<30000;
    var r=exclScanFamilyNow(armed);
    status((r.ok?'✓ ':'⚠️ ')+r.msg);
  },';font-size:13px;padding:9px'));
  box.appendChild(mk('ys-offices','#b45309','🏢 סרוק משרדים עכשיו',function(){
    var armed=exclForceArm && (Date.now()-exclForceArm)<30000;   // לחיצה שנייה תוך 30ש' = אילוץ
    var r=exclScanNow(armed);
    status((r.ok?'✓ ':'⚠️ ')+r.msg);
  },';font-size:13px;padding:9px'));
  var st=document.createElement('div');st.id='ys-status';st.style.cssText='font-size:12px;margin-top:8px;color:#cbd5e1';st.textContent='מוכן';
  box.appendChild(st);
  document.body.appendChild(box);
  return true;
}
// שומר-פאנל: מחזיר אותו אם הדף לא היה מוכן, או אם ה-SPA של יד2 מחק אותו ברינדור מחדש
function panelKeeper(){
  try{ if(!document.getElementById('ys-panel')) buildPanel(); }catch(e){}
}
function revealAll(){
  paused=true;
  var all=Array.from(document.querySelectorAll('button,[role="button"],a,span')).filter(function(el){return el.textContent.trim()==='הצגת מספר'&&el.offsetParent!==null;});
  var btns=all.filter(function(el){return !all.some(function(o){return o!==el&&el.contains(o);});});
  if(!btns.length){status('לא נמצאו כפתורים לחשיפה');return;}
  status('חושף 0/'+btns.length+'...');
  var i=0;
  (function next(){
    if(i>=btns.length){status('✓ נחשפו '+btns.length+'. עכשיו לחצי שמור');return;}
    try{btns[i].click();}catch(e){}
    i++;status('חושף '+i+'/'+btns.length+'...');
    // קצב אנושי: 0.9-2.7ש' בין חשיפות, והפסקה ארוכה (3-6ש') כל ~15 — כמו מזכירה אמיתית
    var d=900+Math.random()*1800; if(i%15===0)d+=3000+Math.random()*3000;
    setTimeout(next,d);
  })();
}
function hasPhone(r){return String(r&&r.phone||'').replace(/\D/g,'').length>=7;}
function saveRows(rows,dom,full,done){
  // ⚠️ שומרים רק כשברור שזו טבלת השוק (מפתח מקור עם area:N). עמוד "הנכסים שלי"
  // או כל עמוד אחר בפלוס מייצר מקור profile:/default — ואז השורות מזהמות את
  // המודעות הפרטיות. עדיף לא לשמור מאשר לשמור לא נכון (v8.7).
  var sk=''; try{sk=srcKey();}catch(e){}
  if(sk.indexOf('area:')===-1){
    var msg='לא נשמר — העמוד אינו טבלת השוק (מקור '+(sk||'לא ידוע')+')';
    lastScanMsg=msg; try{postHB('ok');}catch(e){}
    status('⚠️ '+msg);
    if(done)done(msg);
    return;
  }
  mergeDomPhones(rows,dom);
  var withPhone=rows.filter(hasPhone).length, withLink=rows.filter(function(r){return r.link;}).length;
  status('שומר '+rows.length+' נכסים ('+withPhone+' טל׳, '+withLink+' קישורים)...');
  postRows(rows,function(resp){
    var m,ok=false;
    try{var j=JSON.parse(resp);m='נוספו '+j.added+' · פרטים '+(j.extras||0)+' · ירדו '+(j.delisted||0)+' · טל׳ '+withPhone+'/'+rows.length+' · קישורים '+withLink+' · מקור '+(j.src||'?');ok=true;}
    catch(e){
      // הפאנל נשאר נקי; הפירוט (מה גוגל באמת החזיר) נשלח בסימן-החיים ונקרא מרחוק ב-?health=1
      var snip=String(resp||'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,110);
      lastScanMsg='שגיאת שרת · '+(snip||'(תשובה ריקה)');
      try{postHB('ok');}catch(e2){}
      m='שגיאת שרת — לא נשמר (ננסה בסריקה הבאה)';
    } // תשובת HTML של גוגל במקום JSON: לא שופכים אותה לפאנל
    if(pgDiag)m+=' · '+pgDiag;   // למה הכיסוי הוא כזה — נראה גם בפאנל וגם מרחוק
    if(profSwitchNote)m+=profSwitchNote;
    if(ok){ lastScanMsg=m; try{postHB('ok');}catch(e2){} }   // שמירה מוצלחת גם היא מדווחת
    status((ok?'✓ ':'⚠️ ')+m);if(done)done(m);
  }, full);
}
// הסריקה המלאה — משמשת גם ידני וגם אוטומטי: כל העמודים + token/טלפון + זיהוי "ירד מפרסום"
function runFullScan(statusFn, done){
  var W=(typeof unsafeWindow!=='undefined')?unsafeWindow:window;
  var fetchFn=function(u){return fetchT(W,u);}; // עם תקרת זמן — בקשה תקועה לא מקפיאה את הסריקה
  // fin נקרא בדיוק פעם אחת בכל מסלול (כולל חריגה) — כך ה-paused של הלופ משוחרר תמיד
  scanStart=Date.now(); lastScanMsg='רץ מ-'+new Date().toLocaleTimeString('he-IL',{hour:'2-digit',minute:'2-digit'});
  var fin=once(function(msg){ scanStart=0; if(msg)lastScanMsg=msg; if(done)done(); });
  try{
    statusFn('קורא את כל הנכסים...');
    var afterPages=function(rows, full){
      try{
        var dom=extractRows();
        if(!rows.length){ // אין API בכלל — נפילה אחרונה לטבלה
          rows=dom;
          if(!rows.length){statusFn('לא נמצאו נכסים — הטבלה עוד לא נטענה');fin('אין נכסים');return;}
          saveRows(rows,dom,false,function(m){fin(m);}); return;
        }
        // תקרת שליפות בסריקה אחת — השאר יושלמו בסריקות הבאות (מונע סריקה שנמשכת שעות)
        var needAll=needTokens(rows), need=needAll.slice(0,TOKENS_PER_SCAN);
        if(!need.length){ saveRows(rows,dom,full,function(m){fin(m);}); return; }
        statusFn('משיג קישורים 0/'+need.length+(needAll.length>need.length?(' (מתוך '+needAll.length+', השאר בסריקה הבאה)'):'')+'…');
        fetchTokens(need, fetchFn,
          function(i,n,ok){ if(i%5===0||i===n) statusFn('משיג קישורים '+i+'/'+n+' ('+ok+' נמצאו)…'); },
          function(cache,ok){
            try{
              rows.forEach(function(r){var c=cache[r._orderId];if(c){if(!r.link&&c.t)r.link=itemLink(r._orderId,c.t,r._city);if(!hasPhone(r)&&c.p)r.phone=c.p;if(!r.description&&c.d)r.description=c.d;}});
              saveRows(rows,dom,full,function(m){fin(m);});
            }catch(e){log('scan error (tokens): '+e);fin('שגיאה: '+e);}
          });
      }catch(e){log('scan error (pages): '+e);fin('שגיאה: '+e);}
    };
    // דרך א' (מועדפת): הממשק של יד2 טוען את העמודים — הבקשות שלו לא נחסמות.
    // דרך ב' (גיבוי): משיכה עצמית, שנעצרת על 100 מודעות כשיד2 חוסם.
    uiPaginateAll(function(cur,total,n){ statusFn('עמוד '+cur+'/'+total+' · '+n+' נכסים...'); },
      function(uiRows, uiFull){
        if(uiRows && uiRows.length){ log('📄 פגינציה דרך הממשק: '+uiRows.length+' נכסים'+(uiFull?' (עד הסוף)':'')); afterPages(uiRows, uiFull); return; }
        activeFetchAllPages(fetchFn, function(page,n){ statusFn('קורא עמוד '+page+' ('+n+' נכסים)...'); }, afterPages);
      });
  }catch(e){log('scan error (start): '+e);fin('שגיאה: '+e);}
}
function manualSave(){ paused=true; runFullScan(status, function(){paused=false;}); }
// שומר-ראש: סריקה שנמשכת מעל SCAN_MAX_MIN דקות (חניקת טיימרים ברקע / בקשה תקועה / חסימת יד2)
// אינה "מתאוששת" מעצמה — ריענון הדף מנקה הכול ומתחיל סריקה חדשה מאפס.
function scanWatchdog(){
  if(!scanStart)return false;
  var mins=(Date.now()-scanStart)/60000;
  if(mins < SCAN_MAX_MIN)return false;
  log('⏱️ שומר-ראש: הסריקה תקועה '+mins.toFixed(1)+' דק׳ — מרענן את הדף');
  lastScanMsg='נתקע '+mins.toFixed(0)+' דק׳ → רוענן';
  postHB('stuck');
  scanStart=0; paused=false;
  setTimeout(function(){try{location.reload();}catch(e){}},1500); // שהיה ל-HB להישלח
  return true;
}

// ===== החלפת פרופיל אוטומטית (v6.7) =====
// החלפת הפרופיל ביד2 היא מצב-שרת ולא כתובת (נבדק 03/08), ולכן הדרך היחידה לסרוק את שני
// המלאים היא ללחוץ בתפריט החשבון. הכל עטוף: כשל בהחלפה = סורקים את הפרופיל הפעיל, בלי נזק.
var profSwitchNote='';
var PROFILE_KEY='yad2_profiles_v1';   // {labels:[...], last:'<label>'}
var SWITCH_TIMEOUT_MS=25000;
function profStore(){try{return JSON.parse(localStorage.getItem(PROFILE_KEY)||'{}');}catch(e){return {};}}
function profSave(o){try{localStorage.setItem(PROFILE_KEY,JSON.stringify(o));}catch(e){}}
// פריטי תפריט שאינם פרופיל. "עדכונים" נתפס בשטח (31/08) — הסורק לחץ עליו וההחלפה
// "לא הגיבה". כל מילה כאן היא פריט אמיתי מתפריט החשבון של יד2.
function notProfile(t){
  return /צור קשר|יצירת קשר|יציאה|התנתק|מהמערכת|לצפיה בפרופיל|לצפייה בפרופיל|הגדרות|עזרה|עדכונים|הודעות|התראות|תמיכה|חיפושים שמורים|המודעות שלי|הנכסים שלי|חשבון|מרכז|תשלום|חשבונית|מנוי/.test(t);
}
// כפתור החשבון בכותרת (מציג את שם הפרופיל הפעיל)
function accountButton(){ var a=activeProfile(); return a?a.el:null; }
// פריטי הפרופילים בתפריט הפתוח
function profileItems(){
  var out=[],seen={};
  var els=document.querySelectorAll('button,[role="button"],a,li,div');
  for(var i=0;i<els.length;i++){
    var t=(els[i].textContent||'').trim().replace(/\s+/g,' ');
    if(!t||t.length<4||t.length>40)continue;
    if(notProfile(t))continue;
    if(!/[֐-׿]/.test(t))continue;
    if(els[i].children&&els[i].children.length>2)continue;
    if(els[i].offsetParent===null)continue;
    if(seen[t])continue; seen[t]=1;
    out.push({el:els[i],label:t});
  }
  return out;
}
// מחליף לפרופיל שאינו הפעיל. done(true/false) — כשל לא מפיל כלום.
// profSwitchWhy — באיזה שלב בדיוק נכשלה ההחלפה. "נכשלה" לבד לא אומר כלום (v9.0).
var profSwitchWhy='';
function profileSwitch(done){
  done=once(done);
  var before=srcKey(), active=profileLabel();
  var beforeOffice=(function(){try{return officeIdSeen()||'';}catch(e){return '';}})();
  var beforeSig=(function(){try{return lastTableSig();}catch(e){return '';}})();
  profSwitchWhy='';
  var btn=accountButton();
  if(!btn){ profSwitchWhy='אין כפתור חשבון'; log('👤 לא נמצא כפתור החשבון — סורקים את הפרופיל הפעיל'); done(false); return; }
  try{btn.click();}catch(e){ profSwitchWhy='לחיצה על החשבון נכשלה'; done(false); return; }
  setTimeout(function(){
    var all=profileItems();
    var items=all.filter(function(x){return !active||x.label!==active;});
    // מכירים כבר את שמות הפרופילים? הם קודמים לכל ניחוש מהתפריט.
    var known=(profStore().labels||[]).filter(function(l){return l&&l!==active;});
    if(known.length){
      var pref=items.filter(function(x){return known.indexOf(x.label)>-1;});
      if(pref.length)items=pref.concat(items.filter(function(x){return known.indexOf(x.label)===-1;}));
    }
    if(!items.length){ profSwitchWhy='אין פרופיל שני בתפריט ('+all.length+' פריטים)'; log('👤 לא נמצא פרופיל אחר בתפריט'); try{btn.click();}catch(e){} done(false); return; }
    var st=profStore(); st.labels=(st.labels||[]);
    items.concat(active?[{label:active}]:[]).forEach(function(x){ if(st.labels.indexOf(x.label)===-1)st.labels.push(x.label); });
    profSave(st);
    log('👤 מחליף פרופיל ל-'+items[0].label);
    try{items[0].el.click();}catch(e){ done(false); return; }
    var t0=Date.now(), tries=0;
    (function wait(){
      // שלושה סימנים להצלחה — di שלושתם אומרים "המלאי שמול העיניים התחלף":
      // (1) מפתח המקור השתנה · (2) מזהה המשרד השתנה · (3) הגיעה תשובת טבלה חדשה.
      // בעבר נבדק רק (1), והוא נגזר ממסנן האזור — ולכן החלפה מוצלחת בין שני פרופילים
      // באותו אזור דווחה ככישלון (אייל, 31/08).
      var nowSrc=srcKey();
      var nowOffice=(function(){try{return officeIdSeen()||'';}catch(e){return '';}})();
      var nowSig=(function(){try{return lastTableSig();}catch(e){return '';}})();
      if(nowSrc!==before || (nowOffice&&nowOffice!==beforeOffice) || (nowSig&&nowSig!==beforeSig)){
        var st2=profStore(); st2.last=items[0].label; profSave(st2);
        profSwitchWhy='';
        log('👤 הוחלף בהצלחה ל-'+items[0].label+' ('+nowSrc+')');
        done(true); return;
      }
      // תקרה כפולה: זמן *וגם* מספר נסיונות (מכשיר שנרדם מקפיא את השעון ותוקע את הלופ)
      if(++tries>=16 || Date.now()-t0>SWITCH_TIMEOUT_MS){
        profSwitchWhy='נלחץ "'+items[0].label+'" ולא הגיב ('+nowSrc+')';
        log('👤 ההחלפה לא נקלטה — ממשיכים עם מה שיש'); done(false); return;
      }
      setTimeout(wait,1500);
    })();
  },1200);
}
// ===== auto loop — סריקה מלאה אוטומטית (זהה לידני, בלי מגע יד) =====
function waitScrape(attempt){
  attempt=attempt||0;
  if(attempt>30){log('rows never appeared');scheduleNext();return;}
  if(!latestApiTemplate()){ setTimeout(function(){waitScrape(attempt+1);},1000); return; } // ממתין שהטבלה/API ייטענו
  paused=true; // חוסם ריענון אוטומטי בזמן הסריקה הארוכה
  log('auto full scan starting…');
  // סירוגין בין הפרופילים: מחליפים ואז סורקים. בסריקה הבאה נחליף חזרה.
  profileSwitch(function(ok){
    // ההחלפה נכשלה? ניסיון שני (התפריט לפעמים נטען לאט), ואז מדווחים לשרת —
    // אחרת פרופיל אחד נסרק שוב ושוב ואיש לא יודע (אייל: "לא סורק את היוזר השני").
    if(ok){ profSwitchNote=''; runFullScan(log, function(){ paused=false; scheduleNext(); }); return; }
    setTimeout(function(){
      profileSwitch(function(ok2){
        profSwitchNote = ok2 ? '' : (' · ⚠️ החלפת פרופיל: '+(profSwitchWhy||'נכשלה'));
        runFullScan(log, function(){ paused=false; scheduleNext(); });
      });
    }, 3000);
  });
}
function scheduleNext(){
  if(paused){setTimeout(scheduleNext,60000);return;}
  if(isActive()){
    var d=rDelay();log('next reload in '+(d/60000).toFixed(1)+' min');
    setTimeout(function(){if(paused){scheduleNext();return;}log('reloading now');location.reload();},d);
  }else{
    log('💤 מחוץ לשעות הפעילות. ישן עד '+nextActive().toLocaleString());sleepCheck();
  }
}
function sleepCheck(){
  setTimeout(function(){if(isActive()){log('☀️ מתעורר, מרענן');location.reload();}else sleepCheck();},CHECK_MIN*60000);
}

// ===== init (deferred — the script itself starts at document-start for the tap) =====
// ===== קצב אנושי (v8.1) =====
// רצף בקשות במרווח אחיד הוא מה שמסגיר מכונה. כאן: רוב ההמתנות קצרות, אחת מכל כמה
// ארוכה בהרבה ("הסחת דעת"), וכל 8-14 בקשות יש הפסקה אמיתית של חצי דקה עד דקה וחצי.
var _gapN=0, _gapNext=8+Math.floor(Math.random()*7);
function humanGap(base, spread){
  var d = base + Math.random()*spread;
  if(Math.random()<0.18) d *= 2.5+Math.random()*3.5;          // עצירה קצרה באמצע
  if(++_gapN >= _gapNext){                                     // הפסקה ארוכה, במרווחים לא קבועים
    _gapN=0; _gapNext=8+Math.floor(Math.random()*7);
    d += 25000+Math.random()*65000;
  }
  return Math.round(d);
}
// כמות משתנה בכל ריצה — מספר קבוע של שליפות בכל סריקה הוא חתימה בפני עצמו
function jitterCap(cap){ return Math.max(3, Math.round(cap*(0.6+Math.random()*0.4))); }
// ערבוב — סדר קבוע של משרדים גם הוא חתימה (סניפי Family נשארים ראשונים)
function shuffle(arr){
  var a=arr.slice();
  for(var i=a.length-1;i>0;i--){ var j=Math.floor(Math.random()*(i+1)); var t=a[i];a[i]=a[j];a[j]=t; }
  return a;
}
// ===== סורק בלעדיות משרדים (2×יום: רנדומלי 08-09 + 17-18) =====
// השיטה (אומתה 22/7 בפרויקט הזחילה): דפי משרד/סוכן ציבוריים → __NEXT_DATA__ → isAssetExclusive.
// התזמון רץ בטאב פלוס (פתוח כל היום); בשעה שנקבעה נפתח טאב רקע ל-www שסורק, שולח (feed=daily) ונסגר.
// מדריך המשרדים של הקריות — הסורק מגלה ממנו את כל המשרדים בכל סריקה (משרד חדש נכנס אוטומטית)
var EXCL_DIRECTORY='https://www.yad2.co.il/realestate/agencies?region=5&area=6';
// שלושת דפי הסוכנות של רימקס Family (אייל, 24/08). נתוני המשרד עצמו נשאבים מהם בלבד,
// והם תמיד נסרקים — גם אם גילוי המדריך נכשל וגם אם נגמרה תקרת המשרדים לריצה.
var FAMILY_IDS=['5625538','5628636','8532791'];
function isFamId(id){return FAMILY_IDS.indexOf(String(id||''))>-1;}
var EXCL_OFFICES=FAMILY_IDS.map(function(id){return {id:Number(id),name:'Re/max Family'};}); // רשת ביטחון
var EXCL_FLAG='ysExclScan';
var EXCL_FAM_FLAG='famonly';   // סריקת שלושת סניפי Family בלבד (כפתור ייעודי)
// חילוץ משרדים מדף המדריך: עוגני agency/{id} + שם המשרד מתוך הכרטיס (השורה העברית הארוכה בטקסט העוגן)
function exclParseDirectory(html){
  var out={},m,re=/<a[^>]+href="[^"]*\/realestate\/agency\/(\d+)[^"]*"[^>]*>([\s\S]*?)<\/a>/g;
  while((m=re.exec(String(html)))){
    var id=m[1];
    var txt=m[2].replace(/<[^>]*>/g,'\n');
    var name='';
    // שם המשרד = השורה הראשונה בכרטיס שנראית כשם (2-60 תווים, מכילה אותיות, לא מונה כמו "12 נכסים")
    txt.split(/\n+/).map(function(s){return htmlDecode(s).replace(/\s+/g,' ').trim();}).forEach(function(line){
      if(!name&&line.length>=2&&line.length<=60&&/[֐-׿A-Za-z]/.test(line)&&!/^\d/.test(line)&&!/נכסים|מודעות למכירה|מודעות להשכרה/.test(line))name=line;
    });
    if(!out[id])out[id]={id:Number(id),name:name||('משרד '+id)};
    else if(out[id].name.indexOf('משרד ')===0&&name)out[id].name=name;
  }
  // גיבוי: מזהים שמופיעים ב-HTML בלי עוגן תקני
  var re2=/\/realestate\/agency\/(\d+)/g;
  while((m=re2.exec(String(html)))){if(!out[m[1]])out[m[1]]={id:Number(m[1]),name:'משרד '+m[1]};}
  return Object.keys(out).map(function(k){return out[k];});
}
// גילוי כל המשרדים מהמדריך (מעומד) — עד שאין מזהים חדשים. done(offices, dirDiag)
function exclDiscoverOffices(fetchFn,done){
  var all={},page=1,perPage=[]; // perPage: כמה מזהים חדשים כל עמוד תרם (דיאגנוסטיקה: המדריך מעומד באמת? נגמר מוקדם?)
  function fin(){
    // גם אם המדריך לא החזיר אותם (או נחסם) — שלושת סניפי Family נכנסים תמיד, ובראש הרשימה
    FAMILY_IDS.forEach(function(id){ if(!all[id]) all[id]={id:Number(id),name:'Re/max Family'}; });
    var list=Object.keys(all).map(function(k){return all[k];});
    var fam=list.filter(function(o){return isFamId(o.id);});
    var rest=shuffle(list.filter(function(o){return !isFamId(o.id);}));   // סדר משתנה בכל ריצה
    list=fam.concat(rest);
    done(list,{pages:perPage.length,perPage:perPage,total:list.length,fam:FAMILY_IDS.length});
  }
  (function next(){
    fetchFn(EXCL_DIRECTORY+'&page='+page).then(function(html){
      var found=exclParseDirectory(html),fresh=0;
      found.forEach(function(o){if(!all[o.id]){all[o.id]=o;fresh++;}});
      perPage.push(fresh);
      if(fresh&&page<30){page++;setTimeout(next,humanGap(1300,1500));}
      else fin();
    }).catch(fin);
  })();
}
function gmGet(k,d){try{if(typeof GM_getValue==='function'){var v=GM_getValue(k);return v===undefined?d:v;}}catch(e){}try{var s=localStorage.getItem('gm_'+k);return s===null?d:s;}catch(e){return d;}}
function gmSet(k,v){try{if(typeof GM_setValue==='function'){GM_setValue(k,v);return;}}catch(e){}try{localStorage.setItem('gm_'+k,v);}catch(e){}}
// לוח זמנים יומי: רגע רנדומלי בחלון 08-09 ורגע רנדומלי בחלון 17-18 (rnd מוזרק לבדיקות)
function exclSchedule(dayStr,rnd){
  rnd=rnd||Math.random;
  var d=new Date(dayStr+'T00:00:00');
  var m=new Date(d);m.setHours(8,0,0,0);
  var e=new Date(d);e.setHours(17,0,0,0);
  return {date:dayStr,m:{t:m.getTime()+Math.floor(rnd()*3600000),done:false},e:{t:e.getTime()+Math.floor(rnd()*3600000),done:false}};
}
function exclDayStr(now){var d=new Date(now);var p=function(n){return (n<10?'0':'')+n;};return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());}
// אילו סריקות הגיע זמנן (כולל השלמה אם הדפדפן היה סגור בחלון — catch-up); שתיהן יחד = סריקה אחת שמסמנת את שתיהן
function exclDue(state,now){
  var due=[];
  if(state&&state.m&&!state.m.done&&now>=state.m.t)due.push('m');
  if(state&&state.e&&!state.e.done&&now>=state.e.t)due.push('e');
  return due;
}
function exclLoadState(now){
  var day=exclDayStr(now);
  var st=null;try{st=JSON.parse(gmGet('ysExclSched','null'));}catch(e){}
  if(!st||st.date!==day){st=exclSchedule(day);gmSet('ysExclSched',JSON.stringify(st));}
  return st;
}
function exclSaveState(st){gmSet('ysExclSched',JSON.stringify(st));}
// __NEXT_DATA__ מתוך HTML (regex — בלי DOMParser, ניתן לבדיקה ב-node)
function exclParseNextData(html){
  var m=String(html).match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if(!m)return null;
  try{return JSON.parse(m[1]);}catch(e){return null;}
}
// מאתר את מערכי המודעות בכל מקום ב-JSON (אובייקטים עם token+price+address) — איחוד לפי token
function exclFindListings(nd){
  var out={},n=0;
  (function walk(o,d){
    if(!o||typeof o!=='object'||d>8)return;
    if(Array.isArray(o)){
      o.forEach(function(x){
        if(x&&typeof x==='object'&&x.token&&x.address&&(x.price!==undefined)){if(!out[x.token]){out[x.token]=x;n++;}}
        else walk(x,d+1);
      });
    }else{for(var k in o)walk(o[k],d+1);}
  })(nd,0);
  return Object.keys(out).map(function(t){return out[t];});
}
// מודעה מ-__NEXT_DATA__ (המודל המאומת) → שורת ייבוא. בלעדיות בלבד (inProperty.isAssetExclusive)
// כתובת התמונה הראשונה של מודעת משרד. המבנה של יד2 משתנה בין גרסאות, ולכן:
// קודם מפתחות מוכרים, ואם אין — הכתובת הראשונה בפריט שנראית כמו קובץ תמונה.
// ⚠️ אפס בקשות נוספות ליד2 — הכל מתוך ה-JSON שכבר נקרא.
function itemImage(it){
  try{
    var direct=[it.coverImage, it.cover_image, it.mainImage,
      it.metaData&&it.metaData.coverImage, it.metaData&&it.metaData.images&&it.metaData.images[0],
      it.images&&(it.images[0]||it.images.images&&it.images.images[0])];
    for(var i=0;i<direct.length;i++){
      var v=direct[i];
      if(typeof v==='string'&&/^https?:\/\//.test(v))return v;
      if(v&&typeof v==='object'&&typeof v.src==='string')return v.src;
      if(v&&typeof v==='object'&&typeof v.url==='string')return v.url;
    }
    var found='';
    (function walk(o,d){
      if(found||!o||typeof o!=='object'||d>6)return;
      if(Array.isArray(o)){o.forEach(function(x){walk(x,d+1);});return;}
      for(var k in o){
        if(found)return;
        var v=o[k];
        if(typeof v==='string'){
          if(/^https?:\/\/[^\s"']+\.(?:jpe?g|png|webp)/i.test(v)&&!/logo|icon|sprite|avatar/i.test(v))found=v;
        } else walk(v,d+1);
      }
    })(it,0);
    return found;
  }catch(e){ return ''; }
}
function exclMapItem(it){
  it=it||{};var a=it.address||{};
  var g=function(o,k){return (o&&o[k]&&o[k].text!==undefined)?String(o[k].text):'';};
  var det=it.additionalDetails||{};
  var tags=(it.tags||[]).map(function(t){return t&&t.name?String(t.name):'';}).filter(Boolean).join(';');
  return{
    image:itemImage(it),
    agent:'',city:g(a,'city'),neighborhood:g(a,'neighborhood'),street:g(a,'street'),
    homeNum:(a.house&&a.house.number!=null)?String(a.house.number):'',
    type:(det.property&&det.property.text)?String(det.property.text):'',
    rooms:det.roomsCount!=null?String(det.roomsCount):'',sqm:det.squareMeter!=null?String(det.squareMeter):'',
    price:it.price!=null?String(it.price):'',tags:tags,
    link:'https://www.yad2.co.il/realestate/item/'+it.token,description:'',phone:''
  };
}
function exclIsExclusive(it){return !!(it&&it.inProperty&&it.inProperty.isAssetExclusive===true);}
// ===== סוכן אמיתי לכל מודעה (v6.0) =====
// "שם סוכן אמיתי" = לא ריק, לא 'משרד', לא '(לא משויך)', ולא שם המשרד עצמו — כי מה שמעניין זה מי הסוכן.
function isRealAgent(name, officeName){
  var s=String(name||'').trim();
  if(!s||s.length<2)return false;
  // ⚠️ בלי \b — ב-JS גבול-מילה לא עובד על עברית (אות עברית אינה \w). 'משרד' / 'משרד 4723809' = מציין-מקום.
  if(/^משרד(\s*\d+)?$/.test(s)||/\(לא משויך\)/.test(s)||/^סוכן \d+$/.test(s))return false;
  var o=String(officeName||'').trim();
  if(o && (s===o || s.indexOf(o)===0))return false;   // "מגה נדל"ן" כשם סוכן = בעצם המשרד
  return true;
}
var AGENT_CACHE_KEY='yad2_agents_v1';
function agentCache(){try{return JSON.parse(localStorage.getItem(AGENT_CACHE_KEY)||'{}');}catch(e){return {};}}
function agentCacheSave(c){try{localStorage.setItem(AGENT_CACHE_KEY,JSON.stringify(c));}catch(e){}}
// שם+טלפון הסוכן מדף המודעה הציבורי: מחפשים בכל ה-JSON אובייקט שנראה כמו "כרטיס סוכן"
// (שם + טלפון, ובונוס למספר רישיון) ומדלגים על כרטיס המשרד. מחזיר {a:שם, p:טלפון}.
function parseItemAgent(html, officeName){
  var nd=exclParseNextData(html); var best=null;
  var nameKey=/^(name|fullName|full_name|contactName|agentName|customerName|title)$/i;
  var phoneKey=/(phone|mobile|cell|tel)/i;
  var licKey=/(licen[cs]e|licenseNumber|license_number|rishayon)/i;
  function consider(o){
    var nm='',ph='',lic=false,agencyish=false;
    for(var k in o){
      var v=o[k];
      if(typeof v==='string'){
        if(!nm&&nameKey.test(k)&&v.trim().length>=2&&v.trim().length<=40&&/[֐-׿A-Za-z]/.test(v))nm=v.trim();
        if(!ph&&phoneKey.test(k)){var d=normPhone(v);if(d)ph=d;}
      }else if(typeof v==='number'&&phoneKey.test(k)){var d2=normPhone(String(v));if(!ph&&d2)ph=d2;}
      if(licKey.test(k)&&v)lic=true;
      if(/agency|office|merchant|company|brand/i.test(k)&&typeof v==='string'&&v.trim())agencyish=true;
    }
    if(!nm)return;
    if(!isRealAgent(nm,officeName))return;
    var score=(ph?2:0)+(lic?3:0)+(agencyish?1:0);
    if(!best||score>best.score)best={a:nm,p:ph,score:score};
  }
  (function walk(o,d){
    if(!o||typeof o!=='object'||d>10)return;
    if(Array.isArray(o)){o.forEach(function(x){walk(x,d+1);});return;}
    consider(o);
    for(var k in o)walk(o[k],d+1);
  })(nd,0);
  if(!best){ // גיבוי: שם צמוד ל"מס' רישיון" בטקסט הדף (כמו שמוצג למשתמש)
    var m=String(html).match(/([֐-׿][֐-׿' ]{2,30})\s*<[^>]*>\s*(?:מס['׳] רישיון|מספר רישיון)/);
    if(m&&isRealAgent(m[1],officeName)){var pm=String(html).match(/href="tel:([\d\-+ ]{7,20})"/);best={a:m[1].trim(),p:pm?normPhone(pm[1]):'',score:0};}
  }
  var desc=itemDesc(html);                       // התיאור מאותו דף — "חינם", בלי בקשה נוספת
  if(!best)return desc?{a:'',p:'',d:desc}:null;   // אין סוכן אבל יש תיאור? עדיין שווה לשמור
  return {a:best.a,p:best.p,d:desc};
}
// תיאור הנכס מדף המודעה: התיאור החופשי הארוך ביותר בעברית ב-__NEXT_DATA__, בלי זבל/HTML
function itemDesc(html){
  var nd=exclParseNextData(html); if(!nd)return '';
  var keys=/^(description|info_text|freeText|adDescription|about|remark|remarks|text|body_text)$/i;
  var best='';
  (function walk(o,d){
    if(!o||typeof o!=='object'||d>10)return;
    if(Array.isArray(o)){o.forEach(function(x){walk(x,d+1);});return;}
    for(var k in o){
      var v=o[k];
      if(typeof v==='string'){
        var t=v.trim();
        if(t.length>=25&&/[֐-׿]/.test(t)&&!looksJunk(t)&&(keys.test(k)||t.length>best.length+40)){
          if(t.length>best.length)best=t;
        }
      } else walk(v,d+1);
    }
  })(nd,0);
  return cleanAdDesc(best).slice(0,2000);   // תיאור הנכס בלבד, בלי SEO ובלי פרסומת המשרד
}
// שליפת דף מודעה עבור שורות בלי סוכן אמיתי — עדין, מוגבל בכמות, ועם cache לנצח (טוקן→סוכן)
function fetchItemAgents(rows, officeName, fetchFn, cap, onProg, done, stats, officeId){
  done=once(done);
  stats=stats||{};stats.tried=0;stats.ok=0;stats.fail=0;stats.blocked=0;
  var cache=agentCache(), need=[], seen={}, now=Date.now();
  (rows||[]).forEach(function(r){
    var tok=String(r.link||'').split('/').pop();
    if(!tok||seen[tok])return; seen[tok]=1;
    var c=cache[tok];
    if(c&&c.a)return;                                     // כבר יש סוכן ב-cache
    var noAgent=!isRealAgent(r.agent,officeName);
    // כשל נשמר עם מונה+חותמת: עד 3 ניסיונות. מודעה בלי שם סוכן חוזרת אחרי 6 שעות
    // (זה החוסר הבולט בסיכום), מודעה שחסר בה רק תיאור — אחרי יממה.
    if(c&&c.f){ if(c.f>=3 || (now-(c.t||0)) < (noAgent?6:24)*3600000) return; }
    if(!noAgent && r.phone && r.description)return;       // יש סוכן+טלפון+תיאור → אין צורך
    // דירוג: קודם מי שאין לו שם סוכן, אחריו מי שחסר תיאור, ואז השאר
    need.push({tok:tok,row:r,pri:(noAgent?0:(r.description?2:1))});
  });
  need.sort(function(a,b){return a.pri-b.pri;});
  // סניפי רימקס Family — פי ארבעה, כי זה הסיכום שאייל עובד איתו (וסניף חדש מגיע ריק)
  var isFam=isFamId(officeId);
  need=need.slice(0, cap||jitterCap(isFam?ITEM_AGENTS_PER_SCAN*3:ITEM_AGENTS_PER_SCAN));
  if(!need.length){ applyAgents(rows,cache,officeName); done(0); return; }
  var i=0, got=0;
  var fin=function(){ agentCacheSave(cache); applyAgents(rows,cache,officeName); done(got); };
  (function next(){
    if(i>=need.length){ fin(); return; }
    var it=need[i++];
    fetchFn('https://www.yad2.co.il/realestate/item/'+it.tok).then(function(html){
      stats.tried++;
      if(looksBlocked(html)){ // ⚠️ חסימה — לא רושמים כשל (אחרת נמחקת המודעה מהתור לנצח); עוצרים
        stats.blocked++;
        if(!stats.sample)stats.sample={why:'blocked',len:String(html).length};
        if(onProg)onProg(i,need.length,got);
        fin(); return;
      }
      var a=parseItemAgent(html, officeName);
      if(a){ cache[it.tok]={a:a.a,p:a.p,d:a.d||''}; got++; stats.ok++; }  // גם התיאור נשמר ב-cache
      else { var pf=cache[it.tok]; cache[it.tok]={f:((pf&&pf.f)||0)+1,t:Date.now()}; stats.fail++;
             if(!stats.sample){ var tm=String(html).match(/<title>([^<]{0,60})/); stats.sample={why:'noagent',title:tm?tm[1]:'',nd:String(html).indexOf('__NEXT_DATA__')>-1,len:String(html).length}; } }
      if(onProg)onProg(i,need.length,got);
      setTimeout(next, humanGap(1400,2600));
    }).catch(function(e){
      stats.tried++;stats.fail++;
      var pf=cache[it.tok]; cache[it.tok]={f:((pf&&pf.f)||0)+1,t:Date.now()};
      if(!stats.sample)stats.sample={why:'fetcherr',err:String(e&&e.message||e).slice(0,40)};
      if(onProg)onProg(i,need.length,got); setTimeout(next,humanGap(1800,2600));
    });
  })();
}
// מחיל את ה-cache על השורות: שם הסוכן וטלפונו גוברים על "משרד"/טלפון המשרד
function applyAgents(rows, cache, officeName){
  (rows||[]).forEach(function(r){
    var tok=String(r.link||'').split('/').pop();
    var a=cache&&cache[tok];
    if(!a)return;
    if(a.a&&!isRealAgent(r.agent,officeName))r.agent=a.a;
    if(a.p)r.phone=a.p;
    if(a.d&&!r.description)r.description=a.d;   // תיאור הנכס — מדף המודעה
  });
}
// מזהי סוכנים מדף המשרד + שם סוכן מדף הסוכן (h1; נפילה ל'סוכן <id>')
function exclBrokerIds(html){
  var ids={},m,re=/\/broker\/(\d+)/g;
  while((m=re.exec(String(html))))ids[m[1]]=1;
  return Object.keys(ids);
}
function exclBrokerName(html){
  var m=String(html).match(/<h1[^>]*>([\s\S]*?)<\/h1>/);
  if(!m)return'';
  return m[1].replace(/<[^>]*>/g,'').replace(/\s+/g,' ').trim();
}
// מפענח ישויות HTML בשמות (נדל&quot;ן → נדל"ן)
function htmlDecode(s){return String(s||'').replace(/&quot;/g,'"').replace(/&#x27;/gi,"'").replace(/&#39;/g,"'").replace(/&apos;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&');}
// נרמול טלפון ישראלי: 972... → 0...; רק 9-10 ספרות נחשב טלפון
function normPhone(p){var d=String(p||'').replace(/\D/g,'');if(d.slice(0,3)==='972')d='0'+d.slice(3);return (d.length>=9&&d.length<=10)?d:'';}
// טלפונים מדף ציבורי (משרד/סוכן): קישורי tel: + מפתחות phone ב-JSON המוטמע. ייחודי, מנורמל.
function pagePhones(html){
  var s=String(html),out=[],m;
  var re=/href="tel:([\d+\-() ]{7,20})"/g;
  while((m=re.exec(s)))out.push(m[1]);
  var re2=/"[A-Za-z_]*[Pp]hone[A-Za-z_0-9]*"\s*:\s*"([\d+\-() ]{7,20})"/g;
  while((m=re2.exec(s)))out.push(m[1]);
  var seen={},res=[];
  out.forEach(function(p){var n=normPhone(p);if(n&&!seen[n]){seen[n]=1;res.push(n);}});
  return res;
}
// שם המשרד מדף המשרד (title / og:title) — גיבוי כשהמדריך לא חילץ שם
function exclOfficeName(html){
  var s=String(html);
  var m=s.match(/<title>([\s\S]*?)<\/title>/);
  if(m){var t=htmlDecode(m[1]).replace(/\s+/g,' ').replace(/\s*[|\-–—].*$/,'').trim();
    if(t&&t.length>=2&&t.length<=60&&!/^yad2$|^יד2$/i.test(t))return t;}
  var og=s.match(/property="og:title"\s+content="([^"]+)"/)||s.match(/content="([^"]+)"\s+property="og:title"/);
  if(og){var o=htmlDecode(og[1]).replace(/\s*[|\-–—].*$/,'').trim();if(o&&o.length<=60)return o;}
  return '';
}
// זחילת משרד שלם: סוכן-סוכן (שיוך שם) ואז עמודי המשרד (לא-משויכים). fetchFn מוזרק; קצב אנושי.
function exclCrawlOffice(office,fetchFn,onProg,done){
  var base='https://www.yad2.co.il/realestate/agency/'+office.id;
  var rows={},order=[]; // token → row
  var officePhone=''; // טלפון המשרד מדף הסוכנות — נופל אליו כשאין טלפון סוכן
  // דיאגנוסטיקה: התפלגות דגל הבלעדיות + דגימת שדות של מודעה ראשונה (לניתוח מרחוק דרך action=diag)
  var diag={id:office.id,name:office.name,items:0,exclTrue:0,exclFalse:0,noInProp:0,phones:0,sample:null};
  function addItems(items,agent,phone){
    items.forEach(function(it){
      if(!it||!it.token)return;
      diag.items++;
      if(!it.inProperty)diag.noInProp++;
      else if(exclIsExclusive(it))diag.exclTrue++;else diag.exclFalse++;
      if(!diag.sample)diag.sample={keys:Object.keys(it).slice(0,40),inProperty:it.inProperty||null,tags:(it.tags||[]).map(function(t){return t&&t.name;}).filter(Boolean)};
      // 🐞 v8.4: עמוד 1 של המשרד נקרא לפני עמודי הסוכנים ומוסיף הכל כ"לא משויך".
      // ה-dedupe לפי token חסם אחר כך את השם האמיתי מעמוד הסוכן — ולכן מודעות
      // מעמוד 1 נשארו בלי שם סוכן לתמיד (אייל: "לקובי חמו 28 מודעות ומופיע 7").
      // עכשיו: שורה קיימת עם שם-מדומה מקבלת שדרוג כששם אמיתי מגיע.
      var ex=rows[it.token];
      if(ex){
        if(isRealAgent(agent,office.name) && !isRealAgent(ex.agent,office.name)){
          ex.agent=agent;
          if(phone)ex.phone=phone;
          diag.upgraded=(diag.upgraded||0)+1;
        }
        return;
      }
      var r=exclMapItem(it);r.agent=agent;r.excl=exclIsExclusive(it)?'1':'0';
      // טלפון הסוכן קודם; טלפון המשרד רק כנפילה (אייל: "מה שמעניין זה מי הסוכן, לא המשרד")
      r.phone=phone||officePhone||''; if(r.phone)diag.phones++;
      if(!diag.sampleItemKeys)diag.sampleItemKeys=Object.keys(it); // לאימות שדות הסוכן במודעה עצמה
      rows[it.token]=r;order.push(it.token);
    });
  }
  function pages(url,cb,collect){ // עובר עמודים עד עמוד ריק (תקרה 60)
    var p=1;
    (function next(){
      fetchFn(url+'?page='+p).then(function(html){
        if(looksBlocked(html)){ diag.blocked=1; cb(); return; }
        var nd=exclParseNextData(html);
        var items=nd?exclFindListings(nd):[];
        collect(items,html,p);
        if(onProg)onProg(office.name,url.split('/').slice(-2).join('/'),p,items.length);
        if(items.length&&p<60){p++;setTimeout(next,humanGap(1800,2200));} // קצב אנושי = פחות חסימות
        else cb();
      }).catch(function(){cb();});
    })();
  }
  // שלב 1: דף משרד ראשון — רשימת הסוכנים
  fetchFn(base+'/forsale?page=1').then(function(html){
    if(looksBlocked(html)){ diag.blocked=1; done([],diag); return; } // עמוד CAPTCHA — לא "משרד ריק"
    var nm=exclOfficeName(html); if(nm && (!office.name || office.name.indexOf('משרד ')===0)) office.name=nm; // שם אמיתי מדף המשרד אם המדריך נכשל
    officePhone=pagePhones(html)[0]||''; // טלפון המשרד (tel:/JSON) — ברירת המחדל לכל מודעות המשרד
    var bids=exclBrokerIds(html);
    var nd=exclParseNextData(html);if(nd)addItems(exclFindListings(nd),office.name+' (לא משויך)','');
    var bi=0;
    (function nextBroker(){
      if(bi>=bids.length){ // שלב 3: שאר עמודי המשרד — מה שלא שויך לסוכן
        var p=2;
        (function nextOfficePage(){
          fetchFn(base+'/forsale?page='+p).then(function(h){
            var nd2=exclParseNextData(h);var items=nd2?exclFindListings(nd2):[];
            addItems(items,office.name+' (לא משויך)','');
            if(onProg)onProg(office.name,'forsale',p,items.length);
            if(items.length&&p<60){p++;setTimeout(nextOfficePage,humanGap(1800,2200));}
            else done(order.map(function(t){return rows[t];}),diag);
          }).catch(function(){done(order.map(function(t){return rows[t];}),diag);});
        })();
        return;
      }
      var bid=bids[bi++];
      // שלב 2: עמודי הסוכן — הנכסים שלו על שמו (+טלפון הסוכן מהדף שלו, כשמופיע)
      fetchFn(base+'/broker/'+bid+'/forsale?page=1').then(function(h1){
        var nm0=exclBrokerName(h1);
        var name=isRealAgent(nm0,office.name)?nm0:('סוכן '+bid); // h1 שהוא 'משרד'/שם המשרד = לא סוכן
        var bPhone=pagePhones(h1)[0]||'';
        var nd1=exclParseNextData(h1);if(nd1)addItems(exclFindListings(nd1),name,bPhone);
        var p=2;
        (function nextBp(){
          fetchFn(base+'/broker/'+bid+'/forsale?page='+p).then(function(h){
            var ndp=exclParseNextData(h);var items=ndp?exclFindListings(ndp):[];
            addItems(items,name,bPhone);
            if(onProg)onProg(office.name,'broker/'+bid,p,items.length);
            if(items.length&&p<40){p++;setTimeout(nextBp,1500+Math.random()*1500);}
            else setTimeout(nextBroker,2500+Math.random()*2000);
          }).catch(function(){setTimeout(nextBroker,1200);});
        })();
      }).catch(function(){setTimeout(nextBroker,1200);});
    })();
  }).catch(function(){done([],diag);});
}
// שליחת סנאפשוט משרד ל-CRM (feed=daily → ירידות/מחירים/תיאורים מטופלים בשרת)
function exclPostOffice(officeName,officeId,rowsArr,cb){
  var body='secret='+encodeURIComponent(SECRET)+'&action=importexcl&feed=daily&office='+encodeURIComponent(officeName)+'&officeId='+encodeURIComponent(officeId||'')+'&machine='+encodeURIComponent((function(){try{return machineId();}catch(e){return '';}})())+'&data='+encodeURIComponent(JSON.stringify(rowsArr));
  GM_xmlhttpRequest({method:'POST',url:WEBHOOK,data:body,headers:{'Content-Type':'application/x-www-form-urlencoded'},
    onload:function(r){var j={};try{j=JSON.parse(r.responseText);}catch(e){}cb(null,j);},
    onerror:function(){cb('network');}});
}
// צד פלוס: טיימר דקה — כשמגיע הזמן, פותחים טאב רקע לסריקה
// הפעלה ידנית של סריקת המשרדים (כפתור בפאנל). אותו מסלול כמו המתוזמנת —
// מנקה את סימון "בוצע היום" ואת ההתקדמות, כדי שהסריקה תתחיל מהמשרד הראשון.
// מנוחה אחרי חסימת יד2 מכובדת: לחיצה ראשונה מזהירה, שנייה מאלצת.
var exclForceArm=0;
// סריקת שלושת הסניפים בלבד. אותן הגנות כמו הסריקה המלאה.
function exclScanFamilyNow(force){
  var now=Date.now();
  var cool=Number(gmGet('ysExclCool','0'));
  if(now<cool && !force){
    exclForceArm=now;
    return {ok:false,msg:'יד2 חסם לאחרונה — מנוחה עוד '+Math.ceil((cool-now)/60000)+' דק׳. לחץ שוב כדי לסרוק בכל זאת'};
  }
  if(!force && !exclScanDead(now,Number(gmGet('ysExclScanHB','0')),Number(gmGet('ysExclLaunch','0')))){
    // ההודעה הישנה ("כבר רצה") הטעתה: לרוב זו פשוט לחיצה שנייה בתוך 5 דקות (אייל, 01/09)
    var hb2=Number(gmGet('ysExclScanHB','0')), lc2=Number(gmGet('ysExclLaunch','0'));
    var why = (now-hb2<3*60000) ? ('סריקה פעילה — דופק לפני '+Math.round((now-hb2)/1000)+'ש׳')
                                : ('שוגרה לפני '+Math.round((now-lc2)/60000)+' דק׳');
    return {ok:false,msg:why+'. לחץ שוב כדי להפעיל בכל זאת'};
  }
  if(force){gmSet('ysExclCool','0');gmSet('ysExclScanHB','0');gmSet('ysExclLaunch','0');}
  try{ exclRunClear(); }catch(e){}          // שהסניפים לא ידולגו בגלל יומן ההתקדמות
  gmSet('ysExclLaunch',String(now));
  try{ GM_openInTab(EXCL_DIRECTORY+'#'+EXCL_FLAG+'-'+EXCL_FAM_FLAG,{active:true,insert:true}); }
  catch(e){ return {ok:false,msg:'פתיחת הטאב נכשלה: '+e}; }
  log('🏠 סריקת רימקס Family הופעלה ידנית'+(force?' (בכפייה)':''));
  return {ok:true,msg:'סורק את 3 סניפי רימקס Family — נפתח טאב, אל תסגור אותו'};
}
function exclScanNow(force){
  var now=Date.now();
  var cool=Number(gmGet('ysExclCool','0'));
  if(now<cool && !force){
    var mins=Math.ceil((cool-now)/60000);
    exclForceArm=now;
    return {ok:false,msg:'יד2 חסם לאחרונה — מנוחה עוד '+mins+' דק׳. לחץ שוב כדי לסרוק בכל זאת'};
  }
  if(!force && !exclScanDead(now,Number(gmGet('ysExclScanHB','0')),Number(gmGet('ysExclLaunch','0')))){
    var hb3=Number(gmGet('ysExclScanHB','0')), lc3=Number(gmGet('ysExclLaunch','0'));
    var why3 = (now-hb3<3*60000) ? ('סריקה פעילה — דופק לפני '+Math.round((now-hb3)/1000)+'ש׳')
                                 : ('שוגרה לפני '+Math.round((now-lc3)/60000)+' דק׳');
    return {ok:false,msg:why3+'. לחץ שוב כדי להפעיל בכל זאת'};
  }
  if(force){gmSet('ysExclCool','0');gmSet('ysExclScanHB','0');gmSet('ysExclLaunch','0');}
  try{
    var st=exclLoadState(now); st.m.done=false; st.e.done=false; exclSaveState(st); // שתי הריצות "לא בוצעו"
  }catch(e){}
  try{ exclRunClear(); }catch(e){}          // מתחילים מהמשרד הראשון (סניפי Family בראש)
  gmSet('ysExclLaunch',String(now));
  try{ GM_openInTab(EXCL_DIRECTORY+'#'+EXCL_FLAG,{active:true,insert:true}); }
  catch(e){ return {ok:false,msg:'פתיחת הטאב נכשלה: '+e}; }
  log('🏢 סריקת משרדים הופעלה ידנית'+(force?' (בכפייה)':''));
  return {ok:true,msg:'סריקת משרדים התחילה — נפתח טאב, אל תסגור אותו'};
}
// גלאי תקיעה לסריקת המשרדים (v9.6). לסריקה הפרטית יש שומר-ראש; לזו לא היה —
// וטאב שנחנק ברקע (כרום מקפיא טיימרים בטאבי רקע) מת בשקט, בלי סיכום ובלי דיאגנוסטיקה.
// כאן: משחררים את הנעילה כדי שהכפתור והמתזמן יוכלו לשגר מחדש, ומדווחים לשרת.
function exclStallCheck(now){
  var launched=Number(gmGet('ysExclLaunch','0'));
  if(!launched)return false;
  var done=Number(gmGet('ysExclDone','0'));
  if(done>=launched)return false;                 // הריצה האחרונה הסתיימה
  if(now-launched<6*60000)return false;           // עדיין בטווח סביר
  var hb=Number(gmGet('ysExclScanHB','0'));
  if(now-hb<3*60000)return false;                 // יש דופק — חיה, גם אם איטית
  gmSet('ysExclLaunch','0'); gmSet('ysExclScanHB','0');   // שחרור
  var mins=Math.round((now-launched)/60000);
  lastScanMsg='⚠️ סריקת משרדים נתקעה ('+mins+' דק׳ בלי דופק) — שוחררה, אפשר להפעיל שוב';
  try{postHB('ok');}catch(e){}
  log('⚠️ סריקת משרדים נתקעה '+mins+' דק׳ — משחרר');
  return true;
}
function exclSchedTick(){
  var now=Date.now(),st=exclLoadState(now),due=exclDue(st,now);
  exclStallCheck(now);   // סריקה שנתקעה משוחררת לפני שמחליטים אם לשגר
  var el=document.getElementById('ys-excl');
  if(!el){var host=document.getElementById('ys-status');if(host&&host.parentNode){el=document.createElement('div');el.id='ys-excl';el.style.cssText='font-size:11px;color:#94a3b8;margin-top:4px';host.parentNode.appendChild(el);}}
  var fmt=function(t){var d=new Date(t);return ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2);};
  if(el){
    var last=gmGet('ysExclLast','');
    var qw=quietWin(new Date(now)),qs=Math.floor(qw.s/60),qm=qw.s%60,qe=Math.floor(qw.e/60),qem=qw.e%60;
    var quietStr=' · 🤫 שקט '+('0'+qs).slice(-2)+':'+('0'+qm).slice(-2)+'-'+('0'+qe).slice(-2)+':'+('0'+qem).slice(-2)+(inQuiet(new Date(now))?' (עכשיו)':'');
    el.textContent='🏢 בלעדיות: בוקר '+fmt(st.m.t)+(st.m.done?' ✓':'')+' · ערב '+fmt(st.e.t)+(st.e.done?' ✓':'')+quietStr+(last?' · '+last:'');
  }
  if(!due.length)return;
  if(inQuiet(new Date(now)))return; // חלון שקט — דוחים; ההשלמה (catch-up) תפעיל אחריו
  var cool=Number(gmGet('ysExclCool','0'));
  if(now<cool)return;               // מנוחה אחרי חסימת יד2 — לא דוחפים לקיר
  // סריקה חיה? טאב הסריקה כותב heartbeat כל ~20ש'. טרי = לא פותחים כפול.
  // מת באמצע (חניקת טיימרים/קריסה)? אחרי 3 דק' בלי דופק משגרים מחדש — וההתקדמות נשמרת (resume).
  if(!exclScanDead(now,Number(gmGet('ysExclScanHB','0')),Number(gmGet('ysExclLaunch','0'))))return;
  gmSet('ysExclLaunch',String(now));
  // active:true — טאב רקע נחנק ע"י כרום אחרי 5 דק' (טיימר פעם בדקה) והסריקה לא מסתיימת לעולם.
  // במכונת המשרד אין משתמש ליד המסך, אז טאב קדמי לא מפריע — והסריקה רצה במלוא הקצב עד הסוף.
  try{GM_openInTab(EXCL_DIRECTORY+'#'+EXCL_FLAG,{active:true,insert:true});log('🏢 נפתח טאב סריקת בלעדיות ('+due.join('+')+')');}
  catch(e){log('GM_openInTab נכשל: '+e);}
}
// מותר לשגר סריקה? רק אם אין דופק טרי (3 דק') וגם עברו 5 דק' מהשיגור הקודם (מרווח ביטחון)
function exclScanDead(now,hb,launched){
  if(now-hb<3*60000)return false;
  if(now-launched<5*60000)return false;
  return true;
}
// התקדמות הסריקה של היום (resume): שיגור-מחדש אחרי מוות ממשיך מהמשרד הבא, לא מהתחלה
function exclRunProg(now){
  var day=exclDayStr(now),pr=null;
  try{pr=JSON.parse(gmGet('ysExclRun','null'));}catch(e){}
  if(!pr||pr.date!==day)pr={date:day,ids:{}};
  return pr;
}
function exclRunSave(pr){gmSet('ysExclRun',JSON.stringify(pr));}
function exclRunClear(){gmSet('ysExclRun','null');}
// שליחת דיאגנוסטיקת הסריקה (דגלי בלעדיות/טלפונים/מדריך) — לניתוח מרחוק; מיטב-מאמץ
function exclPostDiag(diagObj){
  try{
    var body='secret='+encodeURIComponent(SECRET)+'&action=diag&data='+encodeURIComponent(JSON.stringify(diagObj).slice(0,28000));
    GM_xmlhttpRequest({method:'POST',url:WEBHOOK,data:body,headers:{'Content-Type':'application/x-www-form-urlencoded'},onload:function(){},onerror:function(){}});
  }catch(e){}
}
// צד ציבורי: רצים רק כשנקראנו עם הדגל — סורקים את כל המשרדים, שולחים, מסמנים, סוגרים
function exclRunPublic(){
  var fetchFn=function(u){return fetch(u,{credentials:'include'}).then(function(r){return r.text();});};
  // רק סניפי Family? מדלגים על גילוי המדריך ועל שאר המשרדים — סריקה קצרה וממוקדת.
  var famOnly=false; try{famOnly=location.hash.indexOf(EXCL_FAM_FLAG)>-1;}catch(e){}
  if(famOnly){
    gmSet('ysExclScanHB',String(Date.now()));
    setInterval(function(){gmSet('ysExclScanHB',String(Date.now()));},20000);
    log('🏠 סורק רק את סניפי רימקס Family ('+EXCL_OFFICES.length+')');
    lastScanMsg='🏠 סריקת Family התחילה ('+EXCL_OFFICES.length+' סניפים)';
    try{postHB('ok');}catch(e){}
    exclScanOffices(EXCL_OFFICES.slice(), fetchFn, {famOnly:1, total:EXCL_OFFICES.length});
    return;
  }
  // דופק לטאב הסריקה — המתזמן בטאב פלוס יודע שהסריקה חיה ולא משגר כפול; מת → שיגור-מחדש עם resume
  gmSet('ysExclScanHB',String(Date.now()));
  setInterval(function(){gmSet('ysExclScanHB',String(Date.now()));},20000);
  log('🏢 מגלה משרדים מהמדריך…');
  lastScanMsg='🏢 סריקת משרדים התחילה';
  try{postHB('ok');}catch(e){}
  exclDiscoverOffices(fetchFn,function(offices,dirDiag){
    if(!offices.length){log('🏢 גילוי המדריך נכשל — נופלים לרשימה הקבועה');offices=EXCL_OFFICES;}
    log('🏢 נמצאו '+offices.length+' משרדים בקריות');
    exclScanOffices(offices,fetchFn,dirDiag);
  });
}
function exclScanOffices(OFFICES,fetchFn,dirDiag){
  var i=0,summary=[],diags=[],doneThisRun=0,blocked=false;
  var prog=exclRunProg(Date.now()); // resume: משרדים שכבר נשלחו בריצה קטועה של היום — מדלגים
  var skipped=OFFICES.filter(function(o){return prog.ids[o.id]&&!isFamId(o.id);}).length;
  log('🏢 סריקת בלעדיות מתחילה — '+OFFICES.length+' משרדים'+(skipped?(' (ממשיך ריצה קטועה, '+skipped+' כבר נסרקו)'):''));
  (function nextOffice(){
    // נחסמנו (CAPTCHA) או שהגענו לתקרת המשרדים לריצה — עוצרים בלי לסמן את הנותרים כ"בוצעו".
    // ההתקדמות נשמרת, ובסריקה הבאה ממשיכים בדיוק מהמשרד הבא. חסימה → מנוחה לפני ניסיון חדש.
    // מדלגים מראש על מה שכבר נסרק בריצה הזו, כדי לדעת מי המשרד הבא באמת
    // סניפי Family נסרקים בכל ריצה — יומן ההתקדמות היומי לא חוסם אותם.
    while(i<OFFICES.length && prog.ids[OFFICES[i].id] && !isFamId(OFFICES[i].id)) i++;
    var nxt=OFFICES[i]||null;
    // סניפי Family לא נספרים בתקרת המשרדים לריצה: הם המקור לנתוני המשרד שלנו,
    // שאר המשרדים הם מודיעין שוק ויכולים להמתין לריצה הבאה. חסימה עדיין עוצרת הכל.
    var famNext=!!(nxt && isFamId(nxt.id));
    if(blocked || (doneThisRun>=OFFICES_PER_RUN && !famNext)){
      var rest=OFFICES.filter(function(o){return !prog.ids[o.id]&&!isFamId(o.id);}).length;
      if(blocked){
        gmSet('ysExclCool',String(Date.now()+BLOCK_COOLDOWN_MIN*60000));
        summary.push('⛔ יד2 חסם — מנוחה '+BLOCK_COOLDOWN_MIN+' דק׳, נמשיך מ-'+rest+' משרדים');
        postHB('blocked');
      } else summary.push('⏸️ תקרת '+OFFICES_PER_RUN+' משרדים לסריקה — נותרו '+rest+' (סניפי Family נסרקו)');
      exclPostDiag({at:new Date().toISOString(),dir:dirDiag||null,blocked:blocked?1:0,offices:diags});
      gmSet('ysExclLast',new Date().toLocaleTimeString('he-IL',{hour:'2-digit',minute:'2-digit'})+' '+summary.join(' · '));
      gmSet('ysExclDone',String(Date.now()));   // הריצה נגמרה כמו שצריך
      lastScanMsg='🏢 עצירה: '+summary.join(' · ').slice(0,220);
      try{postHB(blocked?'blocked':'ok');}catch(e){}
      log('🏢 עצירה מסודרת: '+summary.join(' · '));
      setTimeout(function(){try{window.close();}catch(e){}},4000);
      return;
    }
    if(i>=OFFICES.length){
      var now=Date.now(),st=exclLoadState(now);
      exclDue(st,now).forEach(function(k){st[k].done=true;});
      exclSaveState(st);
      exclRunClear(); // הריצה הושלמה — הסריקה הבאה (ערב/מחר) מתחילה נקי
      var exT=0,exF=0,phN=0;diags.forEach(function(d){exT+=d.exclTrue;exF+=d.exclFalse;phN+=d.phones;});
      summary.push('סה"כ: בלעדי '+exT+' · רגיל '+exF+' · טל '+phN);
      exclPostDiag({at:new Date().toISOString(),dir:dirDiag||null,offices:diags});
      gmSet('ysExclLast',new Date().toLocaleTimeString('he-IL',{hour:'2-digit',minute:'2-digit'})+' '+summary.join(' · '));
      gmSet('ysExclDone',String(Date.now()));
      lastScanMsg='🏢 הושלמה: '+summary.join(' · ').slice(0,220);
      try{postHB('ok');}catch(e){}
      log('🏢 סריקה הושלמה: '+summary.join(' · '));
      setTimeout(function(){try{window.close();}catch(e){}},4000);
      return;
    }
    var office=OFFICES[i++];
    if(prog.ids[office.id] && !isFamId(office.id)){setTimeout(nextOffice,50);return;} // נסרק בריצה הקטועה — הלאה (Family תמיד נסרק)
    exclCrawlOffice(office,fetchFn,function(name,part,page,n){log('🏢 '+name+' '+part+' עמ׳ '+page+': '+n);},function(rowsArr,diag){
      if(diag)diags.push(diag);
      if(diag&&diag.blocked){ // עמוד CAPTCHA — לא מסמנים "בוצע", עוצרים את הריצה ונחים
        blocked=true; summary.push(office.name+': ⛔ נחסם');
        log('⛔ יד2 החזיר CAPTCHA ב-'+office.name+' — עוצר את הסריקה');
        setTimeout(nextOffice,500); return;
      }
      log('🏢 '+office.name+': '+rowsArr.length+' מודעות נאספו');
      if(!rowsArr.length){summary.push(office.name+': 0 (דילוג)');prog.ids[office.id]=1;if(!isFamId(office.id))doneThisRun++;exclRunSave(prog);setTimeout(nextOffice,4000+Math.random()*3000);return;} // אפס = לא שולחים (מגן על ה-delisting)
      // מי הסוכן? למודעות שלא שויכו לסוכן — שולפים מדף המודעה עצמו (שם + טלפון סוכן), מוגבל בכמות
      var agStats={};
      fetchItemAgents(rowsArr, office.name, fetchFn, ITEM_AGENTS_PER_SCAN,
        function(k,n,ok){ if(k%5===0||k===n) log("👤 "+office.name+" סוכנים "+k+"/"+n+" ("+ok+" נמצאו)"); },
        function(gotAgents){
          if(diag){ diag.agentsFetched=gotAgents; diag.ag=agStats; diag.noAgent=rowsArr.filter(function(r){return !isRealAgent(r.agent,office.name);}).length; }
          exclPostOffice(office.name,office.id,rowsArr,function(err,res){
            // מדווחים גם מה *נבדק*, לא רק מה שנוסף: סריקה תקינה בלי מודעות חדשות
            // נראתה קודם כמו "0 · 0 · 0" — כאילו לא רצה כלל (אייל, 30/08).
            var up=(diag&&diag.upgraded)||0, ag=(res.exclAgentUpd||0)+gotAgents;
            summary.push(office.name+': '+(err?'שגיאה':(
              '✓ '+rowsArr.length+' נבדקו'
              +(res.exclAdded?(' · '+res.exclAdded+' חדשים'):'')
              +(up?(' · '+up+' שמות סוכן'):'')
              +(ag?(' · '+ag+' פרטי סוכן'):'')
              +(res.exclDelisted?(' · '+res.exclDelisted+' ירדו'):'')
              +((!res.exclAdded&&!up&&!ag&&!res.exclDelisted)?' · ללא שינוי':'')
            )));
            if(!err){prog.ids[office.id]=1;if(!isFamId(office.id))doneThisRun++;exclRunSave(prog);} // שגיאה → לא מסומן, יישלח שוב בשיגור הבא
            setTimeout(nextOffice,8000+Math.random()*7000); // הפוגה בין משרדים — הגורם העיקרי לחסימות
          });
        }, agStats, office.id);
    });
  })();
}
try{window.__ysExclSchedule=exclSchedule;window.__ysExclDue=exclDue;window.__ysExclParseNextData=exclParseNextData;window.__ysExclFindListings=exclFindListings;window.__ysExclMapItem=exclMapItem;window.__ysItemImage=itemImage;window.__ysExclIsExclusive=exclIsExclusive;window.__ysExclBrokerIds=exclBrokerIds;window.__ysExclBrokerName=exclBrokerName;window.__ysExclOfficeName=exclOfficeName;window.__ysExclCrawlOffice=exclCrawlOffice;window.__ysExclLoadState=exclLoadState;window.__ysExclRunPublic=exclRunPublic;window.__ysExclParseDirectory=exclParseDirectory;window.__ysIsRealAgent=isRealAgent;window.__ysLooksBlocked=looksBlocked;window.__ysExclSchedTick=exclSchedTick;window.__ysSaveRows=saveRows;window.__ysConstsExcl={OFFICES_PER_RUN:OFFICES_PER_RUN,BLOCK_COOLDOWN_MIN:BLOCK_COOLDOWN_MIN,ITEM_AGENTS_PER_SCAN:ITEM_AGENTS_PER_SCAN};window.__ysParseItemAgent=parseItemAgent;window.__ysItemDesc=itemDesc;window.__ysFetchItemAgents=fetchItemAgents;window.__ysApplyAgents=applyAgents;window.__ysAgentCache=agentCache;window.__ysExclDiscoverOffices=exclDiscoverOffices;window.__ysFamilyIds=FAMILY_IDS;window.__ysIsFamId=isFamId;window.__ysExclScanNow=exclScanNow;window.__ysExclScanFamilyNow=exclScanFamilyNow;window.__ysExclStallCheck=exclStallCheck;window.__ysHumanGap=humanGap;window.__ysJitterCap=jitterCap;window.__ysShuffle=shuffle;window.__ysExclScanOffices=exclScanOffices;window.__ysQuietWin=quietWin;window.__ysInQuiet=inQuiet;window.__ysIsActive=isActive;window.__ysPagePhones=pagePhones;window.__ysNormPhone=normPhone;window.__ysExclScanDead=exclScanDead;window.__ysExclRunProg=exclRunProg;window.__ysExclDayStr=exclDayStr;window.__ysBuildPanel=buildPanel;window.__ysPanelKeeper=panelKeeper;window.__ysInit=init;window.__ysStep=step;}catch(e){}

// ===== סימן-חיים + התאוששות SMS אוטומטית =====
var LOGIN_PHONE='0505709865';  // הנייד שממלאים אוטומטית בכניסה מחדש
var HB_MIN=10, lastHB=0, lastFill=0;
// זהות מכונה קצרה (מק/ווינדוס + 4 תווים אקראיים, נשמרת מקומית). נוסעת בסימן-החיים
// כדי שאפשר יהיה לראות מרחוק איזו מכונה סורקת — ואם שתיים סורקות במקביל, זה יתגלה מיד.
function machineId(){
  try{
    // ⚠️ אחסון של טמפרמונקי (gm) ולא localStorage: הפאנל יושב על plus.yad2.co.il
    // וטאב הסריקה על www.yad2.co.il — שני origin נפרדים, ולכן נוצרו שני מזהים
    // לאותה מכונה (win-yahv / win-6krq). gm משותף לכל הסקריפט (v9.5).
    var k='yad2_machine_v1', v=gmGet(k,'')||localStorage.getItem(k);
    if(v && !gmGet(k,'')) gmSet(k,v);      // מיגרציה: מזהה קיים עובר לאחסון המשותף
    if(!v){
      var ua=String(navigator.userAgent||'');
      var os=/Windows/i.test(ua)?'win':(/Mac/i.test(ua)?'mac':'pc');
      v=os+'-'+Math.random().toString(36).slice(2,6);
      gmSet(k,v); try{localStorage.setItem(k,v);}catch(e){}
    }
    return v;
  }catch(e){ return '?'; }
}
function postHB(status){
  // last = תמצית מצב הסריקה (נקרא מרחוק ב-?health=1) כדי שנדע אם היא רצה/נתקעה בלי גישה למכשיר
  // הגרסה נוסעת עם סימן-החיים: ?health=1 מגלה מרחוק איזו גרסה רצה על כל מכונה
  var last='v'+VER+' '+machineId()+' · '+(scanStart?'סורק כרגע · ':'')+(lastScanMsg||'');
  try{GM_xmlhttpRequest({method:'POST',url:WEBHOOK,data:'secret='+encodeURIComponent(SECRET)+'&action=hb&status='+encodeURIComponent(status||'ok')+'&last='+encodeURIComponent(last.slice(0,200)),headers:{'Content-Type':'application/x-www-form-urlencoded'},timeout:30000,onload:function(){},onerror:function(){},ontimeout:function(){}});}catch(e){}
}
// מחוברים? יש API של נכסים = כן. אחרת, אם יש שדה טלפון/מסך כניסה = מנותקים
function looksLoggedOut(){
  if(latestApiTemplate())return false;
  var body=document.body?(document.body.innerText||''):'';
  var hasLogin=/התחבר|כניסה|קוד אימות|SMS|הזן.{0,10}טלפון/i.test(body);
  return hasLogin && !!phoneField();
}
function phoneField(){return document.querySelector('input[type=tel],input[name*=phone i],input[id*=phone i],input[placeholder*=טלפון],input[placeholder*=נייד]');}
function otpField(){var f=document.querySelector('input[autocomplete=one-time-code],input[name*=code i],input[name*=otp i],input[placeholder*=קוד],input[maxlength="4"],input[maxlength="6"]');return f;}
// כתיבה לשדה React (native setter + אירועי input/change)
function setVal(el,val){try{var proto=Object.getPrototypeOf(el);var pd=Object.getOwnPropertyDescriptor(proto,'value');if(pd&&pd.set)pd.set.call(el,val);else el.value=val;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}}
function clickByText(words){var bs=document.querySelectorAll('button,[role=button],a,input[type=submit]');for(var i=0;i<bs.length;i++){var tx=((bs[i].innerText||bs[i].value||'')+'').trim();for(var j=0;j<words.length;j++){if(tx.indexOf(words[j])>-1){try{bs[i].click();return true;}catch(e){}}}}return false;}
function pollCode(){
  try{GM_xmlhttpRequest({method:'POST',url:WEBHOOK,data:'secret='+encodeURIComponent(SECRET)+'&action=getcode',headers:{'Content-Type':'application/x-www-form-urlencoded'},onload:function(r){
    var code='';try{code=(JSON.parse(r.responseText)||{}).code||'';}catch(e){}
    if(code){var f=otpField();if(f){setVal(f,code);log('🔐 הוזן קוד SMS');setTimeout(function(){clickByText(['אישור','התחבר','כניסה','המשך','שלח']);},400);}}
  },onerror:function(){}});}catch(e){}
}
function tryAutoLogin(){
  var now=Date.now();
  var ph=phoneField();
  if(ph && !ph.value && now-lastFill>180000){ // מילוי נייד + שליחת קוד — פעם ב-3 דק' לכל היותר
    lastFill=now; setVal(ph,LOGIN_PHONE); log('📱 מילאתי את הנייד, שולח קוד');
    setTimeout(function(){clickByText(['שלח קוד','קבל קוד','המשך','שלח']);},500);
  }
  pollCode(); // בכל מקרה — אם הקוד כבר הוזן בטופס, נכניס אותו
}
function healthTick(){
  if(scanWatchdog())return; // סריקה תקועה → ריענון; אין טעם להמשיך את הבדיקות
  var lo=looksLoggedOut(), now=Date.now();
  if(now-lastHB>HB_MIN*60000 || lo){ lastHB=now; postHB(lo?'logged_out':'ok'); }
  if(lo)tryAutoLogin();
}
try{window.__ysLooksLoggedOut=looksLoggedOut;window.__ysSetVal=setVal;window.__ysClickByText=clickByText;window.__ysHealthTick=healthTick;window.__ysScanWatchdog=scanWatchdog;window.__ysOnce=once;window.__ysFetchT=fetchT;window.__ysSrcKey=srcKey;window.__ysPageInfo=pageInfo;window.__ysOwnText=ownText;window.__ysPagerHint=pagerHint;window.__ysCurFromEl=curFromEl;window.__ysPagerInside=pagerInside;window.__ysPagerButtons=pagerButtons;window.__ysUiPaginateAll=uiPaginateAll;window.__ysLastTableSig=lastTableSig;window.__ysListings=LISTINGS;window.__ysOfficeIdSeen=officeIdSeen;window.__ysProfileLabel=profileLabel;window.__ysProfileSwitch=profileSwitch;window.__ysProfSwitchWhy=function(){return profSwitchWhy;};window.__ysAccountButton=accountButton;window.__ysActiveProfile=activeProfile;window.__ysProfileItems=profileItems;window.__ysNotProfile=notProfile;window.__ysScanState=function(v){if(v!==undefined)scanStart=v;return {scanStart:scanStart,paused:paused,lastScanMsg:lastScanMsg};};window.__ysRunFullScan=runFullScan;window.__ysPostHB=postHB;window.__ysPostRows=postRows;window.__ysVer=VER;window.__ysMachineId=machineId;window.__ysPgDiag=function(){return pgDiag;};window.__ysRewind=uiRewindToFirst;window.__ysConsts={FETCH_TIMEOUT_MS:FETCH_TIMEOUT_MS,SCAN_MAX_MIN:SCAN_MAX_MIN,TOKENS_PER_SCAN:TOKENS_PER_SCAN,POST_RETRY_WAITS:POST_RETRY_WAITS};}catch(e){}

// כל שלב באתחול עטוף בנפרד — כשל בפאנל (או בכל שלב אחר) לא מפיל את הסריקה, את סימן-החיים
// ולא את תזמון המשרדים. זו הסיבה שהפאנל "נעלם" והכול מת איתו בגרסאות קודמות.
function step(name, fn){ try{ fn(); }catch(e){ log('⚠️ אתחול "'+name+'" נכשל: '+(e&&e.message||e)); } }
function init(){
  step('פאנל', function(){ buildPanel(); setInterval(panelKeeper,5000); }); // גם אם הדף לא מוכן — יחזור תוך 5ש'
  log('starting Yad2 Plus sync v6.9 (active 08:00-23:00)');
  step('סימן-חיים', function(){ postHB('ok'); setInterval(healthTick,60000); });
  step('לופ סריקה', function(){
    if(!isActive()){log('💤 מחוץ לשעות (08:00-23:00). ישן עד '+nextActive().toLocaleString());sleepCheck();}
    else setTimeout(function(){waitScrape(0);},3000);
  });
  step('תזמון משרדים', function(){ setInterval(exclSchedTick,60000);setTimeout(exclSchedTick,5000); });
}
function initPublic(){ // www.yad2.co.il — סורקים רק כשהטאב נפתח עם הדגל; גלישה רגילה לא מופרעת
  if(location.hash.indexOf(EXCL_FLAG)===-1)return;
  setTimeout(exclRunPublic,2500+Math.random()*2000);
}
var IS_PLUS=location.host==='plus.yad2.co.il';
var booted=false;
function boot(){
  if(booted)return;                      // הגנה מאתחול כפול (טיימרים כפולים = סריקות כפולות)
  booted=true;
  try{ IS_PLUS?init():initPublic(); }catch(e){ log('🔴 boot נכשל: '+(e&&e.message||e)); }
}
// גם DOMContentLoaded וגם גיבוי בזמן — יד2 הוא SPA, ולפעמים ה-body נבנה אחרי האירוע
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);
else boot();
setTimeout(function(){ if(!booted)boot(); else if(IS_PLUS)panelKeeper(); }, 8000); // רשת ביטחון
})();
