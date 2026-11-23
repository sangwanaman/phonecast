"""Plays the phone's raw PCM audio (48 kHz, stereo, s16le) with low latency."""

import threading

import numpy as np

try:
    import sounddevice as sd
except Exception:  # PortAudio missing or no audio device
    sd = None

RATE = 48000
FRAME_BYTES = 4  # 2 channels * 2 bytes
PREBUFFER = int(0.04 * RATE) * FRAME_BYTES   # start playing after 40 ms
MAX_BUFFER = int(0.12 * RATE) * FRAME_BYTES  # never lag more than 120 ms
TRIM_TO = int(0.05 * RATE) * FRAME_BYTES


class AudioPlayer:
    def __init__(self):
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._playing = False
        self.volume = 1.0
        self.muted = False
        self.error = None
        self._stream = None
        if sd is None:
            self.error = "Audio library unavailable"
            return
        try:
            self._stream = sd.RawOutputStream(samplerate=RATE, channels=2, dtype="int16",
                                              latency="low", callback=self._callback)
        except Exception as e:
            self.error = str(e)

    def feed(self, data):
        if self._stream is None:
            return
        with self._lock:
            self._buf += data
            if len(self._buf) > MAX_BUFFER:
                # The laptop clock runs slower than the phone's: drop the oldest audio
                del self._buf[:len(self._buf) - TRIM_TO]
            ready = not self._playing and len(self._buf) >= PREBUFFER
        if ready:
            self._playing = True
            try:
                self._stream.start()
            except Exception as e:
                self.error = str(e)

    def _callback(self, outdata, frames, time_info, status):
        n = frames * FRAME_BYTES
        with self._lock:
            chunk = bytes(self._buf[:n])
            del self._buf[:n]
        if self.muted or not chunk:
            outdata[:] = b"\x00" * n
            return
        if self.volume != 1.0:
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) * self.volume
            chunk = np.clip(samples, -32768, 32767).astype(np.int16).tobytes()
        outdata[:len(chunk)] = chunk
        if len(chunk) < n:
            outdata[len(chunk):] = b"\x00" * (n - len(chunk))

    def close(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
