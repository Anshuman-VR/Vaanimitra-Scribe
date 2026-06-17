import json
import time
import httpx
from dataclasses import dataclass, field
from rapidfuzz import fuzz

@dataclass
class SessionContext:
    session_id: str
    question_index: int
    total_questions: int
    answer_word_count: int
    last_utterances: list
    exam_state: str
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

@dataclass
class UndoEntry:
    action: str
    payload: any
    timestamp: float

COMMAND_LEXICON = {
    "nav_next": ["next question", "next", "move on", "proceed to next", "go to next", "move forward", "continue"],
    "nav_prev": ["previous question", "go back", "last question", "previous", "back"],
    "nav_goto": ["go to question", "jump to question", "question number", "go to"],
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
    "pause_mic": ["pause", "stop listening", "mute"],
    "resume_mic": ["resume", "start listening", "unmute"],
}

VALID_INTENTS = list(COMMAND_LEXICON.keys())

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
}

def extract_number(text: str):
    import re
    match = re.search(r'\d+', text)
    if match: return int(match.group())
    for w, n in WORD_TO_NUM.items():
        if w in text: return n
    return None

class IntentPipeline:
    def __init__(self):
        self.undo_stack = {}

    def _push_undo(self, session_id: str, action: str, payload: any):
        if session_id not in self.undo_stack:
            self.undo_stack[session_id] = []
        self.undo_stack[session_id].append(UndoEntry(action=action, payload=payload, timestamp=time.time()))
        if len(self.undo_stack[session_id]) > 10:
            self.undo_stack[session_id].pop(0)

    def _detect_vaani_prefix(self, text: str, context: SessionContext) -> str:
        words = text.strip().split()
        if not words: return text
        first_word = words[0].lower().strip(',.?!')
        dist = fuzz.distance(first_word, "vaani")
        if dist <= 2:
            context.vaani_prefix_detected = True
            return " ".join(words[1:]).strip(', ')
        return text

    def _heuristic_classify(self, text: str, context: SessionContext):
        if len(text.split()) > 25:
            return PipelineResult(type="transcript", text=text)
            
        clean_text = text.lower().strip(',.?! ')
        
        domain_phrases = ["therefore", "hence", "because", "given that", "we know", "the formula", "substituting", "differentiating", "integrating", "the answer", "in conclusion", "to summarize", "firstly", "secondly"]
        if any(p in clean_text for p in domain_phrases):
            return PipelineResult(type="transcript", text=text)
            
        best_match = None
        best_score = 0
        for intent, phrases in COMMAND_LEXICON.items():
            for phrase in phrases:
                score = fuzz.token_set_ratio(clean_text, phrase)
                if score > best_score:
                    best_score = score
                    best_match = intent
                    
        if best_score >= 92 and best_match:
            res = PipelineResult(type="command", intent=best_match)
            if best_match in ["nav_goto", "delete_last_N"]:
                res.target = extract_number(clean_text)
                if not res.target and best_match == "nav_goto":
                    return None
            return res
            
        return None

    async def _llm_classify(self, text: str, context: SessionContext):
        system = f"""You are an intent classifier for an exam dictation system for students with disabilities.
Your only job is to classify a spoken utterance as either a navigation/control command or answer content.

CONTEXT YOU WILL RECEIVE:
- The utterance text
- Current question number and total questions
- Current answer length in words
- Last 2 utterances (for context)
- List of valid command intents

CLASSIFICATION RULES:
1. If the utterance is clearly a navigation or control action, return a command.
2. If there is ANY doubt, return transcript.
3. Short utterances (under 6 words) after a long answer segment are MORE likely commands.
4. Utterances containing subject-matter content are ALWAYS transcript.
5. The wake word "Vaani" may or may not be present. Ignore it for classification.

OUTPUT FORMAT: Respond with ONLY a JSON object. No explanation. No markdown. No preamble.
Valid formats:
{{"type": "transcript"}}
{{"type": "command", "intent": "nav_next", "target": null}}
{{"type": "command", "intent": "nav_goto", "target": 3}}
{{"type": "command", "intent": "delete_last_N", "target": 5}}

Valid intent values: {", ".join(VALID_INTENTS)}"""

        prompt = f"""Utterance: "{text.replace('"', '')}"
Current question: {context.question_index + 1} of {context.total_questions}
Answer so far: {context.answer_word_count} words
Recent context: {json.dumps(context.last_utterances)}"""

        try:
            async with httpx.AsyncClient(timeout=0.8) as client:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "qwen2.5:3b-instruct-q4_K_M",
                        "prompt": prompt,
                        "system": system,
                        "stream": False,
                        "options": {
                            "temperature": 0.0,
                            "num_predict": 50,
                            "num_ctx": 512
                        }
                    }
                )
            
            raw_res = response.json().get("response", "").strip()
            if raw_res.startswith("```json"): raw_res = raw_res[7:]
            if raw_res.endswith("```"): raw_res = raw_res[:-3]
            raw_res = raw_res.strip()
            
            data = json.loads(raw_res)
            if data.get("type") == "command" and data.get("intent") in VALID_INTENTS:
                return PipelineResult(type="command", intent=data.get("intent"), target=data.get("target"), confidence="llm")
            return PipelineResult(type="transcript", text=text, confidence="llm")
        except Exception as e:
            print(f"[LLM] Error: {e}")
            return PipelineResult(type="transcript", text=text, confidence="llm_error")

    async def process(self, text: str, context: SessionContext):
        raw_text = text.strip()
        if not raw_text: return None
        
        if context.exam_state != "EXAM":
            return PipelineResult(type="transcript", text=raw_text)

        stripped_text = self._detect_vaani_prefix(raw_text, context)
        if not stripped_text:
            return PipelineResult(type="transcript", text=raw_text)
            
        res = None
        if not context.vaani_prefix_detected:
            res = self._heuristic_classify(stripped_text, context)
            
        if not res:
            res = await self._llm_classify(stripped_text, context)
            
        if res.type == "transcript":
            res.text = raw_text
            return res
            
        if res.intent == "clear_answer":
            res.requires_tts_confirm = True
            res.confirm_prompt = f"Did you say: clear your entire answer for Question {context.question_index + 1}? Say I confirm submit to execute or cancel submit to go back."
        elif res.intent == "submit_exam":
            res.requires_tts_confirm = True
            res.confirm_prompt = "Did you say: submit your exam? This cannot be undone. Say I confirm submit to confirm or cancel submit to go back."
        elif res.intent == "delete_last_N" and isinstance(res.target, int) and res.target > 10:
            res.requires_tts_confirm = True
            res.confirm_prompt = f"Did you say: delete the last {res.target} words? Say I confirm submit to confirm or cancel submit to go back."
            
        return res

pipeline = IntentPipeline()
