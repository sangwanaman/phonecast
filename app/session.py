"""A mirroring session: runs the scrcpy server on the phone and talks to it.

Video is decoded with FFmpeg (PyAV) and scaled straight to the on-screen size,
audio is played as raw PCM, and input goes over the control socket.
"""

import random
import socket
import struct
import threading
import time

import av
import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from . import adb, protocol
from .audio import AudioPlayer

CODEC_H265 = 0x68323635
FLAG_SESSION = 1 << 63
FLAG_CONFIG = 1 << 62
FLAG_KEY_FRAME = 1 << 61
PTS_MASK = FLAG_KEY_FRAME - 1

DARK_THRESHOLD = 14      # max channel value counted as "black"
DARK_FRACTION = 0.95     # share of black samples for a frame to count as dark (status bar icons may remain)


class SessionError(Exception):
    pass


def _recv_exact(sock, n):
    buf = bytearray(n)
    view = memoryview(buf)
    got = 0
    while got < n:
        r = sock.recv_into(view[got:], n - got)
        if r == 0:
            raise EOFError("connection closed")
        got += r
    return bytes(buf)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Session(QObject):
    connected = Signal(str)
    failed = Signal(str)
    stopped = Signal(str)
    frame_ready = Signal()
    video_size_changed = Signal(int, int)
    clipboard_changed = Signal(str)
    dark_changed = Signal(bool)
    recording_finished = Signal(str, bool, str)   # path, saved, reason

    def __init__(self, serial, options, video=True, audio=True, control=True):
        super().__init__()
        self.serial = serial
        self.opts = options
        self.want_video = video
        self.want_audio = audio
        self.want_control = control
        self.device_name = ""
        self.video_size = (0, 0)
        self.fps = 0.0
        self.player = None

        self._video_sock = None
        self._audio_sock = None
        self._ctrl = None
        self._ctrl_lock = threading.Lock()
        self._server = None
        self._port = None
        self._running = False
        self._stop_reported = False
        self._server_log = []
        self._cleanup_lock = threading.Lock()

        self._box = (1, 1)
        self._render_lock = threading.Lock()
        self._last_frame = None
        self._latest = None
        self._pending = False
        self._latest_lock = threading.Lock()
        self._frames = 0
        self._fps_t = time.monotonic()
        self._dark = False
        self._dark_t = 0.0
        self._clip_seq = 1
        self._video_codec = "h264"
        self._last_config = b""
        self.recorder = None
        self._rec_lock = threading.Lock()

    # ----------------------------------------------------------------- lifecycle

    def start(self):
        # not a daemon: if the app closes mid-connect, Python waits for it to clean up
        threading.Thread(target=self._connect, name="session-connect").start()

    def _check_stopped(self):
        if self._stop_reported:
            raise SessionError("stopped")

    def stop(self):
        self._stop_reported = True
        self._running = False
        self.stop_recording("stopped")
        self._cleanup()

    def _connect(self):
        try:
            self._open()
        except Exception as e:
            self._cleanup()
            if not self._stop_reported:
                self._stop_reported = True
                self.failed.emit(self._explain(e))
            return
        if self._stop_reported:
            self._cleanup()
            return
        self._running = True
        if self._video_sock:
            threading.Thread(target=self._video_loop, daemon=True, name="session-video").start()
        if self._audio_sock:
            threading.Thread(target=self._audio_loop, daemon=True, name="session-audio").start()
        if self._ctrl:
            threading.Thread(target=self._control_loop, daemon=True, name="session-control").start()
        if self.opts.get("screen_off") and self._ctrl:
            time.sleep(0.4)
            self.send(protocol.set_display_power(False))
        self.connected.emit(self.device_name)

    def _server_params(self, scid):
        o = self.opts
        p = [f"scid={scid:08x}", "log_level=info", "tunnel_forward=true"]
        if self.want_video:
            p += [f"video_codec={o.get('codec', 'h264')}",
                  f"video_bit_rate={int(o.get('bitrate_mbps', 12) * 1_000_000)}",
                  f"max_size={int(o.get('max_size', 0))}",
                  f"max_fps={int(o.get('max_fps', 60))}"]
        else:
            p.append("video=false")
        if self.want_audio:
            p.append("audio_codec=raw")
            if o.get("audio_dup"):
                p += ["audio_source=playback", "audio_dup=true"]
        else:
            p.append("audio=false")
        if not self.want_control:
            p.append("control=false")
        if o.get("show_touches"):
            p.append("show_touches=true")
        if o.get("keep_awake", True) and self.want_control:
            p.append("keep_active=true")
        if not o.get("wake_on_connect", True):
            p.append("power_on=false")
        return p

    def _open(self):
        code, out = adb.run(["push", str(adb.SERVER_FILE), adb.DEVICE_SERVER_PATH],
                            serial=self.serial, timeout=40)
        if code != 0:
            raise SessionError("Could not copy the mirroring service to the phone.\n" + out.strip())
        self._check_stopped()

        scid = random.randint(1, 0x7FFFFFFF)
        self._port = _free_port()
        code, out = adb.run(["forward", f"tcp:{self._port}", f"localabstract:scrcpy_{scid:08x}"],
                            serial=self.serial)
        if code != 0:
            raise SessionError("Could not open the USB tunnel.\n" + out.strip())
        self._check_stopped()

        args = ["shell", f"CLASSPATH={adb.DEVICE_SERVER_PATH}", "app_process", "/",
                "com.genymobile.scrcpy.Server", adb.SERVER_VERSION] + self._server_params(scid)
        self._server = adb.popen(args, serial=self.serial)
        threading.Thread(target=self._read_server_log, args=(self._server,), daemon=True,
                         name="session-log").start()

        deadline = time.monotonic() + 15
        first = True
        if self.want_video:
            self._video_sock = self._open_socket(first, deadline)
            first = False
        if self.want_audio:
            self._audio_sock = self._open_socket(first, deadline)
            first = False
        if self.want_control:
            self._ctrl = self._open_socket(first, deadline)
            self._ctrl.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        first_sock = self._video_sock or self._audio_sock or self._ctrl
        self.device_name = _recv_exact(first_sock, 64).split(b"\0")[0].decode("utf-8", "replace")

        if self._video_sock:
            codec_id = struct.unpack(">I", _recv_exact(self._video_sock, 4))[0]
            if codec_id in (0, 1):
                raise SessionError("The phone could not start screen capture.")
            self._video_codec = "hevc" if codec_id == CODEC_H265 else "h264"
        if self._audio_sock:
            codec_id = struct.unpack(">I", _recv_exact(self._audio_sock, 4))[0]
            if codec_id in (0, 1):
                # The phone refused audio capture: keep mirroring without sound
                self._audio_sock.close()
                self._audio_sock = None
            else:
                self.player = AudioPlayer()
                self.player.muted = self.opts.get("muted", False)

    def _open_socket(self, first, deadline):
        while True:
            self._check_stopped()
            if self._server is None or self._server.poll() is not None:
                time.sleep(0.2)
                raise SessionError("The mirroring service stopped on the phone.")
            if time.monotonic() > deadline:
                raise SessionError("The phone did not answer in time.")
            try:
                s = socket.create_connection(("127.0.0.1", self._port), timeout=2)
            except OSError:
                time.sleep(0.1)
                continue
            if not first:
                s.settimeout(None)
                return s
            # adb accepts the connection even if nothing listens on the phone yet;
            # the server proves it is there by sending one byte.
            s.settimeout(0.5)
            while time.monotonic() < deadline and not self._stop_reported:
                try:
                    b = s.recv(1)
                except socket.timeout:
                    continue
                except OSError:
                    b = b""
                if b == b"\x00":
                    s.settimeout(None)
                    return s
                break
            s.close()
            time.sleep(0.1)

    def _read_server_log(self, proc):
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self._server_log.append(line)
                del self._server_log[:-40]

    def _explain(self, error):
        msg = str(error) or error.__class__.__name__
        errors = [l for l in self._server_log if "ERROR" in l or "Exception" in l]
        if errors:
            msg += "\n\n" + "\n".join(errors[-3:])
        return msg

    def _cleanup(self):
        with self._cleanup_lock:
            self._cleanup_locked()

    def _cleanup_locked(self):
        for attr in ("_video_sock", "_audio_sock", "_ctrl"):
            s = getattr(self, attr)
            if s is not None:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                s.close()
                setattr(self, attr, None)
        if self._server is not None:
            try:
                self._server.terminate()
            except OSError:
                pass
            self._server = None
        if self._port is not None:
            port, self._port = self._port, None
            # not a daemon: Python waits for it on exit, so no stale forward is left behind
            threading.Thread(target=adb.run, args=(["forward", "--remove", f"tcp:{port}"],),
                             kwargs={"serial": self.serial, "timeout": 5}).start()
        if self.player is not None:
            self.player.close()
            self.player = None

    def _report_stop(self, reason):
        if self._stop_reported:
            return
        self._stop_reported = True
        self._running = False
        self.stop_recording("disconnected")
        self._cleanup()
        self.stopped.emit(reason)

    # --------------------------------------------------------------------- video

    def _video_loop(self):
        ctx = av.CodecContext.create(self._video_codec, "r")
        ctx.flags |= av.codec.context.Flags.low_delay
        sock = self._video_sock
        config = b""
        try:
            while self._running:
                header = _recv_exact(sock, 12)
                head = struct.unpack(">Q", header[:8])[0]
                if head & FLAG_SESSION:
                    _, w, h = struct.unpack(">III", header)
                    self.video_size = (w, h)
                    self.video_size_changed.emit(w, h)
                    rec = self.recorder
                    if rec is not None and rec.size != (w, h):
                        if rec.frames:
                            self.stop_recording("resized")
                        else:
                            rec.size = (w, h)
                    continue
                size = struct.unpack(">I", header[8:])[0]
                data = _recv_exact(sock, size)
                if head & FLAG_CONFIG:
                    config = data
                    self._last_config = data
                    continue
                raw = data
                if config:
                    data = config + data
                    config = b""
                rec = self.recorder
                if rec is not None:
                    key = bool(head & FLAG_KEY_FRAME)
                    # key frames carry the codec config in-band, so the file can start on any of them
                    packet = (self._last_config + raw) if key and self._last_config else raw
                    rec.write(packet, head & PTS_MASK, key)
                    if rec.error:
                        self.stop_recording("error")
                try:
                    frames = ctx.decode(av.Packet(data))
                except av.error.FFmpegError:
                    continue
                for frame in frames:
                    with self._render_lock:
                        self._last_frame = frame
                        self._render(frame)
                    self._count_frame()
        except (OSError, EOFError, AttributeError):
            self._report_stop("disconnected")

    @staticmethod
    def _color_args(frame):
        # Samsung tags its stream with a matrix FFmpeg cannot convert (YCgCo);
        # the pixels are really BT.601, which matches the phone's own screenshots.
        return {
            "src_colorspace": "ITU709" if int(frame.colorspace) == 1 else "ITU601",
            "src_color_range": "JPEG" if int(frame.color_range) == 2 else "MPEG",
            "dst_color_range": "JPEG",
        }

    def _render(self, frame):
        bw, bh = self._box
        fw, fh = frame.width, frame.height
        scale = min(bw / fw, bh / fh)
        tw, th = max(2, int(fw * scale)), max(2, int(fh * scale))
        arr = frame.to_ndarray(format="bgra", width=tw, height=th,
                               interpolation="AREA" if scale < 1 else "BICUBIC",
                               **self._color_args(frame))
        if not arr.flags["C_CONTIGUOUS"]:
            arr = np.ascontiguousarray(arr)
        img = QImage(arr.data, tw, th, arr.strides[0], QImage.Format_RGB32)
        with self._latest_lock:
            self._latest = (img, arr)
            notify = not self._pending
            self._pending = True
        if notify:
            self.frame_ready.emit()

        now = time.monotonic()
        if now - self._dark_t > 0.5:
            self._dark_t = now
            sample = arr[::max(1, th // 64), ::max(1, tw // 32), :3]
            dark = bool((sample.max(axis=2) < DARK_THRESHOLD).mean() > DARK_FRACTION)
            if dark != self._dark:
                self._dark = dark
                self.dark_changed.emit(dark)

    def _count_frame(self):
        self._frames += 1
        now = time.monotonic()
        if now - self._fps_t >= 1.0:
            self.fps = self._frames / (now - self._fps_t)
            self._frames = 0
            self._fps_t = now

    def current_fps(self):
        # the phone only sends frames when the screen changes, so a still screen reads 0
        return self.fps if time.monotonic() - self._fps_t < 2.0 else 0.0

    def take_frame(self):
        """Latest (QImage, buffer) pair; the buffer must outlive the QImage."""
        with self._latest_lock:
            self._pending = False
            return self._latest

    def snapshot(self):
        """The last frame at full resolution, as a standalone QImage."""
        with self._render_lock:
            frame = self._last_frame
            if frame is None:
                return None
            arr = np.ascontiguousarray(frame.to_ndarray(format="rgb24", **self._color_args(frame)))
        h, w = arr.shape[:2]
        return QImage(arr.data, w, h, arr.strides[0], QImage.Format_RGB888).copy()

    # ----------------------------------------------------------------- recording

    def start_recording(self, path):
        """Start saving the stream to path (an .mp4). Returns an error message or None."""
        from .recorder import Recorder
        if not self.want_video or not self._running:
            return "The phone's picture is not streaming."
        if self.recorder is not None:
            return "Already recording."
        w, h = self.video_size
        if not (w and h):
            return "The picture has not started yet."
        self.recorder = Recorder(path, self._video_codec, w, h)
        # ask the phone for a fresh key frame, so the recording starts right away
        self.send(protocol.simple(protocol.RESET_VIDEO))
        return None

    def stop_recording(self, reason="user"):
        with self._rec_lock:     # the video thread and the UI thread may both get here
            rec, self.recorder = self.recorder, None
        if rec is None:
            return
        saved = rec.close()
        why = reason if not rec.error else "error: " + rec.error
        self.recording_finished.emit(str(rec.path), saved, why)

    def set_box(self, width, height):
        """Size (in device pixels) of the area the video is drawn into."""
        width, height = max(2, int(width)), max(2, int(height))
        if (width, height) == self._box:
            return
        self._box = (width, height)
        with self._render_lock:
            if self._last_frame is not None:
                self._render(self._last_frame)

    # --------------------------------------------------------------------- audio

    def _audio_loop(self):
        sock = self._audio_sock
        try:
            while self._running:
                header = _recv_exact(sock, 12)
                head = struct.unpack(">Q", header[:8])[0]
                size = struct.unpack(">I", header[8:])[0]
                data = _recv_exact(sock, size)
                if head & FLAG_CONFIG:
                    continue
                player = self.player
                if player is not None:
                    player.feed(data)
        except (OSError, EOFError, AttributeError):
            if not self._video_sock:
                self._report_stop("disconnected")

    def set_muted(self, muted):
        if self.player is not None:
            self.player.muted = muted

    # ------------------------------------------------------------------- control

    def _control_loop(self):
        sock = self._ctrl
        try:
            while self._running:
                kind = _recv_exact(sock, 1)[0]
                if kind == protocol.DEVICE_CLIPBOARD:
                    n = struct.unpack(">I", _recv_exact(sock, 4))[0]
                    text = _recv_exact(sock, n).decode("utf-8", "replace")
                    self.clipboard_changed.emit(text)
                elif kind == protocol.DEVICE_ACK_CLIPBOARD:
                    _recv_exact(sock, 8)
                elif kind == protocol.DEVICE_UHID_OUTPUT:
                    _recv_exact(sock, 2)
                    n = struct.unpack(">H", _recv_exact(sock, 2))[0]
                    _recv_exact(sock, n)
                else:
                    break
        except (OSError, EOFError, AttributeError):
            if not self._video_sock:
                self._report_stop("disconnected")

    @property
    def has_control(self):
        return self._ctrl is not None

    def send(self, data):
        sock = self._ctrl
        if sock is None:
            return False
        with self._ctrl_lock:
            try:
                sock.sendall(data)
                return True
            except OSError:
                return False

    def press_key(self, keycode, meta=0):
        self.send(protocol.inject_keycode(protocol.ACTION_DOWN, keycode, 0, meta))
        self.send(protocol.inject_keycode(protocol.ACTION_UP, keycode, 0, meta))

    def type_text(self, text):
        # The server caps one message at 300 bytes
        for i in range(0, len(text), 100):
            self.send(protocol.inject_text(text[i:i + 100]))

    def paste_text(self, text):
        self._clip_seq += 1
        self.send(protocol.set_clipboard(self._clip_seq, text, paste=True))
