// Study view: card queue, answer judging, voice recording, teacher and TTS.
(function () {
  var config = document.getElementById('study-config').dataset;
  var flipEl = document.getElementById('flip');
  var deckOptionsEl = document.getElementById('deck-options');
  var statusEl = document.getElementById('status');
  var emptyEl = document.getElementById('empty');
  var studyEl = document.getElementById('study-card');
  var questionEl = document.getElementById('question');
  var cardStateEl = document.getElementById('card-state');
  var answerInput = document.getElementById('answer-input');
  var recordButton = document.getElementById('record');
  var recordingCounter = document.getElementById('recording-counter');
  var eqCanvas = document.getElementById('eq');
  var dueCountEl = document.getElementById('due-count');
  var textModeButton = document.getElementById('text-mode');
  var submitButton = document.getElementById('submit');
  var resultEl = document.getElementById('result');
  var feedbackEl = document.getElementById('feedback');
  var judgeInfoEl = document.getElementById('judge-info');
  var expectedAnswerEl = document.getElementById('expected-answer');
  var detailsWrap = document.getElementById('details-wrap');
  var detailsEl = document.getElementById('details');
  var teacherWrap = document.getElementById('teacher-wrap');
  var teacherExplanationEl = document.getElementById('teacher-explanation');
  var teacherInfoEl = document.getElementById('teacher-info');
  var teacherBtn = document.getElementById('teacher-btn');
  var teacherRegenBtn = document.getElementById('teacher-regen');
  var speakQuestionBtn = document.getElementById('speak-question');
  var speakExplanationBtn = document.getElementById('speak-explanation');
  var ratingControls = document.getElementById('rating-controls');
  var ratingInput = document.getElementById('rating');
  var correctInput = document.getElementById('correct');
  var finalRatingEl = document.getElementById('final-rating');
  var confirmButton = document.getElementById('confirm');
  var nextButton = document.getElementById('next');
  var startPanel = document.getElementById('start-panel');
  var startButton = document.getElementById('start-study');
  var tagPanelEl = document.getElementById('tag-panel');
  var tagOptionsEl = document.getElementById('tag-options');
  var cardTagsEl = document.getElementById('card-tags');
  var reviewTagsEl = document.getElementById('review-tags');
  var batchDoneEl = document.getElementById('batch-done');
  var batchContinueBtn = document.getElementById('batch-continue');
  var batchMenuBtn = document.getElementById('batch-menu');
  var voiceAutoJudge = config.voiceAutoJudge === 'true';
  var autoConfirm = config.autoConfirm === 'true';
  var teacherEnabled = config.teacherEnabled === 'true';
  var ttsEnabled = config.ttsEnabled === 'true';
  var voiceAllowed = config.voiceAllowed === 'true';
  var teacherVocal = config.teacherVocal === 'true';
  var batchEnabled = config.batchEnabled === 'true';
  var batchSize = Number(config.batchSize) || 5;
  var batchProgressEl = document.getElementById('batch-progress');

  // Focusing the answer field on a touch device raises the on-screen keyboard, which
  // then hides the card at every new question. Autofocus only where a mouse or
  // trackpad exists: a phone or tablet has no fine pointer at all, while a
  // touch-screen laptop still counts as a keyboard device.
  var touchOnly =
    window.matchMedia('(any-pointer: coarse)').matches &&
    !window.matchMedia('(any-pointer: fine)').matches;

  function focusAnswer() {
    if (!touchOnly) answerInput.focus();
  }

  var current = null;
  var startedAt = 0;
  var currentLogId = null;
  var inputMethod = 'text';
  var sttDuration = null;
  var audioDuration = null;
  var lastPayload = null;
  var pendingResult = null;
  var recorder = null;
  var recordingStream = null;
  var chunks = [];
  var recordingStartedAt = 0;
  var recordingTimer = null;
  var recordingRequest = 0;
  var startingRecording = false;
  var microphoneAuthorized = false;
  var audioCtx = null;
  var analyser = null;
  var eqData = null;
  var eqFrame = null;
  var dueCount = Number(dueCountEl.textContent) || 0;
  var batch = null;
  var reviewIndex = 0;
  var started = false;

  function formatDate(value) {
    var date = new Date(value);
    return Number.isNaN(date.getTime())
      ? value
      : date.toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'});
  }

  function setStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.className = isError ? 'error' : 'muted';
  }

  function selectedTags() {
    var tags = [];
    var inputs = document.querySelectorAll('input[name="study-tag"]');
    Array.prototype.forEach.call(inputs, function (input) {
      if (input.checked) tags.push(input.value);
    });
    return tags;
  }

  function selectedDecks() {
    var decks = [];
    var inputs = document.querySelectorAll('input[name="study-deck"]');
    Array.prototype.forEach.call(inputs, function (input) {
      if (input.checked) decks.push(input.value);
    });
    return decks;
  }

  function tagCheckbox(tag, checked) {
    return '<label class="tag-check"><input type="checkbox" name="study-tag" value="' +
      escapeHtml(tag) + '"' + (checked ? ' checked' : '') + '> <span class="tag">' +
      escapeHtml(tag) + '</span></label>';
  }

  async function refreshStudyTags() {
    var preserved = selectedTags();
    var tags;
    try {
      tags = await api('/api/study/tags' + studyQuery());
    } catch (error) {
      return;
    }
    tagOptionsEl.innerHTML = tags.map(function (tag) {
      return tagCheckbox(tag, preserved.indexOf(tag) !== -1);
    }).join('');
    tagPanelEl.hidden = !tags.length;
  }

  async function refreshDueCount() {
    try {
      var data = await api('/api/study/due' + studyQuery());
    } catch (error) {
      return;
    }
    dueCount = data.count;
    dueCountEl.textContent = dueCount + ' card' + (dueCount === 1 ? '' : 's') + ' due';
  }

  async function onFilterChange() {
    await refreshStudyTags();
    await refreshDueCount();
    if (!started) return;
    if (batchEnabled) void startBatch();
    else void loadNext();
  }

  function studyQuery(extra) {
    var params = [];
    selectedDecks().forEach(function (deck) {
      params.push('deck_id=' + encodeURIComponent(deck));
    });
    selectedTags().forEach(function (tag) { params.push('tag=' + encodeURIComponent(tag)); });
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        params.push(encodeURIComponent(key) + '=' + encodeURIComponent(extra[key]));
      });
    }
    return params.length ? '?' + params.join('&') : '';
  }

  function ratingScale() {
    var scale = current && current.grading_scale;
    if (!scale || !scale.max) return {max: 4, labels: {}};
    return scale;
  }

  function defaultLevel(scale) {
    return Math.round((scale || ratingScale()).max / 2);
  }

  function levelLabel(level) {
    var labels = ratingScale().labels || {};
    return labels[level] || labels[String(level)] || '';
  }

  function ratingText(level) {
    var label = levelLabel(level);
    return label ? level + ' (' + label + ')' : String(level);
  }

  function renderRatingOptions(scale) {
    var labels = (scale && scale.labels) || {};
    var html = '';
    for (var level = 0; level <= scale.max; level++) {
      var label = labels[level] || labels[String(level)] || '';
      html += '<option value="' + level + '">' + level + (label ? ' · ' + escapeHtml(label) : '') + '</option>';
    }
    ratingInput.innerHTML = html;
  }

  function renderTags(el, tags) {
    if (!el) return;
    if (!tags || !tags.length) {
      el.innerHTML = '';
      el.hidden = true;
      return;
    }
    el.innerHTML = tags.map(function (tag) {
      return '<span class="tag">' + escapeHtml(tag.name) + '</span>';
    }).join('');
    el.hidden = false;
  }

  function renderActiveTags() {
    var tags = current ? current.card.tags : [];
    renderTags(cardTagsEl, tags);
    renderTags(reviewTagsEl, tags);
  }

  function startSession() {
    started = true;
    startPanel.hidden = true;
    emptyEl.hidden = true;
    batchDoneEl.hidden = true;
    flipEl.hidden = false;
    if (batchEnabled) void startBatch();
    else void loadNext();
  }

  function setFlipped(on) {
    if (on) requestAnimationFrame(function () { requestAnimationFrame(function () { flipEl.classList.add('flipped'); }); });
    else flipEl.classList.remove('flipped');
  }

  var csrfToken = document.querySelector('meta[name="csrf-token"]').content;

  async function api(url, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {}, {'X-CSRF-Token': csrfToken});
    var response = await fetch(url, Object.assign({}, options, {headers: headers, credentials: 'same-origin'}));
    var data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed');
    }
    return data;
  }

  function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderInline(text) {
    var out = escapeHtml(text);
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return out;
  }

  // Minimal, escaping-first Markdown subset: headings, lists, code, bold, italic, links.
  function renderMarkdown(source) {
    if (!source) return '';
    var lines = String(source).replace(/\r\n/g, '\n').split('\n');
    var html = [];
    var list = null;
    var inCode = false;
    var code = [];

    function closeList() {
      if (list) { html.push('</' + list + '>'); list = null; }
    }

    lines.forEach(function (line) {
      if (/^\s*```/.test(line)) {
        if (inCode) {
          html.push('<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>');
          code = [];
          inCode = false;
        } else {
          closeList();
          inCode = true;
        }
        return;
      }
      if (inCode) { code.push(line); return; }

      var heading = line.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        closeList();
        var level = heading[1].length;
        html.push('<h' + level + '>' + renderInline(heading[2]) + '</h' + level + '>');
        return;
      }
      var ul = line.match(/^\s*[-*+]\s+(.*)$/);
      if (ul) {
        if (list !== 'ul') { closeList(); html.push('<ul>'); list = 'ul'; }
        html.push('<li>' + renderInline(ul[1]) + '</li>');
        return;
      }
      var ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ol) {
        if (list !== 'ol') { closeList(); html.push('<ol>'); list = 'ol'; }
        html.push('<li>' + renderInline(ol[1]) + '</li>');
        return;
      }
      if (!line.trim()) { closeList(); return; }
      closeList();
      html.push('<p>' + renderInline(line) + '</p>');
    });
    if (inCode) html.push('<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>');
    closeList();
    return html.join('');
  }

  function setTextMode() {
    inputMethod = 'text';
    sttDuration = null;
    audioDuration = null;
    setStatus('Text answer mode.');
  }

  function updateRecordingCounter() {
    var seconds = Math.floor((Date.now() - recordingStartedAt) / 1000);
    var minutes = Math.floor(seconds / 60);
    recordingCounter.textContent = minutes + ':' + String(seconds % 60).padStart(2, '0');
  }

  function stopRecordingCounter() {
    if (recordingTimer !== null) clearInterval(recordingTimer);
    recordingTimer = null;
    recordingCounter.hidden = true;
    recordingCounter.textContent = '0:00';
  }

  function stopEqualizer() {
    if (eqFrame !== null) cancelAnimationFrame(eqFrame);
    eqFrame = null;
    eqCanvas.hidden = true;
    document.body.classList.remove('recording');
    if (audioCtx) {
      void audioCtx.close();
      audioCtx = null;
      analyser = null;
      eqData = null;
    }
  }

  function startEqualizer(stream) {
    if (!window.AudioContext) return;
    stopEqualizer();
    audioCtx = new AudioContext();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    eqData = new Uint8Array(analyser.frequencyBinCount);
    eqCanvas.hidden = false;
    document.body.classList.add('recording');
    var ctx = eqCanvas.getContext('2d');
    function draw() {
      eqFrame = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(eqData);
      ctx.clearRect(0, 0, eqCanvas.width, eqCanvas.height);
      var barWidth = eqCanvas.width / eqData.length;
      for (var i = 0; i < eqData.length; i++) {
        var height = (eqData[i] / 255) * eqCanvas.height;
        // Resolved colour: the canvas inherits the accent from #eq's own style.
        ctx.fillStyle = getComputedStyle(eqCanvas).color || '#3b82f6';
        ctx.fillRect(i * barWidth, eqCanvas.height - height, barWidth - 1, height);
      }
    }
    draw();
  }

  function cancelRecording() {
    recordingRequest += 1;
    startingRecording = false;
    stopEqualizer();
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      if (recorder.state !== 'inactive') recorder.stop();
    }
    if (recordingStream) recordingStream.getTracks().forEach(function (track) { track.stop(); });
    recorder = null;
    recordingStream = null;
    chunks = [];
    stopRecordingCounter();
    recordButton.textContent = 'Record voice';
    recordButton.disabled = false;
  }

  var spokenAudio = null;

  function resetPanels() {
    cancelRecording();
    answerInput.blur();
    current = null;
    setFlipped(false);
    studyEl.hidden = true;
    emptyEl.hidden = true;
    resultEl.hidden = true;
    ratingControls.hidden = true;
    confirmButton.hidden = true;
    confirmButton.disabled = false;
    nextButton.hidden = true;
    nextButton.disabled = false;
    answerInput.disabled = false;
    answerInput.value = '';
    submitButton.disabled = false;
    submitButton.textContent = 'Submit answer';
    finalRatingEl.textContent = '';
    currentLogId = null;
    teacherWrap.hidden = true;
    teacherExplanationEl.textContent = '';
    teacherInfoEl.textContent = '';
    teacherBtn.disabled = false;
    teacherRegenBtn.disabled = false;
    speakQuestionBtn.disabled = false;
    speakExplanationBtn.disabled = false;
    if (spokenAudio) {
      spokenAudio.pause();
      spokenAudio = null;
    }
    pendingResult = null;
    lastPayload = null;
    setTextMode();
  }

  function maybeAutoRecord() {
    if (!microphoneAuthorized || !current || studyEl.hidden || !studyEl || recorder) return;
    if (batchEnabled && batch && batch.phase !== 'answer') return;
    if (!batchEnabled && pendingResult) return;
    void startRecording();
  }

  async function loadNext() {
    resetPanels();
    setStatus('Loading next card…');
    try {
      current = await api('/api/study/next' + studyQuery());
      if (!current) {
        emptyEl.hidden = false;
        startPanel.hidden = false;
        flipEl.hidden = true;
        started = false;
        setStatus('Queue empty.');
        return;
      }
      questionEl.textContent = current.card.question;
      cardStateEl.textContent = current.is_new ? 'New card' : 'Review · due ' + formatDate(current.due);
      renderActiveTags();
      studyEl.hidden = false;
      startedAt = Date.now();
      focusAnswer();
      setStatus('Timer started.');
      maybeAutoRecord();
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function makePayload() {
    return {
      card_id: current.card.id,
      answer_text: answerInput.value,
      input_method: inputMethod,
      response_time_ms: Date.now() - startedAt,
      stt_duration_ms: sttDuration,
      audio_duration_ms: audioDuration
    };
  }

  function showCardContext() {
    expectedAnswerEl.textContent = current.card.answer;
    detailsEl.textContent = current.card.details;
    detailsWrap.hidden = !current.card.details;
    renderRatingOptions(ratingScale());
    renderActiveTags();
    resultEl.hidden = false;
  }

  function showFeedback(result) {
    feedbackEl.innerHTML = result.feedback ? renderMarkdown(result.feedback) : '';
    feedbackEl.hidden = !result.feedback;
  }

  async function fetchExplanation() {
    if (!current) return;
    teacherBtn.disabled = true;
    teacherRegenBtn.disabled = true;
    setStatus('Teacher explaining…');
    try {
      var result = await api('/api/study/explain', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({card_id: current.card.id, log_id: currentLogId})
      });
      teacherExplanationEl.innerHTML = renderMarkdown(result.explanation);
      teacherInfoEl.textContent = 'Teacher: ' + result.model;
      setStatus('Teacher explanation ready.');
    } catch (error) {
      teacherExplanationEl.textContent = '';
      teacherInfoEl.textContent = error.message;
      setStatus(error.message, true);
    } finally {
      teacherBtn.disabled = false;
      teacherRegenBtn.disabled = false;
    }
  }

  function showTeacher() {
    teacherWrap.hidden = false;
    if (teacherEnabled) void fetchExplanation();
  }

  function stopSpoken() {
    if (spokenAudio) {
      spokenAudio.pause();
      spokenAudio = null;
    }
  }

  function appendBuffer(buffer, data) {
    return new Promise(function (resolve, reject) {
      function onEnd() { buffer.removeEventListener('error', onError); resolve(); }
      function onError() { buffer.removeEventListener('updateend', onEnd); reject(new Error('audio buffer error')); }
      buffer.addEventListener('updateend', onEnd, {once: true});
      buffer.addEventListener('error', onError, {once: true});
      try { buffer.appendBuffer(data); } catch (error) { onError(); }
    });
  }

  async function playBlob(response) {
    var blob = await response.blob();
    if (spokenAudio) spokenAudio.pause();
    spokenAudio = new Audio(URL.createObjectURL(blob));
    await spokenAudio.play();
  }

  // Start playback before the whole clip is generated, when the browser can stream it.
  async function playResponse(response) {
    var type = (response.headers.get('Content-Type') || 'audio/mpeg').split(';')[0].trim();
    if (spokenAudio) spokenAudio.pause();
    spokenAudio = null;
    if (!window.MediaSource || !window.MediaSource.isTypeSupported(type) || !response.body) {
      await playBlob(response);
      return;
    }
    var source = new MediaSource();
    var audio = new Audio(URL.createObjectURL(source));
    spokenAudio = audio;
    await new Promise(function (resolve) { source.addEventListener('sourceopen', resolve, {once: true}); });
    var buffer;
    try {
      buffer = source.addSourceBuffer(type);
    } catch (error) {
      stopSpoken();
      await playBlob(response);
      return;
    }
    var reader = response.body.getReader();
    var started = false;
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      await appendBuffer(buffer, chunk.value);
      if (!started) { started = true; void audio.play().catch(function () {}); }
    }
    try { source.endOfStream(); } catch (error) { /* source already closed */ }
    if (!started) await audio.play();
  }

  async function speak(endpoint, button) {
    if (!current || !ttsEnabled) return;
    button.disabled = true;
    setStatus('Synthesizing speech…');
    try {
      var response = await fetch(endpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
        credentials: 'same-origin',
        body: JSON.stringify({card_id: current.card.id})
      });
      if (!response.ok) {
        var data = await response.json();
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Speech synthesis failed');
      }
      await playResponse(response);
      setStatus('Playing.');
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function invalidateAssessment() {
    if (!pendingResult) return;
    pendingResult = null;
    setFlipped(false);
    resultEl.hidden = true;
    ratingControls.hidden = true;
    confirmButton.hidden = true;
    nextButton.hidden = true;
    finalRatingEl.textContent = '';
    submitButton.textContent = 'Judge corrected answer';
    setStatus('Answer changed. Judge again to continue.');
  }

  function showAssessment(result, isFallback) {
    pendingResult = result;
    studyEl.hidden = false;
    answerInput.disabled = false;
    submitButton.textContent = 'Correct & judge again';
    showCardContext();
    showFeedback(result);
    showTeacher();
    judgeInfoEl.textContent = result.judge_model ? 'Judge: ' + result.judge_model : 'Manual fallback required';
    ratingInput.value = result.rating != null ? String(result.rating) : String(defaultLevel(ratingScale()));
    correctInput.value = String(result.is_correct === null ? true : result.is_correct);
    var automatic = result.mode === 'ai_assess' && !isFallback;
    ratingControls.hidden = automatic;
    confirmButton.hidden = automatic;
    confirmButton.disabled = false;
    nextButton.hidden = !automatic;
    nextButton.disabled = false;
    nextButton.textContent = 'Save & next card';
    confirmButton.textContent = isFallback ? 'Save manual review' : 'Confirm review';
    confirmButton.onclick = function () { confirmAssessment(isFallback); };
    finalRatingEl.textContent = automatic
      ? 'AI rating ' + ratingText(result.rating) + ' · ' + (result.is_correct ? 'correct' : 'incorrect')
      : '';
    setStatus(
      isFallback
        ? 'Judge failed. Rate this answer manually.'
        : automatic
          ? 'AI assessed. Edit to correct, or save and continue.'
          : 'Confirm, override, or correct the answer and judge again.'
    );
    setFlipped(true);
    if (autoConfirm && !isFallback) void confirmAssessment(false, false);
  }

  function showReviewed(result) {
    pendingResult = null;
    currentLogId = result.log_id || null;
    studyEl.hidden = true;
    answerInput.disabled = true;
    showCardContext();
    showFeedback(result);
    showTeacher();
    judgeInfoEl.textContent = result.mode === 'self_fallback' ? 'Self fallback (judge failed)' : 'Judge: ' + result.judge_model;
    finalRatingEl.textContent = 'Saved rating ' + ratingText(result.rating) + ' · ' + (result.is_correct ? 'correct' : 'incorrect') + ' · next due ' + formatDate(result.due);
    ratingControls.hidden = true;
    confirmButton.hidden = true;
    nextButton.hidden = false;
    nextButton.disabled = false;
    nextButton.textContent = 'Next card';
    dueCount = Math.max(0, dueCount - 1);
    dueCountEl.textContent = dueCount + ' card' + (dueCount === 1 ? '' : 's') + ' due';
    setStatus('Review saved.', false);
    setFlipped(true);
  }

  async function submitAnswer() {
    if (!current) return;
    submitButton.disabled = true;
    recordButton.disabled = true;
    nextButton.disabled = true;
    lastPayload = Object.assign(makePayload(), {preview: true});
    setStatus('Judging answer…');
    try {
      var result = await api('/api/study/answer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(lastPayload)
      });
      if (result.status === 'fallback_required') showAssessment(result, true);
      else if (result.status === 'pending') showAssessment(result, false);
      else showReviewed(result);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      submitButton.disabled = false;
      recordButton.disabled = false;
      nextButton.disabled = false;
    }
  }

  async function confirmAssessment(isFallback, advance) {
    if (!pendingResult || !lastPayload) return;
    confirmButton.disabled = true;
    nextButton.disabled = true;
    var override = {
      rating: Number(ratingInput.value),
      is_correct: correctInput.value === 'true',
      judge_feedback: pendingResult.feedback,
      judge_model: pendingResult.judge_model || '',
      fallback_token: pendingResult.fallback_token || null,
      preview: false
    };
    var payload = Object.assign({}, lastPayload, override, isFallback ? {self_fallback: true} : {confirmed: true});
    try {
      var result = await api('/api/study/answer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      showReviewed(result);
      if (advance) await loadNext();
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      confirmButton.disabled = false;
      nextButton.disabled = false;
    }
  }

  async function nextCard() {
    if (pendingResult && pendingResult.mode === 'ai_assess') {
      await confirmAssessment(false, true);
    } else {
      await loadNext();
    }
  }

  // --- Batch mode ----------------------------------------------------------

  function updateBatchProgress() {
    if (!batchEnabled || !batch || !batch.records.length) {
      batchProgressEl.hidden = true;
      return;
    }
    var total = batch.records.length;
    var currentIdx = batch.phase === 'review' ? reviewIndex : batch.pos;
    var dots = '';
    for (var i = 0; i < total; i++) {
      var cls = i === currentIdx ? 'dot current' : (i < currentIdx ? 'dot done' : 'dot');
      dots += '<span class="' + cls + '"></span>';
    }
    var label = batch.phase === 'review'
      ? 'Review ' + (currentIdx + 1) + ' of ' + total
      : 'Card ' + (currentIdx + 1) + ' of ' + total;
    batchProgressEl.innerHTML = '<span class="batch-label">' + label + '</span>' + dots;
    batchProgressEl.hidden = false;
  }

  function prepareAnswerCard() {
    cancelRecording();
    answerInput.blur();
    stopSpoken();
    setFlipped(false);
    resultEl.hidden = true;
    answerInput.disabled = false;
    answerInput.value = '';
    submitButton.disabled = false;
    submitButton.textContent = 'Submit answer';
    finalRatingEl.textContent = '';
    currentLogId = null;
    teacherWrap.hidden = true;
    teacherExplanationEl.textContent = '';
    teacherInfoEl.textContent = '';
    ratingControls.hidden = true;
    confirmButton.hidden = true;
    nextButton.hidden = true;
    setTextMode();
  }

  function animateAdvance(callback) {
    studyEl.classList.remove('batch-in');
    studyEl.classList.add('batch-out');
    setTimeout(function () {
      studyEl.classList.remove('batch-out');
      callback();
      studyEl.classList.add('batch-in');
      setTimeout(function () { studyEl.classList.remove('batch-in'); }, 320);
    }, 170);
  }

  async function startBatch() {
    prepareAnswerCard();
    batch = {phase: 'answer', pos: 0, records: []};
    reviewIndex = 0;
    updateBatchProgress();
    setStatus('Loading batch…');
    try {
      var cards = await api('/api/study/batch' + studyQuery({size: batchSize}));
      if (!cards.length) {
        batchProgressEl.hidden = true;
        emptyEl.hidden = false;
        startPanel.hidden = false;
        batchDoneEl.hidden = true;
        flipEl.hidden = true;
        started = false;
        studyEl.hidden = true;
        setStatus('Queue empty.');
        return;
      }
      batch.records = cards.map(function (card) { return {card: card, status: 'unseen'}; });
      showBatchCard(0);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function showBatchCard(index) {
    prepareAnswerCard();
    batch.pos = index;
    current = batch.records[index].card;
    questionEl.textContent = current.card.question;
    cardStateEl.textContent = current.is_new ? 'New card' : 'Review · due ' + formatDate(current.due);
    renderActiveTags();
    studyEl.hidden = false;
    startedAt = Date.now();
    updateBatchProgress();
    setStatus('Card ' + (index + 1) + ' of ' + batch.records.length + '. Record or type your answer.');
    studyEl.classList.add('batch-in');
    setTimeout(function () { studyEl.classList.remove('batch-in'); }, 320);
    focusAnswer();
    maybeAutoRecord();
  }

  async function submitBatch() {
    var record = batch.records[batch.pos];
    if (!record || record.status !== 'unseen') return;
    record.payload = makePayload();
    record.status = 'processing';
    record.promise = processRecord(record);
    void record.promise;
    submitButton.disabled = true;
    recordButton.disabled = true;
    animateAdvance(advanceBatch);
  }

  async function submitBatchVoice(blob) {
    var record = batch.records[batch.pos];
    if (!record || record.status !== 'unseen') return;
    record.blob = blob;
    record.response_time_ms = Date.now() - startedAt;
    record.status = 'processing';
    record.promise = processRecord(record);
    void record.promise;
    submitButton.disabled = true;
    recordButton.disabled = true;
    animateAdvance(advanceBatch);
  }

  async function transcribePayload(record) {
    var form = new FormData();
    form.append('audio', record.blob, 'answer.webm');
    var result = await api('/api/study/transcribe', {method: 'POST', body: form});
    return {
      card_id: record.card.card.id,
      answer_text: result.text,
      input_method: 'voice',
      response_time_ms: record.response_time_ms || 0,
      stt_duration_ms: result.stt_duration_ms,
      audio_duration_ms: result.audio_duration_ms
    };
  }

  function advanceBatch() {
    var next = batch.pos + 1;
    if (next < batch.records.length) {
      showBatchCard(next);
    } else {
      enterReview();
    }
  }

  async function processRecord(record) {
    var payload = record.payload;
    if (!payload && record.blob) {
      try {
        payload = await transcribePayload(record);
        record.payload = payload;
      } catch (error) {
        record.error = error.message;
        record.status = 'error';
        return;
      }
    }
    try {
      var preview = await api('/api/study/answer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(Object.assign({}, payload, {preview: true}))
      });
      record.preview = preview;
      if (preview.status === 'fallback_required') {
        record.status = 'manual';
        record.manual = true;
        record.fallbackToken = preview.fallback_token;
        record.feedback = preview.feedback || 'Rate this answer manually.';
        return;
      }
      var saved = await api('/api/study/answer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(Object.assign({}, payload, {
          preview: false,
          confirmed: true,
          rating: preview.rating,
          is_correct: preview.is_correct,
          judge_feedback: preview.feedback || '',
          judge_model: preview.judge_model || ''
        }))
      });
      record.saved = saved;
      record.status = 'saved';
      dueCount = Math.max(0, dueCount - 1);
      dueCountEl.textContent = dueCount + ' card' + (dueCount === 1 ? '' : 's') + ' due';
    } catch (error) {
      record.error = error.message;
      record.status = 'error';
      return;
    }
    if (teacherEnabled) {
      try {
        var explained = await api('/api/study/explain', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            card_id: record.card.card.id,
            log_id: record.saved ? record.saved.log_id : null
          })
        });
        record.explanation = explained.explanation;
        record.teacherModel = explained.model;
      } catch (error) {
        record.explanationError = error.message;
      }
    }
    if (ttsEnabled && record.explanation) {
      await prefetchAudio(record);
    }
  }

  async function prefetchAudio(record) {
    try {
      var response = await fetch('/api/study/speak', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
        credentials: 'same-origin',
        body: JSON.stringify({text: record.explanation, vocal: teacherVocal})
      });
      if (!response.ok) return;
      var blob = await response.blob();
      if (record.audioUrl) URL.revokeObjectURL(record.audioUrl);
      record.audioUrl = URL.createObjectURL(blob);
    } catch (error) {
      // Audio prefetch is best effort; the review falls back to the next button.
    }
  }

  function enterReview() {
    batch.phase = 'review';
    reviewIndex = 0;
    cancelRecording();
    stopSpoken();
    answerInput.disabled = true;
    studyEl.hidden = true;
    setFlipped(true);
    showReviewCard(0);
  }

  async function showReviewCard(index) {
    reviewIndex = index;
    var record = batch.records[index];
    if (!record) {
      finishBatch();
      return;
    }
    current = record.card;
    stopSpoken();
    updateBatchProgress();
    setStatus('Reviewing card ' + (index + 1) + ' of ' + batch.records.length + '.');
    if (record.status === 'processing' || record.status === 'unseen') {
      expectedAnswerEl.textContent = record.card.card.answer;
      detailsEl.textContent = record.card.card.details;
      detailsWrap.hidden = !record.card.card.details;
      feedbackEl.innerHTML = '';
      feedbackEl.hidden = true;
      judgeInfoEl.textContent = 'Preparing…';
      teacherWrap.hidden = !teacherEnabled;
      teacherExplanationEl.textContent = 'Preparing explanation…';
      teacherInfoEl.textContent = '';
      ratingControls.hidden = true;
      confirmButton.hidden = true;
      nextButton.hidden = false;
      nextButton.disabled = true;
      nextButton.textContent = 'Next';
      finalRatingEl.textContent = '';
      resultEl.hidden = false;
      await record.promise;
    }
    renderReview(record);
  }

  function renderReviewJudgeInfo(record) {
    if (record.manual) {
      judgeInfoEl.textContent = 'Automatic judging failed; rate this answer manually.';
      return;
    }
    if (record.error) {
      judgeInfoEl.textContent = record.error;
      return;
    }
    var model =
      (record.saved && record.saved.judge_model) ||
      (record.preview && record.preview.judge_model) ||
      '';
    judgeInfoEl.textContent = model ? 'Judge: ' + model : '';
  }

  function renderReviewTeacher(record) {
    if (!teacherEnabled) {
      teacherWrap.hidden = true;
      return;
    }
    teacherWrap.hidden = false;
    if (record.explanation) teacherExplanationEl.innerHTML = renderMarkdown(record.explanation);
    else if (record.explanationError) teacherExplanationEl.textContent = record.explanationError;
    else teacherExplanationEl.textContent = '';
    teacherInfoEl.textContent = record.teacherModel ? 'Teacher: ' + record.teacherModel : '';
  }

  function showManualReview(record) {
    ratingControls.hidden = false;
    confirmButton.hidden = false;
    confirmButton.disabled = false;
    confirmButton.textContent = 'Save review';
    confirmButton.onclick = function () { void saveManual(record); };
    ratingInput.value = record.rating != null ? String(record.rating) : String(defaultLevel(ratingScale()));
    correctInput.value = 'true';
    finalRatingEl.textContent = '';
  }

  function renderReview(record) {
    expectedAnswerEl.textContent = record.card.card.answer;
    detailsEl.textContent = record.card.card.details;
    detailsWrap.hidden = !record.card.card.details;
    currentLogId = record.saved ? record.saved.log_id : null;
    renderRatingOptions(ratingScale());
    renderActiveTags();
    var feedback = record.feedback || (record.saved ? record.saved.feedback : '');
    feedbackEl.innerHTML = feedback ? renderMarkdown(feedback) : '';
    feedbackEl.hidden = !feedback;
    resultEl.hidden = false;
    renderReviewJudgeInfo(record);
    renderReviewTeacher(record);
    nextButton.hidden = false;
    nextButton.disabled = false;
    nextButton.textContent = 'Next';
    setStatus(
      'Card ' + (reviewIndex + 1) + ' of ' + batch.records.length +
      '. Press Next (or Enter) to continue.'
    );
    if (record.manual) {
      showManualReview(record);
      return;
    }
    ratingControls.hidden = true;
    confirmButton.hidden = true;
    finalRatingEl.textContent = record.saved
      ? 'Rating ' + ratingText(record.saved.rating) + ' · ' + (record.saved.is_correct ? 'correct' : 'incorrect')
      : '';
    if (record.audioUrl) playReviewAudio(record.audioUrl);
  }

  function playReviewAudio(url) {
    stopSpoken();
    spokenAudio = new Audio(url);
    spokenAudio.play().catch(function () {
      // Autoplay may be blocked; the Next button still works.
    });
  }

  function advanceReview() {
    stopSpoken();
    var next = reviewIndex + 1;
    if (next < batch.records.length) {
      showReviewCard(next);
    } else {
      finishBatch();
    }
  }

  async function saveManual(record) {
    confirmButton.disabled = true;
    try {
      var saved = await api('/api/study/answer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(Object.assign({}, record.payload, {
          rating: Number(ratingInput.value),
          is_correct: correctInput.value === 'true',
          judge_feedback: record.feedback || '',
          judge_model: '',
          fallback_token: record.fallbackToken || null,
          preview: false,
          self_fallback: true
        }))
      });
      record.saved = saved;
      record.manual = false;
      currentLogId = saved.log_id || null;
      ratingControls.hidden = true;
      confirmButton.hidden = true;
      finalRatingEl.textContent = 'Saved rating ' + ratingText(saved.rating) + ' · ' + (saved.is_correct ? 'correct' : 'incorrect');
      setStatus('Review saved.');
    } catch (error) {
      setStatus(error.message, true);
      confirmButton.disabled = false;
    }
  }

  function finishBatch() {
    stopSpoken();
    batchProgressEl.hidden = true;
    studyEl.hidden = true;
    resultEl.hidden = true;
    flipEl.hidden = true;
    batchDoneEl.hidden = false;
    setStatus('Batch complete.');
  }

  function continueBatch() {
    batchDoneEl.hidden = true;
    flipEl.hidden = false;
    void startBatch();
  }

  function backToMenu() {
    stopSpoken();
    batchDoneEl.hidden = true;
    emptyEl.hidden = true;
    flipEl.hidden = true;
    studyEl.hidden = true;
    resultEl.hidden = true;
    started = false;
    startPanel.hidden = false;
    setStatus('Choose one or more decks and tags, then press Start.');
  }

  async function submitCurrent() {
    // Drop focus with the answer: the keyboard must not cover the result on a phone,
    // and the result shortcuts (Enter, digits) ignore keys typed into a field.
    answerInput.blur();
    if (batchEnabled && batch && batch.phase === 'answer') {
      await submitBatch();
      return;
    }
    await submitAnswer();
  }

  async function transcribeAudio(blob) {
    var form = new FormData();
    form.append('audio', blob, 'answer.webm');
    submitButton.disabled = true;
    recordButton.disabled = true;
    setStatus('Transcribing audio…');
    try {
      var result = await api('/api/study/transcribe', {method: 'POST', body: form});
      invalidateAssessment();
      answerInput.value = result.text;
      inputMethod = 'voice';
      sttDuration = result.stt_duration_ms;
      audioDuration = result.audio_duration_ms;
      if (voiceAutoJudge) {
        await submitCurrent();
      } else {
        setStatus('Transcript ready. Edit it if needed, then submit.');
        focusAnswer();
      }
    } catch (error) {
      setTextMode();
      setStatus(error.message + '. You can still answer with text.', true);
    } finally {
      submitButton.disabled = false;
      recordButton.disabled = false;
    }
  }

  async function startRecording() {
    if (startingRecording || recorder || !current || studyEl.hidden) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      setStatus('Voice recording is unsupported in this browser. Use text.', true);
      return;
    }
    invalidateAssessment();
    var requestId = ++recordingRequest;
    startingRecording = true;
    recordButton.disabled = true;
    try {
      var stream = await navigator.mediaDevices.getUserMedia({audio: true});
      if (requestId !== recordingRequest || !current || studyEl.hidden) {
        stream.getTracks().forEach(function (track) { track.stop(); });
        return;
      }
      microphoneAuthorized = true;
      chunks = [];
      recordingStream = stream;
      startEqualizer(stream);
      var activeRecorder = new MediaRecorder(stream);
      recorder = activeRecorder;
      activeRecorder.ondataavailable = function (event) { if (event.data.size) chunks.push(event.data); };
      activeRecorder.onstop = function () {
        stream.getTracks().forEach(function (track) { track.stop(); });
        stopEqualizer();
        if (requestId !== recordingRequest) return;
        var blob = new Blob(chunks, {type: activeRecorder.mimeType || 'audio/webm'});
        recorder = null;
        recordingStream = null;
        chunks = [];
        stopRecordingCounter();
        recordButton.textContent = 'Record voice';
        if (batchEnabled && batch && batch.phase === 'answer' && voiceAutoJudge) {
          void submitBatchVoice(blob);
        } else {
          void transcribeAudio(blob);
        }
      };
      activeRecorder.start();
      recordingStartedAt = Date.now();
      updateRecordingCounter();
      recordingCounter.hidden = false;
      recordingTimer = setInterval(updateRecordingCounter, 1000);
      recordButton.textContent = 'Stop recording';
      setStatus('Recording…');
    } catch (error) {
      if (requestId === recordingRequest) cancelRecording();
      microphoneAuthorized = false;
      setStatus('Microphone unavailable: ' + error.message, true);
    } finally {
      if (requestId === recordingRequest) {
        startingRecording = false;
        recordButton.disabled = false;
      }
    }
  }

  function toggleRecording() {
    if (recorder && recorder.state === 'recording') {
      recordButton.disabled = true;
      recorder.stop();
      return;
    }
    void startRecording();
  }

  async function watchMicrophonePermission() {
    if (!voiceAllowed || !navigator.permissions || !navigator.mediaDevices) return;
    try {
      var permission = await navigator.permissions.query({name: 'microphone'});
      microphoneAuthorized = permission.state === 'granted';
      permission.onchange = function () {
        microphoneAuthorized = permission.state === 'granted';
        maybeAutoRecord();
      };
      maybeAutoRecord();
    } catch {
      // Permission queries are unsupported on some browsers; the record button still works.
    }
  }

  function inReviewPhase() {
    return batchEnabled && batch && batch.phase === 'review';
  }

  function primaryAction() {
    if (!nextButton.hidden) {
      if (inReviewPhase()) advanceReview();
      else void nextCard();
    } else if (!studyEl.hidden && !submitButton.disabled) {
      void submitCurrent();
    }
  }

  function shortcutAction(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      primaryAction();
    } else if (/^[0-9]$/.test(event.key) && !ratingControls.hidden) {
      var level = Number(event.key);
      if (level <= ratingScale().max) ratingInput.value = String(level);
    } else if (event.key === 'n' && !nextButton.hidden) {
      if (inReviewPhase()) advanceReview();
      else void nextCard();
    }
  }

  function onKeydown(event) {
    if (event.key === 'Enter' && recorder && recorder.state === 'recording') {
      event.preventDefault();
      toggleRecording();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && event.target === answerInput) {
      event.preventDefault();
      void submitCurrent();
      return;
    }
    var tag = event.target && event.target.tagName;
    var typing =
      event.target === answerInput || tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA';
    if (typing || event.ctrlKey || event.metaKey || event.altKey) return;
    shortcutAction(event);
  }

  deckOptionsEl.addEventListener('change', function () { void onFilterChange(); });
  tagOptionsEl.addEventListener('change', function () { void refreshDueCount(); });
  submitButton.addEventListener('click', function () { void submitCurrent(); });
  teacherBtn.addEventListener('click', fetchExplanation);
  teacherRegenBtn.addEventListener('click', fetchExplanation);
  speakQuestionBtn.addEventListener('click', function () { void speak('/api/study/speak-question', speakQuestionBtn); });
  speakExplanationBtn.addEventListener('click', function () { void speak('/api/study/speak-explanation', speakExplanationBtn); });
  recordButton.addEventListener('click', toggleRecording);
  textModeButton.addEventListener('click', setTextMode);
  nextButton.addEventListener('click', function () {
    if (inReviewPhase()) advanceReview();
    else void nextCard();
  });
  answerInput.addEventListener('input', invalidateAssessment);
  document.addEventListener('keydown', onKeydown);
  startButton.addEventListener('click', startSession);
  batchContinueBtn.addEventListener('click', continueBatch);
  batchMenuBtn.addEventListener('click', backToMenu);
  void watchMicrophonePermission();
})();
