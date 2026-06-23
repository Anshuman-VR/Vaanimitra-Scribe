<div align="center">
  <img src="https://img.shields.io/badge/Status-Work%20In%20Progress-orange?style=for-the-badge" alt="Status Badge"/>
  <img src="https://img.shields.io/badge/Compliance-RPWD%20Act%202016-blue?style=for-the-badge" alt="Compliance Badge"/>
  <img src="https://img.shields.io/badge/UGC-Guidelines%20Compliant-success?style=for-the-badge" alt="UGC Badge"/>
  <img src="https://img.shields.io/badge/Architecture-Server%20Authoritative-purple?style=for-the-badge" alt="Architecture Badge"/>
  
  <h1>Vaanimitra Scribe</h1>
  <p><strong>Autonomous Examination Platform for Students with Disabilities</strong></p>
</div>

---

## Overview
Vaanimitra Scribe is a voice-controlled examination system designed for students with physical or learning disabilities (PwD). It operates as a direct technological replacement for human scribes, providing a highly accurate, real-time speech-to-text interface. 

The system is architected for university-scale deployment, balancing strict academic integrity controls with accessibility requirements.

## Compliance and Security
The system is developed in adherence to:
- **RPWD Act 2016 (Rights of Persons with Disabilities Act)**
- **UGC Guidelines for Conducting Written Examinations for PwD**

Designed for on-premise deployment, the architecture ensures:
- **Data Sovereignty:** All audio processing and examination records remain within the institutional network.
- **Auditability:** Every acoustic event, voice command, and transcript is logged with timestamps.
- **Accuracy:** Eliminates human error and cognitive bias, ensuring a direct representation of the student's dictated answers.

## Architecture and Features
- **Server-Authoritative State Management:** Hardened server infrastructure prevents client-side state manipulation.
- **Dual WebSocket Streaming:** Parallel connections manage real-time UI feedback and context-aware final transcription processing simultaneously.
- **Client-Side Voice Activity Detection (VAD):** WebAssembly implementations filter non-speech noise at the browser level, reducing server bandwidth and compute overhead.
- **NLP Command Routing:** The natural language processing pipeline distinguishes between dictated examination answers and system navigation commands.
- **Automated Document Generation:** Compiles authenticated, formatted examination scripts in PDF format upon session submission.

## Setup and Deployment
> **Deployment configurations and setup instructions are coming soon.**
> 
> *The system is currently undergoing active development and HPC performance tuning.*
