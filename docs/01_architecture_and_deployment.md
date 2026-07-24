---
tags:
  - architecture
  - deployment
  - hpc
  - compliance
---
# Vaanimitra Scribe: Architecture & Deployment

## 1. System Overview & Goals
**Vaanimitra Scribe** is an AI-powered, voice-controlled examination platform designed specifically for students with disabilities (PwD). It replaces the need for a human scribe by providing an autonomous, highly accurate speech-to-text (STT) interface that allows students to dictate answers, navigate questions, and edit text entirely via voice commands.

### Compliance & Regulatory Context
The system is built to comply with:
- **RPWD Act 2016 (Rights of Persons with Disabilities Act)**: Ensuring equal access to education and examination for students with physical or learning disabilities.
- **UGC Guidelines for Conducting Written Examinations for PwD**:
  - Ensures accurate representation of the student's intent without external human interference.
  - Maintains strict auditability (all voice interactions, commands, and dictated answers are logged).
  - Operates entirely locally (on-premise) to maintain the integrity and confidentiality of the examination process. No data leaves the university network.

---

## 2. High-Level Architecture
The system follows a **Client-Server** architecture with real-time bidirectional communication. It is heavily **Server-Authoritative**, meaning the server maintains the ultimate truth of the exam state, registered students, answers, and audit logs. The client is primarily a "dumb terminal" responsible for audio capture, voice activity detection (VAD), and rendering UI updates instructed by the server.

### 2.1 Technology Stack
- **Frontend (Client)**: 
  - Vanilla HTML/CSS/JS (Zero framework overhead for maximum performance on lower-end devices).
  - `onnxruntime-web`: Runs WebAssembly (WASM) locally in the browser to process audio.
  - `vad-web` (Silero VAD v5): Client-side Voice Activity Detection.
- **Backend (Server)**:
  - `FastAPI` + `Uvicorn`: High-performance asynchronous Python web server.
  - [[02_data_flow_and_state|WebSockets]]: Dual-channel WebSockets for real-time streaming and command/control.
  - `faster-whisper`: Optimized Whisper implementation (CTranslate2) running directly on the GPU for zero-latency transcription.
  - `Ollama` + `Qwen 2.5 (3B Instruct, Q4_K_M)`: Local LLM used strictly for intent classification and command extraction.
- **Database**:
  - `SQLite` (via `aiosqlite` and `SQLAlchemy`): Lightweight, server-local relational database. See [[03_api_and_database|API & Database Reference]].

---

## 3. Server-Authoritative Design
To prevent cheating and ensure consistency, the system enforces a strict server-authoritative model:

1. **State Synchronization**: The client does not independently transition between "Waiting", "Onboarding", or "Exam" states. It waits for WebSocket broadcasts (`start_onboarding`, `exam_started`) from the Admin Dashboard (via the server).
2. **Answer Persistence**: When a student dictates an answer, it is not just stored in the browser. It is immediately committed to the SQLite database (`AnswerSegment` table). If the browser crashes, the server's state is preserved.
3. **Auditability**: Every single audio chunk transcribed (whether it results in an answer, a command, or noise) is logged in the `AuditLog` table with a timestamp, raw text, and classification type.
4. **LLM as an Engine, Not an Oracle**: The LLM is **never** used to answer questions or generate content. It is strictly fenced as an NLP classifier to differentiate between "dictated answer text" and "system voice commands" (e.g., distinguishing the dictated sentence "We move on to the next topic" from the command "Next question").

---

## 4. Deployment Topology (HPC Infrastructure)
Vaanimitra Scribe is deployed on an HPC (High-Performance Computing) cluster using a PBS scheduler.

### 4.1 Hardware & Network
- **HPC Nodes**: 7x NVIDIA H200 GPUs.
- **Jump Host**: `172.16.13.100` (SSH entry point).
- **Target Node**: `dgx-node1` (IP: `172.16.13.91`).
- **Student Network**: Students access the system via the campus LAN directly at `https://172.16.13.91:8765`.
- **Target Scale**: Designed to support 20-50+ concurrent students in a large examination hall.

### 4.2 Port Mappings & Services
| Service | Host | Port | Description |
|---------|------|------|-------------|
| **Ollama** | `127.0.0.1` | `45881` | Serves the Qwen 2.5 3B model. Binds locally; not exposed to LAN. |
| **Uvicorn (FastAPI)** | `0.0.0.0` | `8765` | Main application server. Binds to all interfaces to accept LAN traffic. |

### 4.3 Startup Sequence (`start.sh`)
The server initialization is automated via `start.sh`:
1. **GPU Selection**: Dynamically probes `nvidia-smi` to find the specific H200 GPU with the most free VRAM and sets `CUDA_VISIBLE_DEVICES`.
2. **LLM Preload**: Fires a silent `curl` request to Ollama (`prompt: "Wake up"`, `keep_alive: "15m"`) to ensure the Qwen model is fully loaded into VRAM before the first student connects, preventing latency spikes.
3. **Uvicorn Boot**: Starts the server on port 8765 with a single worker (`--workers 1`), injecting self-signed SSL certificates (`cert.pem`, `key.pem`). HTTPS is mandatory because modern browsers require secure contexts to access the `navigator.mediaDevices.getUserMedia` (Microphone) API.

### 4.4 Model Lifecycle (`main.py` Lifespan)
During FastAPI startup (`@asynccontextmanager lifespan`):
1. SQLite Database is initialized and a demo exam is seeded if empty.
2. `Transcriber()` is instantiated, which synchronously loads the `faster-whisper` (`large-v3`) model onto the GPU.
3. An asyncio background task (`keep_llm_warm`) is spawned, which pings the Ollama instance every 180 seconds. This guarantees the LLM is never evicted from VRAM by Ollama's idle timeouts, ensuring immediate response times for voice commands.

---
## 🔗 Related Documents
- [[Index|Home (Master Index)]]
- [[02_data_flow_and_state|Data Flow & State Management]]
- [[03_api_and_database|API & Database Reference]]
