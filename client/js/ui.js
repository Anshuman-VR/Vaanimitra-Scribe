import { questions, currentQuestionIndex, setCurrentQuestionIndex, answers, setAnswers, sessionId, speakTTS, examMeta, STATE, getState, setState, setRegistrationPhaseData, studentName, studentReg, startExamTimer, startAppConnection } from './main.js';
import { sendMessage } from './websocket.js';
import { stopSpeechStream } from './audio.js';

let registrationPhase = null;

export function getRegistrationPhase() {
  return registrationPhase;
}

export function renderInvigilatorSetup() {
  const container = document.getElementById('app-container');
  container.innerHTML = `
    <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background: #0a1628; color: white;">
        <h1 style="margin-bottom: 24px;">AI Scribe Terminal</h1>
        <button id="btn-ready-terminal" style="padding: 16px 32px; font-size: 1.5rem; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">Invigilator: Ready Terminal</button>
    </div>
  `;
  document.getElementById('btn-ready-terminal').onclick = () => {
    // This unlocks AudioContext on click!
    startAppConnection();
    renderPreOnboarding();
  };
}

export function renderPreOnboarding() {
  const container = document.getElementById('app-container');
  container.innerHTML = `
    <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background: #f3f4f6; color: #0a1628;">
        <h2 style="color: #6b7280; font-style: italic;">Terminal ready.</h2>
        <h1 style="margin-top: 16px;">Waiting for Invigilator to start onboarding...</h1>
    </div>
  `;
}

export function renderQuestion(index) {
  if (questions.length === 0) return;
  const q = questions[index];
  
  document.getElementById('course-code').textContent = examMeta ? examMeta.course_code : '';
  document.getElementById('subject').textContent = examMeta ? examMeta.subject : '';
  document.getElementById('exam-status').textContent = 'Active';

  document.getElementById('q-part').textContent = `Part ${q.part}`;
  document.getElementById('q-progress').textContent = `Q${index+1}/${questions.length}`;
  document.getElementById('q-marks').textContent = `[${q.marks} marks]`;
  document.getElementById('q-text').textContent = q.text;
  
  document.getElementById('committed-text').textContent = answers[q.id] ? answers[q.id] + " " : "";
  document.getElementById('pending-text').textContent = "";
  
  sendMessage({ "type": "set_question", "question_id": q.id });
}

