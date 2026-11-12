// One page for the twelve months: reads the month from the path, asks the edge for the data,
// and shows the photo grid; without a valid code it sends the visitor to the front door at /months.
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
  document.addEventListener('langchange', heading);

  function show(id) { ['locked', 'open'].forEach(function (x) { $(x).classList.toggle('hidden', x !== id); }); }

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
    if (res.status === 503) { $('status').textContent = window.t(data.error === 'paused' ? 'err_paused' : 'err_closed'); show('locked'); return; }
    location.replace('/months');
  }

  load();
});
