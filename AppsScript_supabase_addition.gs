/***********************************************************************
 * Supabase — כתיבה כפולה של "נכס נולד" (תוספת בלבד, לא משנה כלום בקיים)
 * ---------------------------------------------------------------------
 * איך מחברים (2 צעדים):
 *   1) הדבק את כל הקובץ הזה כקובץ חדש בעורך ה-Apps Script
 *      (File ▸ New ▸ Script file ▸ שם: supabase).
 *   2) בתוך addnewborn, מיד לפני השורה:
 *          return _buyersJson({ ok: true });
 *      הוסף את השורה:
 *          try { sbNewbornUpsert_(p); } catch (_sbErr) {}
 *      ובתוך newborncontact, מיד לפני return _buyersJson({ ok: true });
 *      (זה שאחרי appendRow של הפנייה) הוסף:
 *          try { sbNewbornContact_(p); } catch (_sbErr) {}
 *
 * הגדרות (Project Settings ⚙ ▸ Script Properties) — לא בקוד:
 *   SUPABASE_URL         = https://tstisabwwmqximgahbtf.supabase.co
 *   SUPABASE_SERVICE_KEY = (service_role key מ-Supabase ▸ Settings ▸ API)
 *   SB_OFFICE_ID         = 11111111-1111-4111-8111-111111111111
 *
 * בטיחות: אם ה-Properties חסרים או ש-Supabase לא זמין — הפונקציות יוצאות
 * בשקט והגיליון ממשיך לעבוד בדיוק כמו היום. כל קריאה עטופה try/catch.
 ***********************************************************************/

function _sbConf_() {
  var pr = PropertiesService.getScriptProperties();
  var url = String(pr.getProperty('SUPABASE_URL') || '').replace(/\/+$/, '');
  var key = String(pr.getProperty('SUPABASE_SERVICE_KEY') || '');
  var off = String(pr.getProperty('SB_OFFICE_ID') || '');
  if (!url || !key || !off) return null;
  return { url: url, key: key, office: off };
}

