// One page for the twelve months: reads the month from the path, asks the edge for the data,
// and shows "not yet", the code form, or the photo grid.
document.addEventListener('DOMContentLoaded', function () {
  var $ = function (id) { return document.getElementById(id); };
  var month = location.pathname.replace(/^\/|\/$/g, '').toLowerCase();
  var idx = window.MONTHS.indexOf(month);
  if (idx < 0) { location.replace('/january'); return; }

  function heading() {
    $('heading').textContent = window.t('month_title') + ' ' + window.monthName(idx).toLowerCase();
    document.title = 'Calendar 2026 · ' + window.monthName(idx);
    var nav = $('months'); nav.innerHTML = '';
    window.MONTHS.forEach(function (m, i) {
      var a = document.createElement('a'); a.href = '/' + m; a.textContent = window.monthName(i);
      if (i === idx) a.setAttribute('aria-current', 'page');
      nav.appendChild(a);
    });
  }
  heading();
  document.addEventListener('langchange', function () { heading(); if (opensAt) showNotYet(opensAt); });

  var opensAt = null, timer = null;
  function show(id) { ['not-yet', 'locked', 'open'].forEach(function (x) { $(x).classList.toggle('hidden', x !== id); }); }

  function showNotYet(iso) {
    opensAt = iso;
    var when = new Date(iso);
    $('opens-date').textContent = when.toLocaleDateString(window.lang === 'es' ? 'es-ES' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
    function tick() {
      var ms = when - Date.now();
      if (ms <= 0) { clearInterval(timer); load(); return; }
      var d = Math.floor(ms / 86400000), h = Math.floor(ms % 86400000 / 3600000), m = Math.floor(ms % 3600000 / 60000);
      $('countdown').textContent = d + ' ' + window.t('countdown_days') + ' ' + String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
    }
    clearInterval(timer); tick(); timer = setInterval(tick, 30000);
    show('not-yet');
  }

  function render(list) {
    var grid = $('grid'); grid.innerHTML = '';
    $('empty').classList.toggle('hidden', list.length > 0);
    list.forEach(function (p) {
      var a = document.createElement('a'); a.href = '/' + month + '/p/' + p.id + '.webp';
      var img = document.createElement('img'); img.loading = 'lazy'; img.alt = ''; img.src = '/' + month + '/p/' + p.id + '_t.webp';
      if (p.w && p.h) { img.width = p.w; img.height = p.h; }
      a.appendChild(img);
      a.addEventListener('click', function (e) { e.preventDefault(); $('lightbox-img').src = a.href; $('lightbox').setAttribute('open', ''); });
      grid.appendChild(a);
    });
    show('open');
  }
  $('lightbox').addEventListener('click', function () { $('lightbox').removeAttribute('open'); $('lightbox-img').src = ''; });

  async function load() {
    var res = await fetch('/' + month + '/index.json', { credentials: 'same-origin', cache: 'no-store' });
    var data = {};
    try { data = await res.json(); } catch (e) {}
    if (res.status === 200) return render(data.photos || []);
    if (res.status === 423 && data.error === 'not_yet') return showNotYet(data.opens);
    if (res.status === 503) { $('status').textContent = window.t(data.error === 'paused' ? 'err_paused' : 'err_closed'); show('locked'); return; }
    show('locked');
  }

  $('unlock').addEventListener('click', async function () {
    var code = $('code').value.trim();
    if (!code) return;
    $('unlock').disabled = true; $('status').textContent = window.t('unlocking'); $('status').classList.remove('error');
    var r = await window.api('POST', '/api/unlock', { code: code });
    $('unlock').disabled = false;
    if (r.status !== 200) { $('status').textContent = window.t(window.errorKey(r.status, r.data)); $('status').classList.add('error'); return; }
    $('status').textContent = '';
    load();
  });
  $('code').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('unlock').click(); });

  load();
});
