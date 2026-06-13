/**
 * AI Scribe - UI Management Module
 * Handles all DOM manipulation and rendering.
 */

let wordCount = 0;
let chunkCount = 0;

// Command label map
const CMD_LABELS = {
  nav_next:       '→ Next question',
  nav_prev:       '← Previous question',
  nav_goto:       '⤳ Go to question',
  read_question:  '📖 Reading question',
  read_answer:    '📖 Reading your answer',
  clear_answer:   '🗑 Answer cleared',
  delete_last:    '↩ Last sentence deleted',
};

// ── Status Updates ────────────────────────────────────────────────────────

export function setWSStatus(label, stateClass) {
  document.getElementById('wsLabel').textContent = label;
  document.getElementById('wsDot').className = 'dot ' + (stateClass || '');
}

export function setVADStatus(speaking) {
  document.getElementById('vadDot').className = 'dot' + (speaking ? ' speaking' : '');
  document.getElementById('vadLabel').textContent = speaking ? 'Speaking detected...' : 'Listening for speech...';
}

export function logDebug(msg) {
  const el = document.getElementById('logPreview');
  const t = new Date().toLocaleTimeString('en-GB', { hour12: false });
  el.textContent = `[${t}] ${msg}`;
  console.log(`[AI Scribe] ${msg}`);
}

export function updateStats(inference_ms, newChunk = false) {
  document.getElementById('statInf').textContent = `Inference: ${inference_ms} ms`;
  if (newChunk) {
    chunkCount++;
    document.getElementById('statChunks').textContent = `Chunks: ${chunkCount}`;
  }
}

// ── Transcript Rendering ──────────────────────────────────────────────────

function _getBox() {
  const box = document.getElementById('transcript');
  if (box.querySelector('.placeholder')) box.innerHTML = '';
  return box;
}

function getPendingSpan() {
  const box = _getBox();
  let p = box.querySelector('.pending');
  if (!p) {
    p = document.createElement('span');
    p.className = 'sent pending';
    box.appendChild(p);
  }
  return p;
}

export function updatePending(text) {
  const p = getPendingSpan();
  p.textContent = text + '...';
  p.parentElement.scrollTop = p.parentElement.scrollHeight;
}

export function commitPending(text, words) {
  const box = _getBox();
  const existing = box.querySelector('.pending');

  const p = document.createElement('span');
  p.className = 'sent';

  if (words && words.length > 0) {
    words.forEach(w => {
      const span = document.createElement('span');
      span.className = 'w' + (w.low_confidence ? ' lo' : '');
      span.textContent = w.word + ' ';
      if (w.low_confidence) {
        span.title = `confidence: ${(w.probability * 100).toFixed(0)}%`;
      }
      p.appendChild(span);
    });
    wordCount += words.length;
  } else {
    p.textContent = text + ' ';
    wordCount += text.split(/\s+/).filter(Boolean).length;
  }
  
  document.getElementById('wordCount').textContent = `Words: ${wordCount}`;

  if (existing) box.replaceChild(p, existing);
  else box.appendChild(p);

  box.scrollTop = box.scrollHeight;
}

export function clearPending() {
  const box = document.getElementById('transcript');
  const p = box.querySelector('.pending');
  if (p) p.remove();
}

// ── Command Feedback ──────────────────────────────────────────────────────

let cmdTimer = null;
export function showCommand(action, raw) {
  document.getElementById('cmdText').textContent = `${CMD_LABELS[action] || action}  —  "${raw}"`;
  const bar = document.getElementById('cmdBar');
  bar.classList.add('visible');
  
  clearTimeout(cmdTimer);
  cmdTimer = setTimeout(() => bar.classList.remove('visible'), 4000);
  logDebug(`Command: ${action}`);
}

// ── Button UI ─────────────────────────────────────────────────────────────

export function setButtonState(isStarted, isInit = false) {
  const btn = document.getElementById('startBtn');
  if (isInit) {
    btn.disabled = true;
    btn.textContent = '⏳ Initialising...';
    btn.classList.remove('stopping');
  } else if (isStarted) {
    btn.disabled = false;
    btn.textContent = '🔴 Stop Dictation';
    btn.classList.add('stopping');
  } else {
    btn.disabled = false;
    btn.textContent = 'Start Exam Dictation';
    btn.classList.remove('stopping');
  }
}

// ── Dynamic Question Rendering (Placeholder) ─────────────────────────────

export function renderQuestion(number, text) {
  const area = document.getElementById('questionArea');
  area.innerHTML = `
    <div class="question-item">
      <div class="question-number">Question ${number}</div>
      <div class="question-text">${text}</div>
    </div>
  `;
}
