"""Audio accumulator for mixing speaker and microphone channels."""

import threading
import numpy as np


class _AudioAccumulator:
    """Thread-safe audio accumulator for speaker and mic channels.

    Unlike the old _AudioBuffer, this class has no timestamp-offset tracking —
    OnlineASRProcessor owns its own buffer internally. We just mix the two
    channels and hand chunks to the processor.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self._speaker: np.ndarray | None = None
        self._mic: np.ndarray | None = None

    def add_frames(self, kind: str, frame: np.ndarray):
        with self.lock:
            if kind == "speaker":
                self._speaker = (
                    np.concatenate((self._speaker, frame))
                    if self._speaker is not None
                    else frame.copy()
                )
            elif kind == "mic":
                self._mic = (
                    np.concatenate((self._mic, frame))
                    if self._mic is not None
                    else frame.copy()
                )

    def pop_mixed(self) -> np.ndarray | None:
        """Return a mixed mono chunk and clear the accumulator."""
        with self.lock:
            spk = self._speaker
            mic = self._mic
            self._speaker = None
            self._mic = None

        if spk is None and mic is None:
            return None
        if spk is None:
            return mic
        if mic is None:
            return spk

        # Pad shorter to same length, sum, clip
        if spk.shape[0] > mic.shape[0]:
            mic = np.pad(mic, (0, spk.shape[0] - mic.shape[0]))
        elif mic.shape[0] > spk.shape[0]:
            spk = np.pad(spk, (0, mic.shape[0] - spk.shape[0]))
        return np.clip(spk + mic, -1.0, 1.0).astype(np.float32)
