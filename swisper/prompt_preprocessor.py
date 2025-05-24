import re
import datetime
import emoji # For stripping emojis
from langdetect import detect, LangDetectException # For language detection
import logging

# Configure logger for this module
logger = logging.getLogger(__name__)

def clean_and_tag(raw: str, user_id="anon") -> dict:
    original_text = raw

    # 1. Whitespace normalization (replace multiple spaces/tabs/newlines with single space, strip)
    cleaned_text = re.sub(r'\s+', ' ', raw).strip()

    # 2. Emoji stripping
    # First, replace emojis with their textual representation (e.g., :smile:)
    demojized_text = emoji.demojize(cleaned_text)
    # Then, remove these textual representations
    cleaned_text_no_codes = re.sub(r':[a-zA-Z_]+(?:_[a-zA-Z_]+)*:', '', demojized_text)
    
    # As a fallback or for emojis not caught by demojize/regex (e.g., some complex flags or newer emojis)
    # remove characters that are known emojis.
    # This ensures that if demojize doesn't work perfectly, we still attempt removal.
    cleaned_text_no_direct_emojis = ''.join(char for char in cleaned_text_no_codes if char not in emoji.EMOJI_DATA)
    
    # Final strip and whitespace re-normalization after emoji removal, as removal might leave extra spaces
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text_no_direct_emojis).strip()


    # 3. Language detection
    detected_language = "en" # Default language
    if cleaned_text: # Only attempt detection if there's text left
        try:
            detected_language = detect(cleaned_text)
        except LangDetectException:
            logger.warning(f"Language detection failed for text: '{cleaned_text[:50]}...'. Defaulting to 'und'.")
            detected_language = "und" # Undetermined
    else:
        detected_language = "und" # No text to detect from

    # 4. Timestamp
    timestamp = datetime.datetime.now().isoformat()

    logger.info(f"Preprocessed: original='{original_text[:30]}...', cleaned='{cleaned_text[:30]}...', lang='{detected_language}'")

    return {
        "cleaned_text": cleaned_text,
        "language": detected_language,
        "timestamp": timestamp,
        "user_id": user_id,
        "original_text": original_text
    }

# Example Usage (for testing locally if needed)
if __name__ == '__main__':
    # Setup basic logging for local test
    logging.basicConfig(level=logging.INFO)

    test_cases = [
        "Hello world   how are you? 😄",
        "  Bonjour le monde  🇫🇷  ",
        "  これはテストです  🇯🇵  ✨  ",
        "    ",
        "Short one 👍",
        "12345",
        "Emoji test: 😂😃😄😅😆😇😈😉😊😋😌😍😎😏😐😑😒😓😔😕😖😗😘😙😚"
    ]
    for text in test_cases:
        result = clean_and_tag(text, user_id="test_user")
        logger.info(f"Original: '{text}'")
        logger.info(f"Processed: {result}\n")
