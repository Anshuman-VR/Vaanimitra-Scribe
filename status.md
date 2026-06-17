# AI Scribe - Single Source of Truth (SSOT)

## Branch Context
**Active Branch:** `LLM-Integration`
**All changes must be confined to this branch to protect the working demo.**

## Complete Context of Work So Far
We have successfully implemented the core infrastructure for an LLM-powered Natural Language Processing (NLP) pipeline within the AI Scribe system. This pipeline replaces the previous brittle string-matching logic and allows for robust voice-command routing.

### Core Achievements
1. **Server-Authoritative Navigation & UI**
   - The frontend (`client/js/main.js`, `client/js/ui.js`) now strictly relies on the backend to maintain state, handle undo stacks, and trigger navigation. 
   - We implemented a comprehensive command taxonomy (`COMMAND_LEXICON`) that supports complex actions like `delete_last_N`, `check_time`, `nav_goto`, etc.
   - Destructive commands trigger a TTS confirmation overlay (e.g. "Did you say: submit exam?").

2. **Context-Aware WebSocket Architecture**
   - The websocket bridge now bundles a rich `SessionContext` with every audio chunk.
   - Context includes: `session_id`, `question_index`, `total_questions`, `answer_word_count`, `last_utterances`, and `exam_state`.
   - This provides the backend LLM with critical spatial and temporal awareness to properly classify intents.

3. **LLM Integration via Ollama**
   - We set up a local `Qwen2.5:3b-instruct` instance running via Ollama on a dedicated port (`45881`) to prevent collisions on the HPC.
   - The backend `IntentPipeline` queries this model asynchronously with strict JSON constraints, acting as a smart intent classifier for utterances that are ambiguous.

4. **Dynamic GPU Allocation**
   - `start.sh` was rewritten to dynamically poll `nvidia-smi` and automatically assign `CUDA_VISIBLE_DEVICES` to the GPU with the most free memory.

## TODOs & Fixes Required Now
The current pipeline crashes on the rapidfuzz import, and the onboarding state machine is currently broken because it still relies on naive transcript assignments.

### 1. Fix RapidFuzz Import Bug
- `module 'rapidfuzz.fuzz' has no attribute 'distance'`
- Must update `server/pipeline.py` to correctly use `from rapidfuzz.distance import Levenshtein`.

### 2. Implement the Bulletproof Dual-Command System
We need a robust, two-tier classification pipeline:
- **Tier 1 (Fuzzy Prefix):** Use fuzzy matching to detect the wake word (e.g., "Vaani" or "Vani"). Since Whisper transcribes the name inconsistently, we cannot rely on exact string matching.
- **Tier 2 (LLM Inference):** A robust LLM-based inference mechanism. The LLM must infer what the person said based on the raw utterance, the current context of the transcript, and the state of the exam.

### 3. Expand LLM Usage to All Heuristic Bottlenecks
Now that the LLM is integrated, we should use it everywhere that relying on raw transcripts is insufficient:
- **Onboarding:** Route the registration audio (name and register number) through the LLM to extract the exact details (e.g., "My name is John" -> "John"). Determine if the student is ready to start based on LLM inference, not exact phrase matching.
- **Destructive Actions:** Use the LLM to confidently parse intents for submitting, deleting specific word counts, and undoing operations.

## Instructions for Next Agent
**CRITICAL:** You must plan thoroughly before execution. The state-machine changes required to route Onboarding through the LLM have significant frontend and backend implications. Outline your plan, verify the logic, and only execute once confident. **Keep all changes confined strictly to the `LLM-Integration` branch.**
