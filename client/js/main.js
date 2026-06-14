import { initStreamCapture, initVAD } from './audio.js';
import { connectWS, connectStreamWS, sendMessage } from './websocket.js';
import { renderQuestion, executeCommand, updateTimerDisplay, updatePending } from './ui.js';

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

export function handleTranscript(text) {
  if (appState === STATE.REGISTRATION) {
    import('./ui.js').then(ui => ui.handleRegistrationVoice(text));
    return;
  }
  
  if (appState !== STATE.EXAM) return;

  const qid = getCurrentQuestionId();
  if (!qid) return;
  
  if (answers[qid]) {
    answers[qid] += " " + text;
  } else {
    answers[qid] = text;
  }
  
  renderQuestion(currentQuestionIndex);
  sendMessage({ type: "set_question", question_id: qid });
}

export function handleCommand(cmd) {
  if (appState === STATE.REGISTRATION || appState === STATE.ONBOARDING || appState === STATE.WAITING) {
    const action = cmd.action || cmd;
    if (action === "student_ready") {
      import('./ui.js').then(ui => ui.handleStudentReady());
    }
    return;
  }
  
  if (appState !== STATE.EXAM) return;
  executeCommand(cmd);
}

export function speakTTS(text, onend = null) {
  window.speechSynthesis.cancel();
  const ut = new SpeechSynthesisUtterance(text);
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