function _sbFetch_(conf, path, payload, prefer) {
  return UrlFetchApp.fetch(conf.url + path, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'apikey': conf.key,
      'Authorization': 'Bearer ' + conf.key,
      'Prefer': prefer || 'resolution=merge-duplicates'
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

// אותו מפתח יציב כמו _nb_key ב-app.py: id:<מזהה> / ln:<קישור> / ad:<רחוב>|<נוצר>
function _sbNbKey_(pid, link, street, created) {
  pid = String(pid || '').trim();
  if (pid) return 'id:' + pid;
  link = String(link || '').trim();
  if (link) return 'ln:' + link;
  return 'ad:' + String(street || '').trim() + '|' + String(created || '').trim();
}

function _sbIso_(s) {
  var ep = (typeof _nbParseDate === 'function') ? _nbParseDate(s) : 0;
  return ep ? new Date(ep).toISOString() : null;
}

// בונה רשומת listing מ-payload של ה-webhook (אותם שמות עבריים כמו בגיליון —
// נשמרים ב-raw כדי שה-Backend החדש יוכל להחזיר JSON זהה 1:1 לקיים)
function _sbListingRecord_(conf, p) {
  var raw = {
    'שם בעל הנכס': String(p.owner || ''), 'טלפון בעל הנכס-': String(p.phone || ''),
    'רחוב': String(p.street || ''), 'נוצר בתאריך': String(p.created || ''),
    'עודכן בתאריך': String(p.updated || ''), 'מחיר': String(p.price || ''),
    'תיאור נכס': String(p.desc || ''), 'קישור': String(p.link || ''),
    'הערות חדש': String(p.notes || ''), 'משתמש': String(p.agent || ''),
    'עיר': String(p.city || ''), 'מזהה': String(p.pid || '')
  };
  return {
    office_id: conf.office,
    source_key: _sbNbKey_(p.pid, p.link, p.street, p.created),
    pid: String(p.pid || ''),
    owner_name: String(p.owner || ''),
    owner_phone: String(p.phone || ''),
    street: String(p.street || ''),
    city: String(p.city || ''),
    price: String(p.price || ''),
    description: String(p.desc || ''),
    link: String(p.link || ''),
    notes: String(p.notes || ''),
    lister: String(p.agent || ''),
    created_at_source: _sbIso_(p.created),
    updated_at_source: _sbIso_(p.updated),
    raw: raw,
    updated_at: new Date().toISOString()
  };
}

/** נקרא מתוך addnewborn — upsert של המודעה ל-Supabase (במקביל לגיליון). */
function sbNewbornUpsert_(p) {
  var conf = _sbConf_();
  if (!conf) return;
  _sbFetch_(conf,
    '/rest/v1/newborn_listings?on_conflict=office_id,source_key',
    _sbListingRecord_(conf, p),
    'resolution=merge-duplicates');
}

/** נקרא מתוך newborncontact — רישום "כבר פנו" ל-Supabase (במקביל לגיליון). */
function sbNewbornContact_(p) {
  var conf = _sbConf_();
  if (!conf) return;
  var key = String(p.key || '').trim(), ag = String(p.agent || '').trim();
  if (!key) return;
  _sbFetch_(conf,
    '/rest/v1/newborn_contacts?on_conflict=office_id,listing_key,agent_name',
    { office_id: conf.office, listing_key: key, agent_name: ag, addr: String(p.addr || '') },
    'resolution=ignore-duplicates');
}

/***********************************************************************
 * בדיקת חיבור — הרץ פעם אחת מהעורך (Run ▶) אחרי הגדרת ה-Properties.
 * כותב רשומת בדיקה, מוודא שנקלטה, ומוחק אותה. מציג תוצאה ב-Log.
 ***********************************************************************/
function sbTestConnection() {
  var conf = _sbConf_();
  if (!conf) { Logger.log('❌ חסרות הגדרות Script Properties'); return '❌ missing properties'; }
  var r = _sbFetch_(conf,
    '/rest/v1/newborn_listings?on_conflict=office_id,source_key',
    { office_id: conf.office, source_key: 'test:connection', street: 'בדיקת חיבור', raw: {} },
    'resolution=merge-duplicates');
  var code = r.getResponseCode();
  if (code >= 200 && code < 300) {
    // ניקוי רשומת הבדיקה
    UrlFetchApp.fetch(conf.url + '/rest/v1/newborn_listings?office_id=eq.' + conf.office + '&source_key=eq.test:connection', {
      method: 'delete',
      headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
      muteHttpExceptions: true
    });
    Logger.log('✅ החיבור ל-Supabase עובד!');
    return '✅ ok';
  }
  Logger.log('❌ שגיאה ' + code + ': ' + r.getContentText().substring(0, 300));
  return '❌ ' + code;
}

/***********************************************************************
 * Backfill חד-פעמי — מעתיק את ההיסטוריה הקיימת מהגיליון ל-Supabase.
 * הרץ מהעורך (Run ▶) אחרי ש-sbTestConnection הצליח.
 * קריאה בלבד מהגיליון; בטוח להרצה חוזרת (upsert לפי source_key).
 ***********************************************************************/
function sbBackfillNewborn() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('נכס נולד');
  if (!sh || sh.getLastRow() < 2) return 'אין נתונים';
  var v = sh.getDataRange().getDisplayValues();
  var hd = v[0].map(function (h) { return String(h).trim(); });
  var recs = [];
  for (var i = 1; i < v.length; i++) {
    var o = {}, any = false;
    for (var c = 0; c < hd.length; c++) {
      if (!hd[c]) continue;
      o[hd[c]] = v[i][c];
      if (String(v[i][c]).trim()) any = true;
    }
    if (!any) continue;
    recs.push({
      office_id: conf.office,
      source_key: _sbNbKey_(o['מזהה'], o['קישור'], o['רחוב1'] || o['רחוב'], o['נוצר בתאריך']),
      pid: String(o['מזהה'] || ''),
      owner_name: String(o['שם בעל הנכס'] || ''),
      owner_phone: String(o['טלפון בעל הנכס-'] || o['טלפון בעל הנכס'] || ''),
      street: String(o['רחוב1'] || o['רחוב'] || ''),
      city: String(o['עיר'] || o['עיר / ישוב'] || ''),
      neighborhood: String(o['שכונה'] || o['שכונה/אזור'] || ''),
      price: String(o['מחיר'] || ''),
      description: String(o['תיאור נכס'] || ''),
      link: String(o['קישור'] || ''),
      notes: String(o['הערות חדש'] || ''),
      lister: String(o['משתמש'] || o['סוכן 1'] || ''),
      created_at_source: _sbIso_(o['נוצר בתאריך'] || o['תאריך יצירה']),
      updated_at_source: _sbIso_(o['עודכן בתאריך']),
      raw: o
    });
  }
  // איחוד כפילויות בתוך הגיליון (אותו מזהה/קישור פעמיים) — שומרים את השורה
  // האחרונה (החדשה ביותר); Postgres דוחה קבוצה עם מפתח כפול באותה פקודה
  var byKey = {};
  recs.forEach(function (rec) { byKey[rec.source_key] = rec; });
  var unique = Object.keys(byKey).map(function (k) { return byKey[k]; });
  var dups = recs.length - unique.length;
  var BATCH = 200, sent = 0, errs = 0;
  for (var b = 0; b < unique.length; b += BATCH) {
    var chunk = unique.slice(b, b + BATCH);
    var r = _sbFetch_(conf, '/rest/v1/newborn_listings?on_conflict=office_id,source_key',
                      chunk, 'resolution=merge-duplicates');
    var code = r.getResponseCode();
    if (code >= 200 && code < 300) sent += chunk.length;
    else { errs++; Logger.log('שגיאה בקבוצה ' + b + ': ' + code + ' ' + r.getContentText().substring(0, 200)); }
  }
  var msg = 'הועברו ' + sent + '/' + unique.length + ' מודעות ייחודיות' +
            (dups ? (' (אוחדו ' + dups + ' שורות כפולות בגיליון)') : '') +
            (errs ? (' · ' + errs + ' קבוצות נכשלו') : ' · הכל תקין ✅');
  Logger.log(msg);
  return msg;
}

/***********************************************************************
 * ══ שלב 2: "שיחות" ═════════════════════════════════════════════════
 * חיבור (2 שורות בתוך upsertEvent_ ב-קוד.gs, לפני כל אחד מה-return):
 *   אחרי sh.getRange(rowIdx, ...).setValues([row]); הוסף:
 *       try { sbCallRow_(sheetName, fields, row); } catch (_sbErr) {}
 *   אחרי sh.appendRow(baseRow.concat([now, now])); הוסף:
 *       try { sbCallRow_(sheetName, fields, baseRow.concat([now, now])); } catch (_sbErr) {}
 * ובבלוק hidecall/unhidecall:
 *   אחרי if (foundRow < 0) hsh.appendRow([eid]); הוסף:
 *       try { sbHiddenAdd_(eid); } catch (_sbErr) {}
 *   אחרי if (foundRow >= 1) hsh.deleteRow(foundRow); הוסף:
 *       try { sbHiddenRemove_(eid); } catch (_sbErr) {}
 ***********************************************************************/

// המרת ערך תא לתאריך-בלבד ISO (כמו parseDate_ ב-קוד.gs) או null
function _sbDateOnly_(v) {
  var ep = (typeof parseDate_ === 'function') ? parseDate_(v) : null;
  if (!ep) return null;
  var d = new Date(ep);
  return d.getFullYear() + '-' +
         ('0' + (d.getMonth() + 1)).slice(-2) + '-' +
         ('0' + d.getDate()).slice(-2);
}

// מפתח יציב לשיחה: event_id אם קיים, אחרת hash דטרמיניסטי מהערכים+אינדקס
function _sbCallKey_(eventId, rowVals, idx) {
  var eid = String(eventId || '').trim();
  if (eid) return eid;
  var basis = rowVals.map(function (x) { return String(x == null ? '' : x); }).join('|') + '|' + idx;
  var dig = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_1, basis)
    .map(function (b) { return ('00' + (b & 0xFF).toString(16)).slice(-2); }).join('');
  return 'x:' + dig.slice(0, 16);
}

