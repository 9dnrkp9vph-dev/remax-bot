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

// בונה רשומת signature מ-headers+values — אותו עיקרון כמו _sbCallRecord_
function _sbSigRecord_(conf, headers, vals, idx) {
  var raw = {}, rxVal = null;
  for (var i = 0; i < headers.length; i++) {
    var h = String(headers[i] == null ? '' : headers[i]).trim();
    if (h === 'received_at') rxVal = vals[i];
    raw[h] = (vals[i] instanceof Date) ? vals[i].toISOString() : vals[i];
  }
  var eid = String(raw['event_id'] == null ? '' : raw['event_id']).trim();
  if (!eid) eid = String(vals[0] == null ? '' : vals[0]).trim();
  return {
    office_id: conf.office,
    source_key: _sbCallKey_(eid, vals, idx),
    event_id: eid,
    deal_type: String(raw['deal_type'] == null ? '' : raw['deal_type']),
    agent: String(raw['agent'] == null ? '' : raw['agent']),
    client_name: String(raw['client_name'] == null ? '' : raw['client_name']),
    address: String(raw['address'] == null ? '' : raw['address']),
    city: String(raw['city'] == null ? '' : raw['city']),
    commission_pct: String(raw['commission_pct'] == null ? '' : raw['commission_pct']),
    notes: String(raw['notes'] == null ? '' : raw['notes']),
    received_at: _sbDateOnly_(rxVal),
    raw: raw,
    updated_at: new Date().toISOString()
  };
}

/** נקרא מתוך upsertEvent_ — כתיבה כפולה ללשוניות 'שיחות' ו'חתימות'.
 *  קורא את שורת הכותרות האמיתית מהגיליון כדי ש-raw יהיה זהה 1:1 ל-getRaw_. */
function sbCallRow_(sheetName, fields, rowVals) {
  if (sheetName !== 'שיחות' && sheetName !== 'חתימות') return;
  var conf = _sbConf_();
  if (!conf) return;
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  var headers = sh.getRange(1, 1, 1, Math.max(sh.getLastColumn(), rowVals.length)).getValues()[0];
  if (sheetName === 'שיחות') {
    _sbFetch_(conf, '/rest/v1/calls?on_conflict=office_id,source_key',
              _sbCallRecord_(conf, headers, rowVals, 'live'),
              'resolution=merge-duplicates');
  } else {
    _sbFetch_(conf, '/rest/v1/signatures?on_conflict=office_id,source_key',
              _sbSigRecord_(conf, headers, rowVals, 'live'),
              'resolution=merge-duplicates');
  }
}

/** נקרא מתוך addsigning — חתימה דיגיטלית מהאפליקציה (append לגיליון). */
function sbSigningAdd_(sghd, rec) {
  var conf = _sbConf_();
  if (!conf) return;
  var vals = sghd.map(function (h) { return (rec[h] !== undefined) ? rec[h] : ''; });
  _sbFetch_(conf, '/rest/v1/signatures?on_conflict=office_id,source_key',
            _sbSigRecord_(conf, sghd, vals, 'app'),
            'resolution=merge-duplicates');
}

/** נקרא מתוך updatesigning — אחרי שהלקוח חתם מרחוק: החלפת טוקן ב-event_id וקישור. */
function sbSigningUpdate_(oldTok, newEv, newLink) {
  var conf = _sbConf_();
  if (!conf || !oldTok) return;
  var base = conf.url + '/rest/v1/signatures?office_id=eq.' + conf.office +
             '&event_id=eq.' + encodeURIComponent(String(oldTok));
  var g = UrlFetchApp.fetch(base + '&select=id,raw', {
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    muteHttpExceptions: true
  });
  if (g.getResponseCode() !== 200) return;
  var found = JSON.parse(g.getContentText()) || [];
  for (var i = 0; i < found.length; i++) {
    var raw = found[i].raw || {};
    if (newLink) raw['commission_pct'] = newLink;
    if (newEv) raw['event_id'] = newEv;
    var patch = { raw: raw, updated_at: new Date().toISOString() };
    if (newLink) patch.commission_pct = newLink;
    if (newEv) { patch.event_id = newEv; patch.source_key = newEv; }
    UrlFetchApp.fetch(conf.url + '/rest/v1/signatures?id=eq.' + found[i].id, {
      method: 'patch',
      contentType: 'application/json',
      headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
      payload: JSON.stringify(patch),
      muteHttpExceptions: true
    });
  }
}

