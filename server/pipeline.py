# AI Scribe — Sentence buffer and command router
#
# One Pipeline instance per WebSocket connection (one per student session).
# Stateful: buffers Whisper output across VAD chunks until sentence is complete.
#
# Why buffering is needed:
#   vad-web fires onSpeechEnd after 1200ms of silence.
#   A speaker may pause mid-sentence (e.g. "The answer is… forty-two.").
#   Whisper returns "The answer is" without end-punctuation.
#   Pipeline buffers it, waits for "forty-two.", then flushes the full sentence.

from server.config import COMMAND_PREFIXES, SENTENCE_END_CHARS, BUFFER_MAX_CHARS


class Pipeline:
    """
    Stateless per-session processing pipeline.

    Responsibilities
    ----------------
    1. Route Whisper chunks: command keywords → command response,
       everything else → dictation transcript (committed immediately).
    """

    def __init__(self) -> None:
        pass

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, transcription: dict) -> dict | None:
        """
        Feed one Whisper result into the pipeline.
        Since buffering is removed, this ALWAYS returns a complete message
        (either command or transcript) if there is text.

        Parameters
        ----------
        transcription
            Dict returned by Transcriber.transcribe():
            {text: str, words: list, language: str}
        """
        text  = transcription.get("text", "").strip()
        words = transcription.get("words", [])

        if not text:
            return None

        # Command routing: strip trailing punctuation, lowercase, prefix-match.
        normalized = text.lower().rstrip(".?! ")
        for prefix, action in COMMAND_PREFIXES.items():
            if normalized.startswith(prefix):
                return {"type": "command", "action": action, "raw": text}

        # Not a command → dictation output (committed immediately)
        return {"type": "transcript", "text": text, "words": words}

    def force_flush(self) -> dict | None:
        """
        No-op, since we no longer buffer.
        """
        return None