// בונה רשומת call מ-headers+values.
// חשוב: raw נבנה בדיוק כמו getRaw_ — לפי כותרות הגיליון כפי שהן, כולל כותרת
// ריקה (עמודת ה-ID בגיליון "שיחות" היא ללא כותרת!), בלי לדלג על כלום.
function _sbCallRecord_(conf, headers, vals, idx) {
  var raw = {}, rxVal = null;
  for (var i = 0; i < headers.length; i++) {
    var h = String(headers[i] == null ? '' : headers[i]).trim();
    if (h === 'received_at') rxVal = vals[i];   // הערך המקורי (Date/מחרוזת)
    raw[h] = (vals[i] instanceof Date) ? vals[i].toISOString() : vals[i];
  }
  // מזהה השיחה: עמודת event_id אם קיימת בכותרות, אחרת עמודה A (כמו הדדופ ב-upsertEvent_)
  var eid = String(raw['event_id'] == null ? '' : raw['event_id']).trim();
  if (!eid) eid = String(vals[0] == null ? '' : vals[0]).trim();
  return {
    office_id: conf.office,
    source_key: _sbCallKey_(eid, vals, idx),
    event_id: eid,
    status: String(raw['status'] == null ? '' : raw['status']),
    agent: String(raw['agent'] == null ? '' : raw['agent']),
    agent_phone: String(raw['agent_phone'] == null ? '' : raw['agent_phone']),
    caller_phone: String(raw['caller_phone'] == null ? '' : raw['caller_phone']),
    duration_sec: String(raw['duration_sec'] == null ? '' : raw['duration_sec']),
    transcript_summary: String(raw['transcript_summary'] == null ? '' : raw['transcript_summary']),
    received_at: _sbDateOnly_(rxVal),   // מהערך המקורי — זהה ל-getRaw_ (חיתוך תאריך מקומי)
    raw: raw,
    updated_at: new Date().toISOString()
  };
}

