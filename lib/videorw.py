import os
import numpy as np
import cv2 as cv


READ_EXTENSIONS = frozenset((".mpg", ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".3gp", ".ts", ".webm", ".flv"))

def isVideoFile(path: str):
    ext = os.path.splitext(path)[1].lower()
    return ext in READ_EXTENSIONS


def readSize(path: str) -> tuple[int, int]:
    cap = cv.VideoCapture(path)
    try:
        if cap.isOpened():
            w = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
        else:
            w = h = -1
    except:
        w = h = -1
    finally:
        cap.release()

    return (w, h)


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
    from PySide6.QtCore import Signal, Slot, QRectF, QSize, QProcess
    from PySide6.QtGui import QImage, QPolygonF, QTransform
    import math
    from lib import qtlib

    def thumbnailVideoQImage(path: str, maxWidth: int, tiling: int) -> tuple[QImage, tuple[int, int]]:
        mat, size = thumbnailVideo(path, maxWidth, tiling)
        return qtlib.numpyToQImage(mat), size


    class VideoExportProcess(QProcess):
        done     = Signal(str, str) # srcFile, destFile
        progress = Signal(str)      # msg
        fail     = Signal(str)      # msg

        def __init__(
            self, parent,
            srcFile: str, srcSize: QSize, srcPosMs: int,
            destFile: str, poly: QPolygonF, targetSize: QSize, rotation: float,
            numFrames: int, fps: float
        ):
            super().__init__(parent)
            self.srcFile = srcFile
            self.destFile = destFile

            filters = [f'fps={fps}']
            bbox, crop = self.calcRotatedCrop(srcSize, poly, rotation)

            if rotation != 0.0:
                rotRad = math.radians(rotation)
                filters.append( f'rotate={rotRad}:ow={bbox.width()}:oh={bbox.height()}:fillcolor=black@0' )

            if crop != bbox:
                filters.append( f'crop={crop.width()}:{crop.height()}:{crop.x()}:{crop.y()}' )

            if crop.size() != targetSize:
                filters.append( f'scale={targetSize.width()}:{targetSize.height()}:flags=lanczos' )  # TODO: Use interpolation settings from preset?

            overwriteFlag = '-y'  # '-n'
            pos = srcPosMs / 1000
            duration = numFrames / fps

            args = [
                '-nostdin', overwriteFlag, '-v', 'error',
                '-ss', str(pos), '-i', srcFile, '-ss', '0', '-t', str(duration),
                '-vf', ','.join(filters), '-frames:v', str(numFrames),
                '-c:v', 'libx264', '-preset', 'veryslow', '-crf', '17', '-movflags', '+faststart',
                '-c:a', 'aac', '-b:a', '192k',
                '-pix_fmt', 'yuv420p', '-avoid_negative_ts', 'make_zero',
                destFile
            ]

            #print(f"ffmpeg args: {args}")

            self.setProgram("ffmpeg")
            self.setArguments(args)

            self.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
            self.started.connect(self._onProcessStarted)
            self.finished.connect(self._onProcessEnded)

        @staticmethod
        def calcRotatedCrop(srcSize: QSize, poly: QPolygonF, rotation: float) -> tuple[QRectF, QRectF]:
            rotTrans = QTransform().rotate(rotation)                                 # Rotation around 0/0
            bbox = rotTrans.mapRect(QRectF(0, 0, srcSize.width(), srcSize.height())) # Bounding box of rotated image
            crop = rotTrans.map(poly).boundingRect()                                 # Rotate selection from image-space to view-space and align with axes
            crop.translate(-bbox.topLeft())                                          # Make crop window relative to bbox
            return bbox, crop

        @Slot()
        def _onProcessStarted(self):
            self.progress.emit("Saving video...")

        @Slot(int, QProcess.ExitStatus)
        def _onProcessEnded(self, exitCode: int, exitStatus: QProcess.ExitStatus):
            if exitCode == 0:
                self.done.emit(self.srcFile, self.destFile)
            else:
                print(f"Video export failed: ffmpeg call failed with exit code {exitCode}, {exitStatus}")
                self.fail.emit(f"ffmpeg call failed with exit code {exitCode}")

            self.readAllStandardOutput()
            self.readAllStandardError()
            self.deleteLater()


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
