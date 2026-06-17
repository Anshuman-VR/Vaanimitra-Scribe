import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import navy, grey, black
from sqlalchemy import select
from server.database import Session, Exam, Question, AnswerSegment

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSWERS_DIR = os.path.join(BASE_DIR, "answers")

if not os.path.exists(ANSWERS_DIR):
    os.makedirs(ANSWERS_DIR)

async def generate_answer_pdf(session_id: str, db) -> bytes:
    # Fetch Data
    session = await db.get(Session, session_id)
    exam = await db.get(Exam, session.exam_id)
    
    stmt_q = select(Question).where(Question.exam_id == session.exam_id).order_by(Question.part, Question.q_number)
    qs_result = await db.execute(stmt_q)
    questions = qs_result.scalars().all()
    
    stmt_a = select(AnswerSegment).where(AnswerSegment.session_id == session_id).order_by(AnswerSegment.question_id, AnswerSegment.sequence_number)
    ans_result = await db.execute(stmt_a)
    segments = ans_result.scalars().all()
    
    answers_dict = {}
    for seg in segments:
        if seg.question_id not in answers_dict:
            answers_dict[seg.question_id] = []
        answers_dict[seg.question_id].append(seg.text)
        
    # PDF Setup
    pdf_path = os.path.join(ANSWERS_DIR, f"{session_id}.pdf")
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=40, leftMargin=40, topMargin=50, bottomMargin=50
    )
    
    styles = getSampleStyleSheet()
    
    style_h1 = ParagraphStyle('H1', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, alignment=1, spaceAfter=4)
    style_h2 = ParagraphStyle('H2', parent=styles['Normal'], fontName='Helvetica', fontSize=11, alignment=1, spaceAfter=4)
    style_h3 = ParagraphStyle('H3', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=10, alignment=1, spaceAfter=4)
    style_meta = ParagraphStyle('Meta', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=grey, alignment=1, spaceAfter=20)
    
    style_q_head = ParagraphStyle('QHead', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=black, spaceAfter=6)
    style_q_text = ParagraphStyle('QText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=black, spaceAfter=8)
    style_ans = ParagraphStyle('Ans', parent=styles['Normal'], fontName='Helvetica', fontSize=11, textColor=black, leading=14)
    style_no_ans = ParagraphStyle('NoAns', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=11, textColor=grey, spaceAfter=12)

    story = []
    
    story.append(Paragraph("SASTRA DEEMED UNIVERSITY", style_h1))
    story.append(Paragraph("School of Computing", style_h2))
    story.append(Paragraph(f"{exam.course_code} – {exam.subject}", style_h2))
    story.append(Paragraph("AI Scribe Generated Answer Sheet", style_h3))
    
    sub_time = session.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if session.submitted_at else "N/A"
    story.append(Paragraph(f"Session ID: {session_id} | Submitted: {sub_time}", style_meta))
    
    story.append(Paragraph("_________________________________________________________________________________", style_meta))
    story.append(Spacer(1, 20))
    
    for q in questions:
        story.append(Paragraph(f"Q{q.q_number}. [{q.marks} marks]", style_q_head))
        story.append(Paragraph(q.text, style_q_text))
        
        if q.id in answers_dict and len(answers_dict[q.id]) > 0:
            full_ans = " ".join(answers_dict[q.id])
            story.append(Paragraph(full_ans, style_ans))
        else:
            story.append(Paragraph("[ No answer provided ]", style_no_ans))
            
        story.append(Spacer(1, 12))
        
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(grey)
        footer_text = f"AI Scribe System — SASTRA University | Page {doc.page}"
        canvas.drawCentredString(A4[0] / 2.0, 30, footer_text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    
    with open(pdf_path, "rb") as f:
        return f.read()
