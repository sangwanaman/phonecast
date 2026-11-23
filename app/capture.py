"""HDMI capture card source.

The phone drives a real HDMI display (so nothing is hidden, exactly like a TV),
a USB capture card turns that HDMI signal into a webcam-like device, and this
class shows it. Control still goes to the phone over Wi-Fi adb.
"""

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (QAudioInput, QAudioOutput, QCamera, QMediaCaptureSession,
                                  QMediaDevices, QVideoSink)


def video_inputs():
    return list(QMediaDevices.videoInputs())


def audio_inputs():
    return list(QMediaDevices.audioInputs())


def _best_format(device):
    def score(fmt):
        size = fmt.resolution()
        area = min(size.width() * size.height(), 1920 * 1080)
        return (area, min(fmt.maxFrameRate(), 60.0))
    formats = list(device.videoFormats())
    return max(formats, key=score) if formats else None


class CaptureSource(QObject):
    frame_ready = Signal()
    error = Signal(str)

    def __init__(self, video_device, audio_device=None):
        super().__init__()
        self.frame_size = (0, 0)
        self.last_image = None
        self._box = (1, 1)
        self._latest = None

        self.camera = QCamera(video_device)
        fmt = _best_format(video_device)
        if fmt is not None:
            self.camera.setCameraFormat(fmt)
        self.camera.errorOccurred.connect(lambda _err, text: self.error.emit(text))

        self.capture = QMediaCaptureSession()
        self.capture.setCamera(self.camera)
        self.sink = QVideoSink()
        self.capture.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._on_frame)

        self.audio_in = self.audio_out = None
        if audio_device is not None:
            self.audio_in = QAudioInput(audio_device)
            self.audio_out = QAudioOutput()
            self.capture.setAudioInput(self.audio_in)
            self.capture.setAudioOutput(self.audio_out)

    def start(self):
        self.camera.start()

    def stop(self):
        self.camera.stop()
        if self.audio_out is not None:
            self.audio_out.setMuted(True)

    def set_muted(self, muted):
        if self.audio_out is not None:
            self.audio_out.setMuted(muted)

    def set_box(self, width, height):
        self._box = (max(2, int(width)), max(2, int(height)))
        if self.last_image is not None:
            self._publish(self.last_image)

    def _on_frame(self, frame):
        img = frame.toImage()
        if img.isNull():
            return
        self.last_image = img
        self.frame_size = (img.width(), img.height())
        self._publish(img)

    def _publish(self, img):
        bw, bh = self._box
        scaled = img.scaled(bw, bh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._latest = (scaled.convertToFormat(QImage.Format_RGB32), None)
        self.frame_ready.emit()

    def take_frame(self):
        return self._latest
