# AI Scribe — Whisper transcription wrapper
#
# Accepts raw Float32 PCM bytes from the browser (vad-web onSpeechEnd gives
# a Float32Array; its .buffer is sent over WebSocket as a binary frame).
#
# Passes a numpy float32 ndarray directly to faster-whisper.transcribe().
# No temp files. No disk I/O. Each 1200ms VAD chunk is ~75KB in RAM.
#
# Confirmed from recon:
#   faster_whisper 1.1.1
#   transcribe() signature: audio: Union[str, BinaryIO, numpy.ndarray]  ← numpy OK
#   GPU: CUDA device_index=3 (55GB free, 0% util)

import numpy as np
from faster_whisper import WhisperModel

from server.config import (
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    CUDA_DEVICE_INDEX,
    WHISPER_BEAM_SIZE,
    CONFIDENCE_THRESHOLD,
)


class Transcriber:
    def __init__(self) -> None:
        print(
            f"[Transcriber] Loading {WHISPER_MODEL} "
            f"on GPU {CUDA_DEVICE_INDEX} ({WHISPER_COMPUTE_TYPE})…"
        )
        self.model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            device_index=CUDA_DEVICE_INDEX,
        )
        print("[Transcriber] Ready.")

    def transcribe(self, audio_bytes: bytes) -> dict:
        """
        Transcribe one voiced audio chunk.

        Parameters
        ----------
        audio_bytes
            Raw IEEE 754 float32 little-endian bytes, 16 kHz mono.
            This is exactly what vad-web onSpeechEnd produces:
              Float32Array  →  Float32Array.buffer  →  WebSocket binary frame
              →  websocket.receive_bytes()  →  here.

        Returns
        -------
        dict with keys:
            text     (str)   full transcript of chunk, whitespace-stripped
            words    (list)  [{word, probability, low_confidence}, …]
            language (str)   ISO 639-1 code detected by Whisper
        """
        # np.frombuffer returns a read-only view; .copy() makes it writable —
        # faster-whisper requires a C-contiguous writable float32 array.
        audio_np: np.ndarray = np.frombuffer(audio_bytes, dtype=np.float32).copy()

        segments_iter, info = self.model.transcribe(
            audio_np,
            language="en",
            beam_size=WHISPER_BEAM_SIZE,
            word_timestamps=True,
            vad_filter=False,              # VAD already done client-side
            condition_on_previous_text=False,
            # FUTURE: pass rolling buffer as initial_prompt for cross-chunk coherence
        )

        words: list[dict] = []
        full_text = ""

        for segment in segments_iter:
            full_text += segment.text
            if segment.words:
                for w in segment.words:
                    words.append({
                        "word":           w.word,
                        "probability":    round(w.probability, 4),
                        "low_confidence": bool(w.probability < CONFIDENCE_THRESHOLD),
                    })

        return {
            "text":     full_text.strip(),
            "words":    words,
            "language": info.language,
        }
