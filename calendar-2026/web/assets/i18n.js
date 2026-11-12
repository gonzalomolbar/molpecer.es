// Strings for both languages. The page picks from navigator.language; the toggle overrides and remembers.
window.I18N = {
  es: {
    title: 'Calendario 2026',
    intro_1: 'Este calendario tiene vida más allá del papel. Mándanos una foto o un dibujo, con unas palabras si quieres, y a cambio te damos un código.',
    intro_2: 'El código abre los meses: una página por mes con las fotos que se quedaron fuera del calendario. Contenido VIP.',
    intro_3: 'Lo que envías lo vemos solo nosotros dos. Se admiten hipopotamadas.',
    tab_photo: 'Foto', tab_doodle: 'Dibujo',
    name: 'Tu nombre (hasta 12 letras)', text: 'Un texto (opcional)',
    photo_pick: 'Elige o haz una foto', photo_hint: 'JPG, PNG, HEIC… hasta 10 MB. La reducimos antes de subirla.',
    doodle_hint: 'Dibuja con el dedo o el ratón.', clear: 'Borrar',
    send: 'Enviar', sending: 'Enviando…', uploading: 'Subiendo la imagen…',
    thanks: '¡Gracias! Este es tu código:', keep: 'Guárdalo: abre los meses en cualquier dispositivo.', go_months: 'Ver los meses',
    another: 'Enviar otra cosa',
    err_generic: 'Algo ha fallado. Prueba otra vez.', err_bot: 'Espera unos segundos y vuelve a intentarlo.',
    err_full: 'Hoy ya no caben más envíos. Vuelve mañana.', err_limit: 'Has enviado muchas cosas hoy. Vuelve mañana.',
    err_big: 'La imagen es demasiado grande.', err_paused: 'Los envíos están pausados un rato. Vuelve más tarde.',
    err_closed: 'Esto está cerrado por ahora.', err_banned: 'No se admiten envíos desde esta red.', err_empty: 'Elige una foto o haz un dibujo.', err_name: 'Escribe tu nombre.',
    month_title: 'Fotos de', months_title: 'Los meses', months_locked: 'Los meses se abren con un código. Lo consigues enviando una foto o un dibujo en la portada.', months_pick: 'Elige un mes para ver las fotos que se quedaron fuera del calendario.', code_label: 'Tu código',
    unlock: 'Abrir', unlocking: 'Abriendo…', err_code: 'Ese código no existe. Revísalo.',
    empty_month: 'Todavía no hay fotos aquí.', all_months: 'Todos los meses', home: 'Portada',
    months: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
    not_found: 'Esa página no existe.',
  },
  en: {
    title: 'Calendar 2026',
    intro_1: 'This calendar has a life beyond paper. Send us a photo or a doodle, with a few words if you like, and you get a code in return.',
    intro_2: 'The code opens the months: one page per month with the photos that did not make it into the calendar. VIP content.',
    intro_3: 'What you send is seen by the two of us only. Hippo-level nonsense welcome.',
    tab_photo: 'Photo', tab_doodle: 'Doodle',
    name: 'Your name (up to 12 letters)', text: 'A few words (optional)',
    photo_pick: 'Pick or take a photo', photo_hint: 'JPG, PNG, HEIC… up to 10 MB. It is shrunk before upload.',
    doodle_hint: 'Draw with your finger or the mouse.', clear: 'Clear',
    send: 'Send', sending: 'Sending…', uploading: 'Uploading the image…',
    thanks: 'Thank you! This is your code:', keep: 'Keep it: it opens the months on any device.', go_months: 'See the months',
    another: 'Send something else',
    err_generic: 'Something went wrong. Try again.', err_bot: 'Wait a few seconds and try again.',
    err_full: 'No more room today. Come back tomorrow.', err_limit: 'You have sent a lot today. Come back tomorrow.',
    err_big: 'That image is too large.', err_paused: 'Submissions are paused for a bit. Come back later.',
    err_closed: 'This is closed for now.', err_banned: 'Submissions from this network are not accepted.', err_empty: 'Pick a photo or draw something.', err_name: 'Write your name.',
    month_title: 'Photos of', months_title: 'The months', months_locked: 'The months open with a code. You get one by sending a photo or a doodle on the front page.', months_pick: 'Pick a month to see the photos that did not make it into the calendar.', code_label: 'Your code',
    unlock: 'Open', unlocking: 'Opening…', err_code: 'That code does not exist. Check it.',
    empty_month: 'No photos here yet.', all_months: 'All months', home: 'Front page',
    months: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    not_found: 'That page does not exist.',
  }
};
window.MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
window.lang = (function () {
  var saved = null;
  try { saved = localStorage.getItem('calendar2026_lang'); } catch (e) {}
  if (saved === 'es' || saved === 'en') return saved;
  return (navigator.language || 'es').toLowerCase().indexOf('es') === 0 ? 'es' : 'en';
})();
window.t = function (key) { return (window.I18N[window.lang] || window.I18N.es)[key]; };
window.setLang = function (l) {
  window.lang = l;
  try { localStorage.setItem('calendar2026_lang', l); } catch (e) {}
  document.documentElement.lang = l;
  document.querySelectorAll('[data-i18n]').forEach(function (el) { el.textContent = window.t(el.getAttribute('data-i18n')); });
  document.querySelectorAll('.lang button').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-lang') === l ? 'true' : 'false'); });
  document.dispatchEvent(new CustomEvent('langchange'));
};
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.lang button').forEach(function (b) { b.addEventListener('click', function () { window.setLang(b.getAttribute('data-lang')); }); });
  window.setLang(window.lang);
});
