"""Vendored from ufal/whisper_streaming (MIT License).
Source: https://github.com/ufal/whisper_streaming/blob/main/whisper_online.py
Commit pinned: main branch, retrieved 2026-05-10

Changes from upstream:
- Removed CLI entry point (__main__ block) and file-loading helpers (load_audio,
  load_audio_chunk) — not needed for embedded use.
- Removed unused backends: WhisperTimestampedASR, MLXWhisper, OpenaiApiASR.
- Removed librosa / soundfile imports (only used by the removed helpers).
- Removed VACOnlineASRProcessor (requires torch; we use faster-whisper's built-in VAD).
- FasterWhisperASR.load_model: changed device="cuda" → device="auto",
  compute_type="float16" → compute_type="auto" to match the existing convention
  and to gracefully fall back to CPU when no GPU is available.
- Added OnlineASRProcessor.process_iter_with_tentative() — returns both the
  confirmed flush and the current unconfirmed hypothesis, so callers can drive a
  live tentative display without accessing internal attributes directly.
"""

import sys
import numpy as np
from functools import lru_cache
import time
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ASR base
# ---------------------------------------------------------------------------

class ASRBase:

    sep = " "

    def __init__(self, lan, modelsize=None, cache_dir=None, model_dir=None, logfile=sys.stderr):
        self.logfile = logfile

        self.transcribe_kargs = {}
        if lan == "auto":
            self.original_language = None
        else:
            self.original_language = lan

        self.model = self.load_model(modelsize, cache_dir, model_dir)

    def load_model(self, modelsize, cache_dir, model_dir):
        raise NotImplementedError("must be implemented in the child class")

    def transcribe(self, audio, init_prompt=""):
        raise NotImplementedError("must be implemented in the child class")

    def use_vad(self):
        raise NotImplementedError("must be implemented in the child class")


# ---------------------------------------------------------------------------
# faster-whisper backend
# ---------------------------------------------------------------------------

class FasterWhisperASR(ASRBase):
    """Uses faster-whisper (CTranslate2) as the backend."""

    sep = ""

    def load_model(self, modelsize=None, cache_dir=None, model_dir=None):
        from faster_whisper import WhisperModel

        if model_dir is not None:
            logger.debug(
                f"Loading whisper model from model_dir {model_dir}. "
                "modelsize and cache_dir parameters are not used."
            )
            model_size_or_path = model_dir
        elif modelsize is not None:
            model_size_or_path = modelsize
        else:
            raise ValueError("modelsize or model_dir parameter must be set")

        # device="auto" / compute_type="auto": CTranslate2 picks GPU (CUDA) when
        # available and falls back to CPU — same behaviour as the previous
        # WhisperModel(model_size, device="auto", compute_type="auto") call.
        model = WhisperModel(
            model_size_or_path,
            device="auto",
            compute_type="auto",
            download_root=cache_dir,
        )
        return model

    def transcribe(self, audio, init_prompt=""):
        segments, info = self.model.transcribe(
            audio,
            language=self.original_language,
            initial_prompt=init_prompt,
            beam_size=5,
            word_timestamps=True,
            condition_on_previous_text=True,
            **self.transcribe_kargs,
        )
        return list(segments)

    def ts_words(self, segments):
        o = []
        for segment in segments:
            for word in segment.words:
                if segment.no_speech_prob > 0.9:
                    continue
                w = word.word
                t = (word.start, word.end, w)
                o.append(t)
        return o

    def segments_end_ts(self, res):
        return [s.end for s in res]

    def use_vad(self):
        """Enable faster-whisper's built-in Silero VAD filter (no torch required)."""
        self.transcribe_kargs["vad_filter"] = True

    def set_translate_task(self):
        self.transcribe_kargs["task"] = "translate"


# ---------------------------------------------------------------------------
# Hypothesis buffer (LocalAgreement-2)
# ---------------------------------------------------------------------------

