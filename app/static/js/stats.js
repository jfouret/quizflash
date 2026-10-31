// Stats page: chart the per-card and per-tag mean normalized rating with Chart.js.
(function () {
  var config = document.getElementById('stats-config');
  if (!config || typeof Chart === 'undefined') return;

  function shorten(text, max) {
    return text.length > max ? text.slice(0, max - 1) + '…' : text;
  }

  function draw(canvasId, data) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !data || !data.items.length) return;
    var items = data.items;
    var color = (getComputedStyle(document.body).getPropertyValue('--pico-primary') || '').trim() || '#4f46e5';
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: items.map(function (item) { return shorten(item.label, 40); }),
        datasets: [{
          label: 'Mean / 10',
          data: items.map(function (item) {
            return item.avg_normalized == null ? 0 : Math.round(item.avg_normalized * 10) / 10;
          }),
          backgroundColor: color
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {x: {beginAtZero: true, max: 10}},
        plugins: {legend: {display: false}}
      }
    });
  }

  draw('chart-card', JSON.parse(config.dataset.card));
  draw('chart-tag', JSON.parse(config.dataset.tag));
})();