/** נקרא מתוך upsertEvent_ — כתיבה כפולה של שיחה (רק לשונית 'שיחות').
 *  קורא את שורת הכותרות האמיתית מהגיליון כדי ש-raw יהיה זהה 1:1 ל-getRaw_. */
function sbCallRow_(sheetName, fields, rowVals) {
  if (sheetName !== 'שיחות') return;
  var conf = _sbConf_();
  if (!conf) return;
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  var headers = sh.getRange(1, 1, 1, Math.max(sh.getLastColumn(), rowVals.length)).getValues()[0];
  _sbFetch_(conf, '/rest/v1/calls?on_conflict=office_id,source_key',
            _sbCallRecord_(conf, headers, rowVals, 'live'),
            'resolution=merge-duplicates');
}

/** הסתרת שיחה — כתיבה כפולה. */
function sbHiddenAdd_(eid) {
  var conf = _sbConf_();
  if (!conf || !eid) return;
  _sbFetch_(conf, '/rest/v1/hidden_calls?on_conflict=office_id,event_id',
            { office_id: conf.office, event_id: String(eid) },
            'resolution=ignore-duplicates');
}

/** שחזור שיחה מוסתרת — מחיקה מ-Supabase. */
function sbHiddenRemove_(eid) {
  var conf = _sbConf_();
  if (!conf || !eid) return;
  UrlFetchApp.fetch(conf.url + '/rest/v1/hidden_calls?office_id=eq.' + conf.office +
                    '&event_id=eq.' + encodeURIComponent(String(eid)), {
    method: 'delete',
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    muteHttpExceptions: true
  });
}

