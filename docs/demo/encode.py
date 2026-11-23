"""Turns the captured frames into docs/demo.webp (animated, loops forever) and docs/demo.png (poster).

    python docs/demo/encode.py <frames folder> [--fps 20] [--width 800]

The capture runs a little past one loop; the loop ends at the frame that best matches the first
one again, so the animation repeats without a jump. Frames are stored losslessly: lossy WebP
animation builds each frame on the last one and its small errors pile up into ghosts of
earlier screens, while flat interface colours compress well without loss anyway.
The poster is the middle of the recording beat (the red timer showing), the frame that tells
the whole story on its own.
"""

import argparse
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

DOCS = Path(__file__).resolve().parent.parent


def load(path):
    with av.open(str(path)) as c:
        return next(c.decode(video=0)).to_ndarray(format="rgb24")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--width", type=int, default=800)
    ap.add_argument("--poster", type=float, default=None, help="seconds into the loop for the still")
    args = ap.parse_args()

    files = sorted(Path(args.frames).glob("f*.png"))
    frames = [load(f) for f in files]
    first = frames[0].astype(np.int16)
    # the loop is at least 10 s long: find where the picture returns to the opening frame
    search = range(10 * args.fps, len(frames))
    diffs = [(np.abs(frames[i].astype(np.int16) - first).mean(), i) for i in search]
    best, end = min(diffs)
    loop = frames[:end]
    print(f"{len(files)} frames, loop = {end} frames ({end / args.fps:.2f} s), seam difference {best:.2f}")

    h, w = loop[0].shape[:2]
    out_w = args.width
    out_h = round(h * out_w / w / 2) * 2

    target = DOCS / "demo.webp"
    with av.open(str(target), "w", format="webp") as out:
        stream = out.add_stream("libwebp_anim", rate=args.fps)
        stream.width, stream.height = out_w, out_h
        stream.pix_fmt = "bgra"
        stream.options = {"loop": "0", "lossless": "1", "quality": "100", "compression_level": "6"}
        stream.codec_context.time_base = Fraction(1, args.fps)
        for i, arr in enumerate(loop):
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24").reformat(width=out_w, height=out_h,
                                                                             format="bgra",
                                                                             interpolation="AREA")
            frame.pts = i
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    print(f"wrote {target} ({target.stat().st_size / 1024:.0f} KB, {out_w}x{out_h})")

    if args.poster is not None:
        index = min(len(loop) - 1, round(args.poster * args.fps))
    else:
        # the recording timer is the only #ff3b30 red in the bottom bar
        bar = slice(int(h * 0.90), h)
        red = [int(((f[bar, :, 0] > 230) & (f[bar, :, 1] < 90) & (f[bar, :, 2] < 80)).sum() > 40) for f in loop]
        runs, start = [], None
        for i, r in enumerate(red + [0]):
            if r and start is None:
                start = i
            elif not r and start is not None:
                runs.append((i - start, start))
                start = None
        length, first = max(runs) if runs else (0, len(loop) // 2)
        index = first + int(length * 0.75)
        print(f"recording shows for {length / args.fps:.1f} s from {first / args.fps:.1f} s; poster at {index / args.fps:.1f} s")
    poster = loop[index]
    still = DOCS / "demo.png"
    frame = av.VideoFrame.from_ndarray(poster, format="rgb24").reformat(width=out_w, height=out_h,
                                                                         interpolation="AREA")
    with av.open(str(still), "w", format="image2") as out:
        s = out.add_stream("png", rate=1)
        s.width, s.height, s.pix_fmt = out_w, out_h, "rgb24"
        for packet in s.encode(frame.reformat(format="rgb24")):
            out.mux(packet)
        for packet in s.encode(None):
            out.mux(packet)
    print(f"wrote {still} ({still.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
