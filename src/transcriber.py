"""LiveTranscriber — real-time audio transcription engine.

Extracted from the v3 growing-buffer experiment (vad_realtime_test.py).
Runs recording + transcription on daemon threads. Communicates with the
UI via callbacks.
"""

import multiprocessing
import threading
import time
from typing import Callable

import numpy as np
import pyaudiowpatch as pyaudio
import scipy.signal
from faster_whisper import WhisperModel
from src import debug_log


WHISPER_RATE = 16_000
RECORD_CHUNK_MS = 32

# Transcription loop
TRANSCRIBE_RATE_S = 1.0
MIN_AUDIO_FOR_PASS = 1.0
NO_SPEECH_THRESHOLD = 0.6
SAME_OUTPUT_THRESHOLD = 8

# Buffer management
MAX_BUFFER_S = 45
CLIP_OLDEST_S = 30


class _AudioBuffer:
    """Thread-safe growing audio buffer with offset tracking."""

    def __init__(self):
        self.lock = threading.Lock()
        self.frames_np: np.ndarray | None = None
        self.frames_offset = 0.0
        self.timestamp_offset = 0.0

    def add_frames(self, frame_np: np.ndarray):
        with self.lock:
            if self.frames_np is not None and self.frames_np.shape[0] > MAX_BUFFER_S * WHISPER_RATE:
                self.frames_offset += CLIP_OLDEST_S
                self.frames_np = self.frames_np[int(CLIP_OLDEST_S * WHISPER_RATE):]
                if self.timestamp_offset < self.frames_offset:
                    self.timestamp_offset = self.frames_offset
            if self.frames_np is None:
                self.frames_np = frame_np.copy()
            else:
                self.frames_np = np.concatenate((self.frames_np, frame_np), axis=0)

    def get_chunk_for_processing(self) -> tuple[np.ndarray | None, float]:
        with self.lock:
            if self.frames_np is None:
                return None, 0.0
            samples_skip = max(0, int((self.timestamp_offset - self.frames_offset) * WHISPER_RATE))
            chunk = self.frames_np[samples_skip:].copy()
        return chunk, chunk.shape[0] / WHISPER_RATE

    def advance_offset(self, seconds: float):
        with self.lock:
            self.timestamp_offset += seconds


def _find_loopback_device(p: pyaudio.PyAudio) -> dict | None:
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        return None
    default_out_idx = wasapi_info.get("defaultOutputDevice", -1)
    if default_out_idx < 0:
        return None
    default_speakers = p.get_device_info_by_index(default_out_idx)
    if default_speakers.get("isLoopbackDevice"):
        return default_speakers
    for loopback in p.get_loopback_device_info_generator():
        if default_speakers["name"] in loopback["name"]:
            return loopback
    for loopback in p.get_loopback_device_info_generator():
        return loopback
    return None


def _find_device_by_name(candidates, target_name: str) -> dict | None:
    """Find a device dict whose 'name' matches target_name exactly."""
    for dev in candidates:
        if dev["name"] == target_name:
            return dev
    return None


def list_devices() -> dict[str, list[dict]]:
    """Enumerate available speaker (loopback) and microphone devices.

    Returns ``{"speakers": [...], "mics": [...]}`` where each entry has
    ``"name"`` and ``"index"`` keys.  Callers should persist *names* only
    because device indices are not stable across sessions.
    """
    p = pyaudio.PyAudio()
    speakers: list[dict] = []
    mics: list[dict] = []

    try:
        for dev in p.get_loopback_device_info_generator():
            speakers.append({"name": dev["name"], "index": dev["index"]})

        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            host_idx = wasapi_info["index"]
            for i in range(wasapi_info.get("deviceCount", 0)):
                dev = p.get_device_info_by_host_api_device_index(host_idx, i)
                if dev.get("maxInputChannels", 0) > 0 and not dev.get("isLoopbackDevice", False):
                    mics.append({"name": dev["name"], "index": dev["index"]})
        except OSError:
            pass
    finally:
        p.terminate()

    return {"speakers": speakers, "mics": mics}


