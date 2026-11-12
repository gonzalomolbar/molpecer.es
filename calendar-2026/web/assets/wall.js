// The private wall: login, list, details, delete, ban. Everything rendered with textContent.
document.addEventListener('DOMContentLoaded', function () {
  var $ = function (id) { return document.getElementById(id); };
  var me = null, cursor = null, items = [];

  window.MONTHS.forEach(function (m, i) { var o = document.createElement('option'); o.value = m; o.textContent = window.I18N.en.months[i]; $('f-month').appendChild(o); });

  // --- login ---
  async function whoami() {
    var r = await window.api('GET', '/api/wall/me');
    if (r.status === 200) { me = r.data.name; enter(); }
  }
  $('enter').addEventListener('click', async function () {
    $('enter').disabled = true; $('login-status').textContent = '';
    var r = await window.api('POST', '/api/admin/login', { name: $('who').value, code: $('admin-code').value.trim(), pow: await window.proofOfWork() });
    $('enter').disabled = false;
    if (r.status !== 200) { $('login-status').textContent = r.data.error || 'error'; window.resetProofOfWork(); return; }
    me = r.data.name; enter();
  });
  $('admin-code').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('enter').click(); });
  $('logout').addEventListener('click', async function () { await window.api('POST', '/api/admin/logout'); location.reload(); });

  function enter() {
    $('login').classList.add('hidden'); $('wall').classList.remove('hidden'); $('logout').classList.remove('hidden');
    $('logout').textContent = 'Logout (' + me + ')';
    route();
  }

  // #<post id> shows that one post with its details open; otherwise the filtered list.
  function route() {
    var id = (location.hash || '').slice(1);
    var single = /^[0-9A-Z]{26}$/.test(id);
    $('single-bar').classList.toggle('hidden', !single);
    $('filters-card').classList.toggle('hidden', single);
    if (single) loadOne(id); else load(true);
  }
  window.addEventListener('hashchange', route);
  $('all-posts').addEventListener('click', function () { history.replaceState(null, '', '/wall'); route(); });

  async function loadOne(id) {
    $('posts').innerHTML = ''; $('more').classList.add('hidden'); $('count').textContent = '';
    var r = await window.api('GET', '/api/wall/posts/' + id);
    if (r.status === 401) { location.reload(); return; }
    if (r.status !== 200) { $('single-title').textContent = 'Post ' + id + ': ' + (r.data.error || r.status); return; }
    $('single-title').textContent = 'Post ' + id;
    render(r.data.post, true);
  }

  // --- list ---
  async function load(reset) {
    if (reset) { cursor = null; items = []; $('posts').innerHTML = ''; }
    var q = new URLSearchParams();
    if ($('f-month').value) q.set('month', $('f-month').value);
    if ($('f-kind').value) q.set('kind', $('f-kind').value);
    if ($('f-status').value) q.set('status', $('f-status').value);
    if (cursor) q.set('cursor', cursor);
    var r = await window.api('GET', '/api/wall/posts?' + q.toString());
    if (r.status === 401) { location.reload(); return; }
    if (r.status !== 200) { $('count').textContent = 'error: ' + (r.data.error || r.status); return; }
    var list = r.data.posts;
    if (!$('f-status').value) list = list.filter(function (p) { return p.status !== 'deleted'; });
    list.forEach(render);
    items = items.concat(list);
    cursor = r.data.cursor;
    $('more').classList.toggle('hidden', !cursor);
    $('count').textContent = items.length + ' shown';
  }
  ['f-month', 'f-kind', 'f-status'].forEach(function (id) { $(id).addEventListener('change', function () { load(true); }); });
  $('reload').addEventListener('click', function () { load(true); });
  $('more').addEventListener('click', function () { load(false); });

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

  function render(p, open) {
    var box = el('div', 'post'); box.id = 'post-' + p.id;
    if (p.thumb) {
      var a = el('a'); a.href = p.full; var img = el('img'); img.src = p.thumb; img.alt = ''; a.appendChild(img);
      a.addEventListener('click', function (e) { e.preventDefault(); $('lightbox-img').src = p.full; $('lightbox').setAttribute('open', ''); });
      box.appendChild(a);
    } else {
      box.appendChild(el('div', 'note', p.status));
    }
    var body = el('div');
    var meta = el('div', 'meta');
    [p.month, p.kind, p.status, p.code, p.created ? p.created.replace('T', ' ').replace('Z', '') : ''].forEach(function (x) { if (x) meta.appendChild(el('span', 'tag', x)); });
    body.appendChild(meta);
    body.appendChild(el('div', '', p.name || '(no name)'));
    if (p.text) body.appendChild(el('div', 'text', p.text));
    var v = p.visitor || {};
    var det = el('details'); if (open) det.open = true; det.appendChild(el('summary', '', [v.city, v.country, v.device].filter(Boolean).join(' · ') || 'details'));
    var dl = el('dl');
    [['ip', v.ip], ['net', v.net], ['place', [v.city, v.region, v.country, v.postal].filter(Boolean).join(', ')], ['geo', v.lat && v.lon ? v.lat + ', ' + v.lon : ''], ['tz', v.tz], ['device', v.device], ['lang', v.lang], ['ua', v.ua], ['referer', v.referer], ['size', p.width && p.height ? p.width + 'x' + p.height : ''], ['id', p.id],
      ['actions', (p.actions || []).map(function (a) { return a.what + ' by ' + a.who + ' at ' + a.at; }).join('; ')]]
      .forEach(function (kv) { if (!kv[1]) return; dl.appendChild(el('dt', '', kv[0])); dl.appendChild(el('dd', '', kv[1])); });
    det.appendChild(dl); body.appendChild(det);
    var actions = el('div', 'actions');
    if (p.status !== 'deleted') {
      var del = el('button', 'ghost danger', 'Delete'); del.type = 'button';
      del.addEventListener('click', async function () {
        if (!confirm('Delete this post and its images?')) return;
        var r = await window.api('DELETE', '/api/wall/posts/' + p.id);
        if (r.status === 200) { box.style.opacity = '0.4'; del.disabled = true; } else alert(r.data.error || 'error');
      });
      actions.appendChild(del);
    }
    if (v.net) {
      var ban = el('button', 'ghost danger', 'Ban ' + v.net); ban.type = 'button';
      ban.addEventListener('click', async function () {
        if (!confirm('Ban every future submission from ' + v.net + '?')) return;
        var r = await window.api('POST', '/api/wall/bans', { post: p.id });
        if (r.status === 200) { ban.disabled = true; ban.textContent = 'Banned'; } else alert(r.data.error || 'error');
      });
      actions.appendChild(ban);
    }
    body.appendChild(actions);
    box.appendChild(body);
    $('posts').appendChild(box);
  }

  // --- bans ---
  $('show-bans').addEventListener('click', async function () {
    var pane = $('bans'); pane.classList.toggle('hidden');
    if (pane.classList.contains('hidden')) return;
    pane.innerHTML = '';
    var r = await window.api('GET', '/api/wall/bans');
    if (r.status !== 200) { pane.textContent = 'error'; return; }
    if (!r.data.bans.length) { pane.textContent = 'No bans.'; return; }
    r.data.bans.forEach(function (b) {
      var row = el('div', 'row'); row.appendChild(el('span', '', b.net + ' · by ' + b.by + ' · ' + b.at));
      var un = el('button', 'ghost', 'Unban'); un.type = 'button';
      un.addEventListener('click', async function () { var rr = await window.api('POST', '/api/wall/unban', { net: b.net }); if (rr.status === 200) row.remove(); });
      row.appendChild(un); pane.appendChild(row);
    });
  });

  $('lightbox').addEventListener('click', function () { $('lightbox').removeAttribute('open'); $('lightbox-img').src = ''; });
  whoami();
});
