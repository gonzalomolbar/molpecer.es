// Runs the CloudFront Function locally with a fake key-value store.
//   node calendar-2026/tests/edge.test.mjs
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import nodeCrypto from 'node:crypto';

const source = readFileSync(new URL('../edge/function.js', import.meta.url), 'utf8');
assert.ok(Buffer.byteLength(source) < 10 * 1024, 'function must stay under 10 KB');

const SECRET = 'test-secret';
const store = { mode: 'open', secret: SECRET };
const stub = { kvs: () => ({ get: async (k) => { if (k in store) return store[k]; throw new Error('missing'); } }) };
const ctx = { cf: stub, crypto: nodeCrypto, Date, JSON, String, parseInt, console };
vm.createContext(ctx);
vm.runInContext(source.replace("import cf from 'cloudfront';", '').replace("import crypto from 'crypto';", '') + '\nthis.handler = handler;', ctx);
const handler = ctx.handler;

const sign = (kind, subject, exp, secret = SECRET) => {
  const payload = `${kind}.${subject}.${exp}`;
  return `${payload}.${nodeCrypto.createHmac('sha256', secret).update(payload).digest('hex').slice(0, 32)}`;
};
const FUTURE = 1833926400; // 2028-02-05
const visitor = sign('v', 'LUIS-7K2P', FUTURE);
const preview = sign('p', 'TORIBIOS', FUTURE);

const req = (uri, { cookies = {}, method = 'GET' } = {}) => ({ request: { uri, method, headers: {}, cookies: Object.fromEntries(Object.entries(cookies).map(([k, v]) => [k, { value: v }])), querystring: {} } });
const realNow = Date.now;
const at = (iso) => { Date.now = () => new Date(iso).getTime(); };
const json = (r) => JSON.parse(r.body);

let r;
// hygiene and allow-list
for (const bad of ['/march/../wall/index.json', '/months/december/index.json', '/months/index.html', '/m%6fnths/december/index.json', '/Months/december/index.json', '//march', '/march\\x', '/assets/../index.html', '/assets/x%2e', '/march/p/../../months/december/index.json', '/march/p/zz.webp', '/march/extra', '/maybe', '/wall/other.html', '/index.json', '/robots.txt']) {
  r = await handler(req(bad)); assert.equal(r.statusCode, 403, `should refuse ${bad}`);
}
// api path charset is checked loosely (the api re-validates); uppercase and % are allowed there
r = await handler(req('/api/posts')); assert.equal(r.uri, '/api/posts');
r = await handler(req('/api/w%61ll/posts')); assert.equal(r.statusCode, 403, 'percent in api path refused');

// modes
store.mode = 'closed';
r = await handler(req('/')); assert.equal(r.statusCode, 503); assert.match(r.headers['content-type'].value, /html/);
r = await handler(req('/api/posts', { method: 'POST' })); assert.equal(r.statusCode, 503); assert.equal(json(r).error, 'closed');
store.mode = 'paused';
r = await handler(req('/api/health')); assert.equal(r.statusCode, 503, 'paused blocks every api call'); assert.equal(json(r).error, 'paused');
r = await handler(req('/')); assert.equal(r.uri, '/index.html', 'paused keeps pages up');
delete store.mode;
r = await handler(req('/')); assert.equal(r.statusCode, 503, 'missing mode fails closed');
store.mode = 'garbage';
r = await handler(req('/')); assert.equal(r.statusCode, 503, 'unknown mode fails closed');
store.mode = 'open';

// pages and assets
r = await handler(req('/')); assert.equal(r.uri, '/index.html');
r = await handler(req('/wall')); assert.equal(r.uri, '/wall/index.html');
r = await handler(req('/wall/')); assert.equal(r.uri, '/wall/index.html');
r = await handler(req('/404.html')); assert.equal(r.uri, '/404.html');
r = await handler(req('/assets/app.js')); assert.equal(r.uri, '/assets/app.js');
r = await handler(req('/march')); assert.equal(r.uri, '/month.html');
r = await handler(req('/march/')); assert.equal(r.uri, '/month.html');

// month data: any valid visitor cookie opens any month
at('2026-11-12T12:00:00Z');
r = await handler(req('/march/index.json')); assert.equal(r.statusCode, 423); assert.equal(json(r).error, 'locked');
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: visitor } })); assert.equal(r.uri, '/months/march/index.json');
r = await handler(req('/march/p/0123456789ab_t.webp', { cookies: { calendar2026_s: visitor } })); assert.equal(r.uri, '/months/march/p/0123456789ab_t.webp');
r = await handler(req('/december/index.json', { cookies: { calendar2026_s: visitor } })); assert.equal(r.uri, '/months/december/index.json', 'no time lock');

// bad cookies
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: sign('v', 'LUIS-7K2P', FUTURE, 'other') } })); assert.equal(r.statusCode, 423, 'wrong secret');
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: sign('v', 'LUIS-7K2P', 1000) } })); assert.equal(r.statusCode, 423, 'expired');
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: visitor.slice(0, -1) + '0' } })); assert.equal(r.statusCode, 423, 'tampered sig');
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: sign('a', 'TORIBIOS', FUTURE) } })); assert.equal(r.statusCode, 423, 'admin cookie kind is not for the edge');
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: sign('v', 'bad.subject', FUTURE) } })); assert.equal(r.statusCode, 423, 'dot in subject');
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: 'garbage' } })); assert.equal(r.statusCode, 423);
delete store.secret;
r = await handler(req('/march/index.json', { cookies: { calendar2026_s: visitor } })); assert.equal(r.statusCode, 423, 'no secret configured means locked');
store.secret = SECRET;

// admin cookie kind p is accepted too
r = await handler(req('/december/index.json', { cookies: { calendar2026_s: preview } })); assert.equal(r.uri, '/months/december/index.json');

Date.now = realNow;
console.log('edge tests ok');
