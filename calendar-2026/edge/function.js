// CloudFront Function (runtime cloudfront-js-2.0), viewer-request on both behaviors.
// Gate for calendar-2026: path allow-list, site mode, signed visitor cookie.
// Key-value store keys: mode (open|paused|closed), secret (HMAC key for the visitor cookie).
import cf from 'cloudfront';
import crypto from 'crypto';

var kvs = cf.kvs();

var MONTHS = ['january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december'];

var PAGES = { '/': '/index.html', '/index.html': '/index.html', '/month.html': '/month.html',
  '/wall': '/wall/index.html', '/wall/': '/wall/index.html', '/wall/index.html': '/wall/index.html', '/404.html': '/404.html' };

function reply(status, text, body, extra) {
  var headers = { 'content-type': { value: text }, 'cache-control': { value: 'no-store' } };
  if (extra) { for (var k in extra) { headers[k] = { value: extra[k] }; } }
  var desc = status === 503 ? 'Service Unavailable' : status === 423 ? 'Locked' : 'Forbidden';
  return { statusCode: status, statusDescription: desc, headers: headers, body: body };
}
function deny(status, error, extra) {
  var body = { error: error };
  if (extra) { for (var k in extra) { body[k] = extra[k]; } }
  return reply(status, 'application/json; charset=utf-8', JSON.stringify(body));
}

function cookie(request, name) {
  var c = request.cookies[name];
  if (!c) { return ''; }
  if (c.multiValue && c.multiValue.length) { return c.multiValue[c.multiValue.length - 1].value; }
  return c.value || '';
}

async function kv(key) {
  try { return await kvs.get(key); } catch (e) { return ''; }
}

// calendar2026_s = <kind>.<subject>.<expiry>.<sig>; kind v (visitor code) or p (admin).
// sig = first 32 hex chars of HMAC-SHA256("kind.subject.expiry", secret). Returns kind or ''.
async function sessionKind(request, secret) {
  var parts = cookie(request, 'calendar2026_s').split('.');
  if (parts.length !== 4) { return ''; }
  var kind = parts[0], subject = parts[1], exp = parts[2], sig = parts[3];
  if ((kind !== 'v' && kind !== 'p') || !/^[A-Z0-9-]{1,40}$/.test(subject) || !/^[0-9]{1,12}$/.test(exp) || sig.length !== 32) { return ''; }
  if (parseInt(exp, 10) * 1000 <= Date.now()) { return ''; }
  var expected = crypto.createHmac('sha256', secret).update(kind + '.' + subject + '.' + exp).digest('hex').slice(0, 32);
  return expected === sig ? kind : '';
}

async function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var isApi = uri.indexOf('/api/') === 0;

  if (uri.indexOf('..') >= 0 || uri.indexOf('//') >= 0 || uri.indexOf('\\') >= 0 || (!isApi && (uri.indexOf('%') >= 0 || uri !== uri.toLowerCase()))) {
    return reply(403, 'text/plain', 'forbidden');
  }

  var mode = await kv('mode');
  if (mode !== 'open' && mode !== 'paused') { mode = 'closed'; }

  if (mode === 'closed') {
    if (isApi) { return deny(503, 'closed', null); }
    return reply(503, 'text/html; charset=utf-8',
      '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Calendar 2026</title><p style="font:18px system-ui;text-align:center;margin-top:20vh">Cerrado por ahora · Closed for now</p>',
      { 'retry-after': '3600' });
  }

  if (isApi) {
    if (mode === 'paused') { return deny(503, 'paused', null); }
    if (!/^\/api\/[a-z0-9\/._-]*$/i.test(uri)) { return reply(403, 'text/plain', 'forbidden'); }
    return request;
  }

  if (PAGES[uri]) { request.uri = PAGES[uri]; return request; }
  if (/^\/assets\/[a-z0-9._-]+$/.test(uri)) { return request; }

  var month = uri.match(/^\/([a-z]+)(\/.*)?$/);
  if (!month || MONTHS.indexOf(month[1]) < 0) { return reply(403, 'text/plain', 'forbidden'); }
  var name = month[1], rest = month[2] || '';

  if (rest === '' || rest === '/') { request.uri = '/month.html'; return request; }

  if (rest === '/index.json' || /^\/p\/[0-9a-f]{12}(_t)?\.webp$/.test(rest)) {
    var secret = await kv('secret');
    if (!secret || !(await sessionKind(request, secret))) { return deny(423, 'locked', null); }
    request.uri = '/months/' + name + rest;
    return request;
  }

  return reply(403, 'text/plain', 'forbidden');
}
