<div align="center">
  <img src="https://img.shields.io/badge/Status-Work%20In%20Progress-orange?style=for-the-badge" alt="Status Badge"/>
  <img src="https://img.shields.io/badge/Compliance-RPWD%20Act%202016-blue?style=for-the-badge" alt="Compliance Badge"/>
  <img src="https://img.shields.io/badge/UGC-Guidelines%20Compliant-success?style=for-the-badge" alt="UGC Badge"/>
  <img src="https://img.shields.io/badge/Architecture-Server%20Authoritative-purple?style=for-the-badge" alt="Architecture Badge"/>
  
  <h1>🎙️ Vaanimitra Scribe</h1>
  <p><strong>Autonomous, Voice-Controlled Examination Platform for Students with Disabilities</strong></p>
</div>

---

## 🌟 Overview
**Vaanimitra Scribe** is an enterprise-grade, fully autonomous examination system engineered to empower students with physical or learning disabilities (PwD). Designed as a direct replacement for traditional human scribes, Vaanimitra provides a highly accurate, real-time speech-to-text (STT) interface.

This system is built from the ground up for **industry adaptation and university-scale deployment**, enforcing strict academic integrity while maximizing accessibility.

## 🏛️ Compliance & Security
Vaanimitra Scribe is developed in strict adherence to:
- **RPWD Act 2016 (Rights of Persons with Disabilities Act)**
- **UGC Guidelines for Conducting Written Examinations for PwD**

By operating entirely **on-premise**, the system ensures:
- **Zero Data Leakage:** All voice processing and exam data remain within the secure university network.
- **Strict Auditability:** Every acoustic event, voice command, and dictated transcript is chronologically logged and preserved.
- **No Human Interference:** Removes the cognitive bias and error-rate of human scribes, providing a 1-to-1 representation of the student's intent.

## 🚀 Key Features
- **Server-Authoritative State Management:** Hardened architecture to prevent client-side manipulation and ensure exam integrity.
- **Zero-Latency Dual WebSockets:** Parallel data streams for real-time visual feedback and deep, context-aware transcription.
- **Edge-Optimized Voice Activity Detection:** `onnxruntime-web` + `Silero VAD` filters non-speech noise directly in the browser.
- **Advanced NLP Command Routing:** Seamlessly distinguishes between dictating an answer (e.g., "Therefore, x equals 5") and system commands (e.g., "Next question").
- **Automated PDF Generation:** Instant compilation of authenticated, formatted examination scripts upon submission.

## 🛠️ Setup & Deployment
> 🚧 **Deployment configurations and setup instructions are coming soon!**
> 
> *The system is currently undergoing active development and HPC performance tuning.*

---
<div align="center">
  <p>Built for Accessibility. Engineered for Integrity.</p>
</div>
