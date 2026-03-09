import os
import numpy as np
import cv2 as cv


READ_EXTENSIONS = frozenset((".mpg", ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".3gp", ".ts", ".webm", ".flv"))

def isVideoFile(path: str):
    ext = os.path.splitext(path)[1].lower()
    return ext in READ_EXTENSIONS


def thumbnailVideo(path: str, maxWidth: int, tiling: int) -> tuple[np.ndarray, tuple[int, int]]:
    cap = cv.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {path}")

        origW = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
        origH = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv.CAP_PROP_FPS)
        frameCount = int(cap.get(cv.CAP_PROP_FRAME_COUNT))
        duration = (frameCount / fps) if fps > 0 and frameCount > 0 else 0

        # Extract evenly spaced frames
        numIntervals = tiling*tiling + 1
        frames = list[np.ndarray]()
        for i in range(1, numIntervals):
            pos = round(i * duration/numIntervals)
            cap.set(cv.CAP_PROP_POS_MSEC, pos * 1000)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
            else:
                break

    finally:
        cap.release()

    if not frames:
        raise ValueError("Failed to extract video frames")

    try:
        channels = frames[0].shape[2]
    except IndexError:
        channels = 1

    # Downscale frames
    maxWidth = round(maxWidth / tiling)
    w, h = origW, origH
    if w > maxWidth:
        h = round(h * maxWidth/w)
        w = maxWidth
        frames = [cv.resize(frame, (w, h), interpolation=cv.INTER_AREA) for frame in frames]

    # Tile
    tiles = np.zeros((h*tiling, w*tiling, channels), dtype=np.uint8)
    for i, frame in enumerate(frames):
        x = (i % tiling) * w
        y = (i // tiling) * h
        tiles[y:y+h, x:x+w, :] = frame

    return tiles, (origW, origH)



try:
    from PySide6.QtGui import QImage
    from lib import qtlib

    def thumbnailVideoQImage(path: str, maxWidth: int, tiling: int) -> tuple[QImage, tuple[int, int]]:
        mat, size = thumbnailVideo(path, maxWidth, tiling)
        return qtlib.numpyToQImage(mat), size

except ImportError:
    pass




# import subprocess, json

# def thumbnailVideo(path: str) -> tuple[int, int, np.ndarray]:
#     tiling = 2
#     numIntervals = tiling*tiling + 1

#     # Initial keyframe skipping is much faster than seeking to multiple frames, so call ffmpeg multiple times
#     origW, origH, duration = _getVideoInfo(path)
#     frames = list[np.ndarray]()
#     for i in range(1, numIntervals):
#         pos = round(i * duration/numIntervals)
#         frames.append(_extractVideoFrame(path, pos, thumbnail=True))

#     h, w = frames[0].shape[:2]
#     tiles = np.zeros((h*tiling, w*tiling, 3), dtype=np.uint8)
#     for i, frame in enumerate(frames):
#         x = (i % tiling) * w
#         y = (i // tiling) * h
#         tiles[y:y+h, x:x+w, :] = frame[:, :, :3]

#     return origW, origH, tiles

# def _getVideoInfo(path: str) -> tuple[int, int, float]:
#     cmd = ['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height,duration', '-of', 'default=nw=1:nk=1', path]

#     result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
#     if result.returncode != 0:
#         raise subprocess.SubprocessError(f"Video info unavailable (ffprobe exit code {result.returncode}): {path}")

#     lines = result.stdout.splitlines()
#     return int(lines[0]), int(lines[1]), float(lines[2])

# def _extractVideoFrame(path: str, pos: float, thumbnail=False) -> np.ndarray:
#     cmd = ['ffmpeg', '-skip_frame', 'nokey', '-ss', str(pos), '-an', '-i', path]
#     if thumbnail:
#         cmd += ['-vf', "scale='min(300,iw)':-1", '-sws_flags', 'area']
#     cmd += ['-vframes', '1', '-f', 'image2pipe', '-q:v', '3', '-vcodec', 'mjpeg', '-v', 'error', '-'] # '-' is output file for pipe

#     result = subprocess.run(cmd, capture_output=True, text=False, timeout=4.0)
#     jpegFrame = result.stdout
#     if result.returncode != 0 or not jpegFrame:
#         raise subprocess.SubprocessError(f"Failed to extract video frame (ffmpeg exit code {result.returncode}): {path}")

#     return cv.imdecode(np.frombuffer(jpegFrame, np.uint8), cv.IMREAD_COLOR)


# def get_keyframe_times(video_path, start_sec=10) -> list[float]:
#     """
#     Use ffprobe to get keyframe timestamps (in seconds) after start_sec.
#     Returns list of float pts_times.
#     """
#     command = [
#         'ffprobe', '-loglevel', 'error', '-skip_frame', 'nokey',
#         '-select_streams', 'v:0', '-show_entries', 'frame=pkt_pts_time',
#         '-of', 'csv=p=0', video_path
#     ]
#     result = subprocess.run(command, capture_output=True, text=True)
#     if result.returncode != 0:
#         raise ValueError(f"ffprobe failed: {result.stderr}")

#     print(result.stdout)
#     times = list[float]()
#     for line in result.stdout.splitlines():
#         try:
#             t = float(line)
#             if t >= start_sec:
#                 times.append(t)
#         except ValueError:
#             pass
#     return times

# def get_local_keyframe_time(path: str, start_sec: float, end_sec: float) -> float:
#     target = (start_sec + end_sec) / 2

#     interval = f"{start_sec:.0f}%{end_sec:.0f}"  # e.g., "50%60" for 50-60s
#     # cmd = [
#     #     'ffprobe', '-v', 'error', '-show_frames', '-select_streams', 'v:0',
#     #     '-read_intervals', interval, '-print_format', 'json', path
#     # ]
#     cmd = [
#         'ffprobe', '-v', 'error', '-skip_frame', 'nokey', '-show_entries', 'frame=pkt_pts_time', '-select_streams', 'v:0',
#         '-read_intervals', interval, '-print_format', 'json', path
#     ]
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     if result.returncode != 0:
#         return target

#     data = json.loads(result.stdout)
#     print(data)
#     keyframes = [float(f['pkt_pts_time']) for f in data.get('frames', []) if f.get('key_frame') == 1]

#     if not keyframes:
#         return target

#     # Pick closest to midpoint of interval
#     return min(keyframes, key=lambda t: abs(t - target))
