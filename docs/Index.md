---
tags:
  - index
  - vaanimitra
  - ssot
---
# 🎙️ Vaanimitra Scribe: Master Documentation

Welcome to the **Single Source of Truth (SSOT)** for the Vaanimitra Scribe system. 

This folder contains the complete, interconnected architectural breakdown of the system. You can explore the components using the links below.

## 📚 Core Documentation Modules

### 1. [[01_architecture_and_deployment|Architecture & Deployment]]
Start here for a high-level overview of the system. 
- Covers the core architectural paradigm (Server-Authoritative logic).
- Details the technology stack (FastAPI, Qwen, faster-whisper, Silero VAD).
- Explains the exact deployment topology on the HPC (H200 GPUs, `start.sh` boot sequence, Ollama preload).
- Outlines compliance with the RPWD Act 2016 and UGC Guidelines.

### 2. [[02_data_flow_and_state|Data Flow & State Management]]
Dive into how audio is processed and how the system state evolves.
- Details the dual-websocket audio streaming (`/ws` vs `/ws/stream`).
- Explains the NLP intent pipeline (Wake Word → Heuristics → LLM).
- Maps out the client-server state transitions (Onboarding → Waiting → Exam).

### 3. [[03_api_and_database|API & Database Reference]]
A deep dive into the technical interfaces and persistence layers.
- Full reference for all REST API endpoints (Client and Admin).
- Complete WebSocket JSON message schemas.
- SQLAlchemy Database structure (Exams, Sessions, Audits).
- Overview of the PDF generation architecture.

---
*Generated for internal planning, adversarial analysis, and future AI agent context ingestion.*
