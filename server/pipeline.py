import json
import time
import re
import httpx
from dataclasses import dataclass
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class SessionContext:
    session_id: str
    question_index: int
    total_questions: int
    answer_word_count: int
    last_utterances: list
    exam_state: str
    registration_phase: str | None = None
    vaani_prefix_detected: bool = False

@dataclass
class PipelineResult:
    type: str
    intent: str | None = None
    target: any = None
    text: str | None = None
    requires_tts_confirm: bool = False
    confirm_prompt: str | None = None
    confidence: str = "high"

# ── Known Vaani transcription variants ────────────────────────────────────────
# Whisper transcribes "Vaani" inconsistently. This set covers observed variants
# plus phonetically similar words. Levenshtein fallback catches the rest.
VAANI_VARIANTS = frozenset({
    "vaani", "vani", "wani", "mani", "money", "bani", "bonnie",
    "bunny", "vanny", "moni", "boni", "varni", "nani", "dani",
    "funny", "wanny", "monee", "mony", "vanie", "vaaani",
})

# ── Command Lexicon ───────────────────────────────────────────────────────────

COMMAND_LEXICON = {
    "nav_next": ["next question", "next", "move on", "proceed to next", "go to next", "move forward"],
    "nav_prev": ["previous question", "go back", "last question", "previous", "back"],
    "nav_goto": ["go to question", "jump to question", "question number"],
    "nav_first": ["first question", "go to first", "beginning"],
    "nav_last":  ["last question", "go to last", "final question"],
    "delete_last_word": ["delete last word", "remove last word", "delete word"],
    "delete_last_line": ["delete last line", "remove last line", "scratch that", "delete last sentence", "remove that"],
    "delete_last_N":    ["delete last", "remove last"],
    "clear_answer": ["clear answer", "clear everything", "start over", "erase answer", "delete everything", "wipe answer"],
    "undo": ["undo", "undo that", "take that back", "revert"],
    "read_question": ["read question", "read the question", "what is the question", "repeat question"],
    "read_answer": ["read my answer", "read back", "what have I written", "read answer"],
    "read_last_line": ["read last line", "what did I say", "last sentence"],
    "repeat_last": ["repeat", "say that again", "repeat that"],
    "check_time": ["how much time", "time remaining", "how long", "time left"],
    "check_question": ["which question", "current question", "what question"],
    "check_marks": ["how many marks", "marks for this", "what are the marks"],
    "check_total": ["how many questions", "total questions"],
    "submit_exam": ["submit exam", "submit my exam", "i am done", "finish exam", "end exam", "submit paper"],
    "submit_confirm": ["i confirm submit", "i confirm submission", "yes submit", "confirm"],
    "submit_cancel": ["cancel submit", "cancel submission", "don't submit", "do not submit", "cancel"],
    "student_ready": ["i am ready to start the exam", "ready to start", "i am ready", "ready"],
    "pause_mic": ["pause", "stop listening", "mute"],
    "resume_mic": ["resume", "start listening", "unmute"],
}

VALID_INTENTS = list(COMMAND_LEXICON.keys())

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
}

DOMAIN_PHRASES = [
    "therefore", "hence", "because", "given that", "we know", "the formula",
    "substituting", "differentiating", "integrating", "the answer",
    "in conclusion", "to summarize", "firstly", "secondly", "thirdly",
    "according to", "the reason", "as a result", "for example",
    "in other words", "furthermore", "moreover", "however",
]

OLLAMA_URL = "http://127.0.0.1:45881/api/generate"
OLLAMA_MODEL = "qwen2.5:3b-instruct-q4_K_M"


def extract_number(text: str):
    match = re.search(r'\d+', text)
    if match:
        return int(match.group())
    for w, n in WORD_TO_NUM.items():
        if w in text.lower():
            return n
    return None


# ── Pipeline ──────────────────────────────────────────────────────────────────

