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
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.transcriber import Transcriber
from server.pipeline import Pipeline
from server.database import init_db, AsyncSessionLocal, AnswerSegment, AuditLog, seed_demo_exam, Exam, Question, Session as DBSession
from sqlalchemy import select, delete
from datetime import datetime
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

exam_connections: dict[str, set] = defaultdict(set)

# ── Singleton model ───────────────────────────────────────────────────────────
_transcriber: Transcriber | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _transcriber
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_demo_exam(db)
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

@app.get("/api/exam/{exam_id}/questions")
async def get_exam_questions(exam_id: str):
    async with AsyncSessionLocal() as db:
        exam = await db.get(Exam, exam_id)
        if not exam:
            return {"error": "Exam not found"}
            
        stmt = select(Question).where(Question.exam_id == exam_id).order_by(Question.part, Question.q_number)
        result = await db.execute(stmt)
        questions = result.scalars().all()
        
        return {
            "exam_id": exam.id,
            "subject": exam.subject,
            "course_code": exam.course_code,
            "duration_minutes": exam.duration_minutes,
            "questions": [
                {"id": q.id, "part": q.part, "q_number": q.q_number, "marks": q.marks, "text": q.text, "has_image": q.has_image}
                for q in questions
            ]
        }

@app.post("/api/session/{session_id}/submit")
async def submit_session(session_id: str, request: Request):
    from server.pdf_generator import generate_answer_pdf
    
    data = await request.json()
    answers_dict = data.get("answers", {})
    
    async with AsyncSessionLocal() as db:
        # Delete existing answer segments for this session
        await db.execute(delete(AnswerSegment).where(AnswerSegment.session_id == session_id))
        
        # Insert the final answers dict
        for qid, text in answers_dict.items():
            if text.strip():
                ans = AnswerSegment(
                    session_id=session_id,
                    question_id=qid,
                    text=text,
                    word_count=len(text.split()),
                    sequence_number=1
                )
                db.add(ans)
        
        # Update Session
        session = await db.get(DBSession, session_id)
        if session:
            session.submitted_at = datetime.utcnow()
            session.status = "submitted"
        
        # Audit Log
        log = AuditLog(
            session_id=session_id,
            utterance_type="system",
            raw_text="Exam submitted by candidate",
            confidence_avg=None
        )
        db.add(log)
        
        await db.commit()
        
        # Generate PDF (will be saved to disk)
        await generate_answer_pdf(session_id, db)
        
        return {"status": "submitted", "pdf_url": f"/api/session/{session_id}/pdf"}