/** נקרא מתוך deletesigning — מחיקת הסכם (לפי event_id או לקוח+תאריך). */
function sbSigningDelete_(wEv, wCl, wRa) {
  var conf = _sbConf_();
  if (!conf) return;
  if (String(wEv || '').trim()) {
    UrlFetchApp.fetch(conf.url + '/rest/v1/signatures?office_id=eq.' + conf.office +
                      '&event_id=eq.' + encodeURIComponent(String(wEv).trim()), {
      method: 'delete',
      headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
      muteHttpExceptions: true
    });
    return;
  }
  wCl = String(wCl || '').trim(); wRa = String(wRa || '').trim();
  if (!wCl || !wRa) return;
  var g = UrlFetchApp.fetch(conf.url + '/rest/v1/signatures?office_id=eq.' + conf.office +
                            '&client_name=eq.' + encodeURIComponent(wCl) + '&select=id,raw', {
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    muteHttpExceptions: true
  });
  if (g.getResponseCode() !== 200) return;
  var found = JSON.parse(g.getContentText()) || [];
  for (var i = 0; i < found.length; i++) {
    var ra = String((found[i].raw || {})['received_at'] || '');
    if (ra.indexOf(wRa) === 0) {
      UrlFetchApp.fetch(conf.url + '/rest/v1/signatures?id=eq.' + found[i].id, {
        method: 'delete',
        headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
        muteHttpExceptions: true
      });
    }
  }
}

/** Backfill חד-פעמי לחתימות — הרץ מהעורך. בטוח להרצה חוזרת (upsert). */
function sbBackfillSignatures() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('חתימות');
  if (!sh || sh.getLastRow() < 2) return 'אין נתונים';
  var v = sh.getDataRange().getValues();
  var hd = v[0];
  // מזהי Fireberry ממוחזרים לעסקאות שונות של אותו לקוח — שומרים כל שורה:
  // ההופעה הראשונה מקבלת את המפתח הנקי (עדכוני webhook פוגעים בה, כמו בגיליון),
  // וההופעות הבאות מקבלות סיומת #2, #3...
  var seen = {}, byKey = {}, total = 0, noId = 0;
  for (var i = 1; i < v.length; i++) {
    var any = v[i].some(function (x) { return String(x == null ? '' : x).trim(); });
    if (!any) continue;
    total++;
    var rec = _sbSigRecord_(conf, hd, v[i], i);
    if (!rec.event_id) noId++;
    var k = rec.source_key;
    if (seen[k]) { seen[k]++; rec.source_key = k + '#' + seen[k]; }
    else seen[k] = 1;
    byKey[rec.source_key] = rec;
  }
  var unique = Object.keys(byKey).map(function (k) { return byKey[k]; });
  var BATCH = 400, sent = 0, errs = 0;
  for (var b = 0; b < unique.length; b += BATCH) {
    var chunk = unique.slice(b, b + BATCH);
    var r = _sbFetch_(conf, '/rest/v1/signatures?on_conflict=office_id,source_key',
                      chunk, 'resolution=merge-duplicates');
    var code = r.getResponseCode();
    if (code >= 200 && code < 300) sent += chunk.length;
    else { errs++; Logger.log('שגיאה בקבוצה ' + b + ': ' + code + ' ' + r.getContentText().substring(0, 200)); }
  }
  var msg = 'הועברו ' + sent + '/' + unique.length + ' חתימות ייחודיות (' + total + ' שורות, ' +
            noId + ' בלי event_id → מפתח סינתטי)' +
            (errs ? (' · ' + errs + ' קבוצות נכשלו') : ' · הכל תקין ✅');
  Logger.log(msg);
  return msg;
}