export function executeCommand(cmd) {
  const action = cmd.intent || cmd.action || cmd;
  const target = cmd.target;
  const qid = questions.length > 0 ? questions[currentQuestionIndex].id : null;
  
  showCommandFeedback(action);

  if (cmd.requires_tts_confirm) {
    document.getElementById('overlay-text').textContent = cmd.confirm_prompt || "Please confirm.";
    document.getElementById('overlay').classList.remove('hidden');
    speakTTS(cmd.confirm_prompt);
    window.pendingConfirmationCmd = cmd;
    return;
  }
  
  if (action === "submit_confirm") {
    document.getElementById('overlay').classList.add('hidden');
    if (window.pendingConfirmationCmd && window.pendingConfirmationCmd.intent === "submit_exam") {
        submitExam();
    } else if (window.pendingConfirmationCmd) {
        const execCmd = {...window.pendingConfirmationCmd, requires_tts_confirm: false};
        window.pendingConfirmationCmd = null;
        executeCommand(execCmd);
    } else {
        submitExam(); // fallback if called directly
    }
    return;
  } else if (action === "submit_cancel" || action === "cancel_submit") {
    document.getElementById('overlay').classList.add('hidden');
    window.pendingConfirmationCmd = null;
    speakTTS("Action cancelled");
    return;
  }

  let navigated = false;
  if (action === "nav_next" && currentQuestionIndex < questions.length - 1) {
    setCurrentQuestionIndex(currentQuestionIndex + 1);
    navigated = true;
  } else if (action === "nav_prev" && currentQuestionIndex > 0) {
    setCurrentQuestionIndex(currentQuestionIndex - 1);
    navigated = true;
  } else if (action === "nav_goto" && target) {
    const idx = questions.findIndex(q => q.q_number === target);
    if (idx !== -1) {
      setCurrentQuestionIndex(idx);
      navigated = true;
    }
  } else if (action === "nav_first") {
    setCurrentQuestionIndex(0);
    navigated = true;
  } else if (action === "nav_last") {
    setCurrentQuestionIndex(questions.length - 1);
    navigated = true;
  }
  
  if (navigated) {
    renderQuestion(currentQuestionIndex);
    executeCommand("read_question");
    return;
  }

  if (action === "read_question" && questions.length > 0) {
    speakTTS(questions[currentQuestionIndex].text);
  } else if (action === "read_answer" && qid) {
    speakTTS(answers[qid] || "No answer dictated yet.");
  } else if (action === "read_last_line" && qid) {
    if (answers[qid]) {
        let parts = answers[qid].split('.').filter(p => p.trim().length > 0);
        speakTTS(parts.length > 0 ? parts[parts.length - 1] : "No sentence found");
    }
  } else if (action === "repeat_last") {
    // Optional: implement retry of last TTS. Ignored for now.
  }

  if (action === "check_time") {
      const timerText = document.getElementById('timer').textContent;
      speakTTS(`Time remaining: ${timerText}`);
  } else if (action === "check_question") {
      speakTTS(`You are on question ${currentQuestionIndex + 1}`);
  } else if (action === "check_marks" && questions.length > 0) {
      speakTTS(`This question is worth ${questions[currentQuestionIndex].marks} marks`);
  } else if (action === "check_total") {
      speakTTS(`There are ${questions.length} questions in total`);
  }

  if (["clear_answer", "delete_last_line", "delete_last_word", "delete_last_N"].includes(action) && qid) {
      import('./main.js').then(m => m.pushUndoState(qid));
  }

  if (action === "clear_answer" && qid) {
    setAnswers(qid, "");
    renderQuestion(currentQuestionIndex);
    speakTTS("Answer cleared");
  } else if (action === "delete_last_line" && qid) {
    if (answers[qid]) {
      let parts = answers[qid].split('.').filter(p => p.trim().length > 0);
      parts.pop();
      setAnswers(qid, parts.length > 0 ? parts.join('.') + '.' : "");
      renderQuestion(currentQuestionIndex);
      speakTTS("Last sentence deleted");
    }
  } else if (action === "delete_last_word" && qid) {
    if (answers[qid]) {
      let parts = answers[qid].trim().split(' ');
      parts.pop();
      setAnswers(qid, parts.join(' '));
      renderQuestion(currentQuestionIndex);
      speakTTS("Last word deleted");
    }
  } else if (action === "delete_last_N" && qid && target) {
    if (answers[qid]) {
      let parts = answers[qid].trim().split(' ');
      parts = parts.slice(0, Math.max(0, parts.length - target));
      setAnswers(qid, parts.join(' '));
      renderQuestion(currentQuestionIndex);
      speakTTS(`Last ${target} words deleted`);
    }
  } else if (action === "undo" && qid) {
      import('./main.js').then(m => {
          m.popUndoState(qid);
          renderQuestion(currentQuestionIndex);
          speakTTS("Undo completed");
      });
  }

  if (action === "submit_exam" || action === "submit") {
    document.getElementById('overlay-text').textContent = "To confirm submission, please say exactly: I confirm submit.";
    document.getElementById('overlay').classList.remove('hidden');
    speakTTS("To confirm submission, please say exactly: I confirm submit.");
    window.pendingConfirmationCmd = { intent: "submit_exam" };
  }
}

async function submitExam() {
  document.getElementById('overlay').classList.remove('hidden');
  document.getElementById('overlay-text').classList.add('hidden');
  document.getElementById('cancel-submit-btn').classList.add('hidden');
  document.getElementById('submission-spinner').classList.remove('hidden');
  
  try {
    const res = await fetch(`/api/session/${sessionStorage.getItem('session_id')}/submit`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ answers: answers })
    });
    
    if (res.ok) {
      const data = await res.json();
      stopSpeechStream();
      document.getElementById('overlay').classList.add('hidden');
      document.getElementById('app-container').classList.add('hidden');
      document.getElementById('success-screen').classList.remove('hidden');
      document.getElementById('download-pdf-link').href = data.pdf_url;
      document.getElementById('success-session-id').textContent = `Session: ${sessionStorage.getItem('session_id')}`;
      speakTTS("Your exam has been submitted successfully. Thank you.");
    }
  } catch (err) {
    console.error(err);
    alert("Submission failed!");
    document.getElementById('overlay').classList.add('hidden');
  }
}

export function updateTimerDisplay(seconds) {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  document.getElementById('timer').textContent = `${m}:${s}`;
}

export function updatePending(text) {
  document.getElementById('pending-text').textContent = text + "...";
}

export function clearPending() {
  const el = document.getElementById('pending-text');
  if (el) el.textContent = "";
}

function showCommandFeedback(cmdString) {
  const fb = document.getElementById('command-feedback');
  if(!fb) return;
  fb.textContent = `Command: ${cmdString} ✓`;
  fb.classList.remove('hidden');
  setTimeout(() => fb.classList.add('hidden'), 2000);
}

