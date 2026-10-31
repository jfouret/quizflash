// Deck detail: fill the edit-card dialog from the card API, then submit the form.
(function () {
  var dialog = document.getElementById('edit-card');
  var form = document.getElementById('edit-card-form');
  if (!dialog || !form) return;

  var csrf = document.querySelector('meta[name="csrf-token"]');
  var fields = {
    question: document.getElementById('edit-question'),
    answer: document.getElementById('edit-answer'),
    details: document.getElementById('edit-details'),
    context: document.getElementById('edit-context'),
    expected: document.getElementById('edit-expected-time'),
    tags: document.getElementById('edit-tags')
  };

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-edit-card]');
    if (!button) return;
    var id = button.dataset.editCard;
    var headers = csrf ? {'X-CSRF-Token': csrf.content} : {};
    fetch('/api/cards/' + encodeURIComponent(id), {credentials: 'same-origin', headers: headers})
      .then(function (response) {
        if (!response.ok) throw new Error('card not found');
        return response.json();
      })
      .then(function (card) {
        fields.question.value = card.question;
        fields.answer.value = card.answer;
        fields.details.value = card.details;
        fields.context.value = card.context;
        fields.expected.value = card.expected_time_s || '';
        fields.tags.value = card.tags.map(function (tag) { return tag.name; }).join(', ');
        form.setAttribute('action', '/cards/' + encodeURIComponent(id) + '/update');
        dialog.showModal();
      })
      .catch(function () {
        window.alert('Could not load this card.');
      });
  });
})();