/** Parity לחתימות — משווה מפתחות גיליון ↔ Supabase. */
function sbParitySignatures() {
  var conf = _sbConf_();
  if (!conf) { Logger.log('❌ חסרות הגדרות'); return '❌'; }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('חתימות');
  var v = sh.getDataRange().getValues();
  var hd = v[0];
  var sheetKeys = {}, seen = {}, total = 0;
  for (var i = 1; i < v.length; i++) {
    var any = v[i].some(function (x) { return String(x == null ? '' : x).trim(); });
    if (!any) continue;
    total++;
    var k = _sbSigRecord_(conf, hd, v[i], i).source_key;
    if (seen[k]) { seen[k]++; k = k + '#' + seen[k]; }
    else seen[k] = 1;
    sheetKeys[k] = true;
  }
  var sbKeys = {}, offset = 0, PAGE = 1000;
  while (true) {
    var r = UrlFetchApp.fetch(conf.url + '/rest/v1/signatures?select=source_key' +
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
  Logger.log('✍️ חתימות — גיליון: ' + total + ' שורות (' + sheetList.length + ' ייחודיות) · Supabase: ' + sbList.length);
  Logger.log(missing.length ? ('❌ חסרות ב-Supabase: ' + missing.length + ' — ' + missing.slice(0, 3).join(' | '))
                            : '✅ אף חתימה לא חסרה');
  Logger.log(extra.length ? ('⚠️ עודפות ב-Supabase: ' + extra.length) : '✅ אין עודפות');
  var ok = !missing.length;
  Logger.log(ok ? '🟢 PARITY חתימות מלא' : '🔴 יש פערים');
  return ok ? 'OK' : 'GAPS';
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
 * ══ שלב 4: "קונים" ═════════════════════════════════════════════════
 * חיבור (3 שורות בבלוק הקונים ב-קוד.gs):
 *   addbuyer   — אחרי sh.appendRow([...]):
 *       try { sbBuyerRow_(sh, sh.getLastRow()); } catch (_sbErr) {}
 *   updatebuyer — אחרי sh.getRange(rw, 8).setValue(...):
 *       try { sbBuyerRow_(sh, rw); } catch (_sbErr) {}
 *   deletebuyer — אחרי sh.deleteRow(dr):
 *       try { sbBuyerDelete_(dr); } catch (_sbErr) {}
 ***********************************************************************/

var _SB_BUYER_KEYS = ['date', 'name', 'phone', 'budget', 'summary', 'agent', 'agent_phone', 'search'];

function _sbBuyerRaw_(vals) {
  var raw = {};
  for (var i = 0; i < _SB_BUYER_KEYS.length; i++) {
    var v = (vals[i] === undefined || vals[i] === null) ? '' : vals[i];
    raw[_SB_BUYER_KEYS[i]] = (v instanceof Date) ? v.toISOString() : v;
  }
  return raw;
}

/** upsert שורת קונה לפי מספר שורה — משמש גם להוספה וגם לעדכון. */
function sbBuyerRow_(sh, rowIdx) {
  var conf = _sbConf_();
  if (!conf || !rowIdx || rowIdx < 2) return;
  var vals = sh.getRange(rowIdx, 1, 1, 8).getValues()[0];
  _sbFetch_(conf, '/rest/v1/buyers?on_conflict=office_id,sheet_row',
            { office_id: conf.office, sheet_row: rowIdx, raw: _sbBuyerRaw_(vals),
              updated_at: new Date().toISOString() },
            'resolution=merge-duplicates');
}

/** מחיקת קונה — מוחק ומזיז את השורות שאחריו (כמו deleteRow בגיליון). */
function sbBuyerDelete_(rowIdx) {
  var conf = _sbConf_();
  if (!conf || !rowIdx) return;
  UrlFetchApp.fetch(conf.url + '/rest/v1/rpc/buyers_delete_row', {
    method: 'post',
    contentType: 'application/json',
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    payload: JSON.stringify({ p_office: conf.office, p_row: rowIdx }),
    muteHttpExceptions: true
  });
}

/** Backfill חד-פעמי לקונים — מוחק וממלא מחדש (הטבלה קטנה). */
function sbBackfillBuyers() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('קונים');
  if (!sh || sh.getLastRow() < 2) return 'אין נתונים';
  UrlFetchApp.fetch(conf.url + '/rest/v1/buyers?office_id=eq.' + conf.office, {
    method: 'delete',
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    muteHttpExceptions: true
  });
  var v = sh.getDataRange().getValues();
  var recs = [];
  for (var i = 1; i < v.length; i++) {
    recs.push({ office_id: conf.office, sheet_row: i + 1, raw: _sbBuyerRaw_(v[i]) });
  }
  var r = _sbFetch_(conf, '/rest/v1/buyers?on_conflict=office_id,sheet_row',
                    recs, 'resolution=merge-duplicates');
  var ok = r.getResponseCode() >= 200 && r.getResponseCode() < 300;
  var msg = (ok ? 'הועברו ' : '❌ שגיאה ') + recs.length + ' קונים' + (ok ? ' · הכל תקין ✅' : ': ' + r.getContentText().substring(0, 150));
  Logger.log(msg);
  return msg;
}

/** Parity לקונים — משווה שורה-שורה. */
function sbParityBuyers() {
  var conf = _sbConf_();
  if (!conf) { Logger.log('❌ חסרות הגדרות'); return '❌'; }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('קונים');
  var v = sh.getDataRange().getValues();
  var g = UrlFetchApp.fetch(conf.url + '/rest/v1/buyers?select=sheet_row,raw&office_id=eq.' + conf.office + '&order=sheet_row.asc&limit=10000', {
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    muteHttpExceptions: true
  });
  if (g.getResponseCode() !== 200) { Logger.log('❌ שגיאת קריאה'); return '❌'; }
  var sb = JSON.parse(g.getContentText()) || [];
  var byRow = {};
  sb.forEach(function (x) { byRow[x.sheet_row] = x.raw || {}; });
  var sheetRows = v.length - 1;
  var diffs = 0, example = '';
  for (var i = 1; i < v.length; i++) {
    var raw = _sbBuyerRaw_(v[i]);
    var other = byRow[i + 1];
    if (!other) { diffs++; if (!example) example = 'שורה ' + (i + 1) + ' חסרה'; continue; }
    for (var k = 0; k < _SB_BUYER_KEYS.length; k++) {
      var f = _SB_BUYER_KEYS[k];
      if (String(raw[f] == null ? '' : raw[f]) !== String(other[f] == null ? '' : other[f])) {
        diffs++;
        if (!example) example = 'שורה ' + (i + 1) + ' שדה ' + f;
        break;
      }
    }
  }
  Logger.log('👥 קונים — גיליון: ' + sheetRows + ' · Supabase: ' + sb.length +
             (diffs ? (' · ❌ ' + diffs + ' הבדלים (' + example + ')') : ' · ✅ זהים שורה-שורה'));
  var ok = !diffs && sheetRows === sb.length;
  Logger.log(ok ? '🟢 PARITY קונים מלא' : '🔴 יש פערים');
  return ok ? 'OK' : 'GAPS';
}

/***********************************************************************
 * ══ שלב 5: "קונפיג" ═══════════════════════════════════════════════
 * חיבור (שורה אחת בבלוק setconfig ב-קוד.gs, אחרי ssh.getRange(1,1).setValue):
 *     try { sbConfigSplit_(String(p.config || '')); } catch (_sbErr) {}
 * מפרק את בלוב ה-JSON לשורה-לכל-מפתח ב-office_config — בכל שמירה.
 ***********************************************************************/
function sbConfigSplit_(blob) {
  var conf = _sbConf_();
  if (!conf) return;
  var cfg;
  try { cfg = JSON.parse(String(blob || '') || '{}'); } catch (e) { return; }
  if (!cfg || typeof cfg !== 'object') return;
  var keys = Object.keys(cfg);
  var recs = keys.map(function (k) {
    return { office_id: conf.office, key: k, value: cfg[k],
             updated_at: new Date().toISOString() };
  });
  if (recs.length) {
    _sbFetch_(conf, '/rest/v1/office_config?on_conflict=office_id,key',
              recs, 'resolution=merge-duplicates');
  }
  // מחיקת מפתחות שהוסרו מהבלוב (רשימת המפתחות היא ASCII בלבד)
  var keep = keys.filter(function (k) { return /^[A-Za-z0-9_]+$/.test(k); });
  if (keep.length) {
    UrlFetchApp.fetch(conf.url + '/rest/v1/office_config?office_id=eq.' + conf.office +
                      '&key=not.in.(' + keep.join(',') + ')', {
      method: 'delete',
      headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
      muteHttpExceptions: true
    });
  }
}

/** Backfill חד-פעמי לקונפיג — קורא את הבלוב מהתא ומפצל לשורות. */
function sbBackfillConfig() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var gsh = ss.getSheetByName('config');
  if (!gsh) return 'אין גיליון config';
  var blob = String(gsh.getRange(1, 1).getValue() || '');
  if (!blob) return 'הבלוב ריק';
  sbConfigSplit_(blob);
  var keys = Object.keys(JSON.parse(blob));
  var msg = 'פוצל הקונפיג ל-' + keys.length + ' מפתחות: ' + keys.join(', ');
  Logger.log(msg);
  return msg;
}

/** Parity לקונפיג — משווה את הבלוב מול השורות, מפתח-מפתח (השוואה עמוקה). */
function sbParityConfig() {
  var conf = _sbConf_();
  if (!conf) { Logger.log('❌ חסרות הגדרות'); return '❌'; }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var blob = String(ss.getSheetByName('config').getRange(1, 1).getValue() || '');
  var cfg = JSON.parse(blob || '{}');
  var r = UrlFetchApp.fetch(conf.url + '/rest/v1/office_config?select=key,value&office_id=eq.' + conf.office + '&limit=1000', {
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    muteHttpExceptions: true
  });
  if (r.getResponseCode() !== 200) { Logger.log('❌ שגיאת קריאה: ' + r.getResponseCode()); return '❌'; }
  var rows = JSON.parse(r.getContentText()) || [];
  var sb = {};
  rows.forEach(function (x) { sb[x.key] = x.value; });
  // השוואה קנונית — jsonb ממיין מפתחות באובייקטים, אז ממיינים גם כאן לפני ההשוואה
  function canon(v) {
    if (v === null || typeof v !== 'object') return JSON.stringify(v);
    if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
    return '{' + Object.keys(v).sort().map(function (k) {
      return JSON.stringify(k) + ':' + canon(v[k]);
    }).join(',') + '}';
  }
  var bad = [];
  Object.keys(cfg).forEach(function (k) {
    if (canon(cfg[k]) !== canon(sb[k])) bad.push(k);
  });
  var extra = Object.keys(sb).filter(function (k) { return !(k in cfg); });
  Logger.log('⚙️ קונפיג — מפתחות בבלוב: ' + Object.keys(cfg).length + ' · ב-Supabase: ' + rows.length);
  Logger.log(bad.length ? ('❌ מפתחות שונים: ' + bad.join(', ')) : '✅ כל המפתחות זהים ערך-בערך');
  if (extra.length) Logger.log('⚠️ עודפים ב-Supabase: ' + extra.join(', '));
  var ok = !bad.length && !extra.length;
  Logger.log(ok ? '🟢 PARITY קונפיג מלא' : '🔴 יש פערים');
  return ok ? 'OK' : 'GAPS';
}

/***********************************************************************
 * ══ שלב 6: "נכסים בשת"פ" + "נכסים במשרד" ═══════════════════════════
 * שני המקורות נשארים בגיליונות (אוטומציה חיצונית / הזנה ידנית) —
 * הסנכרון המתוזמן (sbReconcileAll) משקף אותם ל-Supabase. אין hooks.
 * לגיליון הנכסים הנפרד: הוסף Script Property בשם PROPS_SHEET_ID עם ה-ID
 * של הקובץ (אם לא הוגדר — נעשה שימוש בברירת המחדל שבקוד).
 ***********************************************************************/
var _SB_PROPS_SHEET_DEFAULT = '1PnQm-ifyLrh6sBbNNQbNlAHmJWeBnbzXJJERmTuaAVM';

/** סנכרון "בלעדויות חיצוניות" — כמו שיחות: raw + received_at, מפתח event_id. */
function sbBackfillExclusives() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('בלעדויות חיצוניות');
  if (!sh || sh.getLastRow() < 2) return 'אין נתונים';
  var v = sh.getDataRange().getValues();
  var hd = v[0];
  var byKey = {}, total = 0, noId = 0;
  for (var i = 1; i < v.length; i++) {
    var any = v[i].some(function (x) { return String(x == null ? '' : x).trim(); });
    if (!any) continue;
    total++;
    var raw = {}, rxVal = null, eid = '';
    for (var c = 0; c < hd.length; c++) {
      var h = String(hd[c] == null ? '' : hd[c]).trim();
      if (h === 'received_at') rxVal = v[i][c];
      if (h === 'event_id') eid = String(v[i][c] == null ? '' : v[i][c]).trim();
      raw[h] = (v[i][c] instanceof Date) ? v[i][c].toISOString() : v[i][c];
    }
    if (!eid) { eid = _sbCallKey_('', v[i], i); noId++; }
    byKey[eid] = {
      office_id: conf.office, source_key: eid, event_id: eid,
      street: String(raw['street'] == null ? '' : raw['street']),
      dest: String(raw['dest'] == null ? '' : raw['dest']),
      link: String(raw['link'] == null ? '' : raw['link']),
      price: String(raw['price'] == null ? '' : raw['price']),
      received_at: _sbDateOnly_(rxVal),
      raw: raw, updated_at: new Date().toISOString()
    };
  }
  var unique = Object.keys(byKey).map(function (k) { return byKey[k]; });
  var BATCH = 400, sent = 0, errs = 0;
  for (var b = 0; b < unique.length; b += BATCH) {
    var r = _sbFetch_(conf, '/rest/v1/external_exclusives?on_conflict=office_id,source_key',
                      unique.slice(b, b + BATCH), 'resolution=merge-duplicates');
    var code = r.getResponseCode();
    if (code >= 200 && code < 300) sent += Math.min(BATCH, unique.length - b);
    else { errs++; Logger.log('שגיאה בקבוצה ' + b + ': ' + code + ' ' + r.getContentText().substring(0, 150)); }
  }
  var msg = 'הועברו ' + sent + '/' + unique.length + ' בלעדויות (' + total + ' שורות, ' + noId + ' בלי מזהה)' +
            (errs ? (' · ' + errs + ' קבוצות נכשלו') : ' · הכל תקין ✅');
  Logger.log(msg);
  return msg;
}

