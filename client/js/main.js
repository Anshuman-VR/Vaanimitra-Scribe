/**
 * AI Scribe - Main Application Entry
 * Orchestrates initialization and ties modules together.
 */

import { initVAD, initStreamCapture, cleanupAudio } from './audio.js';
import { connectWS, connectStreamWS, cleanupWebSockets, setSessionActive } from './websocket.js';
import { logDebug, setButtonState, setWSStatus, clearPending, setVADStatus } from './ui.js';

let isStarted = false;

async function initSession() {
  if (isStarted) return;
  setButtonState(false, true); // Loading state

  try {
    logDebug('Fetching VAD config...');
    const cfgResp = await fetch('/config');
    const vadCfg = await cfgResp.json();
    logDebug('VAD config loaded.');

    await initVAD(vadCfg);

    setSessionActive(true);
    connectWS();
    connectStreamWS();

    await initStreamCapture();

    // Start VAD listening
    import('./audio.js').then(({ micVad }) => {
      micVad.start();
    });

    isStarted = true;
    setButtonState(true);
    logDebug('Session started - live dictation active');

  } catch (err) {
    logDebug(`Init failed: ${err.message}`);
    console.error('[AI Scribe] Init error:', err);
    setButtonState(false);
  }
}

function stopSession() {
  if (!isStarted) return;

  setSessionActive(false);
  cleanupAudio();
  cleanupWebSockets();
  clearPending();

  isStarted = false;
  setButtonState(false);
  setWSStatus('Disconnected', '');
  setVADStatus(false);
  logDebug('Session stopped');
}

// ── Event Listeners ───────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('startBtn');
  btn.addEventListener('click', () => {
    if (!isStarted) initSession();
    else stopSession();
  });
});
