"""Audio device discovery for WASAPI loopback and microphone devices."""

import pyaudiowpatch as pyaudio


def _find_loopback_device(p: pyaudio.PyAudio) -> dict | None:
    """Find the default WASAPI loopback device."""
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
                if dev.get("maxInputChannels", 0) > 0 and not dev.get(
                    "isLoopbackDevice", False
                ):
                    mics.append({"name": dev["name"], "index": dev["index"]})
        except OSError:
            pass
    finally:
        p.terminate()

    return {"speakers": speakers, "mics": mics}