/** Backfill חד-פעמי לשיחות — הרץ מהעורך. בטוח להרצה חוזרת (upsert). */
function sbBackfillCalls() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('שיחות');
  if (!sh || sh.getLastRow() < 2) return 'אין נתונים';
  var v = sh.getDataRange().getValues();
  var hd = v[0].map(function (h) { return String(h).trim(); });
  var byKey = {}, total = 0, noId = 0;
  for (var i = 1; i < v.length; i++) {
    var any = v[i].some(function (x) { return String(x == null ? '' : x).trim(); });
    if (!any) continue;
    total++;
    var rec = _sbCallRecord_(conf, hd, v[i], i);
    if (!rec.event_id) noId++;
    byKey[rec.source_key] = rec;
  }
  var unique = Object.keys(byKey).map(function (k) { return byKey[k]; });
  var BATCH = 400, sent = 0, errs = 0;
  for (var b = 0; b < unique.length; b += BATCH) {
    var chunk = unique.slice(b, b + BATCH);
    var r = _sbFetch_(conf, '/rest/v1/calls?on_conflict=office_id,source_key',
                      chunk, 'resolution=merge-duplicates');
    var code = r.getResponseCode();
    if (code >= 200 && code < 300) sent += chunk.length;
    else { errs++; Logger.log('שגיאה בקבוצה ' + b + ': ' + code + ' ' + r.getContentText().substring(0, 200)); }
  }
  var msg = 'הועברו ' + sent + '/' + unique.length + ' שיחות ייחודיות (' + total + ' שורות, ' +
            noId + ' בלי event_id → מפתח סינתטי)' +
            (errs ? (' · ' + errs + ' קבוצות נכשלו') : ' · הכל תקין ✅');
  Logger.log(msg);
  return msg;
}

/** Backfill חד-פעמי לשיחות מוסתרות. */
function sbBackfillHidden() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('מוסתרות');
  if (!sh || sh.getLastRow() < 1) return 'אין נתונים';
  var v = sh.getDataRange().getValues();
  var recs = [], seen = {};
  for (var i = 0; i < v.length; i++) {
    var eid = String(v[i][0] == null ? '' : v[i][0]).trim();
    if (!eid || seen[eid]) continue;
    seen[eid] = true;
    recs.push({ office_id: conf.office, event_id: eid });
  }
  var r = _sbFetch_(conf, '/rest/v1/hidden_calls?on_conflict=office_id,event_id',
                    recs, 'resolution=ignore-duplicates');
  var ok = r.getResponseCode() >= 200 && r.getResponseCode() < 300;
  var msg = (ok ? 'הועברו ' : '❌ שגיאה ') + recs.length + ' מוסתרות' + (ok ? ' · הכל תקין ✅' : '');
  Logger.log(msg);
  return msg;
}