def _recording_process_worker(
    device_configs: list[dict],
    stop_flag: multiprocessing.Event,
    audio_queue: multiprocessing.Queue,
):
    """Child process: open PyAudio streams, read frames, send via queue.

    If WASAPI triggers a native abort(), only THIS process dies.
    The parent process detects the death and stops gracefully.
    """
    import pyaudiowpatch as pyaudio
    import numpy as np
    import scipy.signal

    p = pyaudio.PyAudio()
    streams = []

    for cfg in device_configs:
        # Find device by name
        dev_info = None
        if cfg["kind"] == "speaker":
            for lb in p.get_loopback_device_info_generator():
                if lb["name"] == cfg["device_name"]:
                    dev_info = lb
                    break
        else:
            try:
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                host_idx = wasapi_info["index"]
                for i in range(wasapi_info.get("deviceCount", 0)):
                    dev = p.get_device_info_by_host_api_device_index(host_idx, i)
                    if dev["name"] == cfg["device_name"]:
                        dev_info = dev
                        break
            except OSError:
                pass

        if dev_info is None:
            continue

        native_rate = int(dev_info["defaultSampleRate"])
        channels = int(dev_info["maxInputChannels"])
        frame_samples = int(native_rate * RECORD_CHUNK_MS / 1000)

        stream = p.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=native_rate,
            frames_per_buffer=frame_samples,
            input=True,
            input_device_index=dev_info["index"],
        )
        stream.start_stream()
        streams.append((stream, native_rate, channels, frame_samples, cfg["kind"]))

    # Read loop — runs until stop_flag is set or process is terminated
    while not stop_flag.is_set():
        for stream, native_rate, channels, frame_samples, kind in streams:
            try:
                available = stream.get_read_available()
                if available < frame_samples:
                    continue
                raw_data = stream.read(frame_samples, exception_on_overflow=False)
            except OSError:
                continue

            arr = np.frombuffer(raw_data, dtype=np.float32).reshape(-1, channels)
            mono = arr.mean(axis=1) if channels > 1 else arr.flatten()

            if native_rate != WHISPER_RATE:
                mono = scipy.signal.resample_poly(
                    mono, WHISPER_RATE, native_rate
                ).astype(np.float32)

            try:
                audio_queue.put_nowait((kind, mono.tobytes()))
            except Exception:
                pass  # queue full — drop frame

        stop_flag.wait(0.005)  # ~5ms between read cycles

    # Cleanup in the child process — if it aborts, only child dies
    for stream, *_ in streams:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
    try:
        p.terminate()
    except Exception:
        pass