/** סנכרון "נכסים במשרד" — גיליון נפרד, תמונת-מצב לפי שורה (כמו קונים). */
function sbBackfillProperties() {
  var conf = _sbConf_();
  if (!conf) return '❌ missing properties';
  var pid = String(PropertiesService.getScriptProperties().getProperty('PROPS_SHEET_ID') || '').trim() || _SB_PROPS_SHEET_DEFAULT;
  var sh;
  try { sh = SpreadsheetApp.openById(pid).getSheetByName('נכסים'); }
  catch (e) { Logger.log('❌ אין גישה לגיליון הנכסים: ' + e); return '❌ no access'; }
  if (!sh || sh.getLastRow() < 2) return 'אין נתונים';
  var v = sh.getDataRange().getValues();
  var hd = v[0];
  // מחיקה ומילוי מחדש — תמונת-מצב (הגיליון ידני, שורות זזות)
  UrlFetchApp.fetch(conf.url + '/rest/v1/properties?office_id=eq.' + conf.office, {
    method: 'delete',
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key },
    muteHttpExceptions: true
  });
  var recs = [];
  for (var i = 1; i < v.length; i++) {
    var raw = {}, any = false;
    for (var c = 0; c < hd.length; c++) {
      var h = String(hd[c] == null ? '' : hd[c]).trim();
      var val = (v[i][c] instanceof Date) ? v[i][c].toISOString() : v[i][c];
      if (h) raw[h] = (val == null ? '' : val);
      if (String(val == null ? '' : val).trim()) any = true;
    }
    if (!any) continue;
    // תיאור מעמודה AE (אינדקס 30) — כמו _fetch_sheet_rows_raw באפליקציה
    raw['_desc_ae'] = String((v[i].length > 30 ? v[i][30] : '') || '').trim();
    recs.push({ office_id: conf.office, sheet_row: i + 1, raw: raw });
  }
  var BATCH = 300, sent = 0, errs = 0;
  for (var b = 0; b < recs.length; b += BATCH) {
    var r = _sbFetch_(conf, '/rest/v1/properties?on_conflict=office_id,sheet_row',
                      recs.slice(b, b + BATCH), 'resolution=merge-duplicates');
    var code = r.getResponseCode();
    if (code >= 200 && code < 300) sent += Math.min(BATCH, recs.length - b);
    else { errs++; Logger.log('שגיאה בקבוצה ' + b + ': ' + code + ' ' + r.getContentText().substring(0, 150)); }
  }
  var msg = 'הועברו ' + sent + '/' + recs.length + ' נכסים' + (errs ? (' · ' + errs + ' קבוצות נכשלו') : ' · הכל תקין ✅');
  Logger.log(msg);
  return msg;
}