/** Parity לשיחות — משווה מפתחות גיליון ↔ Supabase + מוסתרות. */
function sbParityCalls() {
  var conf = _sbConf_();
  if (!conf) { Logger.log('❌ חסרות הגדרות'); return '❌'; }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('שיחות');
  var v = sh.getDataRange().getValues();
  var hd = v[0].map(function (h) { return String(h).trim(); });
  var sheetKeys = {}, total = 0;
  for (var i = 1; i < v.length; i++) {
    var any = v[i].some(function (x) { return String(x == null ? '' : x).trim(); });
    if (!any) continue;
    total++;
    var rec = _sbCallRecord_(conf, hd, v[i], i);
    sheetKeys[rec.source_key] = true;
  }
  var sbKeys = {}, offset = 0, PAGE = 1000;
  while (true) {
    var r = UrlFetchApp.fetch(conf.url + '/rest/v1/calls?select=source_key' +
                              '&office_id=eq.' + conf.office + '&limit=' + PAGE + '&offset=' + offset, {
      headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
      muteHttpExceptions: true
    });
    if (r.getResponseCode() !== 200) { Logger.log('❌ שגיאת קריאה: ' + r.getResponseCode()); return '❌'; }
    var arr = JSON.parse(r.getContentText());
    arr.forEach(function (x) { sbKeys[x.source_key] = true; });
    if (arr.length < PAGE) break;
    offset += PAGE;
  }
  var sheetList = Object.keys(sheetKeys), sbList = Object.keys(sbKeys);
  var missing = sheetList.filter(function (k) { return !sbKeys[k]; });
  var extra = sbList.filter(function (k) { return !sheetKeys[k]; });
  Logger.log('📞 שיחות — גיליון: ' + total + ' שורות (' + sheetList.length + ' ייחודיות) · Supabase: ' + sbList.length);
  Logger.log(missing.length ? ('❌ חסרות ב-Supabase: ' + missing.length + ' — ' + missing.slice(0, 3).join(' | '))
                            : '✅ אף שיחה לא חסרה');
  Logger.log(extra.length ? ('⚠️ עודפות ב-Supabase: ' + extra.length) : '✅ אין עודפות');

  // מוסתרות
  var hsh = ss.getSheetByName('מוסתרות');
  var hSheet = {};
  if (hsh && hsh.getLastRow() > 0) {
    hsh.getDataRange().getValues().forEach(function (row) {
      var eid = String(row[0] == null ? '' : row[0]).trim();
      if (eid) hSheet[eid] = true;
    });
  }
  var hr = UrlFetchApp.fetch(conf.url + '/rest/v1/hidden_calls?select=event_id&office_id=eq.' + conf.office + '&limit=10000', {
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key }, muteHttpExceptions: true
  });
  var hSb = {};
  (JSON.parse(hr.getContentText()) || []).forEach(function (x) { hSb[x.event_id] = true; });
  var hMiss = Object.keys(hSheet).filter(function (k) { return !hSb[k]; });
  var hExtra = Object.keys(hSb).filter(function (k) { return !hSheet[k]; });
  Logger.log('🙈 מוסתרות — גיליון: ' + Object.keys(hSheet).length + ' · Supabase: ' + Object.keys(hSb).length +
             ((hMiss.length || hExtra.length) ? (' · ❌ פערים: ' + hMiss.length + '/' + hExtra.length) : ' · ✅ תואם'));

  var ok = !missing.length && !hMiss.length;
  Logger.log(ok ? '🟢 PARITY שיחות מלא' : '🔴 יש פערים');
  return ok ? 'OK' : 'GAPS';
}

/***********************************************************************
 * בדיקת Parity — משווה גיליון ↔ Supabase (קריאה בלבד משני הצדדים).
 * הרץ מהעורך (Run ▶) בכל רגע; מדפיס דוח מלא ליומן הביצוע.
 ***********************************************************************/
