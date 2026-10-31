// Client-side filter for the public deck list.
(function () {
  var input = document.getElementById('deck-search');
  if (!input) return;
  var cards = document.querySelectorAll('#public-decks [data-search]');
  var none = document.getElementById('no-match');
  input.addEventListener('input', function () {
    var term = input.value.trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {
      var match = card.dataset.search.indexOf(term) !== -1;
      card.hidden = !match;
      if (match) shown += 1;
    });
    none.hidden = shown !== 0;
  });
})();
