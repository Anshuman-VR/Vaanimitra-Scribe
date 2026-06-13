/**
 * AI Scribe - WebSocket Management Module
 * Handles connections to the server for transcription and commands.
 */

import { setWSStatus, logDebug, updatePending, commitPending, clearPending, showCommand, updateStats } from './ui.js';
import { isSpeaking } from './audio.js';

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
      case 'transcript':
        commitPending(msg.text, msg.words);
        updateStats(msg.inference_ms, true);
        break;
      case 'command':
        clearPending();
        showCommand(msg.action, msg.raw);
        updateStats(msg.inference_ms, true);
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

export function sendAudioChunk(float32Array) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    logDebug('WS not open - dropping audio chunk');
    return;
  }
  ws.send(float32Array.buffer);
  logDebug(`Sent ${float32Array.length} samples`);
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
