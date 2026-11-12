// Shared helpers: API calls (with the body hash the Lambda origin requires), month maths, image shrinking.
(function () {
  async function sha256Hex(text) {
    var buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
  }

  // POST/DELETE through CloudFront to the Lambda URL: the body must be hashed into x-amz-content-sha256.
  window.api = async function (method, path, body) {
    var text = body === undefined ? '' : JSON.stringify(body);
    var headers = { 'x-amz-content-sha256': await sha256Hex(text) };
    if (body !== undefined) headers['content-type'] = 'application/json';
    var res = await fetch(path, { method: method, headers: headers, body: body === undefined ? undefined : text, credentials: 'same-origin' });
    var data = null;
    try { data = await res.json(); } catch (e) { data = {}; }
    return { status: res.status, data: data };
  };

  // The calendar year and the "one month early" rule, mirrored from the edge function.
  window.CALENDAR_YEAR = 2027;
  window.OPENS = [
    Date.UTC(2026, 10, 30, 23), Date.UTC(2026, 11, 31, 23), Date.UTC(2027, 0, 31, 23), Date.UTC(2027, 1, 28, 23),
    Date.UTC(2027, 2, 31, 22), Date.UTC(2027, 3, 30, 22), Date.UTC(2027, 4, 31, 22), Date.UTC(2027, 5, 30, 22),
    Date.UTC(2027, 6, 31, 22), Date.UTC(2027, 7, 31, 22), Date.UTC(2027, 8, 30, 22), Date.UTC(2027, 9, 31, 23)
  ];
  window.monthFromQuery = function () {
    var m = new URLSearchParams(location.search).get('m');
    if (m) {
      m = m.toLowerCase();
      var i = window.MONTHS.indexOf(m);
      if (i >= 0) return i;
      var n = parseInt(m, 10);
      if (n >= 1 && n <= 12) return n - 1;
    }
    var now = new Date();
    if (now.getFullYear() === window.CALENDAR_YEAR) return now.getMonth();
    return 0;
  };
  window.monthName = function (i) { return window.t('months')[i]; };

  // Shrink a picked file in the browser: max 2000 px, JPEG. Falls back to the original when decoding fails.
  window.shrinkImage = async function (file, maxPx) {
    maxPx = maxPx || 2000;
    try {
      var bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
      var scale = Math.min(1, maxPx / Math.max(bitmap.width, bitmap.height));
      var w = Math.round(bitmap.width * scale), h = Math.round(bitmap.height * scale);
      var canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h);
      bitmap.close && bitmap.close();
      var blob = await new Promise(function (resolve) { canvas.toBlob(resolve, 'image/jpeg', 0.85); });
      if (blob) return blob;
    } catch (e) { /* HEIC on a browser that cannot decode it, or a corrupt file: send as is */ }
    return file;
  };

  // Direct upload to S3 with the presigned POST the API returned.
  window.uploadTo = async function (presigned, blob) {
    var form = new FormData();
    Object.keys(presigned.fields).forEach(function (k) { form.append(k, presigned.fields[k]); });
    form.append('file', blob);
    var res = await fetch(presigned.url, { method: 'POST', body: form });
    return res.ok;
  };

  // Proof of work: find a nonce so that sha256("ts.nonce.host") starts with POW_BITS zero bits.
  // Started at page load; by the time the form is filled in it is done. The API also requires the
  // load timestamp to be at least a few seconds old, so a script cannot skip the waiting either.
  var POW_BITS = 13;
  var powPromise = null;
  window.proofOfWork = function () {
    if (powPromise) return powPromise;
    var ts = Math.floor(Date.now() / 1000);
    var enc = new TextEncoder();
    powPromise = (async function () {
      for (var nonce = 0; ; nonce++) {
        var buf = await crypto.subtle.digest('SHA-256', enc.encode(ts + '.' + nonce + '.' + location.hostname));
        var head = new DataView(buf).getUint32(0);
        if ((head >>> (32 - POW_BITS)) === 0) return ts + '.' + nonce;
        if (nonce % 500 === 0) await new Promise(function (r) { setTimeout(r, 0); });
      }
    })();
    return powPromise;
  };
  window.resetProofOfWork = function () { powPromise = null; return window.proofOfWork(); };
  document.addEventListener('DOMContentLoaded', function () { window.proofOfWork(); });

  window.errorKey = function (status, data) {
    var e = (data && data.error) || '';
    if (e === 'bot_check') return 'err_bot';
    if (e === 'full_today') return 'err_full';
    if (e === 'limit_posts' || e === 'limit_bytes' || e === 'limit_unlocks') return 'err_limit';
    if (e === 'too_big') return 'err_big';
    if (e === 'paused') return 'err_paused';
    if (e === 'closed') return 'err_closed';
    if (e === 'banned') return 'err_banned';
    if (e === 'unknown_code' || e === 'bad_code') return 'err_code';
    return 'err_generic';
  };
})();