class HypothesisBuffer:

    def __init__(self, logfile=sys.stderr):
        self.commited_in_buffer = []
        self.buffer = []
        self.new = []

        self.last_commited_time = 0.0
        self.last_commited_word = None

        self.logfile = logfile

    def insert(self, new, offset):
        new = [(a + offset, b + offset, t) for a, b, t in new]
        self.new = [(a, b, t) for a, b, t in new if a > self.last_commited_time - 0.1]

        if len(self.new) >= 1:
            a, b, t = self.new[0]
            if abs(a - self.last_commited_time) < 1:
                if self.commited_in_buffer:
                    cn = len(self.commited_in_buffer)
                    nn = len(self.new)
                    for i in range(1, min(min(cn, nn), 5) + 1):
                        c = " ".join(
                            [self.commited_in_buffer[-j][2] for j in range(1, i + 1)][::-1]
                        )
                        tail = " ".join(self.new[j - 1][2] for j in range(1, i + 1))
                        if c == tail:
                            words = []
                            for j in range(i):
                                words.append(repr(self.new.pop(0)))
                            logger.debug(f"removing last {i} words: {' '.join(words)}")
                            break

    def flush(self):
        """Return the longest common prefix of the last two inserts (committed chunk)."""
        commit = []
        while self.new:
            na, nb, nt = self.new[0]

            if len(self.buffer) == 0:
                break

            if nt == self.buffer[0][2]:
                commit.append((na, nb, nt))
                self.last_commited_word = nt
                self.last_commited_time = nb
                self.buffer.pop(0)
                self.new.pop(0)
            else:
                break
        self.buffer = self.new
        self.new = []
        self.commited_in_buffer.extend(commit)
        return commit

    def pop_commited(self, time):
        while self.commited_in_buffer and self.commited_in_buffer[0][1] <= time:
            self.commited_in_buffer.pop(0)

    def complete(self):
        return self.buffer


# ---------------------------------------------------------------------------
# Online ASR processor
# ---------------------------------------------------------------------------

