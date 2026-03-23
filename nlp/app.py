"""
QuizLens FastAPI Backend
Run: uvicorn app:app --reload --port 8000
"""

import io
import hashlib
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pdfplumber
from docx import Document as DocxDocument
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from analyzer import analyze_paper, sha256_bytes

app = FastAPI(title="QuizLens NLP API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── File text extraction ──────────────────────────────────────
def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        text = ""
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        return text
    elif ext in (".docx", ".doc"):
        doc = DocxDocument(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)
    elif ext in (".txt", ".md"):
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise HTTPException(400, f"Unsupported file type: {ext}. Use PDF, DOCX, or TXT.")


# ── PDF report generator ──────────────────────────────────────
def build_report_pdf(analysis) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=50, rightMargin=50, topMargin=60, bottomMargin=50)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("title", parent=styles["Title"],
                                 fontSize=20, spaceAfter=6, textColor=colors.HexColor("#1E3A5F"))
    h2_style    = ParagraphStyle("h2", parent=styles["Heading2"],
                                 fontSize=13, spaceBefore=14, spaceAfter=4, textColor=colors.HexColor("#2563EB"))
    body_style  = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    mono_style  = ParagraphStyle("mono", parent=styles["Normal"], fontSize=8,
                                 fontName="Courier", textColor=colors.HexColor("#0F6E56"))

    story.append(Paragraph(f"QuizLens Analysis Report", title_style))
    story.append(Paragraph(f"Exam: {analysis.title}", styles["Heading3"]))
    story.append(Spacer(1, 10))

    # ── Summary table ──
    story.append(Paragraph("Summary", h2_style))
    summary_data = [
        ["Metric", "Value"],
        ["Questions detected",    str(analysis.question_count)],
        ["Flesch reading ease",   f"{analysis.flesch_score} / 100  ({analysis.readability_label})"],
        ["Flesch-Kincaid grade",  f"Grade {analysis.flesch_grade}"],
        ["Avg sentence length",   f"{analysis.avg_sentence_length} words"],
        ["Dominant Bloom level",  analysis.overall_bloom.capitalize()],
        ["Bias flags found",      str(len(analysis.bias_summary))],
        ["Ambiguous questions",   str(len(analysis.ambiguous_questions)) or "None"],
    ]
    t = Table(summary_data, colWidths=[220, 280])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#F8FAFC"), colors.white]),
        ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # ── Per-question breakdown ──
    story.append(Paragraph("Per-question analysis", h2_style))
    q_data = [["#", "Bloom level", "Confidence", "Bias flags", "Ambiguous"]]
    for q in analysis.questions:
        q_data.append([
            str(q.index),
            q.bloom_level.capitalize(),
            q.bloom_confidence,
            ", ".join(q.bias_flags) if q.bias_flags else "None",
            "Yes" if q.index in analysis.ambiguous_questions else "No",
        ])
    qt = Table(q_data, colWidths=[25, 90, 75, 180, 65])
    qt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2563EB")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#F0F9FF"), colors.white]),
        ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#BFDBFE")),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(qt)
    story.append(Spacer(1, 12))

    # ── Hashes ──
    story.append(Paragraph("Cryptographic hashes (for blockchain notarization)", h2_style))
    story.append(Paragraph(f"Paper SHA-256:", body_style))
    story.append(Paragraph(analysis.paper_hash, mono_style))
    story.append(Spacer(1, 6))

    doc.build(story)
    return buf.getvalue()


# ── API Endpoints ─────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "QuizLens NLP API running", "version": "1.0.0"}


@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    title: str = Form("Untitled Exam")
):
    """
    Analyze a question paper.
    Returns: readability, bloom levels, bias flags, hashes.
    """
    file_bytes = await file.read()
    filename = file.filename or "unknown.txt"

    # Extract text
    text = extract_text(file_bytes, filename)
    if len(text.strip()) < 20:
        raise HTTPException(400, "Could not extract text from file — ensure it's a readable PDF/DOCX/TXT.")

    # Run NLP analysis
    analysis = analyze_paper(text, title)

    # Build PDF report
    report_pdf = build_report_pdf(analysis)
    report_hash = sha256_bytes(report_pdf)
    analysis.report_hash = report_hash

    return JSONResponse({
        "title":              analysis.title,
        "question_count":     analysis.question_count,
        "flesch_score":       analysis.flesch_score,
        "flesch_grade":       analysis.flesch_grade,
        "readability_label":  analysis.readability_label,
        "avg_sentence_length": analysis.avg_sentence_length,
        "overall_bloom":      analysis.overall_bloom,
        "bias_summary":       analysis.bias_summary,
        "ambiguous_questions": analysis.ambiguous_questions,
        "questions": [
            {
                "index":           q.index,
                "text":            q.text[:200],
                "bloom_level":     q.bloom_level,
                "bloom_confidence": q.bloom_confidence,
                "bias_flags":      q.bias_flags,
            }
            for q in analysis.questions
        ],
        "paper_hash":  analysis.paper_hash,
        "report_hash": report_hash,
        "report_pdf_b64": __import__("base64").b64encode(report_pdf).decode(),
    })