export function setWSStatus(text, state) {
  const el = document.getElementById('ws-status');
  if(el) el.textContent = text;
}

export function setVADStatus(isActive) {
  const dot = document.getElementById('mic-dot');
  if (!dot) return;
  if (isActive) {
    dot.classList.add('active');
    document.getElementById('mic-label').textContent = 'Listening...';
  } else {
    dot.classList.remove('active');
    document.getElementById('mic-label').textContent = 'Mic Ready';
  }
}

export function logDebug(msg) {
  console.log(`[UI] ${msg}`);
}

// Button listeners
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-next').onclick = () => executeCommand('nav_next');
  document.getElementById('btn-prev').onclick = () => executeCommand('nav_prev');
  document.getElementById('cancel-submit-btn').onclick = () => executeCommand('submit_cancel');
});

// Phase 2 UI Functions
export function renderWaitingRoom() {
  const container = document.getElementById('app-container');
  const d = new Date();
  const dateStr = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric' });
  
  container.innerHTML = `
    <header>
        <div class="header-left">
            <h2 id="course-code">${examMeta.course_code}</h2>
            <h1 id="subject">${examMeta.subject}</h1>
        </div>
        <div class="header-right">
            <div class="status-badge" id="exam-status">Onboarding</div>
            <div id="timer" class="timer">Waiting</div>
        </div>
    </header>
    <main style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding: 48px; background: white; margin: 24px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
        <h1 style="color: #0a1628; margin-bottom: 8px; font-size: 2rem;">${examMeta.subject}</h1>
        <h2 style="color: #6b7280; margin-bottom: 24px;">${examMeta.course_code}</h2>
        <p style="font-size: 1.1rem; color: #4b5563; margin-bottom: 8px;">Maximum Marks: <strong>${examMeta.total_marks}</strong></p>
        <p style="font-size: 1.1rem; color: #4b5563; margin-bottom: 8px;">Duration: <strong>${examMeta.duration_minutes} minutes</strong></p>
        <p style="font-size: 1.1rem; color: #4b5563; margin-bottom: 32px;">Date: <strong>${dateStr}</strong></p>
        
        <div style="background: #f9fafb; padding: 24px; border-radius: 8px; border: 1px solid #e5e7eb; width: 100%; max-width: 500px; text-align: left;">
            <h3 style="margin-bottom: 16px; color: #2563eb; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px;">Registration Status</h3>
            <p style="margin-bottom: 8px;"><strong>Name:</strong> <span id="reg-name">—</span></p>
            <p style="margin-bottom: 8px;"><strong>Register No:</strong> <span id="reg-no">—</span></p>
            <p style="margin-top: 16px; color: #6b7280; font-style: italic;" id="reg-badge">Status: Onboarding</p>
        </div>
        
        <div style="margin-top: 48px; text-align: center;">
            <div id="mic-dot" class="mic-dot"></div>
            <span id="mic-label" style="display:block; margin-top:12px; color: #6b7280; font-weight: bold;">Listening...</span>
            <div id="command-feedback" class="toast hidden"></div>
            <span id="pending-text" style="color: #9ca3af; font-style: italic; display:block; margin-top:8px;"></span>
        </div>
    </main>
  `;
  
  runOnboardingSequence();
}

function playTone() {
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const osc = audioCtx.createOscillator();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(440, audioCtx.currentTime);
  osc.connect(audioCtx.destination);
  osc.start();
  osc.stop(audioCtx.currentTime + 0.3);
}

function runOnboardingSequence() {
  const utterances = [
    `Welcome to the AI Scribe examination system. I will be your digital scribe for today's examination in ${examMeta.subject}, course code ${examMeta.course_code}. The maximum marks are ${examMeta.total_marks}. The duration is ${examMeta.duration_minutes} minutes.`,
    "This system will transcribe everything you speak into your answer. You can navigate entirely using your voice. Here are the commands available to you.",
    "For navigation: say Next question to go forward. Say Previous question to go back. Say Go to question followed by a number to jump directly.",
    "For reviewing: say Read question to hear the current question again. Say Read my answer to hear what you have dictated so far.",
    "For editing: say Delete last sentence to remove your last sentence. Say Clear answer to erase your entire answer for the current question.",
    "To submit your exam when you are finished: say Submit exam. You will be asked to confirm with a specific phrase before submission is finalised.",
    "Important: this session is being recorded for audit purposes. Your voice, screen, and all transcriptions are logged. Speak clearly and at a natural pace.",
    "We will now register your details. Please state your full name clearly after the tone."
  ];

  let idx = 0;
  function speakNext() {
    if (idx < utterances.length) {
      speakTTS(utterances[idx], speakNext);
      idx++;
    } else {
      playTone();
      setState(STATE.REGISTRATION);
      registrationPhase = "name";
      document.getElementById('exam-status').textContent = 'Registering';
      document.getElementById('reg-badge').textContent = 'Status: Registering';
    }
  }
  speakNext();
}