class OnlineASRProcessor:

    SAMPLING_RATE = 16000

    def __init__(self, asr, tokenizer=None, buffer_trimming=("segment", 15), logfile=sys.stderr):
        """
        asr: FasterWhisperASR (or compatible ASRBase subclass)
        tokenizer: sentence tokenizer — only required for buffer_trimming="sentence"
        buffer_trimming: ("segment"|"sentence", seconds)
        """
        self.asr = asr
        self.tokenizer = tokenizer
        self.logfile = logfile

        self.init()

        self.buffer_trimming_way, self.buffer_trimming_sec = buffer_trimming

    def init(self, offset=None):
        """Run this when starting or restarting processing."""
        self.audio_buffer = np.array([], dtype=np.float32)
        self.transcript_buffer = HypothesisBuffer(logfile=self.logfile)
        self.buffer_time_offset = 0.0
        if offset is not None:
            self.buffer_time_offset = offset
        self.transcript_buffer.last_commited_time = self.buffer_time_offset
        self.commited = []

    def insert_audio_chunk(self, audio):
        self.audio_buffer = np.append(self.audio_buffer, audio)

    def prompt(self):
        """Return (prompt, context) for the next transcribe call."""
        k = max(0, len(self.commited) - 1)

        while k > 0 and self.commited[k - 1][1] > self.buffer_time_offset:
            k -= 1

        p = self.commited[:k]
        p = [t for _, _, t in p]
        prompt = []
        l = 0
        while p and l < 200:
            x = p.pop(-1)
            l += len(x) + 1
            prompt.append(x)
        non_prompt = self.commited[k:]
        return (
            self.asr.sep.join(prompt[::-1]),
            self.asr.sep.join(t for _, _, t in non_prompt),
        )

    def process_iter(self):
        """Run on the current audio buffer.

        Returns: (beg_timestamp, end_timestamp, "confirmed text") or (None, None, "").
        The non-empty text is committed and will not change.
        """
        prompt, non_prompt = self.prompt()
        logger.debug(f"PROMPT: {prompt}")
        logger.debug(f"CONTEXT: {non_prompt}")
        logger.debug(
            f"transcribing {len(self.audio_buffer)/self.SAMPLING_RATE:2.2f}s "
            f"from {self.buffer_time_offset:2.2f}"
        )
        res = self.asr.transcribe(self.audio_buffer, init_prompt=prompt)

        tsw = self.asr.ts_words(res)

        self.transcript_buffer.insert(tsw, self.buffer_time_offset)
        o = self.transcript_buffer.flush()
        self.commited.extend(o)
        completed = self.to_flush(o)
        logger.debug(f">>>>COMPLETE NOW: {completed}")
        the_rest = self.to_flush(self.transcript_buffer.complete())
        logger.debug(f"INCOMPLETE: {the_rest}")

        if o and self.buffer_trimming_way == "sentence":
            if len(self.audio_buffer) / self.SAMPLING_RATE > self.buffer_trimming_sec:
                self.chunk_completed_sentence()

        if self.buffer_trimming_way == "segment":
            s = self.buffer_trimming_sec
        else:
            s = 30

        if len(self.audio_buffer) / self.SAMPLING_RATE > s:
            self.chunk_completed_segment(res)
            logger.debug("chunking segment")

        logger.debug(f"len of buffer now: {len(self.audio_buffer)/self.SAMPLING_RATE:2.2f}")
        return self.to_flush(o)

    def process_iter_with_tentative(self):
        """Like process_iter() but also returns the current unconfirmed hypothesis.

        Returns:
            confirmed: (beg, end, text) or (None, None, "") — committed, won't change.
            tentative: str — the current unconfirmed tail (may be empty).

        This drives a live-caption display: show tentative immediately, replace it
        with confirmed text once LocalAgreement commits it.
        """
        prompt, non_prompt = self.prompt()
        logger.debug(f"PROMPT: {prompt}")
        logger.debug(f"CONTEXT: {non_prompt}")
        logger.debug(
            f"transcribing {len(self.audio_buffer)/self.SAMPLING_RATE:2.2f}s "
            f"from {self.buffer_time_offset:2.2f}"
        )
        res = self.asr.transcribe(self.audio_buffer, init_prompt=prompt)

        tsw = self.asr.ts_words(res)

        self.transcript_buffer.insert(tsw, self.buffer_time_offset)
        o = self.transcript_buffer.flush()
        self.commited.extend(o)
        confirmed = self.to_flush(o)

        # Unconfirmed tail — words Whisper produced but LocalAgreement hasn't
        # committed yet.  This is the "live caption" text.
        tentative_words = self.transcript_buffer.complete()
        tentative_text = self.to_flush(tentative_words)[2]  # just the string

        logger.debug(f">>>>COMPLETE NOW: {confirmed}")
        logger.debug(f"INCOMPLETE (tentative): {tentative_text!r}")

        if o and self.buffer_trimming_way == "sentence":
            if len(self.audio_buffer) / self.SAMPLING_RATE > self.buffer_trimming_sec:
                self.chunk_completed_sentence()

        if self.buffer_trimming_way == "segment":
            s = self.buffer_trimming_sec
        else:
            s = 30

        if len(self.audio_buffer) / self.SAMPLING_RATE > s:
            self.chunk_completed_segment(res)
            logger.debug("chunking segment")

        logger.debug(f"len of buffer now: {len(self.audio_buffer)/self.SAMPLING_RATE:2.2f}")
        return confirmed, tentative_text

    def chunk_completed_sentence(self):
        if self.commited == []:
            return
        logger.debug(self.commited)
        sents = self.words_to_sentences(self.commited)
        for s in sents:
            logger.debug(f"\t\tSENT: {s}")
        if len(sents) < 2:
            return
        while len(sents) > 2:
            sents.pop(0)
        chunk_at = sents[-2][1]
        logger.debug(f"--- sentence chunked at {chunk_at:2.2f}")
        self.chunk_at(chunk_at)

    def chunk_completed_segment(self, res):
        if self.commited == []:
            return

        ends = self.asr.segments_end_ts(res)
        t = self.commited[-1][1]

        if len(ends) > 1:
            e = ends[-2] + self.buffer_time_offset
            while len(ends) > 2 and e > t:
                ends.pop(-1)
                e = ends[-2] + self.buffer_time_offset
            if e <= t:
                logger.debug(f"--- segment chunked at {e:2.2f}")
                self.chunk_at(e)
            else:
                logger.debug("--- last segment not within committed area")
        else:
            logger.debug("--- not enough segments to chunk")

    def chunk_at(self, time):
        """Trim the hypothesis and audio buffer at 'time'."""
        self.transcript_buffer.pop_commited(time)
        cut_seconds = time - self.buffer_time_offset
        self.audio_buffer = self.audio_buffer[int(cut_seconds * self.SAMPLING_RATE):]
        self.buffer_time_offset = time

    def words_to_sentences(self, words):
        """Sentence-segment word list using self.tokenizer."""
        assert self.tokenizer is not None, "words_to_sentences requires a tokenizer"
        cwords = [w for w in words]
        t = " ".join(o[2] for o in cwords)
        s = self.tokenizer.split(t)
        out = []
        while s:
            beg = None
            end = None
            sent = s.pop(0).strip()
            fsent = sent
            while cwords:
                b, e, w = cwords.pop(0)
                w = w.strip()
                if beg is None and sent.startswith(w):
                    beg = b
                elif end is None and sent == w:
                    end = e
                    out.append((beg, end, fsent))
                    break
                sent = sent[len(w):].strip()
        return out

    def finish(self):
        """Flush incomplete text at the end of processing.

        Returns the same format as process_iter().
        """
        o = self.transcript_buffer.complete()
        f = self.to_flush(o)
        logger.debug(f"last, non-committed: {f}")
        self.buffer_time_offset += len(self.audio_buffer) / 16000
        return f

    def to_flush(self, sents, sep=None, offset=0):
        if sep is None:
            sep = self.asr.sep
        t = sep.join(s[2] for s in sents)
        if len(sents) == 0:
            b = None
            e = None
        else:
            b = offset + sents[0][0]
            e = offset + sents[-1][1]
        return (b, e, t)