/** Parity לשת"פ + נכסים — ספירות והשוואת מפתחות. */
function sbParityProps() {
  var conf = _sbConf_();
  if (!conf) { Logger.log('❌ חסרות הגדרות'); return '❌'; }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  // שת"פ
  var sh = ss.getSheetByName('בלעדויות חיצוניות');
  var v = sh.getDataRange().getValues();
  var sheetN = 0;
  for (var i = 1; i < v.length; i++) {
    if (v[i].some(function (x) { return String(x == null ? '' : x).trim(); })) sheetN++;
  }
  var r = UrlFetchApp.fetch(conf.url + '/rest/v1/external_exclusives?select=source_key&office_id=eq.' + conf.office + '&limit=10000', {
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key }, muteHttpExceptions: true
  });
  var sbN = (JSON.parse(r.getContentText()) || []).length;
  Logger.log('🤝 שת"פ — גיליון: ' + sheetN + ' · Supabase: ' + sbN + (sheetN <= sbN ? ' · ✅' : ' · ❌ חסרות'));
  // נכסים
  var pid = String(PropertiesService.getScriptProperties().getProperty('PROPS_SHEET_ID') || '').trim() || _SB_PROPS_SHEET_DEFAULT;
  var pn = 0;
  try {
    var psh = SpreadsheetApp.openById(pid).getSheetByName('נכסים');
    var pv = psh.getDataRange().getValues();
    for (var j = 1; j < pv.length; j++) {
      if (pv[j].some(function (x) { return String(x == null ? '' : x).trim(); })) pn++;
    }
  } catch (e) { Logger.log('❌ גיליון נכסים: ' + e); }
  var r2 = UrlFetchApp.fetch(conf.url + '/rest/v1/properties?select=sheet_row&office_id=eq.' + conf.office + '&limit=10000', {
    headers: { 'apikey': conf.key, 'Authorization': 'Bearer ' + conf.key }, muteHttpExceptions: true
  });
  var pbN = (JSON.parse(r2.getContentText()) || []).length;
  Logger.log('🏠 נכסים — גיליון: ' + pn + ' · Supabase: ' + pbN + (pn === pbN ? ' · ✅' : ' · ❌'));
  var ok = (sheetN <= sbN) && (pn === pbN);
  Logger.log(ok ? '🟢 PARITY שת"פ+נכסים מלא' : '🔴 יש פערים');
  return ok ? 'OK' : 'GAPS';
}

