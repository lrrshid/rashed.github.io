// Runs before the page is drawn (a plain script in <head>; the content security policy allows no inline scripts):
// applies the saved interface language and direction to <html>, so an Arabic page never flashes left to right,
// and the saved dark mode (data-mode, js/lib/theme.js), so a dark page never flashes light.
// The language itself is handled by js/lib/i18n.js, which reads the same storage key.
(function () {
  var lang = 'en';
  try {
    if (window.localStorage.getItem('cpc.lang') === 'ar') lang = 'ar';
  } catch (e) { /* storage unavailable: English */ }
  document.documentElement.lang = lang;
  try {
    if (window.localStorage.getItem('cpc.mode') === 'dark') document.documentElement.setAttribute('data-mode', 'dark');
  } catch (e) { /* storage unavailable: light */ }
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  // A static page without the app script (404.html) gives its Arabic title in <meta name="fleet-title-ar">.
  if (lang === 'ar') {
    document.addEventListener('DOMContentLoaded', function () {
      var title = document.querySelector('meta[name="fleet-title-ar"]');
      if (title) document.title = title.content;
    });
  }
}());
