/**
 * AI Scribe - Audio Management Module
 * Handles MicVAD initialization and streaming audio capture.
 */

import { setVADStatus, logDebug, clearPending } from './ui.js';
import { sendAudioChunk, sendInterimChunk, sendMessage } from './websocket.js';
import { getCurrentQuestionId } from './main.js';

export let micVad = null;

// Streaming Audio Capture State
let audioCtxStream = null;
let scriptProcessor = null;
let speechBuffer = [];
let speakingForStream = false;
let streamingTimer = null;

// ── VAD Initialization ───────────────────────────────────────────────────

export async function initVAD(vadCfg) {
  logDebug('Loading onnxruntime-web...');
  const ort = await import('/static/ort.wasm.bundle.min.mjs');
  
  ort.env.wasm.wasmPaths = '/static/';
  if (typeof SharedArrayBuffer === 'undefined') {
    ort.env.wasm.numThreads = 1;
    logDebug('SharedArrayBuffer unavailable - using single-threaded WASM');
  }
  window.ort = ort;

  logDebug('Loading vad-web bundle...');
  await new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/static/bundle.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('Failed to load bundle.min.js'));
    document.head.appendChild(s);
  });

  const { MicVAD } = window.vad;
  if (!MicVAD) throw new Error('MicVAD not found after bundle load');

  logDebug('Requesting microphone access...');
  micVad = await MicVAD.new({
    workletURL:       '/static/vad.worklet.bundle.min.js',
    model:            'v5',
    baseAssetPath:    '/static/',
    onnxWASMBasePath: '/static/',

    positiveSpeechThreshold: vadCfg.positiveSpeechThreshold,
    negativeSpeechThreshold: vadCfg.negativeSpeechThreshold,
    redemptionFrames:        vadCfg.redemptionFrames,
    preSpeechPadFrames:      vadCfg.preSpeechPadFrames,
    minSpeechFrames:         vadCfg.minSpeechFrames,

    onSpeechStart: () => {
      setVADStatus(true);
      startSpeechStream();
    },

    onSpeechEnd: (audio) => {
      stopSpeechStream();
      setVADStatus(false);
      
      const qid = getCurrentQuestionId();
      if (qid) {
        sendMessage({ "type": "set_question", "question_id": qid });
      }
      
      import('./main.js').then(m => {
        const ctx = m.getSessionContext();
        sendAudioChunk(audio, ctx);
      });
    },

    onVADMisfire: () => {
      stopSpeechStream();
      clearPending();
      setVADStatus(false);
      logDebug('VAD misfire - ignored');
    },
  });

  logDebug('MicVAD ready');
}

export function isSpeaking() {
  return speakingForStream;
}

// ── Streaming Audio Capture ───────────────────────────────────────────────

export async function initStreamCapture() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: 16000,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    }
  });

  audioCtxStream = new AudioContext({ sampleRate: 16000 });
  const source = audioCtxStream.createMediaStreamSource(stream);

  scriptProcessor = audioCtxStream.createScriptProcessor(4096, 1, 1);
  scriptProcessor.onaudioprocess = (e) => {
    if (!speakingForStream) return;
    speechBuffer.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  };

  source.connect(scriptProcessor);
  scriptProcessor.connect(audioCtxStream.destination);
  logDebug('Stream audio capture ready');
}

function startSpeechStream() {
  speechBuffer = [];
  speakingForStream = true;
  streamingTimer = setInterval(() => {
    const combined = getCombinedAudioChunk();
    if (combined) {
      sendInterimChunk(combined);
      
      // Prevent massive buffer clogging: Force commit every 8 seconds of continuous speech
      if (combined.length >= 16000 * 8) {
        import('./main.js').then(m => {
          const ctx = m.getSessionContext();
          sendAudioChunk(combined, ctx);
        });
        speechBuffer = []; // reset buffer
        clearPending();
      }
    }
  }, 500);
}

export function stopSpeechStream() {
  speakingForStream = false;
  clearInterval(streamingTimer);
  streamingTimer = null;
  speechBuffer = [];
}

function getCombinedAudioChunk() {
  if (speechBuffer.length === 0) return null;

  const totalLen = speechBuffer.reduce((s, b) => s + b.length, 0);
  if (totalLen < 16000 * 0.3) return null;

  const capLen = Math.min(totalLen, 16000 * 25);
  const combined = new Float32Array(capLen);
  let offset = 0;
  for (const chunk of speechBuffer) {
    const take = Math.min(chunk.length, capLen - offset);
    combined.set(chunk.subarray(0, take), offset);
    offset += take;
    if (offset >= capLen) break;
  }
  return combined;
}

export function cleanupAudio() {
  stopSpeechStream();
  if (micVad) { micVad.pause(); micVad = null; }
  if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
  if (audioCtxStream) { audioCtxStream.close(); audioCtxStream = null; }
}
