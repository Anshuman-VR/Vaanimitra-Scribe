import re
import string

COMMANDS = [
    (["next question", "go to next", "move to next"], "nav_next"),
    (["previous question", "go back", "move to previous"], "nav_prev"),
    (["go to question"], "nav_goto"),
    (["read question", "read the question"], "read_question"),
    (["read my answer", "read answer", "read back my answer"], "read_answer"),
    (["clear answer", "clear my answer", "erase answer", "erase my answer"], "clear_answer"),
    (["delete last sentence", "remove last sentence", "undo last sentence"], "delete_last"),
    (["submit exam", "submit my exam", "finish exam", "end exam"], "submit"),
    (["i confirm submit", "i confirm submission", "yes submit"], "submit_confirm"),
    (["cancel submit", "cancel submission", "don't submit", "do not submit"], "submit_cancel"),
    (["i am ready to start the exam", "ready to start the exam", "i am ready to begin"], "student_ready"),
]

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
}

class Pipeline:
    def __init__(self):
        pass

    def process(self, text: str, words: list) -> dict:
        raw_text = text.strip()
        if not raw_text:
            return None

        # Clean text for matching
        clean_text = raw_text.lower()
        # Remove punctuation
        clean_text = clean_text.translate(str.maketrans('', '', string.punctuation)).strip()

        for phrases, action in COMMANDS:
            for phrase in phrases:
                if clean_text.startswith(phrase) or phrase in clean_text:
                    if action == "nav_goto":
                        # Try to extract number
                        target = None
                        digit_match = re.search(r'\d+', clean_text)
                        if digit_match:
                            target = int(digit_match.group())
                        else:
                            for word, num in WORD_TO_NUM.items():
                                if word in clean_text:
                                    target = num
                                    break
                        
                        if target is not None:
                            return {
                                "type": "command",
                                "action": "nav_goto",
                                "target": target,
                                "raw": raw_text
                            }
                        else:
                            # If we couldn't find a target, just treat it as transcript
                            break
                    else:
                        return {
                            "type": "command",
                            "action": action,
                            "raw": raw_text
                        }

        return {
            "type": "transcript",
            "text": raw_text,
            "words": words
        }

# Allow process to be called statically for the test script
def process(text: str, words: list) -> dict:
    return Pipeline().process(text, words)
