"""
QuizLens NLP Analyzer - Lightweight Version
Features:
  1. Readability — Flesch-Kincaid grade & score
  2. Bloom's level — cognitive level per question
  3. Bias detection — gender & cultural bias flags
"""

import re
import hashlib
from dataclasses import dataclass
from typing import List, Tuple, Dict

import textstat


BLOOMS = {
    "remember":    ["define","list","recall","name","state","identify","label","match","memorize","repeat","what","which","who"],
    "understand":  ["explain","describe","summarise","classify","compare","interpret","paraphrase","discuss","illustrate","outline"],
    "apply":       ["solve","use","demonstrate","calculate","compute","show","implement","execute","apply","find","determine"],
    "analyse":     ["analyse","analyze","examine","differentiate","distinguish","break down","inspect","test","question","investigate"],
    "evaluate":    ["evaluate","judge","justify","assess","critique","defend","argue","recommend","appraise","prioritize","critically"],
    "create":      ["design","create","construct","develop","formulate","compose","plan","invent","produce","generate","build"],
}

GENDERED_WORDS = {
    "masculine": ["he","him","his","men","man","businessman","policeman","fireman","chairman","mankind","boy","father","brother"],
    "feminine":  ["she","her","hers","women","woman","businesswoman","policewoman","firewoman","chairwoman","girl","mother","sister"],
}

CULTURAL_FLAGS = [
    "christmas","thanksgiving","halloween","diwali","eid","hanukkah","ramadan",
    "western","eastern","american","british","asian","african","european",
    "dollar","pound","rupee","euro","yuan","yen",
]


@dataclass
class QuestionAnalysis:
    index: int
    text: str
    bloom_level: str
    bloom_confidence: str
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


def sha256_text(text: str) -> str:
    return "0x" + hashlib.sha256(text.encode()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def readability_label(score: float) -> str:
    if score >= 80:  return "Very Easy"
    if score >= 60:  return "Standard"
    if score >= 40:  return "Difficult"
    return "Very Difficult"


def detect_bloom(sentence: str) -> Tuple[str, str]:
    lower = sentence.lower()
    scores: Dict[str, int] = {level: 0 for level in BLOOMS}
    
    for level, keywords in BLOOMS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', lower):
                scores[level] += 1
    
    best_level = "remember"
    best_score = 0
    for level, score in scores.items():
        if score > best_score:
            best_score = score
            best_level = level
    
    total = sum(scores.values())
    
    if best_score >= 2:
        confidence = "high"
    elif best_score == 1:
        confidence = "medium"
    else:
        confidence = "low"
    
    return (best_level if total > 0 else "remember", confidence)


def detect_bias(sentence: str) -> List[str]:
    flags = []
    lower = sentence.lower()
    
    masc = sum(1 for w in GENDERED_WORDS["masculine"] if re.search(r'\b' + w + r'\b', lower))
    fem  = sum(1 for w in GENDERED_WORDS["feminine"]  if re.search(r'\b' + w + r'\b', lower))
    
    if masc > 0 and fem == 0:
        flags.append("gender:masculine-default")
    if fem > 0 and masc == 0:
        flags.append("gender:feminine-default")
    if masc > 0 and fem > 0:
        flags.append("gender:mixed")
    
    for w in CULTURAL_FLAGS:
        if re.search(r'\b' + w + r'\b', lower):
            flags.append(f"cultural:{w}")
    
    return flags


def extract_questions(text: str) -> List[str]:
    pattern = r'(?:^|\n)\s*(?:Q\.?\s*)?(\d+)[.):\s]'
    parts = re.split(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    questions = []
    i = 1
    while i < len(parts) - 1:
        q = parts[i + 1].strip()
        if q and len(q) > 5:
            questions.append(q)
        i += 2
    
    if not questions:
        sentences = re.split(r'[.!?]+', text)
        questions = [s.strip() for s in sentences if "?" in s or len(s.split()) > 8]
    
    return questions[:50]


def is_ambiguous(text: str) -> bool:
    words = text.lower().split()
    if len(words) < 4:
        return True
    vague = ["it", "this", "that", "they", "them", "these", "those"]
    for word in words:
        if word in vague:
            return True
    return False


def analyze_paper(text: str, title: str = "Untitled") -> PaperAnalysis:
    paper_hash = sha256_text(text)
    
    try:
        flesch = round(textstat.flesch_reading_ease(text), 1)
        flesch_grade = round(textstat.flesch_kincaid_grade(text), 1)
        avg_sent_len = round(textstat.avg_sentence_length(text), 1)
    except Exception:
        flesch = 50.0
        flesch_grade = 8.0
        avg_sent_len = 15.0
    
    questions_text = extract_questions(text)
    q_analyses: List[QuestionAnalysis] = []
    ambiguous: List[int] = []
    all_bias: List[str] = []
    bloom_counts: Dict[str, int] = {level: 0 for level in BLOOMS}
    
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
    
    overall_bloom = max(bloom_counts.items(), key=lambda x: x[1])[0] if bloom_counts else "remember"
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