/***********************************************************************
 * ריפוי עצמי — סנכרון-השלמה של כל המודולים. מיועד לטריגר מתוזמן:
 * בעורך: אייקון השעון ⏰ (טריגרים) ▸ הוספת טריגר ▸ פונקציה: sbReconcileAll,
 * מבוסס זמן ▸ כל 30 דקות. סוגר אוטומטית כל פער שנוצר מכשל כתיבה רגעי
 * (כמו בזמן תקלת גוגל) — הגיליון הוא מקור האמת, וה-upsert משלים חוסרים.
 ***********************************************************************/
function sbReconcileAll() {
  var conf = _sbConf_();
  if (!conf) return;
  try { sbBackfillNewborn(); } catch (e) { Logger.log('reconcile newborn: ' + e); }
  try { sbBackfillNewbornContacts(); } catch (e) { Logger.log('reconcile contacts: ' + e); }
  try { sbBackfillCalls(); } catch (e) { Logger.log('reconcile calls: ' + e); }
  try { sbBackfillHidden(); } catch (e) { Logger.log('reconcile hidden: ' + e); }
  try { sbBackfillSignatures(); } catch (e) { Logger.log('reconcile signatures: ' + e); }
  try { sbBackfillBuyers(); } catch (e) { Logger.log('reconcile buyers: ' + e); }
  try { sbBackfillConfig(); } catch (e) { Logger.log('reconcile config: ' + e); }
  try { sbBackfillExclusives(); } catch (e) { Logger.log('reconcile excl: ' + e); }
  try { sbBackfillProperties(); } catch (e) { Logger.log('reconcile props: ' + e); }
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
