"""LiveTranscriber — real-time audio transcription engine."""

import multiprocessing
import threading
import time
from typing import Callable

import numpy as np
import pyaudiowpatch as pyaudio

from multiprocessing.synchronize import Event as _MultiprocessingEvent

from src.native_runtime import add_nvidia_runtime_dll_directory

add_nvidia_runtime_dll_directory()

from src.whisper_online import FasterWhisperASR, OnlineASRProcessor

from src import debug_log
from src.transcriber.constants import (
    WHISPER_RATE,
    MIN_AUDIO_FOR_PASS,
    BUFFER_TRIMMING_SEC,
    SENTENCE_FLUSH_TIMEOUT_S,
    _SENTENCE_ENDS,
)
from src.transcriber.devices.discovery import _find_device_by_name, _find_loopback_device
from src.transcriber.recording.process_worker import _recording_process_worker
from src.transcriber.audio.accumulator import _AudioAccumulator


class LiveTranscriber:
    """Real-time audio transcription powered by whisper_streaming (LocalAgreement-2).

    Args:
        model_size: Whisper model size (``"tiny"``, ``"base"``, ``"small"``,
            ``"turbo"``, etc.)
        speaker_device_name: WASAPI loopback device name to capture.
        mic_device_name: Microphone device name (optional).
        on_confirmed: callback(text: str, minute: int) when a segment is committed.
        on_tentative: callback(text: str) with the live unconfirmed caption.
        on_ready: callback() when the model is loaded and recording begins.
        on_error: callback(message: str) on fatal errors.
    """

    def __init__(
        self,
        model_size: str = "base",
        speaker_device_name: str = "",
        mic_device_name: str = "",
        on_confirmed: Callable[[str, int], None] | None = None,
        on_tentative: Callable[[str], None] | None = None,
        on_ready: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        self.model_size = model_size
        self._speaker_device_name = speaker_device_name
        self._mic_device_name = mic_device_name
        self._on_confirmed = on_confirmed
        self._on_tentative = on_tentative
        self._on_ready = on_ready
        self._on_error = on_error

        self._online: OnlineASRProcessor | None = None
        self._accumulator = _AudioAccumulator()
        self._stop_event = threading.Event()
        self._confirmed_segments: list[tuple[str, int]] = []
        self._current_tentative: str = ""

        self._start_time: float = 0.0
        self._is_loading = False
        self._is_running = False
        self._main_thread: threading.Thread | None = None
        self._recording_process: multiprocessing.Process | None = None
        self._audio_queue: multiprocessing.Queue | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def current_minute(self) -> int:
        return int(time.time() // 60)

    @property
    def tentative(self) -> str:
        return self._current_tentative

    @property
    def transcript(self) -> str:
        """Full confirmed transcript as a single string."""
        parts = [seg[0] for seg in self._confirmed_segments]
        if self._current_tentative:
            parts.append(self._current_tentative)
        return " ".join(parts)

    @property
    def confirmed_segments(self) -> list[tuple[str, int]]:
        return self._confirmed_segments.copy()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start recording + transcription (non-blocking)."""
        debug_log.log_event(
            "RECORDING",
            f"start() called — model={self.model_size} "
            f"speaker={self._speaker_device_name!r} mic={self._mic_device_name!r}",
        )
        self._stop_event.clear()
        self._is_loading = True
        self._main_thread = threading.Thread(target=self._init_and_run, daemon=True)
        self._main_thread.start()

    def stop(self, wait: bool = False) -> list[tuple[str, int]]:
        """Stop transcription. Returns confirmed segments.

        If wait=True, blocks until threads finish (necessary to ensure the final
        segment is promoted before the return value is used).
        """
        debug_log.log_event(
            "RECORDING",
            f"stop() called — wait={wait} segments={len(self._confirmed_segments)}",
        )
        self._stop_event.set()

        # Clean up the audio queue BEFORE terminating the child process.
        # If we terminate first, the queue's internal feeder thread references
        # a dead child, and Python's atexit triggers recursive exception handling
        # in the logging system (RecursionError / 'lost sys.stderr').
        if self._audio_queue is not None:
            try:
                self._audio_queue.cancel_join_thread()  # don't block on feeder thread
                self._audio_queue.close()
            except Exception:
                pass
            self._audio_queue = None

        # Terminate the recording child process (safe — OS cleans up WASAPI)
        if self._recording_process and self._recording_process.is_alive():
            self._recording_process.terminate()
            self._recording_process.join(timeout=3.0)
            debug_log.log_event("RECORDING", "recording process terminated")
        self._recording_process = None

        if wait and self._main_thread:
            self._main_thread.join(timeout=10.0)
        self._is_running = False
        return self._confirmed_segments.copy()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _init_and_run(self):
        """Load model, find devices, then start recording + transcription threads."""
        # Build the ASR backend and wrap it in OnlineASRProcessor.
        try:
            asr = FasterWhisperASR("en", self.model_size)
            # Use faster-whisper's built-in Silero VAD (no torch required).
            asr.use_vad()
            import os as _os
            self._online = OnlineASRProcessor(
                asr,
                tokenizer=None,                          # "segment" trimming only
                buffer_trimming=("segment", BUFFER_TRIMMING_SEC),
                logfile=open(_os.devnull, "w"),
            )
        except Exception as exc:
            self._is_loading = False
            if self._on_error:
                self._on_error(
                    f"Failed to load Whisper model '{self.model_size}': {exc}"
                )
            return

        p_probe = pyaudio.PyAudio()

        # Resolve speaker (loopback) device
        speaker_info = None
        if self._speaker_device_name:
            speaker_info = _find_device_by_name(
                p_probe.get_loopback_device_info_generator(),
                self._speaker_device_name,
            )
        if speaker_info is None:
            speaker_info = _find_loopback_device(p_probe)

        # Resolve mic device (only if name is non-empty)
        mic_info = None
        if self._mic_device_name:
            try:
                wasapi_info = p_probe.get_host_api_info_by_type(pyaudio.paWASAPI)
                host_idx = wasapi_info["index"]
                candidates = []
                for i in range(wasapi_info.get("deviceCount", 0)):
                    dev = p_probe.get_device_info_by_host_api_device_index(host_idx, i)
                    if dev.get("maxInputChannels", 0) > 0 and not dev.get(
                        "isLoopbackDevice", False
                    ):
                        candidates.append(dev)
                mic_info = _find_device_by_name(candidates, self._mic_device_name)
            except OSError:
                pass

        p_probe.terminate()

        if speaker_info is None:
            debug_log.log_event("RECORDING", "No loopback device found — aborting")
            self._is_loading = False
            if self._on_error:
                self._on_error(
                    "No loopback audio device found. Make sure you have an active audio output device."
                )
            return

        debug_log.log_event(
            "RECORDING",
            f"speaker: {speaker_info.get('name', '?')} "
            f"rate={speaker_info.get('defaultSampleRate')} "
            f"ch={speaker_info.get('maxInputChannels')}",
        )

        device_configs = [{"device_name": speaker_info["name"], "kind": "speaker"}]
        if mic_info is not None:
            debug_log.log_event(
                "RECORDING",
                f"mic: {mic_info.get('name', '?')} "
                f"rate={mic_info.get('defaultSampleRate')} "
                f"ch={mic_info.get('maxInputChannels')}",
            )
            device_configs.append({"device_name": mic_info["name"], "kind": "mic"})

        # Start recording in a child process — if WASAPI aborts, only child dies
        audio_queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=200)
        self._audio_queue = audio_queue
        stop_flag = multiprocessing.Event()

        self._recording_process = multiprocessing.Process(
            target=_recording_process_worker,
            args=(device_configs, stop_flag, audio_queue),
            daemon=True,
        )
        self._recording_process.start()

        self._is_loading = False
        self._start_time = time.monotonic()
        self._is_running = True

        if self._on_ready:
            self._on_ready()

        # Start queue reader + transcription threads in parent process
        reader_thread = threading.Thread(
            target=self._queue_reader_loop,
            args=(audio_queue, stop_flag),
            daemon=True,
        )
        transcription_thread = threading.Thread(
            target=self._transcription_loop, daemon=True
        )

        reader_thread.start()
        transcription_thread.start()
        reader_thread.join()
        transcription_thread.join()

        debug_log.log_event("RECORDING", "main thread finished")

    def _queue_reader_loop(
        self, audio_queue: multiprocessing.Queue, stop_flag: _MultiprocessingEvent
    ):
        """Read resampled mono frames from the child process queue and accumulate."""
        last_stats_time = time.monotonic()
        frames_received = 0
        peak_acc = 0.0
        rms_sq_acc = 0.0

        while not self._stop_event.is_set():
            # Check if child process died unexpectedly
            if self._recording_process and not self._recording_process.is_alive():
                debug_log.log_event("RECORDING", "⚠️ recording process died — stopping")
                self._stop_event.set()
                break
            try:
                kind, mono_bytes = audio_queue.get(timeout=0.5)
                mono = np.frombuffer(mono_bytes, dtype=np.float32)
                frames_received += 1
                peak_acc = max(peak_acc, float(np.max(np.abs(mono))))
                rms_sq_acc += float(np.mean(mono**2))
                self._accumulator.add_frames(kind, mono)
            except Exception:
                pass

            now = time.monotonic()
            if now - last_stats_time >= 1.0 and frames_received:
                rms = np.sqrt(rms_sq_acc / frames_received)
                debug_log.log_event(
                    "AUDIO_LEVEL",
                    f"frames={frames_received} peak={peak_acc:.4f} rms={rms:.4f}",
                )
                last_stats_time = now
                frames_received = 0
                peak_acc = 0.0
                rms_sq_acc = 0.0

        # Signal child to stop
        stop_flag.set()

    def _transcription_loop(self):
        """Feed audio chunks to OnlineASRProcessor and emit confirmed + tentative text.

        Confirmed word-level fragments from LocalAgreement are accumulated
        internally and only emitted via on_confirmed when:
          - sentence-ending punctuation (. ? !) is detected, OR
          - SENTENCE_FLUSH_TIMEOUT_S passes without a sentence boundary.

        The tentative display shows accumulated-but-not-yet-emitted text
        followed by the truly unconfirmed hypothesis, giving the user a
        flowing live-caption experience.
        """
        online = self._online
        if online is None:
            return

        # Accumulate audio for MIN_AUDIO_FOR_PASS seconds before the first pass.
        accumulated_s = 0.0

        # Sentence accumulation state
        pending_text = ""          # confirmed words not yet emitted
        pending_since: float | None = None  # monotonic timestamp of first pending word

        def _flush_pending():
            """Emit pending_text as a confirmed segment and reset."""
            nonlocal pending_text, pending_since
            text = pending_text.strip()
            if not text:
                return
            minute = self.current_minute
            self._confirmed_segments.append((text, minute))
            debug_log.log_event("TRANSCRIPT", f"confirmed: {text!r}")
            if self._on_confirmed:
                self._on_confirmed(text, minute)
            pending_text = ""
            pending_since = None

        while not self._stop_event.is_set():
            chunk = self._accumulator.pop_mixed()

            if chunk is not None and chunk.shape[0] > 0:
                online.insert_audio_chunk(chunk)
                accumulated_s += chunk.shape[0] / WHISPER_RATE

            if accumulated_s < MIN_AUDIO_FOR_PASS:
                time.sleep(0.05)
                continue

            # Run one Whisper pass.
            try:
                confirmed, tentative = online.process_iter_with_tentative()
            except Exception as exc:
                debug_log.log_event(
                    "WHISPER", f"process_iter() FAILED — {type(exc).__name__}: {exc}"
                )
                time.sleep(0.5)
                continue

            accumulated_s = 0.0

            # --- Accumulate confirmed text ------------------------------------
            confirmed_text = confirmed[2].strip() if confirmed[2] else ""
            if confirmed_text:
                if pending_text:
                    pending_text += " " + confirmed_text
                else:
                    pending_text = confirmed_text
                    pending_since = time.monotonic()

            # Check if we should flush the pending buffer:
            # 1) Sentence boundary detected
            should_flush = pending_text and pending_text[-1] in _SENTENCE_ENDS
            # 2) Time threshold exceeded
            if (
                not should_flush
                and pending_text
                and pending_since is not None
                and (time.monotonic() - pending_since) >= SENTENCE_FLUSH_TIMEOUT_S
            ):
                should_flush = True

            if should_flush:
                _flush_pending()

            # --- Emit tentative display ----------------------------------------
            # Show accumulated-but-not-emitted confirmed text + unconfirmed
            # hypothesis as one flowing "tentative" string.
            tentative = tentative.strip()
            display_parts = []
            if pending_text.strip():
                display_parts.append(pending_text.strip())
            if tentative:
                display_parts.append(tentative)
            display = " ".join(display_parts)

            if display != self._current_tentative:
                self._current_tentative = display
                if self._on_tentative:
                    self._on_tentative(display)

            time.sleep(1.0)

        # --- Final flush --------------------------------------------------
        # Flush any remaining pending confirmed text
        _flush_pending()

        # Flush anything OnlineASRProcessor hasn't committed yet
        try:
            final = online.finish()
            final_text = final[2].strip() if final[2] else ""
            if final_text:
                minute = self.current_minute
                self._confirmed_segments.append((final_text, minute))
                debug_log.log_event("TRANSCRIPT", f"final-promote: {final_text!r}")
                if self._on_confirmed:
                    self._on_confirmed(final_text, minute)
        except Exception as exc:
            debug_log.log_event(
                "WHISPER", f"finish() FAILED — {type(exc).__name__}: {exc}"
            )

        self._current_tentative = ""
