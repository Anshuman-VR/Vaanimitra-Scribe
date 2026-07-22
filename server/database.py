import asyncio
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text, event
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "ai_scribe.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

# Enable WAL mode on every new connection. This allows concurrent reads while
# a write is in progress, eliminating the latency spikes seen with 2+ sessions.
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=1000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

class Student(Base):
    __tablename__ = "students"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    roll_no = Column(String, unique=True, index=True)
    disability_type = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Exam(Base):
    __tablename__ = "exams"
    id = Column(String, primary_key=True, index=True)
    subject = Column(String, nullable=False)
    course_code = Column(String)
    scheduled_start = Column(DateTime)
    duration_minutes = Column(Integer)
    status = Column(String, default="scheduled")  # scheduled/onboarding/active/completed
    exam_started_at = Column(DateTime, nullable=True)  # Set when status → active

class Question(Base):
    __tablename__ = "questions"
    id = Column(String, primary_key=True, index=True)
    exam_id = Column(String, ForeignKey("exams.id"))
    q_number = Column(Integer)
    part = Column(String)
    text = Column(Text, nullable=False)
    marks = Column(Integer)
    has_image = Column(Boolean, default=False)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    student_id = Column(String, nullable=True)
    student_name = Column(String, nullable=True)
    reg_no = Column(String, nullable=True)
    exam_id = Column(String, ForeignKey("exams.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    status = Column(String, default="active")  # active/submitted/abandoned
    current_question_id = Column(String, nullable=True)  # Last known question for resume

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
    utterance_type = Column(String)  # dictation/command/system
    raw_text = Column(Text)
    confidence_avg = Column(Float, nullable=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def seed_demo_exam(db: AsyncSession):
    from sqlalchemy import select

    # Seed students if none exist
    result = await db.execute(select(Student))
    if not result.scalars().first():
        students = [
            Student(id="s1", name="Anshuman Venkata Raghavan", roll_no="128158003", disability_type="PwD3"),
            Student(id="s2", name="Ashwin Venkata Raghavan",   roll_no="128015006", disability_type="PwD1"),
            Student(id="s3", name="Priya Krishnamurthy",       roll_no="128003001", disability_type="PwD1"),
            Student(id="s4", name="Rahul Nair",                roll_no="128042009", disability_type="PwD3"),
            Student(id="s5", name="Deepika Sundaram",          roll_no="128071004", disability_type="PwD1"),
        ]
        for s in students:
            db.add(s)

    # Seed exam if it doesn't exist
    stmt = select(Exam).where(Exam.id == "1")
    result = await db.execute(stmt)
    if result.scalars().first():
        return

    demo_exam = Exam(
        id="1",
        subject="Design and Analysis of Algorithms",
        course_code="CSE305R01",
        scheduled_start=datetime.utcnow(),
        duration_minutes=90,
        status="scheduled"
    )
    db.add(demo_exam)

    qs = [
        Question(id="1", exam_id="1", part="A", q_number=1, marks=2,  has_image=False, text="Define asymptotic efficiency of an algorithm."),
        Question(id="2", exam_id="1", part="A", q_number=2, marks=2,  has_image=False, text="What are the steps involved in Divide and Conquer approach?"),
        Question(id="3", exam_id="1", part="A", q_number=3, marks=2,  has_image=False, text="What is meant by a stable sort? Give one example."),
        Question(id="4", exam_id="1", part="B", q_number=4, marks=10, has_image=False, text="Explain why a reverse sorted array results in worst case time complexity for Insertion Sort. Illustrate with an example."),
        Question(id="5", exam_id="1", part="B", q_number=5, marks=10, has_image=False, text="What is the Maximum Subarray Problem? Describe the Divide and Conquer approach to solve it and analyse its time complexity."),
    ]
    for q in qs:
        db.add(q)

    await db.commit()
