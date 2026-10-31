// Study view: card queue, answer judging, voice recording, teacher and TTS.
(function () {
  var config = document.getElementById('study-config').dataset;
  var flipEl = document.getElementById('flip');
  var deckSelect = document.getElementById('deck-select');
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
  var voiceAutoJudge = config.voiceAutoJudge === 'true';
  var autoConfirm = config.autoConfirm === 'true';
  var teacherEnabled = config.teacherEnabled === 'true';
  var ttsEnabled = config.ttsEnabled === 'true';
  var voiceAllowed = config.voiceAllowed === 'true';

  var current = null;
  var startedAt = 0;
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
        ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--pico-primary') || '#3b82f6';
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
    if (microphoneAuthorized && current && !studyEl.hidden && !pendingResult && !recorder) {
      void startRecording();
    }
  }

  async function loadNext() {
    resetPanels();
    setStatus('Loading next card…');
    var query = deckSelect.value ? '?deck_id=' + encodeURIComponent(deckSelect.value) : '';
    try {
      current = await api('/api/study/next' + query);
      if (!current) {
        emptyEl.hidden = false;
        setStatus('Queue empty.');
        return;
      }
      questionEl.textContent = current.card.question;
      cardStateEl.textContent = current.is_new ? 'New card' : 'Review · due ' + formatDate(current.due);
      studyEl.hidden = false;
      startedAt = Date.now();
      answerInput.focus();
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
    resultEl.hidden = false;
  }

  function showFeedback(result) {
    feedbackEl.textContent = result.feedback;
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
        body: JSON.stringify({card_id: current.card.id})
      });
      teacherExplanationEl.textContent = result.explanation;
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
      var blob = await response.blob();
      if (spokenAudio) spokenAudio.pause();
      spokenAudio = new Audio(URL.createObjectURL(blob));
      await spokenAudio.play();
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
    ratingInput.value = result.rating || '3';
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
      ? 'AI rating ' + result.rating + ' · ' + (result.is_correct ? 'correct' : 'incorrect')
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
    studyEl.hidden = true;
    answerInput.disabled = true;
    showCardContext();
    showFeedback(result);
    showTeacher();
    judgeInfoEl.textContent = result.mode === 'self_fallback' ? 'Self fallback (judge failed)' : 'Judge: ' + result.judge_model;
    finalRatingEl.textContent = 'Saved rating ' + result.rating + ' · ' + (result.is_correct ? 'correct' : 'incorrect') + ' · next due ' + formatDate(result.due);
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
        await submitAnswer();
      } else {
        setStatus('Transcript ready. Edit it if needed, then submit.');
        answerInput.focus();
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
        void transcribeAudio(blob);
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

  deckSelect.addEventListener('change', loadNext);
  submitButton.addEventListener('click', submitAnswer);
  teacherBtn.addEventListener('click', fetchExplanation);
  teacherRegenBtn.addEventListener('click', fetchExplanation);
  speakQuestionBtn.addEventListener('click', function () { void speak('/api/study/speak-question', speakQuestionBtn); });
  speakExplanationBtn.addEventListener('click', function () { void speak('/api/study/speak-explanation', speakExplanationBtn); });
  recordButton.addEventListener('click', toggleRecording);
  textModeButton.addEventListener('click', setTextMode);
  nextButton.addEventListener('click', nextCard);
  answerInput.addEventListener('input', invalidateAssessment);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && recorder && recorder.state === 'recording') {
      event.preventDefault();
      toggleRecording();
      return;
    }
    var typing = event.target === answerInput || event.target === ratingInput || event.target === correctInput || event.target === deckSelect;
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && event.target === answerInput) {
      event.preventDefault();
      void submitAnswer();
      return;
    }
    if (typing || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      if (!nextButton.hidden) void nextCard();
      else if (!studyEl.hidden && !submitButton.disabled) void submitAnswer();
    } else if (event.key >= '1' && event.key <= '4' && !ratingControls.hidden) {
      ratingInput.value = event.key;
    } else if (event.key === 'n' && !nextButton.hidden) {
      void nextCard();
    }
  });
  void watchMicrophonePermission();
  void loadNext();
})();
