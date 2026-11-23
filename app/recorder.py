"""Screen recording: the phone's own H.264/H.265 stream saved to an MP4 without re-encoding.

No quality is lost and it costs almost no CPU, because the packets the phone sends
are written straight into the file. The recording starts on the next key frame
(the session asks the phone for one) and ends if the picture changes size, for
example when the phone rotates, since an MP4 track cannot change resolution.
"""

import threading
import time
from fractions import Fraction

import av

TIME_BASE = Fraction(1, 1_000_000)   # the phone's timestamps are in microseconds


class Recorder:
    def __init__(self, path, codec, width, height):
        self.path = path
        self.codec = codec               # "h264" or "hevc"
        self.size = (width, height)
        self.started = time.monotonic()
        self.frames = 0
        self.error = None
        self._lock = threading.Lock()
        self._out = None
        self._stream = None
        self._t0 = None
        self._last_pts = -1
        self._closed = False

    def _open(self):
        out = av.open(str(self.path), "w", format="mp4")
        w, h = self.size
        stream = out.add_mux_stream(self.codec, width=w, height=h, time_base=TIME_BASE)
        self._out, self._stream = out, stream

    def write(self, data, pts, key_frame):
        """Add one packet (Annex B, with the codec config prepended to key frames)."""
        with self._lock:
            if self._closed:
                return
            if self._out is None:
                if not key_frame:
                    return       # a file must start on a key frame
                try:
                    self._open()
                except Exception as e:
                    self.error = str(e)
                    self._closed = True
                    return
                self._t0 = pts
            rel = max(pts - self._t0, self._last_pts + 1)
            self._last_pts = rel
            packet = av.Packet(data)
            packet.stream = self._stream
            packet.pts = packet.dts = rel
            packet.time_base = TIME_BASE
            packet.is_keyframe = key_frame
            try:
                self._out.mux(packet)
                self.frames += 1
            except Exception as e:
                self.error = str(e)
                self._closed = True

    @property
    def elapsed(self):
        return time.monotonic() - self.started

    def close(self):
        """Finish the file. Returns True if it holds at least one frame."""
        with self._lock:
            self._closed = True
            out, self._out = self._out, None
        if out is None:
            return False
        try:
            out.close()
        except Exception as e:
            self.error = self.error or str(e)
        if self.frames == 0:
            try:
                self.path.unlink()
            except OSError:
                pass
            return False
        return True
