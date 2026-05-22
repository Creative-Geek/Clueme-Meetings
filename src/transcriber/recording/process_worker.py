"""Recording process worker - captures audio from devices in a child process."""

import numpy as np
import pyaudiowpatch as pyaudio
import scipy.signal

from multiprocessing.synchronize import Event as _MultiprocessingEvent

from src.transcriber.constants import RECORD_CHUNK_MS, WHISPER_RATE


def _recording_process_worker(
    device_configs: list[dict],
    stop_flag: _MultiprocessingEvent,
    audio_queue,
):
    """Child process: open PyAudio streams, read frames, send via queue.

    If WASAPI triggers a native abort(), only THIS process dies.
    The parent process detects the death and stops gracefully.
    """
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
