# AI Scribe — Configuration
# All tuneable parameters in one place. Edit here, nowhere else.

# ── Whisper model ─────────────────────────────────────────────────────────────
WHISPER_MODEL        = "large-v3"
WHISPER_DEVICE       = "cuda"
WHISPER_COMPUTE_TYPE = "float16"
CUDA_DEVICE_INDEX    = 0       # Mapped to 0 because start.sh sets CUDA_VISIBLE_DEVICES=3
WHISPER_BEAM_SIZE    = 5
SAMPLE_RATE          = 16000   # Hz — must match vad-web output (always 16kHz mono)

# ── Server ────────────────────────────────────────────────────────────────────
HOST         = "0.0.0.0"
PORT         = 8765
SSL_CERTFILE = "cert.pem"   # relative to ~/ai_scribe/ (project root on HPC)
SSL_KEYFILE  = "key.pem"

# ── Audio quality ─────────────────────────────────────────────────────────────
# Words returned by Whisper with probability < this value are flagged low-confidence
CONFIDENCE_THRESHOLD = 0.7

# ── Sentence buffer ───────────────────────────────────────────────────────────
# Pipeline flushes when transcript chunk ends with one of these characters
SENTENCE_END_CHARS = frozenset({'.', '?', '!'})
# Safety flush if buffer grows beyond this (handles speakers who never pause)
BUFFER_MAX_CHARS   = 500

# ── VAD (configured client-side via vad-web redemptionFrames) ─────────────────
# vad-web default frame = 1536 samples @ 16kHz = 96 ms
# Target silence before onSpeechEnd: ~1200 ms → 1200 / 96 = 12.5 → use 12
VAD_REDEMPTION_FRAMES   = 12    # sent to client in /config endpoint
VAD_PRE_SPEECH_PAD      = 1     # frames of audio before speech onset to include
VAD_MIN_SPEECH_FRAMES   = 2     # ignore bursts shorter than this (lowered for short commands)
VAD_POS_THRESHOLD       = 0.4
VAD_NEG_THRESHOLD       = 0.35

# ── Command vocabulary ────────────────────────────────────────────────────────
# Keys: lowercase spoken prefix (stripped of trailing punctuation)
# Values: action string sent to client
COMMAND_PREFIXES: dict[str, str] = {
    "next question":      "nav_next",
    "previous question":  "nav_prev",
    "go to question":     "nav_goto",
    "read question":      "read_question",
    "read my answer":     "read_answer",
    "clear answer":       "clear_answer",
    "delete last sentence": "delete_last",
}