@app.get("/api/session/{session_id}/pdf")
async def get_pdf(session_id: str):
    from fastapi.responses import FileResponse
    pdf_path = os.path.join(BASE_DIR, "answers", f"{session_id}.pdf")
    if not os.path.exists(pdf_path):
        return {"error": "PDF not found"}
    return FileResponse(pdf_path, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="answers_{session_id}.pdf"'})

@app.get("/api/session/{session_id}/audit")
async def get_audit(session_id: str):
    async with AsyncSessionLocal() as db:
        stmt = select(AuditLog).where(AuditLog.session_id == session_id).order_by(AuditLog.timestamp)
        result = await db.execute(stmt)
        logs = result.scalars().all()
        return [
            {
                "timestamp": log.timestamp.isoformat(),
                "utterance_type": log.utterance_type,
                "raw_text": log.raw_text,
                "confidence_avg": log.confidence_avg
            }
            for log in logs
        ]

@app.get("/api/admin/sessions")
async def admin_get_sessions():
    from sqlalchemy import func
    async with AsyncSessionLocal() as db:
        stmt = (
            select(DBSession, func.count(AnswerSegment.id).label('answer_count'))
            .outerjoin(AnswerSegment, DBSession.id == AnswerSegment.session_id)
            .group_by(DBSession.id)
            .order_by(DBSession.started_at.desc())
        )
        result = await db.execute(stmt)
        
        return [
            {
                "session_id": row.Session.id,
                "student_name": row.Session.student_name,
                "reg_no": row.Session.reg_no,
                "started_at": row.Session.started_at.isoformat() if row.Session.started_at else None,
                "submitted_at": row.Session.submitted_at.isoformat() if row.Session.submitted_at else None,
                "status": row.Session.status,
                "answer_count": row.answer_count
            }
            for row in result.all()
        ]

@app.get("/api/admin/exam/{exam_id}/status")
async def get_exam_status(exam_id: str):
    async with AsyncSessionLocal() as db:
        exam = await db.get(Exam, exam_id)
        if not exam:
            return {"error": "Exam not found"}
        return {"status": exam.status}

@app.post("/api/admin/exam/{exam_id}/onboard")
async def start_onboarding(exam_id: str):
    notified = 0
    if exam_id in exam_connections:
        for ws in list(exam_connections[exam_id]):
            try:
                await ws.send_json({"type": "start_onboarding"})
                notified += 1
            except Exception:
                pass
    return {"status": "onboarding_started", "notified_clients": notified}

@app.post("/api/admin/exam/{exam_id}/start")
async def start_exam(exam_id: str):
    async with AsyncSessionLocal() as db:
        exam = await db.get(Exam, exam_id)
        if not exam:
            return {"error": "Exam not found"}
        
        exam.status = "active"
        await db.commit()
        
        # Broadcast to all connected WebSockets for this exam
        notified = 0
        if exam_id in exam_connections:
            for ws in list(exam_connections[exam_id]):
                try:
                    await ws.send_json({"type": "exam_started"})
                    notified += 1
                except Exception:
                    pass
                    
        return {"status": "started", "notified_clients": notified}

@app.get("/admin")
async def serve_admin():
    return FileResponse(os.path.join(BASE_DIR, "client", "admin.html"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, exam_id: str = "1"):
    await websocket.accept()
    exam_connections[exam_id].add(websocket)
    
    pipeline = Pipeline()
    client   = websocket.client
    
    session_id = websocket.query_params.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        
    await websocket.send_json({"type": "session_init", "session_id": session_id})
        
    print(f"[WS] Connected: {client} | Session: {session_id}")

    current_question_id = None
    
    # Send exam_load immediately and create Session
    async with AsyncSessionLocal() as db:
        sess = await db.get(DBSession, session_id)
        if not sess:
            sess = DBSession(id=session_id, student_id=None, exam_id=exam_id, started_at=datetime.utcnow(), status="active")
            db.add(sess)
            await db.commit()

        exam = await db.get(Exam, exam_id)
        if exam:
            stmt = select(Question).where(Question.exam_id == exam_id).order_by(Question.part, Question.q_number)
            result = await db.execute(stmt)
            qs = result.scalars().all()
            if qs:
                current_question_id = qs[0].id
            await websocket.send_json({
                "type": "exam_load",
                "exam_id": exam.id,
                "subject": exam.subject,
                "course_code": exam.course_code,
                "duration_minutes": exam.duration_minutes,
                "questions": [
                    {"id": q.id, "part": q.part, "q_number": q.q_number, "marks": q.marks, "text": q.text, "has_image": q.has_image}
                    for q in qs
                ]
            })
            
            if exam.status == "active":
                await websocket.send_json({"type": "exam_started"})
            else:
                await websocket.send_json({"type": "exam_waiting"})

    sequence_num = 0

    try:
        while True:
            message = await websocket.receive()
            audio_bytes = None
            client_context = None

            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "audio":
                        import base64
                        audio_bytes = base64.b64decode(data.get("data", ""))
                        client_context = data.get("context")
                    elif data.get("type") == "set_question":
                        current_question_id = str(data.get("question_id"))
                        continue
                    elif data.get("type") == "register":
                        async with AsyncSessionLocal() as db:
                            sess = await db.get(DBSession, session_id)
                            if sess:
                                sess.student_name = data.get("name")
                                sess.reg_no = data.get("reg_no")
                                await db.commit()
                        await websocket.send_json({
                            "type": "register_confirm",
                            "name": data.get("name"),
                            "reg_no": data.get("reg_no")
                        })
                        continue
                except Exception as e:
                    print(f"Error parsing text message: {e}")
                    continue
            
            if "bytes" in message:
                audio_bytes = message["bytes"]

            if not audio_bytes:
                continue
                
            t0 = time.perf_counter()

            # Whisper inference is blocking
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, _transcriber.transcribe, audio_bytes
            )

            inference_ms = round((time.perf_counter() - t0) * 1000)

            if not result["text"]:
                await websocket.send_json({"type": "empty", "inference_ms": inference_ms})
                continue

            from server.pipeline import SessionContext
            import dataclasses
            
            ctx = SessionContext(
                session_id=session_id,
                question_index=client_context.get("question_index", 0) if client_context else 0,
                total_questions=client_context.get("total_questions", 1) if client_context else 1,
                answer_word_count=client_context.get("answer_word_count", 0) if client_context else 0,
                last_utterances=client_context.get("last_utterances", []) if client_context else [],
                exam_state=client_context.get("exam_state", "EXAM") if client_context else "EXAM"
            )
            
            pipeline_res = await pipeline.process(result["text"], ctx)
            
            if pipeline_res:
                pipeline_out = dataclasses.asdict(pipeline_res)
                pipeline_out["inference_ms"] = inference_ms
                
                # Persistence logic
                async with AsyncSessionLocal() as db:
                    if pipeline_out["type"] == "transcript":
                        sequence_num += 1
                        ans = AnswerSegment(
                            session_id=session_id,
                            question_id=current_question_id,
                            text=pipeline_out.get("text", "") or "",
                            word_count=len(result["words"]) if "words" in result else len(pipeline_out.get("text", "").split()),
                            sequence_number=sequence_num
                        )
                        db.add(ans)
                    
                    log = AuditLog(
                        session_id=session_id,
                        utterance_type=pipeline_out["type"],
                        raw_text=result["text"],
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
    finally:
        if exam_id in exam_connections and websocket in exam_connections[exam_id]:
            exam_connections[exam_id].remove(websocket)


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

