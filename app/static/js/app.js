// Shared UI behaviour: theme toggle, dialogs, copy buttons, confirm prompts.
(function () {
  var order = ['auto', 'light', 'dark'];
  var names = {auto: 'system', light: 'light', dark: 'dark'};
  // The icon shows the state in force: sun and moon for a forced theme, the
  // half sun/moon for "follow the system".
  var icons = {auto: 'theme', light: 'sun', dark: 'moon'};

  function current() {
    return localStorage.getItem('quizdeck-theme') || 'auto';
  }

  function nextState(theme) {
    return order[(order.indexOf(theme) + 1) % order.length];
  }

  function apply() {
    var theme = current();
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
    // The button is re-rendered on every hx-boost navigation, so look it up now.
    var button = document.getElementById('theme-toggle');
    if (!button) return;
    var icon = button.querySelector('use');
    if (icon) {
      // Keep whatever path the template used (it carries the asset version).
      icon.setAttribute('href', (icon.getAttribute('href') || '').split('#')[0] + '#' + icons[theme]);
    }
    var label = 'Colour theme: ' + names[theme] + '. Click for ' + names[nextState(theme)] + '.';
    button.title = label;
    button.setAttribute('aria-label', label);
  }

  function cycle() {
    localStorage.setItem('quizdeck-theme', nextState(current()));
    apply();
  }

  // Times are rendered in UTC by the server; show them in the reader's time zone.
  function localizeTimes() {
    Array.prototype.forEach.call(document.querySelectorAll('time.local-time'), function (el) {
      var date = new Date(el.getAttribute('datetime'));
      if (!Number.isNaN(date.getTime())) {
        el.textContent = date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
      }
    });
  }

  apply();
  localizeTimes();

  // Body scripts re-run on hx-boost navigation: bind document handlers once.
  if (window.quizdeckUiBound) return;
  window.quizdeckUiBound = true;

  // Delegated: hx-boost replaces the header, so a direct listener would be lost.
  document.addEventListener('click', function (event) {
    if (event.target.closest('#theme-toggle')) {
      cycle();
      return;
    }
    var opener = event.target.closest('[data-open]');
    if (opener) document.getElementById(opener.dataset.open).showModal();
    var closer = event.target.closest('[data-close]');
    if (closer) closer.closest('dialog').close();
    var copy = event.target.closest('[data-copy]');
    if (copy) {
      navigator.clipboard.writeText(document.getElementById(copy.dataset.copy).textContent);
      copy.textContent = 'Copied';
    }
  });

  // Filter selects (data-autosubmit) apply as soon as they change; delegated so it survives hx-boost.
  document.addEventListener('change', function (event) {
    var select = event.target.closest('select[data-autosubmit]');
    if (select && select.form) select.form.requestSubmit();
  });

  // Keep the toggle's label in sync after a boosted navigation.
  document.addEventListener('htmx:afterSettle', apply);

  document.addEventListener('submit', function (event) {
    var source = event.submitter && event.submitter.dataset.confirm ? event.submitter : event.target;
    var message = source.dataset.confirm;
    if (message && !confirm(message)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
})();
