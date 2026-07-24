---
tags:
  - data-flow
  - state-machine
  - websocket
  - nlp
---
# Vaanimitra Scribe: Data Flow & State Management

## 1. The Dual WebSocket Architecture
The system employs two parallel WebSocket connections per student to achieve both real-time feedback and high-accuracy transcription without latency bottlenecks.

### 1.1 Command & Control WebSocket (`wss://[host]/ws`)
**Purpose**: Final text processing, system commands, and state synchronization.
- **Trigger**: Fired when Silero VAD triggers `onSpeechEnd`.
- **Payload**: Raw Float32 PCM audio bytes (plus a JSON wrapper if contextual data is attached).
- **Processing Engine**: `faster-whisper` with `beam_size=5` (for maximum accuracy).
- **Pipeline**: Audio → Text → NLP Classifier (Heuristics + LLM) → Command or Transcript.
- **Latency**: ~300-800ms depending on sentence length.

### 1.2 Live Interim Streaming WebSocket (`wss://[host]/ws/stream`)
**Purpose**: Real-time visual feedback ("typing" effect) while the student is still speaking.
- **Trigger**: Fired continuously every 500ms while Silero VAD is active (`speakingForStream = true`).
- **Payload**: Raw Float32 PCM audio bytes (cumulative buffer).
- **Processing Engine**: `faster-whisper` with `beam_size=1` (for maximum speed).
- **Latency**: ~50-150ms.
- **UI Update**: Result is rendered immediately into the `#pending-text` DOM element. Not persisted to DB.

---

## 2. Audio Processing & Transcription Flow
1. **Microphone Capture**: `audioCtxStream` captures raw microphone input at 16kHz mono.
2. **VAD Filtering (Client)**: Silero VAD (running via WASM) processes frames locally. 
   - Non-speech noise (coughing, paper shuffling) is discarded client-side, saving immense server bandwidth and GPU cycles.
3. **Transmission**: Upon detecting a pause (`onSpeechEnd`), the buffered audio chunk is sent to the server.
4. **Whisper Transcription**: `Transcriber.transcribe()` passes the float32 bytes directly to the loaded CTranslate2 model in VRAM (zero disk I/O) on the [[01_architecture_and_deployment|HPC Infrastructure]].
5. **Intent Pipeline**: The resulting text is passed to `IntentPipeline.process()`.

---

## 3. The Intent Pipeline (NLP Routing)
Because the system has no physical buttons, every utterance must be classified as either **Exam Content (Transcript)** or a **System Command**.

### Stage 1: Wake Word Detection
If the text begins with "Vaani" (or a known phonetic mis-transcription like "Wani", "Bonnie", "Vanny", evaluated via Levenshtein distance), the prefix is stripped, and the remainder is flagged with `vaani_prefix_detected = True`.

### Stage 2: Heuristic Classification (Fast Path)
The pipeline checks for domain phrases (e.g., "therefore", "differentiating") which immediately classify the text as a **Transcript**. 
It also uses `rapidfuzz` to match the text against a `COMMAND_LEXICON`. If the score is >88, it's immediately classified as a **Command**.

### Stage 3: LLM Classification (Deep Path)
If heuristics are inconclusive, the utterance is sent to the local Qwen 2.5 LLM.
- **Prompt Formulation**: The LLM is provided the utterance, the current question number, and the last two utterances for context.
- **Strict Fencing**: The LLM is instructed to output strictly JSON (`{"type": "command", "intent": "..."}` or `{"type": "transcript"}`). If there is *any* doubt, the LLM falls back to "transcript" to prevent accidental command execution.

---

## 4. State Management Lifecycle
The exam flow operates strictly through a series of server-enforced states.

### 4.1 Client `STATE` Enum
`PRE_ONBOARDING` → `ONBOARDING` → `REGISTRATION` → `WAITING` → `COUNTDOWN` → `EXAM`

### 4.2 Flow Sequence
1. **Pre-Onboarding**: Terminal booted. Student sits down. UI shows "Waiting for Invigilator".
2. **Start Onboarding**: Admin clicks "Start Onboarding". Server sets Exam Status to `onboarding` and broadcasts `start_onboarding` to all WS clients.
3. **Onboarding Sequence**: Client transitions to `ONBOARDING`. Vaani reads instructions via TTS.
4. **Registration (Lookup & Confirm)**: 
   - State shifts to `REGISTRATION`. 
   - Vaani asks for Register Number. Student speaks number. Audio sent to WS → Transcribed → Client sends `lookup_student` to server.
   - Server looks up the number in the `students` DB table and returns the student's name.
   - Vaani speaks the name and asks the student to confirm ("Yes" or "No").
   - The confirmation is processed by the intent pipeline. Upon success, registration is confirmed.
5. **Waiting Room**: Client enters `WAITING` state. UI shows "Waiting for Exam to Start".
6. **Start Exam**: Admin clicks "Start Exam". Server sets Exam Status to `active` and broadcasts `exam_started`.
7. **Countdown & Execution**: Client runs 3-2-1 countdown, then transitions to `EXAM`. Only now are commands like "Next question" or answer dictation accepted by the pipeline.

### 4.3 Late Joiner & Reconnect Resilience
Because state is persisted in the SQLite DB (see [[03_api_and_database|Database Schema]]) and the browser uses persistent `localStorage` for the `session_id`:
- On WS connect, the server queries the DB for `exam.status` and checks if the `session_id` belongs to an already registered student.
- The server broadcasts an `exam_load` packet with an `is_registered` boolean flag.
- If the student is already registered and the exam is `active`, the client instantly jumps to the `EXAM` state, restoring their answers and the exact server-authoritative timer.
- If it's a completely new unregistered student joining an already `active` exam, they are automatically placed into the `ONBOARDING` flow, after which they will seamlessly drop into the active exam.
This global state sync guarantees robust error recovery across browser crashes and network drops.

---
## 🔗 Related Documents
- [[Index|Home (Master Index)]]
- [[01_architecture_and_deployment|Architecture & Deployment]]
- [[03_api_and_database|API & Database Reference]]
