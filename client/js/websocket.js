/**
 * AI Scribe - WebSocket Management Module
 * Handles connections to the server for transcription and commands.
 */

import { setWSStatus, logDebug, updatePending } from './ui.js';
import { isSpeaking } from './audio.js';
import { handleExamLoad, handleTranscript, handleCommand, STATE, getState, setState } from './main.js';

let ws = null;
let wsStream = null;
let wsReconnectTimer = null;
let isSessionActive = false;

const WS_URL = `wss://${location.host}/ws`;
const WS_STREAM_URL = `wss://${location.host}/ws/stream`;

export function setSessionActive(active) {
  isSessionActive = active;
}

// ── Main WebSocket (Committed Text & Commands) ─────────────────────────────

export function connectWS() {
  if (ws && ws.readyState <= WebSocket.OPEN) return;

  let url = WS_URL;
  const sessionId = sessionStorage.getItem('session_id');
  if (sessionId) {
    url += `?session_id=${sessionId}`;
  }

  ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    setWSStatus('Connected', 'connected');
    logDebug('WebSocket connected');
    clearTimeout(wsReconnectTimer);
  };

  ws.onclose = () => {
    setWSStatus('Reconnecting...', 'error');
    logDebug('WebSocket closed - reconnecting in 2s');
    if (isSessionActive) {
      wsReconnectTimer = setTimeout(connectWS, 2000);
    }
  };

  ws.onerror = () => {
    setWSStatus('Connection error', 'error');
    logDebug('WebSocket error');
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    switch (msg.type) {
      case 'session_init':
        sessionStorage.setItem('session_id', msg.session_id);
        logDebug('Session initialized: ' + msg.session_id);
        break;
      case 'exam_load':
        handleExamLoad(msg);
        break;
      case 'exam_waiting':
        // Wait in pre-onboarding, do not render waiting room yet.
        break;
      case 'start_onboarding':
        if (getState() === STATE.PRE_ONBOARDING || getState() === STATE.PENDING) {
          setState(STATE.ONBOARDING);
          import('./ui.js').then(ui => ui.renderWaitingRoom());
        }
        break;
      case 'exam_started':
        if (getState() === STATE.WAITING) {
          setState(STATE.COUNTDOWN);
          import('./ui.js').then(ui => ui.renderCountdown());
        } else if (getState() === STATE.EXAM) {
          // Reconnected student already in exam
        } else if (getState() === STATE.PRE_ONBOARDING || getState() === STATE.PENDING) {
          // Connected late to an active exam! Must register first.
          setState(STATE.ONBOARDING);
          import('./ui.js').then(ui => ui.renderWaitingRoom());
        }
        // If ONBOARDING or REGISTRATION, do nothing! Let them finish registering naturally.
        break;
      case 'register_confirm':
        import('./ui.js').then(ui => ui.confirmRegistrationStatus());
        break;
      case 'transcript':
        handleTranscript(msg.text, msg.words);
        import('./main.js').then(m => m.addUtteranceContext(msg.text));
        // We no longer display words here; UI handles answer string rendering
        break;
      case 'command':
        handleCommand(msg);
        break;
      case 'empty':
        logDebug(`Empty chunk (noise) - ${msg.inference_ms} ms`);
        break;
      case 'error':
        logDebug('Server error: ' + msg.message);
        break;
      default:
        logDebug('Unknown message type: ' + msg.type);
    }
  };
}

function arrayBufferToBase64(buffer) {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

export function sendAudioChunk(float32Array, context = null) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    logDebug('WS not open - dropping audio chunk');
    return;
  }
  
  if (context) {
    const base64Audio = arrayBufferToBase64(float32Array.buffer);
    ws.send(JSON.stringify({
      type: "audio",
      data: base64Audio,
      context: context
    }));
  } else {
    // Fallback for non-contextual binary sends if any
    ws.send(float32Array.buffer);
  }
  logDebug(`Sent ${float32Array.length} samples with context`);
}

export function sendMessage(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify(obj));
}

// ── Stream WebSocket (Live Interim Text) ───────────────────────────────────

export function connectStreamWS() {
  wsStream = new WebSocket(WS_STREAM_URL);
  wsStream.binaryType = 'arraybuffer';

  wsStream.onopen = () => logDebug('Stream WS connected');
  wsStream.onerror = () => logDebug('Stream WS error');
  wsStream.onclose = () => logDebug('Stream WS closed');

  wsStream.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'interim' && msg.text) {
      if (!isSpeaking()) return; // Prevent delayed interim messages from recreating the pending span
      updatePending(msg.text);
    }
  };
}

export function sendInterimChunk(float32Array) {
  if (!wsStream || wsStream.readyState !== WebSocket.OPEN) return;
  wsStream.send(float32Array.buffer);
}

// ── Cleanup ───────────────────────────────────────────────────────────────

export function cleanupWebSockets() {
  clearTimeout(wsReconnectTimer);
  if (ws) { ws.close(); ws = null; }
  if (wsStream) { wsStream.close(); wsStream = null; }
}
