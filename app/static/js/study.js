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
  var eqFrameEl = document.getElementById('eq-frame');
  var pauseRecordBtn = document.getElementById('pause-record');
  var speechBar = document.getElementById('speech-bar');
  var speechEqCanvas = document.getElementById('speech-eq');
  var pauseSpeechBtn = document.getElementById('pause-speech');
  var stopSpeechBtn = document.getElementById('stop-speech');
  var dueCountEl = document.getElementById('due-count');
  var textModeButton = document.getElementById('text-mode');
  var submitButton = document.getElementById('submit');
  var resultEl = document.getElementById('result');
  var feedbackEl = document.getElementById('feedback');
  var judgeInfoEl = document.getElementById('judge-info');
  var expectedAnswerEl = document.getElementById('expected-answer');
  var yourAnswerWrap = document.getElementById('your-answer-wrap');
  var yourAnswerEl = document.getElementById('your-answer');
  var detailsWrap = document.getElementById('details-wrap');
  var detailsEl = document.getElementById('details');
  var teacherWrap = document.getElementById('teacher-wrap');
  var teacherExplanationEl = document.getElementById('teacher-explanation');
  var teacherInfoEl = document.getElementById('teacher-info');
  var teacherBtn = document.getElementById('teacher-btn');
  var teacherRegenBtn = document.getElementById('teacher-regen');
  var speakQuestionBtn = document.getElementById('speak-question');
  var speakReviewQuestionBtn = document.getElementById('speak-review-question');
  var speakExplanationBtn = document.getElementById('speak-explanation');
  var ratingControls = document.getElementById('rating-controls');
  var ratingInput = document.getElementById('rating');
  var correctInput = document.getElementById('correct');
  var finalRatingEl = document.getElementById('final-rating');
  var retryRecordBtn = document.getElementById('retry-record');
  var confirmButton = document.getElementById('confirm');
  var nextButton = document.getElementById('next');
  var startPanel = document.getElementById('start-panel');
  var startButton = document.getElementById('start-study');
  var micAuthorizeBtn = document.getElementById('mic-authorize');
  var micTestBtn = document.getElementById('mic-test');
  var micStateEl = document.getElementById('mic-state');
  var micEqFrameEl = document.getElementById('mic-eq-frame');
  var micEqCanvas = document.getElementById('mic-eq');
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
  var autoSpeak = config.autoSpeak === 'true';
  var batchEnabled = config.batchEnabled === 'true';
  var batchSize = Number(config.batchSize) || 5;
  var batchProgressEl = document.getElementById('batch-progress');
  var autoSpeakBtn = document.getElementById('auto-speak');
  var reviewQuestionEl = document.getElementById('review-question');

  // Autofocus is for whoever types on a physical keyboard. On a touch device the
  // focus call raises the on-screen keyboard, which then hides the question at every
  // card, so it is skipped there. The media query only gives the starting guess: a
  // pen counts as a fine pointer on some devices, so the real input in use decides.
  var touchInput = window.matchMedia('(any-pointer: coarse)').matches;
  document.addEventListener(
    'pointerdown',
    function (event) {
      if (event.pointerType === 'mouse') touchInput = false;
      else if (event.pointerType === 'touch' || event.pointerType === 'pen') touchInput = true;
    },
    true
  );

  function focusAnswer() {
    if (!touchInput) answerInput.focus();
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
  var eqSilence = null;
  var eqFrame = null;
  var speechEqFrame = null;
  var speechReader = null;
  var recordingPaused = false;
  var recordingElapsed = 0;
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
    // Ask for the microphone before the first card, so the automatic flow works.
    void prepareMicrophone().then(function () {
      if (batchEnabled) void startBatch();
      else void loadNext();
    });
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
    // The interrupt for the automatic voice flow: drop the recording in progress
    // instead of letting it be transcribed and submitted on its own.
    var wasRecording = Boolean(recorder) || startingRecording;
    cancelRecording();
    inputMethod = 'text';
    sttDuration = null;
    audioDuration = null;
    setStatus(wasRecording ? 'Recording interrupted. Type your answer.' : 'Text answer mode.');
  }

  function recordedMs() {
    return recordingElapsed + (recordingPaused ? 0 : Date.now() - recordingStartedAt);
  }

  function updateRecordingCounter() {
    var seconds = Math.floor(recordedMs() / 1000);
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
    eqFrameEl.hidden = true;
    eqFrameEl.classList.remove('paused');
    recordingPaused = false;
    document.body.classList.remove('recording');
    if (audioCtx) {
      void audioCtx.close();
      audioCtx = null;
      analyser = null;
      eqData = null;
    }
  }

  // Bars mirrored around a centre axis: the frame draws the border, this draws the sound.
  function drawEqualizer(canvas, data) {
    var ctx = canvas.getContext('2d');
    var width = canvas.width;
    var height = canvas.height;
    var middle = height / 2;
    // Resolved colour: the canvas inherits the accent from .eq-frame's own style.
    ctx.fillStyle = getComputedStyle(canvas).color || '#3b82f6';
    ctx.clearRect(0, 0, width, height);
    var barWidth = width / data.length;
    for (var i = 0; i < data.length; i++) {
      var half = Math.max(1, (data[i] / 255) * (middle - 1));
      ctx.fillRect(i * barWidth, middle - half, Math.max(1, barWidth - 1.5), half * 2);
    }
    ctx.globalAlpha = 0.35;
    ctx.fillRect(0, middle - 0.5, width, 1);
    ctx.globalAlpha = 1;
  }

  function startEqualizer(stream) {
    if (!window.AudioContext) return;
    stopEqualizer();
    audioCtx = new AudioContext();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    eqData = new Uint8Array(analyser.frequencyBinCount);
    eqSilence = new Uint8Array(analyser.frequencyBinCount);
    eqFrameEl.hidden = false;
    document.body.classList.add('recording');
    function draw() {
      eqFrame = requestAnimationFrame(draw);
      if (recordingPaused) {
        drawEqualizer(eqCanvas, eqSilence);
        return;
      }
      analyser.getByteFrequencyData(eqData);
      drawEqualizer(eqCanvas, eqData);
    }
    draw();
  }

  function cancelRecording() {
    recordingRequest += 1;
    startingRecording = false;
    stopEqualizer();
    allowSleep();
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
    recordButton.disabled = false;
    pauseRecordBtn.hidden = true;
    recordingPaused = false;
    setRecordingControls();
  }

  var spokenAudio = null;
  // The control that started the clip, so its icon returns to Play when it ends.
  var speakingButton = null;
  // A stream fallback URL is the only one this script creates and may revoke.
  var playedBlobUrl = '';

  function resetPanels() {
    cancelRecording();
    answerInput.blur();
    inputMethod = 'text';
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
    retryRecordBtn.hidden = true;
    answerInput.disabled = false;
    answerInput.value = '';
    submitButton.disabled = false;
    submitButton.textContent = 'Submit answer';
    finalRatingEl.textContent = '';
    currentLogId = null;
    renderYourAnswer('', null);
    teacherWrap.hidden = true;
    teacherExplanationEl.textContent = '';
    teacherInfoEl.textContent = '';
    teacherBtn.disabled = false;
    teacherRegenBtn.disabled = false;
    speakQuestionBtn.disabled = false;
    speakReviewQuestionBtn.disabled = false;
    speakExplanationBtn.disabled = false;
    stopSpoken();
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

  // --- Spoken questions, microphone and screen awake -------------------------

  var wakeLock = null;

  async function keepAwake() {
    if (wakeLock || !navigator.wakeLock || document.visibilityState !== 'visible') return;
    try {
      var lock = await navigator.wakeLock.request('screen');
      lock.addEventListener('release', function () { if (wakeLock === lock) wakeLock = null; });
      wakeLock = lock;
    } catch (error) {
      wakeLock = null; // Refused (low battery and the like): the session still works.
    }
  }

  function allowSleep() {
    if (!wakeLock) return;
    var lock = wakeLock;
    wakeLock = null;
    void lock.release().catch(function () {});
  }

  // One place decides what a control shows: the glyph and its label follow the state.
  // A button carries data-icon, data-active-icon, data-label and data-active-label.
  function setIcon(button, name) {
    var use = button.querySelector('use');
    if (!use) return;
    use.setAttribute('href', use.getAttribute('href').split('#')[0] + '#' + name);
  }

  function setControlState(button, active) {
    if (!button) return;
    setIcon(button, (active ? button.dataset.activeIcon : button.dataset.icon) || 'play');
    var label = active ? button.dataset.activeLabel : button.dataset.label;
    if (!label) return;
    button.setAttribute('aria-label', label);
    button.title = label;
  }

  function setRecordingControls() {
    // The mic becomes a stop square while the recorder runs, then turns back.
    setControlState(recordButton, Boolean(recorder));
    setControlState(pauseRecordBtn, recordingPaused);
  }

  function toggleRecordPause() {
    if (!recorder || recorder.state === 'inactive') return;
    if (recordingPaused) {
      recorder.resume();
      recordingPaused = false;
      recordingStartedAt = Date.now();
    } else {
      recorder.pause();
      recordingElapsed += Date.now() - recordingStartedAt;
      recordingPaused = true;
    }
    eqFrameEl.classList.toggle('paused', recordingPaused);
    setRecordingControls();
    updateRecordingCounter();
    setStatus(recordingPaused ? 'Recording paused.' : 'Recording…', false);
  }

  function setAutoSpeakButton() {
    autoSpeakBtn.textContent = 'Read questions aloud: ' + (autoSpeak ? 'on' : 'off');
    autoSpeakBtn.setAttribute('aria-pressed', autoSpeak ? 'true' : 'false');
  }

  async function toggleAutoSpeak() {
    autoSpeak = !autoSpeak;
    setAutoSpeakButton();
    try {
      await api('/api/settings', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({auto_speak_questions: autoSpeak})
      });
    } catch (error) {
      setStatus(error.message, true);
    }
    if (autoSpeak && current && !studyEl.hidden) void speakCurrentQuestion();
  }

  function batchRecord() {
    if (batchEnabled && batch && batch.phase === 'answer') return batch.records[batch.pos] || null;
    return null;
  }

  async function fetchQuestionAudio(cardId) {
    if (!cardId) return '';
    try {
      var response = await fetch('/api/study/speak-question', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
        credentials: 'same-origin',
        body: JSON.stringify({card_id: cardId})
      });
      if (!response.ok) return '';
      var blob = await response.blob();
      if (!blob.size) return '';
      return URL.createObjectURL(blob);
    } catch (error) {
      return '';
    }
  }

  function prefetchQuestion(record) {
    if (!record || record.questionAudioUrl || record.questionAudioPromise) return;
    record.questionAudioPromise = fetchQuestionAudio(record.card.card.id).then(function (url) {
      record.questionAudioUrl = url || '';
      return url;
    });
  }

  function prefetchUpcomingQuestions() {
    if (!autoSpeak || !ttsEnabled || !batchEnabled || !batch || batch.phase !== 'answer') return;
    for (var ahead = 1; ahead <= 2; ahead++) prefetchQuestion(batch.records[batch.pos + ahead]);
  }

  async function playSpoken(url, onEnded, button) {
    stopSpoken();
    var audio = new Audio(url);
    spokenAudio = audio;
    speakingButton = button || null;
    setControlState(speakingButton, true);
    void keepAwake();
    startSpeechEqualizer();
    audio.addEventListener('ended', function () {
      if (spokenAudio !== audio) return;
      stopSpoken();
      if (onEnded) onEnded();
    }, {once: true});
    try {
      await audio.play();
    } catch (error) {
      // Autoplay or the decoder can refuse; the card still works.
      if (spokenAudio === audio) {
        stopSpoken();
        if (onEnded) onEnded();
      }
    }
  }

  // The clip of a question, cached on the record (or on the card in single-card mode).
  async function questionAudio(record) {
    var holder = record || current;
    if (!holder) return '';
    var url = holder.questionAudioUrl;
    if (!url && holder.questionAudioPromise) url = await holder.questionAudioPromise;
    if (!url) {
      var cardId = holder.card.card ? holder.card.card.id : holder.card.id;
      url = await fetchQuestionAudio(cardId);
      if (url) holder.questionAudioUrl = url;
    }
    return url || '';
  }

  function speakCurrentQuestion() {
    if (!autoSpeak || !ttsEnabled || !current || studyEl.hidden) return Promise.resolve();
    prefetchUpcomingQuestions();
    return questionAudio(batchRecord()).then(function (url) {
      if (!url) return maybeAutoRecord();
      return playSpoken(url, maybeAutoRecord);
    });
  }

  // The record whose card the panel is showing: the answer phase, the review loop,
  // or none in the single-card flow, where `current` is the card.
  function shownRecord() {
    if (!batchEnabled || !batch) return null;
    if (batch.phase === 'answer') return batch.records[batch.pos] || null;
    if (batch.phase === 'review') return batch.records[reviewIndex] || null;
    return null;
  }

  function playingThrough(url, button) {
    // The clip already playing through this button toggles instead of restarting.
    return Boolean(spokenAudio) && (spokenAudio.src === url || speakingButton === button);
  }

  async function playQuestion(button) {
    if (!current || !ttsEnabled) return;
    var url = await questionAudio(shownRecord());
    if (!url) {
      setStatus('Question audio is unavailable.', true);
      return;
    }
    if (playingThrough(url, button)) {
      toggleSpeechPause();
      return;
    }
    setStatus('Playing.');
    await playSpoken(url, null, button);
  }

  function playExplanation(button) {
    if (!ttsEnabled) return Promise.resolve();
    var record = shownRecord();
    if (record && record.explanation) {
      if (record.audioUrl) {
        if (playingThrough(record.audioUrl, button)) {
          toggleSpeechPause();
          return Promise.resolve();
        }
        setStatus('Playing.');
        return playSpoken(record.audioUrl, null, button);
      }
      return speakShownText(record.explanation, button);
    }
    // Single-card flow: speak what the panel shows, never a second teacher call.
    var shown = teacherExplanationEl.textContent.trim();
    if (!shown) {
      setStatus('The explanation is not ready yet.', true);
      return Promise.resolve();
    }
    return speakShownText(shown, button);
  }

  // Synthesize a text that is already on screen, through /api/study/speak.
  async function speakShownText(text, button) {
    if (spokenAudio && speakingButton === button) {
      toggleSpeechPause();
      return;
    }
    button.disabled = true;
    setStatus('Synthesizing speech…');
    try {
      var response = await fetch('/api/study/speak', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
        credentials: 'same-origin',
        body: JSON.stringify({text: text, vocal: teacherVocal})
      });
      if (!response.ok) {
        var data = await response.json();
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Speech synthesis failed');
      }
      await playResponse(response, button);
      setStatus('Playing.');
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function beginAnswer() {
    // With spoken questions the recording waits for the clip to end, so it does
    // not record the question itself.
    if (autoSpeak && ttsEnabled) {
      void speakCurrentQuestion();
      return;
    }
    maybeAutoRecord();
  }

  async function prepareMicrophone() {
    if (!voiceAllowed || microphoneAuthorized || !navigator.mediaDevices) return;
    try {
      var stream = await navigator.mediaDevices.getUserMedia({audio: true});
      stream.getTracks().forEach(function (track) { track.stop(); });
      microphoneAuthorized = true;
    } catch (error) {
      setStatus('Microphone unavailable: ' + error.message + '. Answer with text.', true);
    }
  }

  // --- Microphone setup, before the session ---------------------------------

  var micAudioCtx = null;
  var micMeterFrame = null;
  var micTestRecorder = null;
  var micTestTimer = null;

  function setMicState(message, isError) {
    micStateEl.textContent = message;
    micStateEl.className = isError ? 'error' : 'muted';
  }

  function refreshMicState() {
    micAuthorizeBtn.hidden = microphoneAuthorized;
    micTestBtn.hidden = !microphoneAuthorized;
    if (microphoneAuthorized) setMicState('Microphone ready.');
  }

  async function authorizeMicrophone() {
    if (!navigator.mediaDevices) {
      setMicState('This browser cannot record audio.', true);
      return;
    }
    micAuthorizeBtn.disabled = true;
    try {
      var stream = await navigator.mediaDevices.getUserMedia({audio: true});
      stream.getTracks().forEach(function (track) { track.stop(); });
      microphoneAuthorized = true;
      refreshMicState();
    } catch (error) {
      setMicState('Microphone unavailable: ' + error.message + '. You can still type.', true);
    } finally {
      micAuthorizeBtn.disabled = false;
    }
  }

  function stopMicMeter() {
    if (micMeterFrame !== null) cancelAnimationFrame(micMeterFrame);
    micMeterFrame = null;
    micEqFrameEl.hidden = true;
    if (micAudioCtx) {
      void micAudioCtx.close();
      micAudioCtx = null;
    }
  }

  function startMicMeter(stream) {
    if (!window.AudioContext) return;
    stopMicMeter();
    micAudioCtx = new AudioContext();
    var analyser = micAudioCtx.createAnalyser();
    analyser.fftSize = 64;
    micAudioCtx.createMediaStreamSource(stream).connect(analyser);
    var data = new Uint8Array(analyser.frequencyBinCount);
    micEqFrameEl.hidden = false;
    function draw() {
      micMeterFrame = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(data);
      drawEqualizer(micEqCanvas, data);
    }
    draw();
  }

  // A three-second round trip: record, then play it back, so the user hears the
  // microphone themselves before the session relies on it.
  async function testMicrophone() {
    if (micTestRecorder || !navigator.mediaDevices || !window.MediaRecorder) return;
    micTestBtn.disabled = true;
    try {
      var stream = await navigator.mediaDevices.getUserMedia({audio: true});
      microphoneAuthorized = true;
      refreshMicState();
      var recorder = new MediaRecorder(stream);
      micTestRecorder = recorder;
      var chunks = [];
      recorder.ondataavailable = function (event) {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (track) { track.stop(); });
        stopMicMeter();
        micTestRecorder = null;
        micTestBtn.disabled = false;
        setMicState('Playing the test back…');
        var url = URL.createObjectURL(new Blob(chunks, {type: recorder.mimeType || 'audio/webm'}));
        var audio = new Audio(url);
        audio.addEventListener('ended', function () {
          URL.revokeObjectURL(url);
          setMicState('Microphone ready. The test above was your own recording.');
        }, {once: true});
        void audio.play().catch(function () {
          URL.revokeObjectURL(url);
          setMicState('Microphone ready, but playback was blocked.');
        });
      };
      recorder.start();
      startMicMeter(stream);
      setMicState('Recording three seconds…');
      micTestTimer = setTimeout(function () {
        if (micTestRecorder) micTestRecorder.stop();
      }, 3000);
    } catch (error) {
      setMicState('Microphone unavailable: ' + error.message, true);
      micTestBtn.disabled = false;
    }
  }

  // The microphone scope ends with the answer phase: the review does not record,
  // and every track is stopped when the batch leaves the answering loop.
  function releaseMicrophone() {
    cancelRecording();
    if (micTestTimer !== null) {
      clearTimeout(micTestTimer);
      micTestTimer = null;
    }
    if (micTestRecorder) {
      micTestRecorder.onstop = null;
      if (micTestRecorder.state !== 'inactive') micTestRecorder.stop();
      micTestRecorder = null;
    }
    stopMicMeter();
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
      beginAnswer();
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

  function renderYourAnswer(text, isCorrect) {
    var answer = text || '';
    yourAnswerWrap.hidden = !answer;
    yourAnswerEl.textContent = answer;
    // Green when the judgement says correct, red when it says wrong, neutral
    // while no judgement exists yet.
    yourAnswerEl.className = isCorrect === null
      ? 'pre answer-box'
      : isCorrect ? 'pre answer-box' : 'pre answer-box wrong';
  }

  function answerText(payload) {
    return payload ? payload.answer_text : '';
  }

  function showCardContext() {
    reviewQuestionEl.textContent = current.card.question;
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

  // A stand-in for a spectrum: the clip cannot be routed through Web Audio
  // without risking silent playback, so the bars show that sound is running.
  function speechLevelData() {
    var bars = 20;
    var data = new Uint8Array(bars);
    if (!spokenAudio || spokenAudio.paused) return data;
    var t = Date.now() / 240;
    for (var i = 0; i < bars; i++) {
      var wave = Math.sin(t + i * 0.55) * 0.5 + 0.5;
      var swell = Math.sin(t / 3 + i * 0.2) * 0.5 + 0.5;
      data[i] = Math.round(40 + wave * 90 + swell * 70);
    }
    return data;
  }

  function startSpeechEqualizer() {
    stopSpeechEqualizer();
    speechBar.hidden = false;
    function draw() {
      speechEqFrame = requestAnimationFrame(draw);
      drawEqualizer(speechEqCanvas, speechLevelData());
    }
    draw();
  }

  function stopSpeechEqualizer() {
    if (speechEqFrame !== null) cancelAnimationFrame(speechEqFrame);
    speechEqFrame = null;
    setControlState(pauseSpeechBtn, false);
    speechBar.hidden = true;
  }

  function toggleSpeechPause() {
    if (!spokenAudio) return;
    if (spokenAudio.paused) void spokenAudio.play().catch(function () {});
    else spokenAudio.pause();
    setControlState(speakingButton, !spokenAudio.paused);
    setControlState(pauseSpeechBtn, !spokenAudio.paused);
    setStatus(spokenAudio.paused ? 'Paused.' : 'Playing.', false);
  }

  function stopSpoken() {
    if (spokenAudio) {
      spokenAudio.pause();
      spokenAudio = null;
    }
    if (speechReader) {
      void speechReader.cancel().catch(function () {});
      speechReader = null;
    }
    // Never revoke here: the URL belongs to the record that holds it. Revoking a
    // prefetched question clip would make a later replay silent, and a browser may
    // hand the freed URL to another clip, so the question could play the answer.
    setControlState(speakingButton, false);
    speakingButton = null;
    stopSpeechEqualizer();
    allowSleep();
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

  async function playBlob(response, button) {
    var blob = await response.blob();
    if (spokenAudio) spokenAudio.pause();
    if (playedBlobUrl) URL.revokeObjectURL(playedBlobUrl);
    playedBlobUrl = URL.createObjectURL(blob);
    spokenAudio = new Audio(playedBlobUrl);
    speakingButton = button || null;
    setControlState(speakingButton, true);
    await spokenAudio.play();
  }

  // Start playback before the whole clip is generated, when the browser can stream it.
  async function playResponse(response, button) {
    var type = (response.headers.get('Content-Type') || 'audio/mpeg').split(';')[0].trim();
    stopSpoken();
    if (!window.MediaSource || !window.MediaSource.isTypeSupported(type) || !response.body) {
      await playBlob(response, button);
      return;
    }
    var source = new MediaSource();
    var audio = new Audio(URL.createObjectURL(source));
    spokenAudio = audio;
    speakingButton = button || null;
    setControlState(speakingButton, true);
    startSpeechEqualizer();
    audio.addEventListener('ended', function () {
      if (spokenAudio === audio) stopSpoken();
    }, {once: true});
    await new Promise(function (resolve) { source.addEventListener('sourceopen', resolve, {once: true}); });
    var buffer;
    try {
      buffer = source.addSourceBuffer(type);
    } catch (error) {
      stopSpoken();
      await playBlob(response, button);
      return;
    }
    // Held on the script so Stop can cancel the download as well as the sound.
    speechReader = response.body.getReader();
    var started = false;
    while (true) {
      var chunk = await speechReader.read();
      if (chunk.done) break;
      await appendBuffer(buffer, chunk.value);
      if (!started) { started = true; void audio.play().catch(function () {}); }
    }
    try { source.endOfStream(); } catch (error) { /* source already closed */ }
    speechReader = null;
    if (!started) await audio.play();
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
    renderYourAnswer(answerText(lastPayload), isFallback ? null : result.is_correct);
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
    // The answer phase of this card is over: the review needs no microphone.
    releaseMicrophone();
    studyEl.hidden = true;
    answerInput.disabled = true;
    showCardContext();
    renderYourAnswer(answerText(lastPayload), result.is_correct);
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
    inputMethod = 'text';
    stopSpoken();
    setFlipped(false);
    resultEl.hidden = true;
    answerInput.disabled = false;
    answerInput.value = '';
    submitButton.disabled = false;
    submitButton.textContent = 'Submit answer';
    finalRatingEl.textContent = '';
    currentLogId = null;
    renderYourAnswer('', null);
    teacherWrap.hidden = true;
    teacherExplanationEl.textContent = '';
    teacherInfoEl.textContent = '';
    ratingControls.hidden = true;
    confirmButton.hidden = true;
    nextButton.hidden = true;
    retryRecordBtn.hidden = true;
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
    beginAnswer();
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
      if (!response.ok) {
        record.audioUnavailable = true;
        return;
      }
      var blob = await response.blob();
      if (!blob.size) {
        record.audioUnavailable = true;
        return;
      }
      if (record.audioUrl) URL.revokeObjectURL(record.audioUrl);
      record.audioUrl = URL.createObjectURL(blob);
    } catch (error) {
      record.audioUnavailable = true;
    }
  }

  function enterReview() {
    batch.phase = 'review';
    reviewIndex = 0;
    releaseMicrophone();
    stopSpoken();
    answerInput.disabled = true;
    studyEl.hidden = true;
    setFlipped(true);
    showReviewCard(0);
  }

  function showPendingReview(record, index) {
    currentLogId = null;
    reviewQuestionEl.textContent = record.card.card.question;
    renderYourAnswer(answerText(record.payload), null);
    expectedAnswerEl.textContent = record.card.card.answer;
    detailsEl.textContent = record.card.card.details;
    detailsWrap.hidden = !record.card.card.details;
    feedbackEl.innerHTML = '';
    feedbackEl.hidden = true;
    judgeInfoEl.textContent = 'Preparing…';
    teacherWrap.hidden = !teacherEnabled;
    teacherExplanationEl.textContent = teacherEnabled ? 'Preparing explanation…' : '';
    teacherInfoEl.textContent = '';
    ratingControls.hidden = true;
    confirmButton.hidden = true;
    nextButton.hidden = false;
    nextButton.disabled = false;
    nextButton.textContent = 'Next';
    retryRecordBtn.hidden = true;
    finalRatingEl.textContent = '';
    resultEl.hidden = false;
    setStatus(
      'Card ' + (index + 1) + ' of ' + batch.records.length +
      '. Still working in the background; Next moves on without waiting.'
    );
  }

  function showReviewCard(index) {
    reviewIndex = index;
    var record = batch.records[index];
    if (!record) {
      finishBatch();
      return;
    }
    current = record.card;
    stopSpoken();
    updateBatchProgress();
    if (record.status === 'processing' || record.status === 'unseen') {
      showPendingReview(record, index);
      // Fill the card in when its background work lands, unless the user moved on.
      if (record.promise) {
        record.promise.then(function () {
          if (batch.phase === 'review' && batch.records[reviewIndex] === record) {
            renderReview(record);
          }
        });
      }
      return;
    }
    setStatus('Reviewing card ' + (index + 1) + ' of ' + batch.records.length + '.');
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
    reviewQuestionEl.textContent = record.card.card.question;
    var judgment = record.saved ? record.saved.is_correct
      : (record.preview ? record.preview.is_correct : null);
    renderYourAnswer(answerText(record.payload), judgment);
    renderRatingOptions(ratingScale());
    renderActiveTags();
    var feedback = record.feedback || (record.saved ? record.saved.feedback : '');
    feedbackEl.innerHTML = feedback ? renderMarkdown(feedback) : '';
    feedbackEl.hidden = !feedback;
    resultEl.hidden = false;
    renderReviewJudgeInfo(record);
    retryRecordBtn.hidden = !record.error;
    retryRecordBtn.textContent = record.payload ? 'Retry judging' : 'Retry transcription';
    retryRecordBtn.onclick = function () { void retryTranscription(record); };
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
    else if (record.audioUnavailable && teacherEnabled) {
      teacherInfoEl.textContent =
        (record.teacherModel ? 'Teacher: ' + record.teacherModel + ' · ' : '') +
        'explanation audio unavailable';
    }
  }

  function playReviewAudio(url) {
    void playSpoken(url);
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

  async function retryTranscription(record) {
    // The recording is still in this tab's memory: a transcription that came back
    // rate-limited can be tried again during the review.
    retryRecordBtn.disabled = true;
    retryRecordBtn.hidden = true;
    record.error = null;
    record.status = 'processing';
    record.promise = processRecord(record);
    showPendingReview(record, reviewIndex);
    try {
      await record.promise;
    } finally {
      retryRecordBtn.disabled = false;
    }
    if (batch.phase === 'review' && batch.records[reviewIndex] === record) {
      renderReview(record);
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
      renderYourAnswer(answerText(record.payload), saved.is_correct);
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
    releaseMicrophone();
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
    releaseMicrophone();
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
    // The microphone scope ends with the answer phase: nothing records in a review.
    if (inReviewPhase()) return;
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
      void keepAwake();
      recordingElapsed = 0;
      recordingPaused = false;
      chunks = [];
      recordingStream = stream;
      startEqualizer(stream);
      var activeRecorder = new MediaRecorder(stream);
      recorder = activeRecorder;
      activeRecorder.ondataavailable = function (event) { if (event.data.size) chunks.push(event.data); };
      activeRecorder.onstop = function () {
        stream.getTracks().forEach(function (track) { track.stop(); });
        stopEqualizer();
        allowSleep();
        if (requestId !== recordingRequest) return;
        var blob = new Blob(chunks, {type: activeRecorder.mimeType || 'audio/webm'});
        recorder = null;
        recordingStream = null;
        chunks = [];
        stopRecordingCounter();
        pauseRecordBtn.hidden = true;
        setRecordingControls();
        if (batchEnabled && batch && batch.phase === 'answer' && voiceAutoJudge) {
          void submitBatchVoice(blob);
        } else {
          void transcribeAudio(blob);
        }
      };
      // Pausing mid-recording needs the recorder API; the button stays out of the way otherwise.
      pauseRecordBtn.hidden = typeof activeRecorder.pause !== 'function';
      activeRecorder.start();
      recordingStartedAt = Date.now();
      updateRecordingCounter();
      recordingCounter.hidden = false;
      recordingTimer = setInterval(updateRecordingCounter, 1000);
      setRecordingControls();
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
      refreshMicState();
      permission.onchange = function () {
        microphoneAuthorized = permission.state === 'granted';
        refreshMicState();
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
    } else if (event.key === ' ' && !speechBar.hidden) {
      event.preventDefault();
      toggleSpeechPause();
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
  speakQuestionBtn.addEventListener('click', function () { void playQuestion(speakQuestionBtn); });
  speakReviewQuestionBtn.addEventListener('click', function () { void playQuestion(speakReviewQuestionBtn); });
  speakExplanationBtn.addEventListener('click', function () { void playExplanation(speakExplanationBtn); });
  recordButton.addEventListener('click', toggleRecording);
  pauseRecordBtn.addEventListener('click', toggleRecordPause);
  pauseSpeechBtn.addEventListener('click', toggleSpeechPause);
  stopSpeechBtn.addEventListener('click', stopSpoken);
  // Tapping the text button is a request for the keyboard, and the only place where
  // focus is raised on purpose. The automatic fallback (a failed transcription, an
  // unsupported browser) goes through setTextMode alone and leaves the keyboard down.
  textModeButton.addEventListener('click', function () {
    setTextMode();
    answerInput.focus();
  });
  nextButton.addEventListener('click', function () {
    if (inReviewPhase()) advanceReview();
    else void nextCard();
  });
  answerInput.addEventListener('input', invalidateAssessment);
  document.addEventListener('keydown', onKeydown);
  startButton.addEventListener('click', startSession);
  micAuthorizeBtn.addEventListener('click', function () { void authorizeMicrophone(); });
  micTestBtn.addEventListener('click', function () { void testMicrophone(); });
  refreshMicState();
  batchContinueBtn.addEventListener('click', continueBatch);
  batchMenuBtn.addEventListener('click', backToMenu);
  autoSpeakBtn.addEventListener('click', function () { void toggleAutoSpeak(); });
  setAutoSpeakButton();
  // A wake lock is dropped when the page is hidden; take it back on return.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && (recorder || spokenAudio)) void keepAwake();
  });
  void watchMicrophonePermission();
})();
