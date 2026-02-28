import re
import json
import emoji
import os

EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F0A0-\U0001F0FF"
    "\U0001F201-\U0001F2FF"
    "\U0001F300-\U0001F3F0"
    "\U00002300-\U000023FF"
    "\U0001F004"
    "\U00002B06"
    "\u200D"
    "]+", flags=re.UNICODE
)
EMOJI_PATH = './resource/unicode_emojis.json'

class EmojiManager:
    def __init__(self):
        if os.path.exists(EMOJI_PATH) is False:
            emoji_unicode_pattern_list = []
        else:
            with open(EMOJI_PATH, "r", encoding="utf-8") as f:
                emoji_unicode_pattern_list = json.load(f)
        emoji_unicode_pattern_list = sorted(emoji_unicode_pattern_list, key=len, reverse=True)
        self.emoji_unicode_pattern_re = re.compile("|".join(re.escape(e) for e in emoji_unicode_pattern_list))

    def remove_emoji(self, text):
        text = self.emoji_unicode_pattern_re.sub('', text)
        # Use wide-range Unicode regex
        text = EMOJI_PATTERN.sub('', text)

        return text

    def is_all_emoji(self, text: str) -> bool:
        text = text.replace(" ", "")
        if not text:
            return False

        # If the entire string is in the emoji table, return True directly
        if self.emoji_unicode_pattern_re.fullmatch(text):
            return True
        
        # Otherwise, check character by character
        for ch in text:
            if not (self.emoji_unicode_pattern_re.fullmatch(ch) or EMOJI_PATTERN.fullmatch(ch)):
                return False
        return True
    
    @staticmethod
    def is_emoji(ch: str) -> bool:
        if EMOJI_PATTERN.match(ch):
            return True
        if emoji.is_emoji(ch):
            return True
        return False
