import asyncio
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "ai_scribe.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

class Student(Base):
    __tablename__ = "students"
    id = Column(String, primary_key=True, index=True) # UUID
    name = Column(String, nullable=False)
    roll_no = Column(String, unique=True, index=True)
    disability_type = Column(String) # e.g. PwD1/PwD3
    created_at = Column(DateTime, default=datetime.utcnow)

class Exam(Base):
    __tablename__ = "exams"
    id = Column(String, primary_key=True, index=True) # UUID
    subject = Column(String, nullable=False)
    course_code = Column(String)
    scheduled_start = Column(DateTime)
    duration_minutes = Column(Integer)
    status = Column(String, default="scheduled") # scheduled/active/completed

class Question(Base):
    __tablename__ = "questions"
    id = Column(String, primary_key=True, index=True) # UUID
    exam_id = Column(String, ForeignKey("exams.id"))
    q_number = Column(Integer)
    part = Column(String) # A/B/etc
    text = Column(Text, nullable=False)
    marks = Column(Integer)
    has_image = Column(Boolean, default=False)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True) # UUID
    student_id = Column(String, ForeignKey("students.id"), nullable=True)
    exam_id = Column(String, ForeignKey("exams.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    status = Column(String, default="active") # active/submitted/abandoned

class AnswerSegment(Base):
    __tablename__ = "answer_segments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    question_id = Column(String, ForeignKey("questions.id"), nullable=True)
    text = Column(Text, nullable=False)
    committed_at = Column(DateTime, default=datetime.utcnow)
    word_count = Column(Integer, default=0)
    sequence_number = Column(Integer)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    utterance_type = Column(String) # dictation/command/system
    raw_text = Column(Text)
    confidence_avg = Column(Float, nullable=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
