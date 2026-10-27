/**
 * Mock Interview AI — Interactive Face-to-Face Live Interview Console
 * Integrates directly with the real Flask REST API (/api/interviews/<id>).
 * Phase 4 Refinements:
 * - Real Browser Speech-to-Text (STT) via Web Speech API with editable transcript
 * - Real Browser Text-to-Speech (TTS) for spoken AI questions with replay/stop controls
 * - Visual AI Interviewer Avatar with synchronized speaking/listening states
 * - Optional Candidate Self-View Camera Mirror
 * - Strict audio conflict prevention (stops TTS before STT, stops STT before TTS)
 * - Deep permission handling (denied, audio-capture, network, silence/no-speech)
 * - Double-submission prevention, empty answer validation, and transcript clear confirmation
 * - Fallback text-answer support for unsupported browsers or denied permissions
 * - Zero server audio storage (100% local browser speech processing)
 */
document.addEventListener("DOMContentLoaded", () => {
  const metaEl = document.getElementById("interview-meta");
  if (!metaEl) return;

  const interviewId = metaEl.getAttribute("data-id");
  if (!interviewId) return;

  // =========================================================================
  // DOM ELEMENT REFERENCES
  // =========================================================================
  const questionNumEl = document.getElementById("question-num");
  const questionTotalEl = document.getElementById("question-total");
  const progressFill = document.getElementById("progress-fill");
  const progressPercentText = document.getElementById("progress-percent-text");

  const questionCard = document.getElementById("question-card");
  const questionTextEl = document.getElementById("question-text");
  const questionHintBox = document.getElementById("question-hint-box");
  const questionHintText = document.getElementById("question-hint-text");

  // Video Stage Elements
  const aiVideoTile = document.getElementById("ai-video-tile");
  const aiStatusDot = document.getElementById("ai-status-dot");
  const aiStatusPill = document.getElementById("ai-status-pill");
  const ttsPlayBtn = document.getElementById("tts-play-btn");
  const ttsReplayBtn = document.getElementById("tts-replay-btn");
  const ttsStopBtn = document.getElementById("tts-stop-btn");
  const ttsBtnText = document.getElementById("tts-btn-text");
  const autoSpeakCheckbox = document.getElementById("auto-speak-checkbox");

  // Candidate Camera Elements
  const candidateWebcam = document.getElementById("candidate-webcam");
  const cameraPlaceholder = document.getElementById("camera-placeholder");
  const cameraStatusPill = document.getElementById("camera-status-pill");
  const candidateStatusDot = document.getElementById("candidate-status-dot");
  const toggleCameraBtn = document.getElementById("toggle-camera-btn");
  const cameraBtnText = document.getElementById("camera-btn-text");
  const micLiveBadge = document.getElementById("mic-live-badge");

  // Microphone & Speech-to-Text Elements
  const micToggleBtn = document.getElementById("mic-toggle-btn");
  const micStatusTitle = document.getElementById("mic-status-title");
  const micStatusSubtitle = document.getElementById("mic-status-subtitle");
  const liveAudioMeter = document.getElementById("live-audio-meter");
  const startListeningBtn = document.getElementById("start-listening-btn");
  const stopListeningBtn = document.getElementById("stop-listening-btn");
  const cancelRecordingBtn = document.getElementById("cancel-recording-btn");
  const clearTranscriptBtn = document.getElementById("clear-transcript-btn");
  const sttStatusPill = document.getElementById("stt-status-pill");
  const interimStream = document.getElementById("interim-stream");
  const interimText = document.getElementById("interim-text");
  const sttFallbackAlert = document.getElementById("stt-fallback-alert");
  const sttFallbackText = document.getElementById("stt-fallback-text");

  // Textarea & Submit Elements
  const answerInput = document.getElementById("answer-input");
  const wordCountEl = document.getElementById("word-count");
  const charCountEl = document.getElementById("char-count");
  const minCharHint = document.getElementById("min-char-hint");
  const submitBtn = document.getElementById("submit-answer-btn");
  const btnSpinner = document.getElementById("btn-spinner");
  const btnText = document.getElementById("btn-text");

  const sessionErrorAlert = document.getElementById("session-error-alert");
  const sessionErrorText = document.getElementById("session-error-text");

  // Evaluation Elements
  const feedbackCard = document.getElementById("feedback-card");
  const scoreValEl = document.getElementById("score-val");
  const scoreRatingBadge = document.getElementById("score-rating-badge");
  const classificationBadge = document.getElementById("classification-badge");
  const overallFeedbackText = document.getElementById("overall-feedback-text");
  const strengthsList = document.getElementById("strengths-list");
  const weaknessesList = document.getElementById("weaknesses-list");
  const modelAnswerBox = document.getElementById("model-answer-box");
  const modelAnswerText = document.getElementById("model-answer-text");
  const suggestionsBox = document.getElementById("suggestions-box");
  const suggestionsList = document.getElementById("suggestions-list");
  const nextActionBtn = document.getElementById("next-action-btn");
  const nextBtnSpinner = document.getElementById("next-btn-spinner");
  const nextBtnText = document.getElementById("next-btn-text");

  // =========================================================================
  // APPLICATION STATE
  // =========================================================================
  let currentQuestionNumber = 1;
  let totalQuestionsCount = 3;
  let activeQuestionObj = null;
  let isSubmitting = false;

  // STT State
  let recognition = null;
  let isListening = false;
  let speechSupported = false;
  let preTurnTranscript = ""; // Saves transcript before the latest turn for cancel feature

  // Camera State
  let cameraStream = null;
  let isCameraActive = false;

  // TTS State
  let ttsSupported = "speechSynthesis" in window;
  let isSpeaking = false;
  let currentUtterance = null;
  let availableVoices = [];
  let ttsKeepAliveTimer = null;

  // =========================================================================
  // ERROR & ALERT HELPERS
  // =========================================================================
  function showError(msg, isWarning = false) {
    if (sessionErrorAlert && sessionErrorText) {
      sessionErrorText.textContent = msg;
      sessionErrorAlert.className = isWarning ? "alert alert-warning" : "alert alert-danger";
      sessionErrorAlert.style.display = "flex";
      sessionErrorAlert.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function clearError() {
    if (sessionErrorAlert) sessionErrorAlert.style.display = "none";
  }

  // =========================================================================
  // TEXT & CHARACTER COUNT VALIDATION
  // =========================================================================
  function updateCounts() {
    if (!answerInput) return;
    const text = answerInput.value.trim();
    const words = text ? text.split(/\s+/).length : 0;
    const chars = answerInput.value.length;

    if (wordCountEl) wordCountEl.textContent = `${words} word${words === 1 ? "" : "s"}`;
    if (charCountEl) charCountEl.textContent = `${chars} character${chars === 1 ? "" : "s"}`;

    const isValidLength = chars >= 5 && chars <= 5000;
    if (minCharHint) {
      if (chars === 0) {
        minCharHint.textContent = "(Minimum 5 characters required to submit)";
        minCharHint.style.color = "var(--text-muted)";
      } else if (chars < 5) {
        minCharHint.textContent = `(Add ${5 - chars} more character${5 - chars === 1 ? "" : "s"})`;
        minCharHint.style.color = "var(--warning)";
      } else if (chars > 5000) {
        minCharHint.textContent = "(Maximum 5000 characters reached)";
        minCharHint.style.color = "var(--danger)";
      } else {
        minCharHint.textContent = "✓ Ready to submit";
        minCharHint.style.color = "var(--success)";
      }
    }

    if (submitBtn && !isSubmitting) {
      submitBtn.disabled = !isValidLength;
    }
  }

  if (answerInput) {
    answerInput.addEventListener("input", updateCounts);
  }

  // =========================================================================
  // BROWSER TEXT-TO-SPEECH (TTS) MANAGER
  // =========================================================================
  function initTTS() {
    if (!ttsSupported) {
      if (ttsPlayBtn) ttsPlayBtn.style.display = "none";
      if (ttsReplayBtn) ttsReplayBtn.style.display = "none";
      if (autoSpeakCheckbox) autoSpeakCheckbox.parentElement.style.display = "none";
      return;
    }

    function populateVoices() {
      availableVoices = window.speechSynthesis.getVoices();
    }
    populateVoices();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = populateVoices;
    }
  }

  function getBestEnglishVoice() {
    if (!availableVoices.length && ttsSupported) {
      availableVoices = window.speechSynthesis.getVoices();
    }
    const preferred = availableVoices.find(v => 
      (v.lang.startsWith("en") && (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Samantha") || v.name.includes("Zira") || v.name.includes("David")))
    );
    if (preferred) return preferred;
    const anyEn = availableVoices.find(v => v.lang.startsWith("en"));
    return anyEn || availableVoices[0] || null;
  }

  function startTTSKeepAlive() {
    stopTTSKeepAlive();
    ttsKeepAliveTimer = setInterval(() => {
      if (window.speechSynthesis && window.speechSynthesis.speaking) {
        window.speechSynthesis.pause();
        window.speechSynthesis.resume();
      } else {
        stopTTSKeepAlive();
      }
    }, 10000);
  }

  function stopTTSKeepAlive() {
    if (ttsKeepAliveTimer) {
      clearInterval(ttsKeepAliveTimer);
      ttsKeepAliveTimer = null;
    }
  }

  function stopSpeaking() {
    if (!ttsSupported) return;
    stopTTSKeepAlive();
    window.speechSynthesis.cancel();
    isSpeaking = false;
    currentUtterance = null;

    if (aiVideoTile) aiVideoTile.classList.remove("is-speaking");
    if (aiStatusPill) {
      aiStatusPill.className = "status-pill status-ready";
      aiStatusPill.textContent = "Ready";
    }
    if (ttsPlayBtn) {
      ttsPlayBtn.style.display = "inline-flex";
      if (ttsBtnText) ttsBtnText.textContent = "Hear Question";
    }
    if (ttsStopBtn) ttsStopBtn.style.display = "none";
  }

  function speakQuestion(text) {
    if (!ttsSupported || !text) return;

    // RULE 7 & 10: Stop microphone recording before AI speaks to prevent audio feedback loop!
    if (isListening) {
      stopListening();
    }

    stopSpeaking();

    const cleanText = text.trim();
    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;

    const voice = getBestEnglishVoice();
    if (voice) utterance.voice = voice;

    utterance.onstart = () => {
      isSpeaking = true;
      startTTSKeepAlive();
      if (aiVideoTile) aiVideoTile.classList.add("is-speaking");
      if (aiStatusPill) {
        aiStatusPill.className = "status-pill status-speaking";
        aiStatusPill.textContent = "Speaking...";
      }
      if (ttsPlayBtn) ttsPlayBtn.style.display = "none";
      if (ttsStopBtn) ttsStopBtn.style.display = "inline-flex";
    };

    utterance.onend = () => {
      stopSpeaking();
    };

    utterance.onerror = () => {
      stopSpeaking();
    };

    currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  if (ttsPlayBtn) {
    ttsPlayBtn.addEventListener("click", () => {
      const qText = questionTextEl ? questionTextEl.textContent : "";
      speakQuestion(qText);
    });
  }

  if (ttsReplayBtn) {
    ttsReplayBtn.addEventListener("click", () => {
      const qText = questionTextEl ? questionTextEl.textContent : "";
      speakQuestion(qText);
    });
  }

  if (ttsStopBtn) {
    ttsStopBtn.addEventListener("click", () => {
      stopSpeaking();
    });
  }

  // =========================================================================
  // BROWSER SPEECH-TO-TEXT (STT) MANAGER
  // =========================================================================
  function initSTT() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      speechSupported = false;
      if (sttFallbackAlert) {
        sttFallbackAlert.style.display = "flex";
        if (sttFallbackText) {
          sttFallbackText.textContent = "Browser speech recognition is not supported in this browser. Please type your answer directly in the text editor below.";
        }
      }
      if (sttStatusPill) {
        sttStatusPill.className = "stt-status-pill status-idle";
        sttStatusPill.textContent = "Speech Recognition Unsupported";
      }
      if (micToggleBtn) {
        micToggleBtn.classList.add("is-disabled");
        micToggleBtn.disabled = true;
      }
      if (startListeningBtn) startListeningBtn.disabled = true;
      return;
    }

    speechSupported = true;
    try {
      recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        isListening = true;
        setListeningUIState(true);
      };

      recognition.onresult = (event) => {
        let interim = "";
        let finalSegment = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcriptPart = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalSegment += transcriptPart + " ";
          } else {
            interim += transcriptPart;
          }
        }

        if (finalSegment && answerInput) {
          const currentVal = answerInput.value;
          const separator = currentVal && !currentVal.endsWith(" ") && !currentVal.endsWith("\n") ? " " : "";
          answerInput.value = currentVal + separator + finalSegment.trim() + " ";
          updateCounts();
        }

        if (interimStream && interimText) {
          if (interim.trim()) {
            interimStream.style.display = "flex";
            interimText.textContent = `"${interim.trim()}"`;
          } else {
            interimStream.style.display = "none";
          }
        }
      };

      recognition.onerror = (event) => {
        console.warn("Speech recognition notice:", event.error);
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          showError("Microphone access was denied. Please allow microphone permissions in your browser URL bar or type your answer directly.", true);
          if (sttFallbackAlert) {
            sttFallbackAlert.style.display = "flex";
            if (sttFallbackText) {
              sttFallbackText.textContent = "Microphone access blocked. Click the lock icon in your address bar to allow microphone access, or type your answer below.";
            }
          }
          if (micToggleBtn) micToggleBtn.classList.add("is-denied");
          if (sttStatusPill) {
            sttStatusPill.className = "stt-status-pill status-denied";
            sttStatusPill.textContent = "⚠️ Microphone Blocked";
          }
          if (micStatusTitle) micStatusTitle.textContent = "Microphone Access Denied";
          if (micStatusSubtitle) micStatusSubtitle.textContent = "Enable microphone permissions or use keyboard to type response";
        } else if (event.error === "audio-capture") {
          showError("No microphone hardware detected or audio device is in use by another app. You can type your answer directly below.", true);
          if (sttStatusPill) {
            sttStatusPill.className = "stt-status-pill status-denied";
            sttStatusPill.textContent = "❌ No Microphone Found";
          }
        } else if (event.error === "network") {
          showError("Speech recognition network glitch. Check connection or type your answer directly.", true);
          if (sttStatusPill) {
            sttStatusPill.className = "stt-status-pill status-paused";
            sttStatusPill.textContent = "🌐 Speech Network Glitch";
          }
        } else if (event.error === "no-speech") {
          // Candidate paused or silent
          if (sttStatusPill) {
            sttStatusPill.className = "stt-status-pill status-paused";
            sttStatusPill.textContent = "⏸ Paused (Silence)";
          }
          if (micStatusTitle) micStatusTitle.textContent = "Listening Paused (Silence)";
          if (micStatusSubtitle) micStatusSubtitle.textContent = "Click Start Listening to resume speaking";
        }
        setListeningUIState(false);
      };

      recognition.onend = () => {
        if (isListening) {
          // Browser closed stream (e.g. silence timeout)
          setListeningUIState(false);
          if (sttStatusPill) {
            sttStatusPill.className = "stt-status-pill status-paused";
            sttStatusPill.textContent = "⏸ Paused (Silence)";
          }
          if (micStatusTitle) micStatusTitle.textContent = "Listening Paused";
          if (micStatusSubtitle) micStatusSubtitle.textContent = "Click Start Listening to continue speaking";
        }
      };
    } catch (e) {
      speechSupported = false;
      console.warn("Could not initialize SpeechRecognition:", e);
    }
  }

  function setListeningUIState(active) {
    isListening = active;

    if (active) {
      if (micToggleBtn) {
        micToggleBtn.classList.remove("is-denied");
        micToggleBtn.classList.add("is-listening");
      }
      if (micStatusTitle) micStatusTitle.textContent = "Listening... Speak Clearly";
      if (micStatusSubtitle) micStatusSubtitle.textContent = "Click Stop Listening when finished speaking";
      if (sttStatusPill) {
        sttStatusPill.className = "stt-status-pill status-listening";
        sttStatusPill.textContent = "🔴 Recording Speech";
      }
      if (liveAudioMeter) liveAudioMeter.style.display = "flex";
      if (startListeningBtn) startListeningBtn.disabled = true;
      if (stopListeningBtn) stopListeningBtn.disabled = false;
      if (cancelRecordingBtn) cancelRecordingBtn.disabled = false;
      if (micLiveBadge) micLiveBadge.style.display = "flex";
      if (aiVideoTile) aiVideoTile.classList.add("is-listening");
    } else {
      if (micToggleBtn) micToggleBtn.classList.remove("is-listening");
      if (liveAudioMeter) liveAudioMeter.style.display = "none";
      if (interimStream) interimStream.style.display = "none";
      if (startListeningBtn && speechSupported) startListeningBtn.disabled = false;
      if (stopListeningBtn) stopListeningBtn.disabled = true;
      if (cancelRecordingBtn) cancelRecordingBtn.disabled = true;
      if (micLiveBadge) micLiveBadge.style.display = "none";
      if (aiVideoTile) aiVideoTile.classList.remove("is-listening");
    }
  }

  function startListening() {
    if (!speechSupported || !recognition) {
      showError("Speech recognition is not available in this browser. Please type your answer directly.", true);
      return;
    }

    // RULE 7 & 10: Prevent TTS speech playback from conflicting with microphone recording
    stopSpeaking();

    // Save existing transcript so "Cancel Recording" can revert only this turn
    preTurnTranscript = answerInput ? answerInput.value : "";

    try {
      recognition.start();
    } catch (err) {
      console.warn("Recognition already started or error:", err);
    }
  }

  function stopListening() {
    if (!recognition) return;
    try {
      recognition.stop();
    } catch (e) {
      // Ignore
    }
    setListeningUIState(false);
    if (sttStatusPill) {
      sttStatusPill.className = "stt-status-pill status-idle";
      sttStatusPill.textContent = "Microphone Ready";
    }
    if (micStatusTitle) micStatusTitle.textContent = "Click to Start Speaking";
    if (micStatusSubtitle) micStatusSubtitle.textContent = "Browser Speech-to-Text will transcribe your answer";
    updateCounts();
  }

  function cancelRecording() {
    if (!recognition) return;
    try {
      recognition.abort();
    } catch (e) {
      // Ignore
    }
    // Revert answer textarea to state before this recording turn
    if (answerInput) {
      answerInput.value = preTurnTranscript;
      updateCounts();
    }
    setListeningUIState(false);
    if (sttStatusPill) {
      sttStatusPill.className = "stt-status-pill status-idle";
      sttStatusPill.textContent = "Recording Discarded";
      setTimeout(() => {
        if (!isListening && sttStatusPill) {
          sttStatusPill.textContent = "Microphone Ready";
        }
      }, 2000);
    }
  }

  function clearTranscript() {
    if (isListening) {
      stopListening();
    }
    if (answerInput) {
      const textLen = answerInput.value.trim().length;
      if (textLen > 30) {
        const confirmed = window.confirm("Are you sure you want to clear your transcribed response?");
        if (!confirmed) return;
      }
      answerInput.value = "";
      updateCounts();
      answerInput.focus();
    }
  }

  // Hook up Microphone Hero & Button Events
  if (micToggleBtn) {
    micToggleBtn.addEventListener("click", () => {
      if (!speechSupported) return;
      if (isListening) {
        stopListening();
      } else {
        startListening();
      }
    });
  }

  if (startListeningBtn) {
    startListeningBtn.addEventListener("click", startListening);
  }

  if (stopListeningBtn) {
    stopListeningBtn.addEventListener("click", stopListening);
  }

  if (cancelRecordingBtn) {
    cancelRecordingBtn.addEventListener("click", cancelRecording);
  }

  if (clearTranscriptBtn) {
    clearTranscriptBtn.addEventListener("click", clearTranscript);
  }

  // =========================================================================
  // CANDIDATE WEBCAM PREVIEW
  // =========================================================================
  async function toggleCamera() {
    if (isCameraActive) {
      if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
      }
      if (candidateWebcam) {
        candidateWebcam.srcObject = null;
        candidateWebcam.style.display = "none";
      }
      if (cameraPlaceholder) cameraPlaceholder.style.display = "flex";
      if (cameraStatusPill) {
        cameraStatusPill.className = "status-pill status-camera-off";
        cameraStatusPill.textContent = "Camera Standby";
      }
      if (candidateStatusDot) candidateStatusDot.classList.remove("is-active");
      if (cameraBtnText) cameraBtnText.textContent = "Turn Camera On";
      isCameraActive = false;
    } else {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError("Webcam access is not supported by your browser environment.", true);
        return;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false // Speech audio is handled separately by Web Speech API
        });
        cameraStream = stream;
        if (candidateWebcam) {
          candidateWebcam.srcObject = stream;
          candidateWebcam.style.display = "block";
        }
        if (cameraPlaceholder) cameraPlaceholder.style.display = "none";
        if (cameraStatusPill) {
          cameraStatusPill.className = "status-pill status-camera-on";
          cameraStatusPill.textContent = "Camera Live";
        }
        if (candidateStatusDot) candidateStatusDot.classList.add("is-active");
        if (cameraBtnText) cameraBtnText.textContent = "Turn Camera Off";
        isCameraActive = true;
      } catch (err) {
        console.warn("Camera access denied or unavailable:", err);
        showError("Webcam permission was not granted. The camera is optional — you can still complete your interview.", true);
      }
    }
  }

  if (toggleCameraBtn) {
    toggleCameraBtn.addEventListener("click", toggleCamera);
  }

  // Cleanup media stream when student navigates away
  window.addEventListener("beforeunload", () => {
    stopSpeaking();
    if (isListening) stopListening();
    if (cameraStream) {
      cameraStream.getTracks().forEach(t => t.stop());
    }
  });

  // =========================================================================
  // DISPLAY QUESTION IN INTERVIEW CONSOLE
  // =========================================================================
  function displayQuestion(q, currentNum, totalNum) {
    activeQuestionObj = q;
    currentQuestionNumber = currentNum || q.question_number || 1;
    totalQuestionsCount = totalNum || totalQuestionsCount;

    if (questionNumEl) questionNumEl.textContent = currentQuestionNumber;
    if (questionTotalEl) questionTotalEl.textContent = totalQuestionsCount;

    const qText = q.question || q.question_text || "Explain your technical approach and reasoning.";
    if (questionTextEl) {
      questionTextEl.textContent = qText;
    }

    // Set expected aspects or focus topic hint
    const aspects = q.expected_aspects || q.key_points || [];
    if (aspects.length > 0 && questionHintBox && questionHintText) {
      questionHintBox.style.display = "block";
      questionHintText.textContent = `Focus areas: ${aspects.join(" • ")}`;
    } else if (q.topic && questionHintBox && questionHintText) {
      questionHintBox.style.display = "block";
      questionHintText.textContent = `Focus topic: ${q.topic}`;
    } else if (questionHintBox) {
      questionHintBox.style.display = "none";
    }

    // Update progress bar
    const progress = Math.round(((currentQuestionNumber - 1) / totalQuestionsCount) * 100);
    if (progressFill) progressFill.style.width = `${progress}%`;
    if (progressPercentText) progressPercentText.textContent = `${progress}%`;

    // Reset editor
    if (answerInput) {
      answerInput.value = "";
      answerInput.disabled = false;
      answerInput.focus();
    }
    updateCounts();

    // Reset STT state
    if (isListening) {
      stopListening();
    }

    // Reset AI Avatar state
    if (aiVideoTile) {
      aiVideoTile.classList.remove("is-speaking", "is-listening");
    }
    if (aiStatusPill) {
      aiStatusPill.className = "status-pill status-ready";
      aiStatusPill.textContent = "Ready";
    }

    // Hide feedback card
    if (feedbackCard) feedbackCard.style.display = "none";
    clearError();

    // Auto-speak question with browser TTS if enabled
    if (autoSpeakCheckbox && autoSpeakCheckbox.checked && qText) {
      setTimeout(() => {
        speakQuestion(qText);
      }, 500);
    }
  }

  // =========================================================================
  // 1. INITIAL SESSION LOADING FROM REST API
  // =========================================================================
  async function loadInitialSession() {
    try {
      if (questionTextEl) questionTextEl.textContent = "Connecting to interview session...";
      clearError();

      const response = await fetch(`/api/interviews/${interviewId}`, {
        headers: { "Accept": "application/json" }
      });

      if (response.status === 401) {
        showError("Your session has expired. Please log in again to continue.");
        setTimeout(() => { window.location.href = `/auth/login?next=/interview/session/${interviewId}`; }, 2500);
        return;
      }

      if (response.status === 404) {
        showError("Interview session not found. Redirecting to dashboard...");
        setTimeout(() => { window.location.href = "/dashboard/"; }, 2000);
        return;
      }

      if (response.status === 403) {
        showError("You do not have permission to access this interview session.");
        return;
      }

      const data = await response.json();
      if (!response.ok || !data.success || !data.interview) {
        showError(data.error || "Failed to load interview session.");
        return;
      }

      const interview = data.interview;
      totalQuestionsCount = interview.total_questions || 3;

      if (interview.status === "completed") {
        window.location.href = `/interview/report/${interviewId}`;
        return;
      }

      const questions = interview.questions || [];
      const unansweredQ = questions.find(q => !q.answered);

      if (unansweredQ) {
        displayQuestion(unansweredQ, unansweredQ.question_number, totalQuestionsCount);
      } else if (questions.length < totalQuestionsCount) {
        await requestNextQuestion();
      } else {
        await finalizeInterview();
      }
    } catch (err) {
      showError("Network connection error loading interview. Please refresh to try again.");
    }
  }

  // =========================================================================
  // 2. REQUEST NEXT QUESTION FROM REST API
  // =========================================================================
  async function requestNextQuestion() {
    try {
      stopSpeaking();
      if (isListening) stopListening();

      if (nextActionBtn) nextActionBtn.disabled = true;
      if (nextBtnSpinner) nextBtnSpinner.style.display = "inline-block";
      if (nextBtnText) nextBtnText.textContent = "Groq AI is Generating Next Question...";
      clearError();

      const response = await fetch(`/api/interviews/${interviewId}/next`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        }
      });

      if (response.status === 401) {
        showError("Session expired. Please log in again.");
        return;
      }

      const data = await response.json();

      if (nextActionBtn) nextActionBtn.disabled = false;
      if (nextBtnSpinner) nextBtnSpinner.style.display = "none";

      if (!response.ok || !data.success) {
        if (response.status === 503) {
          showError("AI generation service is temporarily busy. Please click 'Proceed to Next Question' to retry.", true);
        } else {
          showError(data.error || "Failed to generate next question.");
        }
        return;
      }

      if (data.completed) {
        await finalizeInterview();
        return;
      }

      if (data.question) {
        displayQuestion(data.question, data.question_number, data.total_questions || totalQuestionsCount);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    } catch (err) {
      if (nextActionBtn) nextActionBtn.disabled = false;
      if (nextBtnSpinner) nextBtnSpinner.style.display = "none";
      if (nextBtnText) nextBtnText.textContent = "Proceed to Next Question →";
      showError("Network failure requesting next question. Please check connection and click to retry.");
    }
  }

  // =========================================================================
  // 3. SUBMIT ANSWER TO REST API
  // =========================================================================
  if (submitBtn) {
    submitBtn.addEventListener("click", async () => {
      // RULE 6: Prevent duplicate submissions
      if (isSubmitting) return;

      // RULE 7 & 8: Stop speech playback and recording before evaluating
      stopSpeaking();
      if (isListening) stopListening();

      const answerText = answerInput ? answerInput.value.trim() : "";
      if (answerText.length < 5) {
        showError("Answer must contain at least 5 characters before submitting.");
        if (answerInput) answerInput.focus();
        return;
      }
      if (answerText.length > 5000) {
        showError("Answer cannot exceed 5000 characters.");
        return;
      }

      // Enter pending state
      isSubmitting = true;
      submitBtn.disabled = true;
      if (answerInput) answerInput.disabled = true;
      if (btnSpinner) btnSpinner.style.display = "inline-block";
      if (btnText) btnText.textContent = "Groq AI is Evaluating Answer...";
      clearError();

      if (aiStatusPill) {
        aiStatusPill.className = "status-pill status-evaluating";
        aiStatusPill.textContent = "Evaluating...";
      }

      try {
        const response = await fetch(`/api/interviews/${interviewId}/answer`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify({
            question_number: currentQuestionNumber,
            answer: answerText
          })
        });

        const data = await response.json();

        // Restore button state
        isSubmitting = false;
        if (btnSpinner) btnSpinner.style.display = "none";
        if (btnText) btnText.textContent = "Submit Answer for AI Evaluation";

        if (aiStatusPill) {
          aiStatusPill.className = "status-pill status-ready";
          aiStatusPill.textContent = "Ready";
        }

        if (response.status === 401) {
          showError("Your session expired. Please log in to save your progress.");
          if (answerInput) answerInput.disabled = false;
          submitBtn.disabled = false;
          return;
        }

        if (response.status === 503) {
          // AI service timeout or rate limit: candidate's transcript is 100% PRESERVED
          showError("Groq AI service is temporarily experiencing high latency. Your answer has been preserved below — please click 'Retry Evaluation'.", true);
          if (answerInput) answerInput.disabled = false;
          submitBtn.disabled = false;
          if (btnText) btnText.textContent = "Retry AI Evaluation";
          return;
        }

        if (!response.ok || !data.success) {
          showError(data.error || "Evaluation failed. Please try submitting again.");
          if (answerInput) answerInput.disabled = false;
          submitBtn.disabled = false;
          return;
        }

        // Render evaluation results
        renderEvaluation(data);

      } catch (err) {
        isSubmitting = false;
        if (btnSpinner) btnSpinner.style.display = "none";
        if (btnText) btnText.textContent = "Retry AI Evaluation";
        if (answerInput) answerInput.disabled = false;
        submitBtn.disabled = false;
        if (aiStatusPill) {
          aiStatusPill.className = "status-pill status-ready";
          aiStatusPill.textContent = "Ready";
        }
        showError("Network failure while submitting answer. Your answer is safe above — please click to retry.");
      }
    });
  }

  // =========================================================================
  // 4. RENDER EVALUATION RESULTS (PHASE 2 & PHASE 3 SCHEMA)
  // =========================================================================
  function renderEvaluation(data) {
    const evalData = data.evaluation || {};
    const score = typeof data.score === "number" ? data.score : (evalData.score || 0);

    // Score display
    if (scoreValEl) scoreValEl.textContent = score;

    // Rating badge & color
    if (scoreRatingBadge) {
      if (score >= 80) {
        scoreRatingBadge.textContent = "Outstanding";
        scoreRatingBadge.className = "badge badge-easy";
      } else if (score >= 60) {
        scoreRatingBadge.textContent = "Proficient";
        scoreRatingBadge.className = "badge badge-medium";
      } else {
        scoreRatingBadge.textContent = "Needs Practice";
        scoreRatingBadge.className = "badge badge-hard";
      }
    }

    // Classification badge (correct / partially_correct / incorrect)
    const classification = data.classification || evalData.classification;
    if (classificationBadge && classification) {
      classificationBadge.style.display = "inline-flex";
      if (classification === "correct") {
        classificationBadge.textContent = "✓ Accurate Response";
        classificationBadge.className = "badge badge-easy";
      } else if (classification === "partially_correct") {
        classificationBadge.textContent = "⚠ Partially Correct";
        classificationBadge.className = "badge badge-medium";
      } else {
        classificationBadge.textContent = "✕ Inaccurate / Needs Revision";
        classificationBadge.className = "badge badge-hard";
      }
    }

    // Feedback narrative / explanation
    if (overallFeedbackText) {
      overallFeedbackText.textContent = evalData.explanation || evalData.feedback || "Answer evaluated against technical rubrics.";
    }

    // Strengths & correct concepts
    if (strengthsList) {
      strengthsList.innerHTML = "";
      const strengths = evalData.correct_concepts || evalData.strengths || ["Addressed question directly."];
      strengths.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        strengthsList.appendChild(li);
      });
    }

    // Mistakes & missing concepts
    if (weaknessesList) {
      weaknessesList.innerHTML = "";
      const weaknesses = [];
      if (evalData.mistakes && Array.isArray(evalData.mistakes)) {
        evalData.mistakes.forEach(m => weaknesses.push(`Misconception: ${m}`));
      }
      if (evalData.missing_concepts && Array.isArray(evalData.missing_concepts)) {
        evalData.missing_concepts.forEach(mc => weaknesses.push(`Omitted: ${mc}`));
      }
      if (!weaknesses.length) {
        (evalData.weaknesses || ["Elaborate further on practical system constraints."]).forEach(w => weaknesses.push(w));
      }
      weaknesses.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        weaknessesList.appendChild(li);
      });
    }

    // Exemplary Model Answer (Improved Answer)
    const improvedAns = evalData.improved_answer;
    if (modelAnswerBox && modelAnswerText) {
      if (improvedAns && improvedAns.trim()) {
        modelAnswerText.textContent = improvedAns.trim();
        modelAnswerBox.style.display = "block";
      } else {
        modelAnswerBox.style.display = "none";
      }
    }

    // Actionable Suggestions
    const suggestions = evalData.suggestions || [];
    if (suggestionsBox && suggestionsList) {
      if (suggestions.length > 0) {
        suggestionsList.innerHTML = "";
        suggestions.forEach((s) => {
          const li = document.createElement("li");
          li.textContent = s;
          suggestionsList.appendChild(li);
        });
        suggestionsBox.style.display = "block";
      } else {
        suggestionsBox.style.display = "none";
      }
    }

    // Update progress bar
    const progress = Math.round((currentQuestionNumber / totalQuestionsCount) * 100);
    if (progressFill) progressFill.style.width = `${progress}%`;
    if (progressPercentText) progressPercentText.textContent = `${progress}%`;

    // Configure Next Button Action
    if (data.is_all_complete || currentQuestionNumber >= totalQuestionsCount) {
      if (nextBtnText) nextBtnText.textContent = "Finish Interview & View Final Report 🏆";
      if (nextActionBtn) {
        nextActionBtn.onclick = async () => {
          await finalizeInterview();
        };
      }
    } else {
      if (nextBtnText) nextBtnText.textContent = `Proceed to Question ${currentQuestionNumber + 1} →`;
      if (nextActionBtn) {
        nextActionBtn.onclick = async () => {
          await requestNextQuestion();
        };
      }
    }

    // Show feedback card with smooth reveal
    if (feedbackCard) {
      feedbackCard.style.display = "block";
      feedbackCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // =========================================================================
  // 5. FINALIZE INTERVIEW
  // =========================================================================
  async function finalizeInterview() {
    try {
      stopSpeaking();
      if (isListening) stopListening();

      if (nextActionBtn) nextActionBtn.disabled = true;
      if (nextBtnSpinner) nextBtnSpinner.style.display = "inline-block";
      if (nextBtnText) nextBtnText.textContent = "Calculating Final Performance Report...";
      clearError();

      const response = await fetch(`/api/interviews/${interviewId}/finish`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        }
      });

      const data = await response.json();

      if (response.ok && data.success) {
        if (nextBtnText) nextBtnText.textContent = "Loading Scorecard...";
        window.location.href = `/interview/report/${interviewId}`;
      } else {
        if (nextActionBtn) nextActionBtn.disabled = false;
        if (nextBtnSpinner) nextBtnSpinner.style.display = "none";
        if (nextBtnText) nextBtnText.textContent = "Finish Interview & View Final Report 🏆";
        showError(data.error || "Failed to finalize report. Please click to retry.");
      }
    } catch (err) {
      if (nextActionBtn) nextActionBtn.disabled = false;
      if (nextBtnSpinner) nextBtnSpinner.style.display = "none";
      if (nextBtnText) nextBtnText.textContent = "Finish Interview & View Final Report 🏆";
      showError("Network error finalizing interview. Please click to retry.");
    }
  }

  // =========================================================================
  // BOOTSTRAP INTERVIEW ROOM
  // =========================================================================
  initTTS();
  initSTT();
  loadInitialSession();
});
