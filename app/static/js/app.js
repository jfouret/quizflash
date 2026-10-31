// Shared UI behaviour: theme toggle, dialogs, copy buttons, confirm prompts.
(function () {
  var button = document.getElementById('theme-toggle');
  var order = ['auto', 'light', 'dark'];
  var labels = {auto: 'Theme: system', light: 'Theme: light', dark: 'Theme: dark'};

  function current() {
    return localStorage.getItem('quizdeck-theme') || 'auto';
  }

  function apply() {
    var theme = current();
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
    if (!button) return;
    button.title = labels[theme];
    button.setAttribute('aria-label', labels[theme] + ' (click to change)');
  }

  if (button) {
    button.addEventListener('click', function () {
      var next = order[(order.indexOf(current()) + 1) % order.length];
      localStorage.setItem('quizdeck-theme', next);
      apply();
    });
  }
  apply();

  // Body scripts re-run on hx-boost navigation: bind document handlers once.
  if (window.quizdeckUiBound) return;
  window.quizdeckUiBound = true;

  document.addEventListener('click', function (event) {
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

  document.addEventListener('submit', function (event) {
    var source = event.submitter && event.submitter.dataset.confirm ? event.submitter : event.target;
    var message = source.dataset.confirm;
    if (message && !confirm(message)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
})();
