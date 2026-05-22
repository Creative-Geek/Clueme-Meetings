"""Constants for audio transcription."""

WHISPER_RATE = 16_000
RECORD_CHUNK_MS = 32

# How many seconds of audio to accumulate before the first transcribe pass.
# Lower = more responsive but more CPU; higher = more context for Whisper.
MIN_AUDIO_FOR_PASS = 1.0

# Buffer trimming: trim the rolling audio buffer when it exceeds this many
# seconds of confirmed-segment audio.
BUFFER_TRIMMING_SEC = 15

# Sentence accumulation: confirmed word-level fragments from LocalAgreement
# are buffered and only emitted via on_confirmed when a sentence boundary
# is detected (. ? !) or this many seconds pass without one.
SENTENCE_FLUSH_TIMEOUT_S = 8.0
_SENTENCE_ENDS = frozenset(".?!")
