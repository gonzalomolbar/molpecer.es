// The front door of the month pages: asks for the code once, then lists the twelve months.
document.addEventListener('DOMContentLoaded', function () {
  var $ = function (id) { return document.getElementById(id); };
  function show(id) { ['locked', 'open'].forEach(function (x) { $(x).classList.toggle('hidden', x !== id); }); }

  function grid() {
    var nav = $('months'); nav.innerHTML = '';
    window.MONTHS.forEach(function (m, i) { var a = document.createElement('a'); a.href = '/' + m; a.textContent = window.monthName(i); nav.appendChild(a); });
  }
  document.addEventListener('langchange', grid);

  // Unlocked means the edge lets month data through; january is as good a probe as any.
  async function check() {
    var res = await fetch('/january/index.json', { credentials: 'same-origin', cache: 'no-store' });
    if (res.status === 200) { grid(); show('open'); return; }
    var data = {}; try { data = await res.json(); } catch (e) {}
    if (res.status === 503) { $('status').textContent = window.t(data.error === 'paused' ? 'err_paused' : 'err_closed'); }
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
    check();
  });
  $('code').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('unlock').click(); });

  check();
});