function sbParityCheck() {
  var conf = _sbConf_();
  if (!conf) { Logger.log('❌ חסרות הגדרות'); return '❌'; }
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // ── צד הגיליון: מודעות ──
  var sh = ss.getSheetByName('נכס נולד');
  var v = sh.getDataRange().getDisplayValues();
  var hd = v[0].map(function (h) { return String(h).trim(); });
  var sheetKeys = {}, totalRows = 0;
  for (var i = 1; i < v.length; i++) {
    var o = {}, any = false;
    for (var c = 0; c < hd.length; c++) {
      if (!hd[c]) continue;
      o[hd[c]] = v[i][c];
      if (String(v[i][c]).trim()) any = true;
    }
    if (!any) continue;
    totalRows++;
    sheetKeys[_sbNbKey_(o['מזהה'], o['קישור'], o['רחוב1'] || o['רחוב'], o['נוצר בתאריך'])] = true;
  }

  // ── צד Supabase: מודעות (בדפים של 1000) ──
  var sbKeys = {}, offset = 0, PAGE = 1000;
  while (true) {
    var r = UrlFetchApp.fetch(conf.url + '/rest/v1/newborn_listings?select=source_key' +
                              '&office_id=eq.' + conf.office + '&limit=' + PAGE + '&offset=' + offset, {
      headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
      muteHttpExceptions: true
    });
    if (r.getResponseCode() !== 200) { Logger.log('❌ שגיאת קריאה מ-Supabase: ' + r.getResponseCode()); return '❌'; }
    var arr = JSON.parse(r.getContentText());
    arr.forEach(function (x) { sbKeys[x.source_key] = true; });
    if (arr.length < PAGE) break;
    offset += PAGE;
  }
  var sheetList = Object.keys(sheetKeys), sbList = Object.keys(sbKeys);
  var missing = sheetList.filter(function (k) { return !sbKeys[k]; });
  var extra = sbList.filter(function (k) { return !sheetKeys[k] && k.indexOf('test:') !== 0; });

  Logger.log('🏠 מודעות — גיליון: ' + totalRows + ' שורות (' + sheetList.length + ' ייחודיות) · Supabase: ' + sbList.length);
  Logger.log(missing.length ? ('❌ חסרות ב-Supabase: ' + missing.length + ' — לדוגמה: ' + missing.slice(0, 5).join(' | '))
                            : '✅ אף מודעה לא חסרה ב-Supabase');
  Logger.log(extra.length ? ('⚠️ קיימות רק ב-Supabase: ' + extra.length + ' — לדוגמה: ' + extra.slice(0, 5).join(' | '))
                          : '✅ אין רשומות עודפות ב-Supabase');

  // ── פניות "כבר פנו" ──
  var ksh = ss.getSheetByName('נכסנולד_פניות');
  var kPairs = {};
  if (ksh && ksh.getLastRow() > 1) {
    var kv = ksh.getDataRange().getDisplayValues();
    for (var ki = 1; ki < kv.length; ki++) {
      var kk = String(kv[ki][1] || '').trim();
      if (kk) kPairs[kk + '::' + String(kv[ki][2] || '').trim()] = true;
    }
  }
  var cbPairs = {}; offset = 0;
  while (true) {
    var cr = UrlFetchApp.fetch(conf.url + '/rest/v1/newborn_contacts?select=listing_key,agent_name' +
                               '&office_id=eq.' + conf.office + '&limit=' + PAGE + '&offset=' + offset, {
      headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
      muteHttpExceptions: true
    });
    if (cr.getResponseCode() !== 200) break;
    var carr = JSON.parse(cr.getContentText());
    carr.forEach(function (x) { cbPairs[x.listing_key + '::' + x.agent_name] = true; });
    if (carr.length < PAGE) break;
    offset += PAGE;
  }
  var kMissing = Object.keys(kPairs).filter(function (k) { return !cbPairs[k]; });
  Logger.log('📲 פניות — גיליון: ' + Object.keys(kPairs).length + ' · Supabase: ' + Object.keys(cbPairs).length +
             (kMissing.length ? (' · ❌ חסרות: ' + kMissing.length) : ' · ✅ תואם'));

  var ok = !missing.length && !kMissing.length;
  Logger.log(ok ? '🟢 PARITY מלא — Supabase מסונכרן עם הגיליון' : '🔴 יש פערים — ראה למעלה');
  return ok ? 'OK' : 'GAPS';
}

/** Backfill חד-פעמי לפניות "כבר פנו" (נכסנולד_פניות). */
function sbBackfillNewbornContacts() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('נכסנולד_פניות');
  if (!sh || sh.getLastRow() < 2) return 'אין נתונים';
  var v = sh.getDataRange().getDisplayValues();
  var recs = [];
  for (var i = 1; i < v.length; i++) {
    var key = String(v[i][1] || '').trim();
    if (!key) continue;
    var rec = { office_id: conf.office, listing_key: key,
                agent_name: String(v[i][2] || '').trim(), addr: String(v[i][3] || '') };
    var ep = _sbIso_(v[i][0]);
    if (ep) rec.contacted_at = ep;
    recs.push(rec);
  }
  var BATCH = 200, sent = 0, errs = 0;
  for (var b = 0; b < recs.length; b += BATCH) {
    var chunk = recs.slice(b, b + BATCH);
    var r = _sbFetch_(conf, '/rest/v1/newborn_contacts?on_conflict=office_id,listing_key,agent_name',
                      chunk, 'resolution=ignore-duplicates');
    var code = r.getResponseCode();
    if (code >= 200 && code < 300) sent += chunk.length;
    else { errs++; Logger.log('שגיאה בקבוצה ' + b + ': ' + code + ' ' + r.getContentText().substring(0, 200)); }
  }
  var msg = 'הועברו ' + sent + '/' + recs.length + ' פניות' + (errs ? (' · ' + errs + ' קבוצות נכשלו') : ' · הכל תקין ✅');
  Logger.log(msg);
  return msg;
}
