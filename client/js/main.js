import { initStreamCapture, initVAD } from './audio.js';
import { connectWS, connectStreamWS, sendMessage } from './websocket.js';
import { renderQuestion, executeCommand, updateTimerDisplay, updatePending, getRegistrationPhase } from './ui.js';

export const STATE = {
  PRE_ONBOARDING: 'pre_onboarding',
  ONBOARDING: 'onboarding',
  REGISTRATION: 'registration',
  WAITING: 'waiting',
  COUNTDOWN: 'countdown',
  EXAM: 'exam'
};
export let appState = STATE.PRE_ONBOARDING;

export let questions = [];
export let currentQuestionIndex = 0;
export let answers = {};
export let sessionId = null;
export let examMeta = {};
export let studentName = null;
export let studentReg = null;
let timerInterval = null;
let secondsRemaining = 0;

export function getState() { return appState; }
export function setState(newState) { appState = newState; }

export function setRegistrationPhaseData(type, val) {
  if (type === 'name') studentName = val;
  else if (type === 'reg_no') studentReg = val;
}

export function getCurrentQuestionId() {
  if (questions.length === 0) return null;
  return questions[currentQuestionIndex].id;
}

export function setCurrentQuestionIndex(idx) {
  currentQuestionIndex = idx;
}

export function setAnswers(qid, text) {
  answers[qid] = text;
  saveAnswersToStorage();
}

export function saveAnswersToStorage() {
  const sid = sessionStorage.getItem('session_id');
  if (sid) {
    localStorage.setItem(`answers_${sid}`, JSON.stringify(answers));
  }
}

export function loadAnswersFromStorage() {
  const sid = sessionStorage.getItem('session_id');
  if (sid) {
    const saved = localStorage.getItem(`answers_${sid}`);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        Object.assign(answers, parsed);
      } catch(e) {
        console.error("Failed to load answers from storage", e);
      }
    }
  }
}

export let answerHistory = {};

export function pushUndoState(qid) {
  if (!answerHistory[qid]) answerHistory[qid] = [];
  answerHistory[qid].push(answers[qid]);
  if (answerHistory[qid].length > 10) answerHistory[qid].shift();
}

export function popUndoState(qid) {
  if (answerHistory[qid] && answerHistory[qid].length > 0) {
    answers[qid] = answerHistory[qid].pop();
    saveAnswersToStorage();
  }
}

export function handleExamLoad(data) {
  examMeta = {
    subject: data.subject,
    course_code: data.course_code,
    duration_minutes: data.duration_minutes,
    total_marks: data.questions.reduce((sum, q) => sum + q.marks, 0)
  };
  questions = data.questions;
  
  // Init answers
  questions.forEach(q => {
    if (!(q.id in answers)) {
      answers[q.id] = "";
    }
  });
  
  loadAnswersFromStorage();

  // We DO NOT start the timer here anymore.
  // wait for exam_waiting or exam_started from websocket.js
}

export function startExamTimer() {
  secondsRemaining = examMeta.duration_minutes * 60;
  updateTimerDisplay(secondsRemaining);
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    secondsRemaining--;
    updateTimerDisplay(secondsRemaining);
    
    if (secondsRemaining === 300) { // 5 mins
      speakTTS("Five minutes remaining.");
    } else if (secondsRemaining === 60) { // 1 min
      speakTTS("One minute remaining.");
    } else if (secondsRemaining <= 0) {
      clearInterval(timerInterval);
      executeCommand({action: "submit"});
      setTimeout(() => executeCommand({action: "submit_confirm"}), 2000);
    }
  }, 1000);
}

export function handleTranscript(text, words = null) {
  if (appState === STATE.REGISTRATION) {
    import('./ui.js').then(ui => ui.handleRegistrationVoice(text));
    return;
  }
  
  if (appState !== STATE.EXAM) return;

  const qid = getCurrentQuestionId();
  if (!qid) return;
  
  let chunkHtml = text;
  if (words && words.length > 0) {
      chunkHtml = words.map(w => w.low_confidence ? `<span style="color:#ef4444;">${w.word}</span>` : w.word).join('');
  }
  
  if (answers[qid]) {
    answers[qid] += (chunkHtml.startsWith(' ') ? chunkHtml : " " + chunkHtml);
  } else {
    answers[qid] = chunkHtml;
  }
  saveAnswersToStorage();
  
  renderQuestion(currentQuestionIndex);
  sendMessage({ type: "set_question", question_id: qid });
}

export let lastUtterances = [];

export function addUtteranceContext(text) {
  lastUtterances.push(text);
  if (lastUtterances.length > 2) {
    lastUtterances.shift();
  }
}

export function getSessionContext() {
  const qid = getCurrentQuestionId();
  let answerWordCount = 0;
  if (qid && answers[qid]) {
    const text = answers[qid].trim();
    answerWordCount = text ? text.split(/\s+/).length : 0;
  }
  return {
    question_index: currentQuestionIndex,
    total_questions: questions.length,
    answer_word_count: answerWordCount,
    last_utterances: lastUtterances,
    exam_state: appState.toUpperCase(),
    registration_phase: getRegistrationPhase()
  };
}

export function handleCommand(cmd) {
  const intent = cmd.intent || cmd.action || cmd;
  
  if (appState === STATE.REGISTRATION || appState === STATE.ONBOARDING || appState === STATE.WAITING) {
    if (intent === "student_ready") {
      import('./ui.js').then(ui => ui.handleStudentReady());
    } else if (intent === "register_name") {
      import('./ui.js').then(ui => ui.handleRegistrationVoice("name", cmd.target));
    } else if (intent === "register_reg_no") {
      import('./ui.js').then(ui => ui.handleRegistrationVoice("reg_no", cmd.target));
    }
    return;
  }
  
  if (appState !== STATE.EXAM) return;
  executeCommand(cmd);
}

export function speakTTS(text, onend = null) {
  window.speechSynthesis.cancel();
  const cleanText = text.replace(/<[^>]*>?/gm, ''); // Strip HTML tags
  const ut = new SpeechSynthesisUtterance(cleanText);
  ut.rate = 0.9;
  if (onend) ut.onend = onend;
  window.speechSynthesis.speak(ut);
}

window.addEventListener('DOMContentLoaded', () => {
  import('./ui.js').then(ui => ui.renderInvigilatorSetup());
});

export async function startAppConnection() {
  try {
    connectWS();
    connectStreamWS();
    const res = await fetch('/config');
    const vadCfg = await res.json();
    await initStreamCapture();
    await initVAD(vadCfg);
  } catch (err) {
    console.error("Initialization error:", err);
  }
}
