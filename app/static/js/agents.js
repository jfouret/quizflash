// Admin agent settings: restore the built-in default prompts for the current step.
(function () {
  var button = document.querySelector('[data-restore-defaults]');
  if (!button) return;
  button.addEventListener('click', function () {
    if (!window.confirm('Replace the prompts with the built-in defaults?')) return;
    var system = document.getElementById('system-prompt');
    var template = document.getElementById('prompt-template');
    if (system) system.value = button.dataset.defaultSystem || '';
    if (template) template.value = button.dataset.defaultPrompt || '';
  });
})();
