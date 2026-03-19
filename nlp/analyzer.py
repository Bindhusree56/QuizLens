"""
QuizLens NLP Analyzer
Runs three analyses on a question paper:
  1. Readability  — Flesch-Kincaid grade & score
  2. Bloom's level — cognitive level per question
  3. Bias detection — gender & cultural bias flags
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import List

import textstat
import spacy

# Load spaCy English model (downloaded during setup)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")


# ── Bloom's taxonomy keyword map ─────────────────────────────
BLOOMS = {
    "remember":    ["define","list","recall","name","state","identify","label","match","memorize","repeat"],
    "understand":  ["explain","describe","summarise","classify","compare","interpret","paraphrase","discuss"],
    "apply":       ["solve","use","demonstrate","calculate","compute","show","implement","execute"],
    "analyse":     ["analyse","examine","differentiate","distinguish","break down","inspect","test","question"],
    "evaluate":    ["evaluate","judge","justify","assess","critique","defend","argue","recommend","appraise"],
    "create":      ["design","create","construct","develop","formulate","compose","plan","invent","produce"],
}

# ── Bias word lists ────────────────────────────────────────────
GENDERED_WORDS = {
    "masculine": ["he","him","his","men","man","businessman","policeman","fireman","chairman","mankind"],
    "feminine":  ["she","her","hers","women","woman","businesswoman","policewoman","firewoman","chairwoman"],
}
CULTURAL_FLAGS = [
    "christmas","thanksgiving","halloween","diwali","eid","hanukkah",
    "western","eastern","american","british","asian","african",
    "dollar","pound","rupee","euro","yuan",
]


@dataclass
class QuestionAnalysis:
    index: int
    text: str
    bloom_level: str
    bloom_confidence: str      # "high" | "medium" | "low"
    bias_flags: List[str]


@dataclass
class PaperAnalysis:
    title: str
    raw_text: str
    question_count: int
    flesch_score: float
    flesch_grade: float
    readability_label: str
    avg_sentence_length: float
    questions: List[QuestionAnalysis]
    overall_bloom: str
    bias_summary: List[str]
    ambiguous_questions: List[int]
    paper_hash: str
    report_hash: str = ""


# ── Helpers ────────────────────────────────────────────────────
def sha256_text(text: str) -> str:
    return "0x" + hashlib.sha256(text.encode()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def readability_label(score: float) -> str:
    if score >= 80:  return "Very easy"
    if score >= 60:  return "Standard"
    if score >= 40:  return "Difficult"
    return "Very difficult"


def detect_bloom(sentence: str) -> tuple[str, str]:
    lower = sentence.lower()
    scores = {level: 0 for level in BLOOMS}
    for level, keywords in BLOOMS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', lower):
                scores[level] += 1
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = "high" if scores[best] >= 2 else ("medium" if scores[best] == 1 else "low")
    return (best if total > 0 else "remember", confidence)


def detect_bias(sentence: str) -> List[str]:
    flags = []
    lower = sentence.lower()
    masc = sum(1 for w in GENDERED_WORDS["masculine"] if re.search(r'\b'+w+r'\b', lower))
    fem  = sum(1 for w in GENDERED_WORDS["feminine"]  if re.search(r'\b'+w+r'\b', lower))
    if masc > 0 and fem == 0: flags.append("gender:masculine-default")
    if fem  > 0 and masc == 0: flags.append("gender:feminine-default")
    for w in CULTURAL_FLAGS:
        if re.search(r'\b'+w+r'\b', lower):
            flags.append(f"cultural:{w}")
    return flags


def extract_questions(text: str) -> List[str]:
    """Split text into individual questions."""
    # Match numbered questions: 1. / 1) / Q1. / Q1:
    pattern = r'(?:^|\n)\s*(?:Q\.?\s*)?(\d+)[.):\s]'
    parts = re.split(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    questions = []
    i = 1
    while i < len(parts) - 1:
        q = parts[i + 1].strip()
        if q:
            questions.append(q)
        i += 2
    if not questions:
        # Fallback: split on sentence endings
        doc = nlp(text)
        questions = [sent.text.strip() for sent in doc.sents if "?" in sent.text or len(sent.text.split()) > 5]
    return questions[:50]   # cap at 50 questions


def is_ambiguous(text: str) -> bool:
    """Flag questions with very short text or vague pronouns without antecedent."""
    words = text.split()
    if len(words) < 4:
        return True
    vague = ["it", "this", "that", "they", "them"]
    doc = nlp(text)
    for token in doc:
        if token.text.lower() in vague and token.dep_ == "nsubj":
            return True
    return False


# ── Main analysis function ────────────────────────────────────
def analyze_paper(text: str, title: str = "Untitled") -> PaperAnalysis:
    paper_hash = sha256_text(text)

    # Global readability on full text
    flesch      = round(textstat.flesch_reading_ease(text), 1)
    flesch_grade = round(textstat.flesch_kincaid_grade(text), 1)
    avg_sent_len = round(textstat.avg_sentence_length(text), 1)

    # Per-question analysis
    questions_text = extract_questions(text)
    q_analyses: List[QuestionAnalysis] = []
    ambiguous: List[int] = []
    all_bias: List[str] = []
    bloom_counts = {level: 0 for level in BLOOMS}

    for i, q in enumerate(questions_text, 1):
        bloom, conf = detect_bloom(q)
        bias = detect_bias(q)
        all_bias.extend(bias)
        bloom_counts[bloom] += 1

        if is_ambiguous(q):
            ambiguous.append(i)

        q_analyses.append(QuestionAnalysis(
            index=i, text=q,
            bloom_level=bloom, bloom_confidence=conf,
            bias_flags=bias
        ))

    overall_bloom = max(bloom_counts, key=bloom_counts.get)
    bias_summary = list(set(all_bias))

    return PaperAnalysis(
        title=title,
        raw_text=text,
        question_count=len(questions_text),
        flesch_score=flesch,
        flesch_grade=flesch_grade,
        readability_label=readability_label(flesch),
        avg_sentence_length=avg_sent_len,
        questions=q_analyses,
        overall_bloom=overall_bloom,
        bias_summary=bias_summary,
        ambiguous_questions=ambiguous,
        paper_hash=paper_hash,
    )