class IntentPipeline:
    def __init__(self):
        self.undo_stack = {}

    # ── Vaani prefix detection ────────────────────────────────────────────

    def _detect_vaani_prefix(self, text: str, context: SessionContext) -> str:
        words = text.strip().split()
        if not words:
            return text
        first_word = words[0].lower().strip(',.?!:;')

        # Known Whisper transcription variants (exact match, instant)
        if first_word in VAANI_VARIANTS:
            context.vaani_prefix_detected = True
            remainder = " ".join(words[1:]).strip(', ')
            print(f"[Pipeline] Vaani prefix detected (variant match): '{first_word}'")
            return remainder

        # Fuzzy fallback: Levenshtein distance ≤ 2
        dist = Levenshtein.distance(first_word, "vaani")
        if dist <= 2:
            context.vaani_prefix_detected = True
            remainder = " ".join(words[1:]).strip(', ')
            print(f"[Pipeline] Vaani prefix detected (Levenshtein={dist}): '{first_word}'")
            return remainder

        return text

    # ── Heuristic classification ──────────────────────────────────────────

    def _heuristic_classify(self, text: str, context: SessionContext):
        clean = text.lower().strip(',.?! ')
        words = clean.split()

        # Domain phrases → definitely transcript
        if any(p in clean for p in DOMAIN_PHRASES):
            print(f"[Pipeline] Heuristic: domain phrase detected → transcript")
            return PipelineResult(type="transcript", text=text)

        # For long utterances: check if the TAIL matches a command
        if len(words) > 15:
            tail = " ".join(words[-6:])
            tail_best_score = 0
            tail_best_match = None
            for intent, phrases in COMMAND_LEXICON.items():
                for phrase in phrases:
                    score = fuzz.token_set_ratio(tail, phrase)
                    if score > tail_best_score:
                        tail_best_score = score
                        tail_best_match = intent
            if tail_best_score >= 85:
                print(f"[Pipeline] Heuristic: long utterance with command tail '{tail}' → {tail_best_match} (score={tail_best_score}), deferring to LLM")
                return None  # Let LLM decide — might be dictation ending with "continue" etc.
            print(f"[Pipeline] Heuristic: >15 words, no command tail → transcript")
            return PipelineResult(type="transcript", text=text)

        # Standard fuzzy match against command lexicon
        best_match = None
        best_score = 0
        for intent, phrases in COMMAND_LEXICON.items():
            for phrase in phrases:
                score = fuzz.token_set_ratio(clean, phrase)
                if score > best_score:
                    best_score = score
                    best_match = intent

        print(f"[Pipeline] Heuristic: best='{best_match}' score={best_score}")

        if best_score >= 88 and best_match:
            res = PipelineResult(type="command", intent=best_match)
            if best_match in ["nav_goto", "delete_last_N"]:
                res.target = extract_number(clean)
                if not res.target and best_match == "nav_goto":
                    return None  # Can't navigate without a target
            return res

        return None  # Ambiguous — let LLM decide

    # ── LLM classification (exam commands) ────────────────────────────────

    async def _llm_classify(self, text: str, context: SessionContext):
        system = f"""You are an intent classifier for a voice-controlled exam system.
Classify the utterance as either a command or answer dictation.

RULES:
1. If the utterance is clearly a command (navigation, editing, submission), return command.
2. If there is ANY doubt, return transcript. Safety first.
3. Short utterances (<6 words) after a long answer are MORE likely commands.
4. Subject-matter content is ALWAYS transcript.

OUTPUT: Respond with ONLY a JSON object. No explanation.
{{"type": "transcript"}}
{{"type": "command", "intent": "nav_next", "target": null}}
{{"type": "command", "intent": "nav_goto", "target": 3}}
{{"type": "command", "intent": "delete_last_N", "target": 5}}

Valid intents: {", ".join(VALID_INTENTS)}"""

        prompt = f"""Utterance: "{text.replace('"', '')}"
Question: {context.question_index + 1}/{context.total_questions}
Answer length: {context.answer_word_count} words
Recent: {json.dumps(context.last_utterances[-2:])}"""

        print(f"[LLM] Sending to Ollama: '{text}'")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "system": system,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 50, "num_ctx": 512}
                    }
                )

            raw_res = response.json().get("response", "").strip()
            # Strip markdown fences if present
            if raw_res.startswith("```json"):
                raw_res = raw_res[7:]
            if raw_res.startswith("```"):
                raw_res = raw_res[3:]
            if raw_res.endswith("```"):
                raw_res = raw_res[:-3]
            raw_res = raw_res.strip()

            print(f"[LLM] Response: {raw_res}")

            data = json.loads(raw_res)
            if data.get("type") == "command" and data.get("intent") in VALID_INTENTS:
                return PipelineResult(
                    type="command",
                    intent=data["intent"],
                    target=data.get("target"),
                    confidence="llm"
                )
            return PipelineResult(type="transcript", text=text, confidence="llm")
        except Exception as e:
            print(f"[LLM] Error: {type(e).__name__} - {e}")
            return PipelineResult(type="transcript", text=text, confidence="llm_error")

    # ── LLM extraction for registration ───────────────────────────────────

    async def _llm_extract_registration(self, text: str, phase: str):
        prompts = {
            "name": (
                'Extract ONLY the person\'s name from this statement. Strip filler words like "my name is", "I am", etc.\n'
                'Examples: "My name is John Smith" → "John Smith", "Anshuman" → "Anshuman"\n'
                'Respond with ONLY: {"value": "extracted name"}'
            ),
            "reg_no": (
                'Extract ONLY the registration/roll number. Strip filler like "my register number is", "it is", etc.\n'
                'Examples: "My register number is 21CS123" → "21CS123", "P128158003" → "P128158003"\n'
                'Respond with ONLY: {"value": "extracted number"}'
            ),
            "ready": (
                'Is this student saying they are ready to start the exam?\n'
                'READY: "I am ready", "Ready", "Yes", "Let\'s start", "Begin"\n'
                'NOT READY: "Wait", "Not yet", "Hold on", "What?"\n'
                'Respond with ONLY: {"ready": true} or {"ready": false}'
            ),
        }

        if phase not in prompts:
            return PipelineResult(type="transcript", text=text)

        print(f"[LLM Registration] Phase='{phase}' Input='{text}'")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": f'Student said: "{text.replace(chr(34), "")}"',
                        "system": prompts[phase],
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 50, "num_ctx": 256}
                    }
                )

            raw_res = response.json().get("response", "").strip()
            if raw_res.startswith("```json"):
                raw_res = raw_res[7:]
            if raw_res.endswith("```"):
                raw_res = raw_res[:-3]
            raw_res = raw_res.strip()

            print(f"[LLM Registration] Response: {raw_res}")
            data = json.loads(raw_res)

            if phase == "ready":
                if data.get("ready", False):
                    return PipelineResult(type="command", intent="student_ready", confidence="llm")
                return None
            else:
                extracted = data.get("value", text).strip()
                intent = "register_name" if phase == "name" else "register_reg_no"
                print(f"[LLM Registration] Extracted: '{extracted}'")
                return PipelineResult(type="command", intent=intent, target=extracted, confidence="llm")

        except Exception as e:
            print(f"[LLM Registration] Error: {type(e).__name__} - {e}, using raw text fallback")
            if phase == "ready":
                ready_kw = ["ready", "yes", "start", "begin", "i am ready"]
                if any(k in text.lower() for k in ready_kw):
                    return PipelineResult(type="command", intent="student_ready", confidence="fallback")
                return None
            intent = "register_name" if phase == "name" else "register_reg_no"
            return PipelineResult(type="command", intent=intent, target=text.strip(), confidence="fallback")

    # ── Main entry point ──────────────────────────────────────────────────

    async def process(self, text: str, context: SessionContext):
        raw_text = text.strip()
        if not raw_text:
            return None

        print(f"\n[Pipeline] ═══ Input: '{raw_text}' | State: {context.exam_state} | RegPhase: {context.registration_phase}")

        # Registration: route through LLM extraction
        if context.exam_state == "REGISTRATION" and context.registration_phase:
            return await self._llm_extract_registration(raw_text, context.registration_phase)

        # Onboarding/Waiting: ignore audio
        if context.exam_state not in ("EXAM",):
            print(f"[Pipeline] State={context.exam_state}, ignoring audio")
            return None

        # ── EXAM state processing ──

        # Stage 0: Vaani prefix detection
        stripped_text = self._detect_vaani_prefix(raw_text, context)
        if not stripped_text:
            return PipelineResult(type="transcript", text=raw_text)

        # Stage 1: Heuristic classification (skipped if Vaani detected — go straight to LLM)
        res = None
        if not context.vaani_prefix_detected:
            res = self._heuristic_classify(stripped_text, context)

        # Stage 2: LLM classification (fallback, or primary when Vaani prefix detected)
        if not res:
            res = await self._llm_classify(stripped_text, context)

        # Ensure transcript carries the original text
        if res.type == "transcript":
            res.text = raw_text
            print(f"[Pipeline] ═══ Result: TRANSCRIPT")
            return res

        print(f"[Pipeline] ═══ Result: COMMAND intent={res.intent} target={res.target} confidence={res.confidence}")

        # Tag destructive commands for frontend confirmation
        if res.intent == "submit_exam":
            res.requires_tts_confirm = True
            res.confirm_prompt = "Are you sure you want to submit your exam? This cannot be undone. Say I confirm submit, or cancel submit."

        return res


pipeline = IntentPipeline()
