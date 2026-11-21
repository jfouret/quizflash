// Stats page: the tag scores and the 30-day activity, drawn with Chart.js.
(function () {
  var config = document.getElementById('stats-config');
  if (!config || typeof Chart === 'undefined') return;

  var scaleMax = parseInt(config.dataset.scaleMax, 10) || 5;

  function shorten(text, max) {
    return text.length > max ? text.slice(0, max - 1) + '…' : text;
  }

  // Read the resolved colour: a light-dark() token would come back unresolved
  // from getPropertyValue. The canvas inherits the accent through .chart-wrap.
  function colorOf(canvas) {
    return getComputedStyle(canvas).color || '#4f46e5';
  }

  function drawTags(data) {
    var canvas = document.getElementById('chart-tag');
    if (!canvas || !data || !data.items.length) return;
    // Weakest first, so the tags to work on sit at the top.
    var items = data.items.filter(function (item) { return item.avg_rating != null; })
      .sort(function (a, b) { return a.avg_rating - b.avg_rating; });
    // One row per tag: a fixed height would crush the bars when there are many.
    document.getElementById('tag-wrap').style.height = (items.length * 28 + 48) + 'px';
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: items.map(function (item) { return shorten(item.label, 30); }),
        datasets: [{
          label: 'Mean score',
          data: items.map(function (item) { return Math.round(item.avg_rating * 10) / 10; }),
          backgroundColor: colorOf(canvas)
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {x: {beginAtZero: true, max: scaleMax}},
        plugins: {legend: {display: false}}
      }
    });
  }

  function drawActivity(data) {
    var canvas = document.getElementById('chart-activity');
    if (!canvas || !data) return;
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.labels.map(function (day) { return day.slice(5); }),
        datasets: [{label: 'Answers', data: data.values, backgroundColor: colorOf(canvas)}]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {y: {beginAtZero: true, ticks: {precision: 0}}, x: {ticks: {maxTicksLimit: 8}}},
        plugins: {legend: {display: false}}
      }
    });
  }

  drawTags(JSON.parse(config.dataset.tag));
  drawActivity(JSON.parse(config.dataset.activity));
})();