export function handleRegistrationVoice(phase, value) {
  if (phase === "name") {
    setRegistrationPhaseData('name', value);
    document.getElementById('reg-name').textContent = value;
    speakTTS(`Got it. I heard: ${value}. Please state your register number.`, () => {
      playTone();
      registrationPhase = "reg_no";
    });
  } else if (phase === "reg_no") {
    setRegistrationPhaseData('reg_no', value);
    document.getElementById('reg-no').textContent = value;
    
    // Server expects name and reg_no, websocket.js handles sending
    sendMessage({ "type": "register", "name": studentName, "reg_no": value });
    
    speakTTS(`Thank you, ${studentName}. Your register number ${value} has been noted.`, () => {
      registrationPhase = "ready";
      speakTTS("When you are ready, say: I am ready to start the exam.");
    });
  }
}

export function confirmRegistrationStatus() {
  const el = document.getElementById('reg-badge');
  if (el) el.innerHTML = 'Status: Confirmed &#10003;';
}

export function handleStudentReady() {
  speakTTS("Details confirmed. Please wait while the invigilator starts the examination.");
  setState(STATE.WAITING);
  document.getElementById('exam-status').textContent = 'Waiting';
  const el = document.getElementById('reg-badge');
  if(el) {
    el.innerHTML = 'Status: Waiting for Exam to Start';
    el.style.animation = 'pulse 2s infinite';
  }
}

export function renderCountdown() {
  const container = document.getElementById('app-container');
  container.innerHTML = `
    <div style="position: fixed; inset: 0; background: #0a1628; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white;">
      <h1 id="countdown-number" style="font-size: 15rem; margin: 0; padding: 0;">3</h1>
    </div>
  `;
  
  speakTTS("3", () => {
    document.getElementById('countdown-number').textContent = "2";
    speakTTS("2", () => {
      document.getElementById('countdown-number').textContent = "1";
      speakTTS("1", () => {
        document.getElementById('countdown-number').textContent = "Begin";
        speakTTS("Begin.", () => {
          startExam();
        });
      });
    });
  });
}

export function startExam() {
  setState(STATE.EXAM);
  
  // Restore the 3-panel layout
  const container = document.getElementById('app-container');
  container.innerHTML = `
    <header>
        <div class="header-left">
            <h2 id="course-code"></h2>
            <h1 id="subject"></h1>
        </div>
        <div class="header-right">
            <div class="status-badge" id="exam-status">Active</div>
            <div id="timer" class="timer">--:--</div>
        </div>
    </header>
    
    <main class="panels">
        <!-- Question Panel -->
        <section class="panel question-panel">
            <div class="panel-header">
                <span class="part-badge" id="q-part">Part A</span>
                <span class="q-progress" id="q-progress">Q1/5</span>
                <span class="q-marks" id="q-marks">[2 marks]</span>
            </div>
            <div class="panel-body">
                <p id="q-text" class="question-text">Loading question...</p>
                <!-- Image goes here if any -->
            </div>
        </section>

        <!-- Answer Panel -->
        <section class="panel answer-panel">
            <div class="panel-header">
                <h3>Your Answer</h3>
            </div>
            <div class="panel-body answer-body">
                <p class="answer-text">
                    <span id="committed-text"></span><span id="pending-text" class="pending-text"></span>
                </p>
            </div>
        </section>
    </main>

    <!-- Status Footer -->
    <footer>
        <div class="footer-left">
            <div id="mic-dot" class="mic-dot"></div>
            <span id="mic-label">Mic Ready</span>
        </div>
        <div class="footer-center">
            <button class="nav-btn" id="btn-prev">◀ Previous</button>
            <button class="nav-btn" id="btn-next">Next ▶</button>
        </div>
        <div class="footer-right">
            <span id="ws-status">Connected</span>
        </div>
    </footer>
    <div id="command-feedback" class="toast hidden"></div>
  `;
  
  // Reattach listeners
  document.getElementById('btn-next').onclick = () => executeCommand('nav_next');
  document.getElementById('btn-prev').onclick = () => executeCommand('nav_prev');
  
  renderQuestion(0);
  startExamTimer();
  
  setTimeout(() => {
    speakTTS(questions[0].text, () => {
      speakTTS("Say 'submit exam' when you have completed all questions.");
    });
  }, 1000);
}