class LiveTranscriber:
    """Real-time audio transcription with growing buffer and continuous re-transcription.

    Args:
        model_size: Whisper model size ("base", "small", "turbo", etc.)
        on_confirmed: callback(text: str, minute: int) when a segment is locked in
        on_tentative: callback(text: str) when tentative text updates
        on_ready: callback() when model is loaded and ready to transcribe
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

        self._model: WhisperModel | None = None
        self._speaker_buffer = _AudioBuffer()
        self._mic_buffer: _AudioBuffer | None = None
        self._stop_event = threading.Event()
        self._confirmed_segments: list[tuple[str, int]] = []
        self._current_tentative: str = ""

        self._start_time: float = 0.0
        self._is_loading = False
        self._is_running = False
        self._main_thread: threading.Thread | None = None
        self._recording_process: multiprocessing.Process | None = None
        self._audio_queue: multiprocessing.Queue | None = None

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    @property
    def is_running(self) -> bool:
        return self._is_running

    def _current_minute(self) -> int:
        """Return current system-time minute (minutes since epoch)."""
        return int(time.time() // 60)

    @property
    def current_minute(self) -> int:
        return self._current_minute()

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

    def start(self):
        """Start recording + transcription (non-blocking)."""
        debug_log.log_event("RECORDING", f"start() called — model={self.model_size} speaker={self._speaker_device_name!r} mic={self._mic_device_name!r}")
        self._stop_event.clear()
        self._is_loading = True
        self._main_thread = threading.Thread(target=self._init_and_run, daemon=True)
        self._main_thread.start()

    def stop(self, wait: bool = False) -> list[tuple[str, int]]:
        """Stop transcription. Returns confirmed segments.

        If wait=True, blocks until threads finish (necessary to ensure final
        segment promotion).
        """
        debug_log.log_event("RECORDING", f"stop() called — wait={wait} segments={len(self._confirmed_segments)}")
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

    def _init_and_run(self):
        """Load model, find devices, then start recording + transcription threads."""
        try:
            self._model = WhisperModel(self.model_size, device="auto", compute_type="auto")
        except Exception as exc:
            self._is_loading = False
            if self._on_error:
                self._on_error(f"Failed to load Whisper model '{self.model_size}': {exc}")
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
                    if dev.get("maxInputChannels", 0) > 0 and not dev.get("isLoopbackDevice", False):
                        candidates.append(dev)
                mic_info = _find_device_by_name(candidates, self._mic_device_name)
            except OSError:
                pass

        p_probe.terminate()

        if speaker_info is None:
            debug_log.log_event("RECORDING", "No loopback device found — aborting")
            self._is_loading = False
            if self._on_error:
                self._on_error("No loopback audio device found. Make sure you have an active audio output device.")
            return

        debug_log.log_event("RECORDING", f"speaker: {speaker_info.get('name', '?')} rate={speaker_info.get('defaultSampleRate')} ch={speaker_info.get('maxInputChannels')}")

        device_configs = [{"device_name": speaker_info["name"], "kind": "speaker"}]
        if mic_info is not None:
            debug_log.log_event("RECORDING", f"mic: {mic_info.get('name', '?')} rate={mic_info.get('defaultSampleRate')} ch={mic_info.get('maxInputChannels')}")
            self._mic_buffer = _AudioBuffer()
            device_configs.append({"device_name": mic_info["name"], "kind": "mic"})

        # Start recording in a child process — if WASAPI aborts, only child dies
        audio_queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=200)
        self._audio_queue = audio_queue  # kept so stop() can close it cleanly
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

    @staticmethod
    def _open_stream(p: pyaudio.PyAudio, device_info: dict) -> tuple:
        """Open a PyAudio stream and return (stream, params_dict)."""
        native_rate = int(device_info["defaultSampleRate"])
        channels = int(device_info["maxInputChannels"])
        frame_samples = int(native_rate * RECORD_CHUNK_MS / 1000)

        stream = p.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=native_rate,
            frames_per_buffer=frame_samples,
            input=True,
            input_device_index=device_info["index"],
        )
        stream.start_stream()
        return stream, {"native_rate": native_rate, "channels": channels, "frame_samples": frame_samples}

    def _queue_reader_loop(self, audio_queue: multiprocessing.Queue, stop_flag: multiprocessing.Event):
        """Read resampled mono frames from the child process queue and feed buffers."""
        while not self._stop_event.is_set():
            # Check if child process died unexpectedly
            if self._recording_process and not self._recording_process.is_alive():
                debug_log.log_event("RECORDING", "⚠️ recording process died — stopping")
                self._stop_event.set()
                break
            try:
                kind, mono_bytes = audio_queue.get(timeout=0.5)
                mono = np.frombuffer(mono_bytes, dtype=np.float32)
                if kind == "speaker":
                    self._speaker_buffer.add_frames(mono)
                elif kind == "mic" and self._mic_buffer is not None:
                    self._mic_buffer.add_frames(mono)
            except Exception:
                continue
        # Signal child to stop
        stop_flag.set()

    @staticmethod
    def _mix_chunks(
        spk: np.ndarray | None, spk_dur: float,
        mic: np.ndarray | None, mic_dur: float,
    ) -> tuple[np.ndarray | None, float]:
        """Mix speaker and mic audio. Pads shorter, sums, clips to [-1, 1]."""
        if mic is None or mic.shape[0] == 0:
            return spk, spk_dur
        if spk is None or spk.shape[0] == 0:
            return mic, mic_dur
        if spk.shape[0] > mic.shape[0]:
            mic = np.pad(mic, (0, spk.shape[0] - mic.shape[0]))
        elif mic.shape[0] > spk.shape[0]:
            spk = np.pad(spk, (0, mic.shape[0] - spk.shape[0]))
        return np.clip(spk + mic, -1.0, 1.0).astype(np.float32), max(spk_dur, mic_dur)

    def _advance_offsets(self, seconds: float):
        """Advance speaker (and optional mic) buffer offsets in lockstep."""
        self._speaker_buffer.advance_offset(seconds)
        if self._mic_buffer is not None:
            self._mic_buffer.advance_offset(seconds)

    def _transcription_loop(self):
        prev_tentative = ""
        same_output_count = 0

        while not self._stop_event.is_set():
            spk_chunk, spk_dur = self._speaker_buffer.get_chunk_for_processing()
            mic_chunk, mic_dur = (None, 0.0)
            if self._mic_buffer is not None:
                mic_chunk, mic_dur = self._mic_buffer.get_chunk_for_processing()
            chunk, duration = self._mix_chunks(spk_chunk, spk_dur, mic_chunk, mic_dur)

            if chunk is None or duration < MIN_AUDIO_FOR_PASS:
                time.sleep(0.1)
                continue

            # Build context prompt from recently confirmed text
            prompt_text = " ".join(seg[0] for seg in self._confirmed_segments[-5:]) if self._confirmed_segments else None

            try:
                segments_gen, info = self._model.transcribe(
                    chunk,
                    language="en",
                    beam_size=5,
                    vad_filter=True,
                    condition_on_previous_text=False,
                    initial_prompt=prompt_text,
                )
                segments = list(segments_gen)
            except Exception:
                time.sleep(0.5)
                continue

            if not segments:
                advanceAmount = max(0.0, duration - 1.0)
                if advanceAmount > 0:
                    self._advance_offsets(advanceAmount)
                time.sleep(TRANSCRIBE_RATE_S)
                continue

            segments = [s for s in segments if s.no_speech_prob < NO_SPEECH_THRESHOLD]
            if not segments:
                advanceAmount = max(0.0, duration - 1.0)
                if advanceAmount > 0:
                    self._advance_offsets(advanceAmount)
                time.sleep(TRANSCRIBE_RATE_S)
                continue

            # 1. Commit all but the last segment (with dedup guard)
            if len(segments) > 1:
                for seg in segments[:-1]:
                    text = seg.text.strip()
                    if not text:
                        continue
                    # Deduplicate: skip if identical to any of the last 3 confirmed
                    recent = [s[0] for s in self._confirmed_segments[-3:]]
                    if text in recent:
                        debug_log.log_event("TRANSCRIPT", f"dedup-skipped: {text!r}")
                        continue
                    minute = self._current_minute()
                    self._confirmed_segments.append((text, minute))
                    debug_log.log_event("TRANSCRIPT", f"confirmed: {text!r}")
                    if self._on_confirmed:
                        self._on_confirmed(text, minute)

            # 2. Extract tentative segment
            tentative_seg = segments[-1] if segments else None
            tentative_text = tentative_seg.text.strip() if tentative_seg else ""
            self._current_tentative = tentative_text

            if tentative_text and self._on_tentative:
                self._on_tentative(tentative_text)

            # 3. Same-output auto-promotion (silence detection)
            if tentative_text == prev_tentative and tentative_text:
                same_output_count += 1
            else:
                same_output_count = 0

            force_committed = False
            # Commit if unchanged for 4s, OR if the chunk is getting dangerously large (>20s)
            if same_output_count >= 4 or (duration > 20.0 and tentative_text):
                if tentative_text:
                    minute = self._current_minute()
                    self._confirmed_segments.append((tentative_text, minute))
                    debug_log.log_event("TRANSCRIPT", f"auto-promoted: {tentative_text!r}")
                    if self._on_confirmed:
                        self._on_confirmed(tentative_text, minute)
                same_output_count = 0
                self._current_tentative = ""
                force_committed = True

            prev_tentative = tentative_text

            # 4. Calculate safe buffer advance
            if force_committed:
                offset_advance = max(0.0, duration - 1.0)
            else:
                offset_advance = max(0.0, tentative_seg.start - 0.5)

            if offset_advance > 0:
                self._advance_offsets(offset_advance)

            time.sleep(TRANSCRIBE_RATE_S)

        # Final: promote any remaining tentative
        if self._current_tentative:
            minute = self._current_minute()
            self._confirmed_segments.append((self._current_tentative, minute))
            debug_log.log_event("TRANSCRIPT", f"final-promote: {self._current_tentative!r}")
            if self._on_confirmed:
                self._on_confirmed(self._current_tentative, minute)
            self._current_tentative = ""
