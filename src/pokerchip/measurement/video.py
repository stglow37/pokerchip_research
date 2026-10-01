"""PyAV streaming decode preserves PTS and display rotation without FPS substitution."""
from collections import deque
from pathlib import Path
import hashlib
import av
import cv2
import numpy as np


def metadata(path):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        return {"width": stream.width, "height": stream.height, "codec": stream.codec_context.name,
                "average_rate": str(stream.average_rate), "time_base": str(stream.time_base),
                "estimated_frames": stream.frames, "stream_metadata": dict(stream.metadata),
                "container_metadata": dict(container.metadata),
                "time_suggestion": "metadata_only_pending_independent_verification"}


def frames(path, start=0, end=None, max_frame_bytes=64*1024*1024):
    previous_hash = None
    intervals = deque(maxlen=31)
    previous_p = None
    with av.open(str(Path(path))) as container:
        stream = container.streams.video[0]
        stream.thread_type = "SLICE"
        stream.codec_context.thread_count = 2
        if stream.width*stream.height*3 > max_frame_bytes:
            raise MemoryError("영상 크기가 frame byte 제한을 초과합니다.")
        for index, frame in enumerate(container.decode(stream)):
            if end is not None and index > end:
                break
            if index < start:
                continue
            rotation = int(round(getattr(frame, "rotation", 0) or float(stream.metadata.get("rotate", 0))))
            if rotation % 90:
                raise ValueError("90도 배수가 아닌 display rotation은 현재 지원하지 않습니다.")
            bgr = frame.to_ndarray(format="bgr24")
            if rotation:
                bgr = np.ascontiguousarray(np.rot90(bgr, k=rotation//90))
            tb = frame.time_base or stream.time_base
            p = float(frame.pts*tb) if frame.pts is not None else None
            small = cv2.resize(bgr, (96, 64))
            h = hashlib.blake2b(small.tobytes(), digest_size=12).digest()
            dt = p-previous_p if p is not None and previous_p is not None else None
            missing_suspected = bool(dt is not None and intervals and dt > 1.6*np.median(intervals))
            if dt is not None and dt > 0:
                intervals.append(dt)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            timing = {"frame_index": index, "pts": frame.pts, "time_base_num": tb.numerator,
                      "time_base_den": tb.denominator, "presentation_time_s": p,
                      "rotation_deg_ccw": rotation, "width": bgr.shape[1], "height": bgr.shape[0],
                      "duplicate_suspected": previous_hash == h,
                      "missing_frame_suspected": missing_suspected,
                      "blur_score": float(cv2.Laplacian(gray, cv2.CV_32F).var()),
                      "clipped_fraction": float(np.mean((small < 3) | (small > 252))),
                      "synthesis_status": "not_determinable_from_pixels_alone"}
            previous_hash, previous_p = h, p
            yield timing, bgr


def frame_at(path, index, **kwargs):
    # Bounded and exact decode from start; avoids ambiguous keyframe/PTS seeks.
    for timing, image in frames(path, start=index, end=index, **kwargs):
        return timing, image
    raise IndexError("프레임이 없습니다.")
