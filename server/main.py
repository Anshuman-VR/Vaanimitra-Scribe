# AI Scribe — FastAPI application
#
# Serves:
#   GET  /          → client/index.html
#   GET  /static/*  → static/ (VAD ONNX, worklet JS, ORT WASM)
#   WS   /ws        → continuous STT pipeline (one Pipeline per connection)
#
# COOP/COEP headers are added to every response so that SharedArrayBuffer
# is available in the browser (required by onnxruntime-web threaded WASM).
# All resources are same-origin, so these headers cause no cross-origin issues.

import asyncio
import time
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.transcriber import Transcriber
from server.pipeline import Pipeline
from server.database import init_db, AsyncSessionLocal, AnswerSegment, AuditLog
from sqlalchemy import select
from server.config import (
    VAD_REDEMPTION_FRAMES, VAD_PRE_SPEECH_PAD, VAD_MIN_SPEECH_FRAMES,
    VAD_POS_THRESHOLD, VAD_NEG_THRESHOLD,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
# This file lives at ~/ai_scribe/server/main.py
# BASE_DIR → ~/ai_scribe/
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_HTML = os.path.join(BASE_DIR, "client", "index.html")
STATIC_DIR  = os.path.join(BASE_DIR, "static")

# ── Singleton model ───────────────────────────────────────────────────────────
_transcriber: Transcriber | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _transcriber
    await init_db()
    _transcriber = Transcriber()   # blocks while loading Whisper onto GPU
    yield
    print("[server] Shutdown.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan, title="AI Scribe")


@app.middleware("http")
async def add_cross_origin_headers(request: Request, call_next: Any):
    """
    Cross-Origin-Opener-Policy + Cross-Origin-Embedder-Policy are required
    for SharedArrayBuffer availability (onnxruntime-web threaded WASM).
    Safe here because all resources are served from the same origin.
    """
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"]   = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    return response


# Static assets: VAD ONNX + worklet + ORT WASM
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Client assets: CSS, JS modules
app.mount("/client", StaticFiles(directory=os.path.join(BASE_DIR, "client")), name="client")


@app.get("/")
async def serve_index():
    return FileResponse(CLIENT_HTML)


@app.get("/config")
async def vad_config():
    """Client fetches this to read VAD parameters from config.py."""
    return {
        "redemptionFrames":   VAD_REDEMPTION_FRAMES,
        "preSpeechPadFrames": VAD_PRE_SPEECH_PAD,
        "minSpeechFrames":    VAD_MIN_SPEECH_FRAMES,
        "positiveSpeechThreshold": VAD_POS_THRESHOLD,
        "negativeSpeechThreshold": VAD_NEG_THRESHOLD,
    }
@app.get("/api/session/{session_id}/answers")
async def get_answers(session_id: str):
    async with AsyncSessionLocal() as db:
        stmt = select(AnswerSegment).where(AnswerSegment.session_id == session_id).order_by(AnswerSegment.sequence_number)
        result = await db.execute(stmt)
        segments = result.scalars().all()
        return [{"id": s.id, "text": s.text, "word_count": s.word_count, "committed_at": s.committed_at} for s in segments]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    pipeline = Pipeline()
    client   = websocket.client
    
    session_id = websocket.query_params.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        await websocket.send_json({"type": "session_init", "session_id": session_id})
        
    print(f"[WS] Connected: {client} | Session: {session_id}")

    sequence_num = 0

    try:
        while True:
            # Receive raw Float32 PCM bytes from browser
            # (vad-web Float32Array.buffer → WebSocket binary frame)
            audio_bytes: bytes = await websocket.receive_bytes()
            t0 = time.perf_counter()

            # Whisper inference is blocking — run in thread pool so the
            # event loop stays free for other WebSocket connections
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, _transcriber.transcribe, audio_bytes
            )

            inference_ms = round((time.perf_counter() - t0) * 1000)

            # Empty transcript: noise burst that slipped past vad-web
            if not result["text"]:
                await websocket.send_json({"type": "empty", "inference_ms": inference_ms})
                continue

            pipeline_out = pipeline.process(result)
            
            # Complete sentence: either {type: transcript} or {type: command}
            if pipeline_out:
                pipeline_out["inference_ms"] = inference_ms
                
                # Persistence logic
                async with AsyncSessionLocal() as db:
                    if pipeline_out["type"] == "transcript":
                        sequence_num += 1
                        ans = AnswerSegment(
                            session_id=session_id,
                            text=pipeline_out["text"],
                            word_count=len(pipeline_out.get("words", [])),
                            sequence_number=sequence_num
                        )
                        db.add(ans)
                    
                    log = AuditLog(
                        session_id=session_id,
                        utterance_type=pipeline_out["type"],
                        raw_text=pipeline_out.get("raw", pipeline_out.get("text", "")),
                        confidence_avg=None
                    )
                    db.add(log)
                    await db.commit()

                await websocket.send_json(pipeline_out)

    except WebSocketDisconnect:
        print(f"[WS] Disconnected: {client}")
    except Exception as exc:
        print(f"[WS] Error: {exc}")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


# ── Streaming interim WebSocket ───────────────────────────────────────────────
@app.websocket("/ws/stream")
async def stream_endpoint(websocket: WebSocket):
    """
    Live interim transcription endpoint.

    While the student is speaking, the client sends the cumulative audio
    captured so far every 500ms. This endpoint transcribes it immediately
    and returns the raw text — no sentence buffer, no command routing.

    The client uses these responses to update the live transcript paragraph
    in place, giving the appearance of words appearing as they are spoken.

    When the student pauses (vad-web fires onSpeechEnd), the main /ws
    endpoint does the definitive transcription with confidence scores.
    """
    await websocket.accept()
    print(f"[WS/stream] Connected: {websocket.client}")

    queue = asyncio.Queue(maxsize=3)

    async def consume_queue():
        loop = asyncio.get_event_loop()
        while True:
            try:
                audio_bytes = await queue.get()
                
                n_samples = len(audio_bytes) // 4
                if n_samples < int(16000 * 0.3):
                    await websocket.send_json({"type": "interim", "text": ""})
                    queue.task_done()
                    continue

                max_samples = 16000 * 25
                if n_samples > max_samples:
                    audio_bytes = audio_bytes[: max_samples * 4]

                # Run transcribe_interim (beam_size=1, no word timestamps)
                result = await loop.run_in_executor(
                    None, _transcriber.transcribe_interim, audio_bytes
                )
                
                await websocket.send_json({
                    "type": "interim",
                    "text": result["text"],
                })
                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[WS/stream] Consumer error: {e}")
                queue.task_done()

    consumer_task = asyncio.create_task(consume_queue())

    try:
        while True:
            audio_bytes: bytes = await websocket.receive_bytes()
            
            # If queue is full, drop the oldest item to make room for the newest audio
            if queue.full():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    pass
            
            await queue.put(audio_bytes)

    except WebSocketDisconnect:
        print(f"[WS/stream] Disconnected: {websocket.client}")
    except Exception as exc:
        print(f"[WS/stream] Error: {exc}")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        consumer_task.cancel()

