import pytest
from unittest import mock
import datetime
from swisper.prompt_preprocessor import clean_and_tag # Assuming swisper is in PYTHONPATH for tests

# Helper to check ISO format (basic check)
def is_iso_format(timestamp_str):
    try:
        datetime.datetime.fromisoformat(timestamp_str)
        return True
    except ValueError:
        return False

@pytest.fixture
def mock_datetime_now():
    # Fixed timestamp for testing
    fixed_now = datetime.datetime(2024, 1, 1, 12, 0, 0)
    # Patching datetime.datetime within the swisper.prompt_preprocessor module
    with mock.patch('swisper.prompt_preprocessor.datetime.datetime') as mock_dt_datetime:
        mock_dt_datetime.now.return_value = fixed_now
        yield fixed_now.isoformat()


@pytest.fixture
def mock_langdetect():
    # Mock langdetect.detect within the swisper.prompt_preprocessor module
    with mock.patch('swisper.prompt_preprocessor.detect') as mock_detect:
        # Default mock behavior, can be overridden in tests
        mock_detect.return_value = 'en'
        yield mock_detect

def test_whitespace_normalization(mock_datetime_now, mock_langdetect):
    raw = "  hello   world  \n next line "
    result = clean_and_tag(raw, user_id="ws_user")
    assert result["cleaned_text"] == "hello world next line"
    assert result["original_text"] == raw
    assert result["user_id"] == "ws_user"
    assert result["timestamp"] == mock_datetime_now

def test_emoji_stripping(mock_datetime_now, mock_langdetect):
    raw = "Hello 😄 world 👍🇫🇷"
    result = clean_and_tag(raw)
    # Based on the implementation:
    # 1. demojize: "Hello :grinning_face_with_big_eyes: world :thumbs_up: :flag_France:"
    # 2. remove codes: "Hello  world  " (assuming codes are removed, spaces might remain)
    # 3. remove direct emojis (shouldn't be any left if codes covered all)
    # 4. final strip and re.sub: "Hello world"
    assert result["cleaned_text"] == "Hello world"
    assert "😄" not in result["cleaned_text"] # Double check after visual inspection of implementation
    assert "👍" not in result["cleaned_text"]
    assert "🇫🇷" not in result["cleaned_text"]


def test_language_detection_english(mock_datetime_now, mock_langdetect):
    raw = "This is a test sentence."
    mock_langdetect.return_value = 'en'
    result = clean_and_tag(raw)
    assert result["language"] == 'en'
    mock_langdetect.assert_called_with("This is a test sentence.")


def test_language_detection_french(mock_datetime_now, mock_langdetect):
    raw = "Ceci est une phrase de test."
    mock_langdetect.return_value = 'fr'
    result = clean_and_tag(raw)
    assert result["language"] == 'fr'
    mock_langdetect.assert_called_with("Ceci est une phrase de test.")

def test_language_detection_failure_due_to_exception(mock_datetime_now, mock_langdetect):
    raw = "..." # Ambiguous text
    # Importing LangDetectException from the correct module for patching side_effect
    from langdetect import LangDetectException
    mock_langdetect.side_effect = LangDetectException(0, "Detection failed") # Simulate langdetect failure
    result = clean_and_tag(raw)
    assert result["language"] == 'und' # Default for failure

def test_empty_string(mock_datetime_now, mock_langdetect):
    raw = ""
    result = clean_and_tag(raw)
    assert result["cleaned_text"] == ""
    assert result["language"] == 'und' # No text to detect from
    assert result["original_text"] == ""

def test_string_with_only_spaces(mock_datetime_now, mock_langdetect):
    raw = "   "
    result = clean_and_tag(raw)
    assert result["cleaned_text"] == ""
    assert result["language"] == 'und'

def test_string_with_only_emojis(mock_datetime_now, mock_langdetect):
    raw = "😄👍🇫🇷"
    result = clean_and_tag(raw)
    # After all emoji removal steps and final strip, should be empty
    assert result["cleaned_text"] == "" 
    assert result["language"] == 'und'

def test_timestamp_format(mock_datetime_now):
    # The mock_datetime_now fixture itself returns the ISO formatted string
    # We call clean_and_tag, and it should use the mocked datetime.now()
    result = clean_and_tag("test") # mock_langdetect will default to 'en'
    assert result["timestamp"] == mock_datetime_now
    assert is_iso_format(result["timestamp"])

def test_user_id_passthrough(mock_datetime_now, mock_langdetect):
    result = clean_and_tag("test", user_id="specific_user_123")
    assert result["user_id"] == "specific_user_123"

def test_specific_emoji_removal_pattern(mock_datetime_now, mock_langdetect):
    raw_text = "Text with 😄 emoji"
    # Implementation steps:
    # 1. Whitespace: "Text with 😄 emoji"
    # 2. Demojize: "Text with :grinning_face_with_big_eyes: emoji"
    # 3. Remove codes: "Text with  emoji" (double space)
    # 4. Remove direct emojis (no effect if codes are comprehensive)
    # 5. Final strip and re.sub: "Text with emoji"
    result = clean_and_tag(raw_text)
    assert result["cleaned_text"] == "Text with emoji"

def test_mixed_content_with_newlines_and_tabs(mock_datetime_now, mock_langdetect):
    raw = "Line one.\n\nLine two.\t Line three. 😄"
    result = clean_and_tag(raw)
    assert result["cleaned_text"] == "Line one. Line two. Line three."
    assert result["original_text"] == raw

def test_text_with_no_emojis_or_extra_whitespace(mock_datetime_now, mock_langdetect):
    raw = "This is a clean sentence."
    result = clean_and_tag(raw)
    assert result["cleaned_text"] == "This is a clean sentence."
    assert result["language"] == 'en' # Assuming mock_langdetect default
    assert result["original_text"] == raw
    assert result["timestamp"] == mock_datetime_now
    assert result["user_id"] == "anon" # Default user_id

# Example of a test that might need adjustment if langdetect is very sensitive
# For now, we rely on the mock.
def test_short_text_language_detection(mock_datetime_now, mock_langdetect):
    raw = "ok"
    mock_langdetect.return_value = 'en' # Explicitly mock for this case
    result = clean_and_tag(raw)
    assert result["language"] == 'en'
    mock_langdetect.assert_called_with("ok")

def test_language_detection_for_empty_cleaned_text(mock_datetime_now, mock_langdetect):
    raw = "👍👍👍" # This should result in an empty cleaned_text
    result = clean_and_tag(raw)
    assert result["cleaned_text"] == ""
    assert result["language"] == 'und' # Undetermined as no text for detection
    # Ensure langdetect.detect was not called with an empty string if that's the logic
    mock_langdetect.assert_not_called()
    # Or, if it can be called with empty string, check behavior:
    # mock_langdetect.assert_called_with("") -> then ensure output is 'und'
    # Based on current prompt_preprocessor: if cleaned_text: detect() else: detected_language = "und"
    # So, it should not be called.
    
# To run these tests, ensure pytest is installed and swisper directory is in PYTHONPATH
# Example: PYTHONPATH=. pytest swisper/tests/test_preprocessor.py
