// Apply the saved theme before first paint: no attribute means "follow system".
(function () {
  var theme = localStorage.getItem('quizdeck-theme') || 'auto';
  if (theme !== 'auto') document.documentElement.setAttribute('data-theme', theme);
})();
