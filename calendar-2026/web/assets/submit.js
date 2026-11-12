document.addEventListener('DOMContentLoaded', function () {
  var kind = 'photo';
  var photoBlob = null;
  var $ = function (id) { return document.getElementById(id); };

  // month picker
  var sel = $('month');
  function fillMonths() {
    var current = sel.value;
    sel.innerHTML = '';
    window.MONTHS.forEach(function (m, i) {
      var o = document.createElement('option'); o.value = m; o.textContent = window.monthName(i); sel.appendChild(o);
    });
    sel.value = current || window.MONTHS[window.monthFromQuery()];
  }
  fillMonths();
  document.addEventListener('langchange', function () { fillMonths(); });

  // tabs
  document.querySelectorAll('[role=tab]').forEach(function (b) {
    b.addEventListener('click', function () {
      kind = b.getAttribute('data-kind');
      document.querySelectorAll('[role=tab]').forEach(function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
      $('pane-photo').classList.toggle('hidden', kind !== 'photo');
      $('pane-doodle').classList.toggle('hidden', kind !== 'doodle');
    });
  });

  // photo
  $('photo').addEventListener('change', async function () {
    var f = $('photo').files[0];
    photoBlob = null;
    $('photo-preview').classList.add('hidden');
    if (!f) return;
    photoBlob = await window.shrinkImage(f);
    var url = URL.createObjectURL(photoBlob);
    $('photo-preview').src = url; $('photo-preview').classList.remove('hidden');
  });

  // doodle
  var canvas = $('doodle'), ctx = canvas.getContext('2d'), drawing = false, color = '#111', touched = false;
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = 10;
  ['#111', '#e5484d', '#f2b544', '#3ddc84', '#4c8dff', '#ffffff'].forEach(function (c, i) {
    var b = document.createElement('button'); b.type = 'button'; b.style.background = c; b.setAttribute('aria-pressed', i === 0 ? 'true' : 'false');
    b.addEventListener('click', function () { color = c; document.querySelectorAll('#palette button').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); }); });
    $('palette').appendChild(b);
  });
  function pos(e) { var r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height]; }
  canvas.addEventListener('pointerdown', function (e) { drawing = true; touched = true; ctx.strokeStyle = color; ctx.beginPath(); ctx.moveTo.apply(ctx, pos(e)); canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', function (e) { if (!drawing) return; ctx.lineTo.apply(ctx, pos(e)); ctx.stroke(); });
  ['pointerup', 'pointercancel'].forEach(function (ev) { canvas.addEventListener(ev, function () { drawing = false; }); });
  $('doodle-clear').addEventListener('click', function () { ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); touched = false; });

  function status(msg, isError) { $('status').textContent = msg || ''; $('status').classList.toggle('error', !!isError); }

  // send
  $('send').addEventListener('click', async function () {
    var text = $('text').value.trim();
    if (kind === 'photo' && !photoBlob) return status(window.t('err_empty'), true);
    if (kind === 'doodle' && !touched) return status(window.t('err_empty'), true);
    $('send').disabled = true; status(window.t('sending'));
    var blob = kind === 'photo' ? photoBlob : await new Promise(function (r) { canvas.toBlob(r, 'image/png'); });
    var body = { kind: kind, month: sel.value, name: $('name').value.trim(), text: text, pow: await window.proofOfWork(), website: $('website').value };
    body.upload = { size: blob.size, type: blob.type || 'image/jpeg' };
    var r = await window.api('POST', '/api/posts', body);
    if (r.status !== 201) {
      $('send').disabled = false; window.resetProofOfWork();
      return status(window.t(window.errorKey(r.status, r.data)), true);
    }
    status(window.t('uploading'));
    var ok = await window.uploadTo(r.data.upload, blob);
    if (!ok) { $('send').disabled = false; return status(window.t('err_generic'), true); }
    status('');
    $('code').textContent = r.data.code;
    $('go-month').href = '/' + sel.value;
    $('form-card').classList.add('hidden'); $('done-card').classList.remove('hidden');
    window.scrollTo(0, 0);
  });
  $('another').addEventListener('click', function () { location.reload(); });
});
