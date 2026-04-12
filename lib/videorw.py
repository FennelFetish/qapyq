import os
import numpy as np
import cv2 as cv
from PIL import Image


READ_EXTENSIONS = frozenset((
    '.3g2', '.3gp', '.amv', '.asf', '.avi', '.divx', '.dv', '.f4v', '.flv',
    '.h264', '.h265', '.hevc', '.m2ts', '.mts',
    '.m1v', '.m2v', '.m4p', '.m4v', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.mpv', '.mxf',
    '.ogv', '.qt', '.rm', '.rmvb', '.ts', '.vob', '.webm', '.wtv', '.wmv',
))

def isVideoFile(path: str):
    ext = os.path.splitext(path)[1].lower()
    return ext in READ_EXTENSIONS



# ========== AV ==========
try:
    import av

    def readSize(path: str) -> tuple[int, int]:
        try:
            with av.open(path, 'r') as container:
                stream = container.streams.video[0]
                return stream.width, stream.height
        except:
            return -1, -1

    def readMetadata(path: str) -> tuple[int, int, float, int]:
        try:
            with av.open(path, 'r') as container:
                stream = container.streams.video[0]
                return stream.width, stream.height, float(stream.average_rate or 0), stream.frames
        except:
            return -1, -1, 0.0, 0


    def getKeyframes(path: str, start: int, end: int) -> list[int]:
        keyframes = list[int]()

        try:
            with av.open(path, 'r') as container:
                stream = container.streams.video[0]
                tb = stream.time_base

                startPts = int((start / 1000) / tb)
                endPts   = int((end / 1000) / tb)

                container.seek(startPts, stream=stream)
                for packet in container.demux(stream):
                    pts = packet.pts or -1
                    if pts > endPts:
                        break

                    if packet.is_keyframe and pts >= startPts:
                        keyframes.append(round(float(pts * tb) * 1000))

        except Exception as ex:
            print(f"Failed to extract keyframes: {ex} ({type(ex).__name__})")

        return keyframes


    class NotSeekableException(Exception): pass

    def thumbnailVideo(path: str, maxWidth: int, tiling: int) -> tuple[np.ndarray, tuple[int, int]]:
        with av.open(path, 'r') as container:
            duration = float(container.duration / av.time_base)
            stream = container.streams.video[0]
            tb = stream.time_base

            w = origW = stream.width
            h = origH = stream.height
            maxWidth = round(maxWidth / tiling)
            if w > maxWidth:
                h = round(h * maxWidth/w)
                w = maxWidth

            tiles = np.zeros((h*tiling, w*tiling, 3), dtype=np.uint8)

            def addFrame(i: int, frame):
                y, x = divmod(i-1, tiling)
                x *= w
                y *= h

                mat = frame.to_ndarray(format="rgb24")
                cv.resize(mat, (w, h), dst=tiles[y:y+h, x:x+w, :], interpolation=cv.INTER_AREA)

            # Extract evenly spaced frames
            numIntervals = tiling*tiling + 1

            i = 1
            try:
                lastPts = -1
                for i in range(1, numIntervals):
                    pos = i * duration/numIntervals
                    container.seek(int(pos / tb), stream=stream)

                    frame = next(container.decode(stream))
                    pts = frame.pts or 0
                    if pts > lastPts:
                        lastPts = pts
                        addFrame(i, frame)
                    else:
                        raise NotSeekableException()

            except NotSeekableException:
                duration = min(duration, 60.0)

                for i in range(i, numIntervals):
                    pos = i * duration/numIntervals
                    for frame in container.decode(stream):
                        if frame.time >= pos:
                            addFrame(i, frame)
                            break
                    else:
                        break

        return tiles, (origW, origH)


    def extractFramesPIL(source, sampleFps: float, maxFrames: int = 64) -> tuple[list, dict]:
        with av.open(source, 'r') as container:
            stream = container.streams.video[0]

            duration = float(container.duration / av.time_base)
            fps = float(stream.average_rate or 0)
            frameCount = stream.frames or int(duration * fps)

            numSampleFrames = min(int(duration * sampleFps), frameCount)
            numSampleFrames &= ~1  # Force even frame count by rounding down
            numSampleFrames = min(max(numSampleFrames, 2), maxFrames)
            sampleFps = numSampleFrames / duration

            posFeed = duration / (numSampleFrames-1)
            tb = stream.time_base

            seek = (posFeed * fps > 24)
            lastSeekPts = -1

            frames = list[Image.Image]()
            for i in range(numSampleFrames):
                targetPts = int((i * posFeed) / tb)
                if seek:
                    container.seek(targetPts, stream=stream)

                for i, frame in enumerate(container.decode(stream)):
                    pts = frame.pts or 0
                    if i == 0 and seek:
                        # Disable seeking if it didn't move forward
                        if pts > lastSeekPts:
                            lastSeekPts = pts
                        else:
                            seek = False

                    if pts + frame.duration > targetPts:
                        frames.append( Image.fromarray(frame.to_ndarray(format="rgb24")) )  # Faster via numpy than frame.to_image()
                        break
                else:
                    break

        if not frames:
            raise RuntimeError("Failed to extract video frames")

        metadata = {
            "fps": sampleFps,
            "frames_indices": [i for i in range(len(frames))],
            "total_num_frames": len(frames),
            "duration": duration
        }

        return frames, metadata



# ========== OpenCV ==========
except ImportError:

    def readSize(path: str) -> tuple[int, int]:
        cap = cv.VideoCapture(path)
        try:
            if cap.isOpened():
                w = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
                return w, h
        except:
            pass
        finally:
            cap.release()

        return -1, -1

    def readMetadata(path: str) -> tuple[int, int, float, int]:
        cap = cv.VideoCapture(path)
        try:
            if cap.isOpened():
                w = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
                frameCount = int(cap.get(cv.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv.CAP_PROP_FPS)
                return w, h, fps, frameCount
        except:
            pass
        finally:
            cap.release()

        return -1, -1, 0.0, 0


    def getKeyframes(path: str, start: int, end: int) -> list[int]:
        startSec = start / 1000.0
        endSec   = end / 1000.0
        interval = f"{startSec}%{endSec}"

        cmd = [
            'ffprobe', '-v', 'error', '-skip_frame', 'nokey', '-select_streams', 'v:0', '-show_entries', 'frame=pkt_pts_time',
            '-read_intervals', interval, '-of', 'csv=p=0', path
        ]

        try:
            import subprocess
            result = subprocess.check_output(cmd, text=True)
            return [round(float(line) * 1000.0) for l in result.splitlines() if (line := l.strip())]
        except Exception as ex:
            print(f"Failed to extract keyframes: {ex} ({type(ex).__name__})")
            return []


    def thumbnailVideo(path: str, maxWidth: int, tiling: int) -> tuple[np.ndarray, tuple[int, int]]:
        cap = cv.VideoCapture(path)
        try:
            if not cap.isOpened():
                raise ValueError(f"Could not open video file: {path}")

            fps = cap.get(cv.CAP_PROP_FPS)
            frameCount = int(cap.get(cv.CAP_PROP_FRAME_COUNT))

            try:
                duration = frameCount / fps
            except ZeroDivisionError:
                raise ValueError("Failed to retrieve video duration")

            # Extract evenly spaced frames
            numIntervals = tiling*tiling + 1
            frames = list[np.ndarray]()
            for i in range(1, numIntervals):
                pos = round(1000 * i * duration/numIntervals)
                cap.set(cv.CAP_PROP_POS_MSEC, pos)
                ret, frame = cap.read()
                if ret:
                    frames.append(frame)
                else:
                    break

        finally:
            cap.release()

        try:
            origH, origW, channels = frames[0].shape
        except IndexError:
            raise ValueError("Failed to extract video frames")
        except ValueError:
            origH, origW = frames[0].shape[:2]
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

        tiles[..., :3] = tiles[..., 2::-1] # Convert BGR(A) -> RGB(A)
        return tiles, (origW, origH)


    def extractFramesPIL(path: str, sampleFps: float, maxFrames: int = 64) -> tuple[list, dict]:
        cap = cv.VideoCapture(path)
        try:
            if not cap.isOpened():
                raise ValueError(f"Could not open video file: {path}")

            fps = cap.get(cv.CAP_PROP_FPS)
            frameCount = int(cap.get(cv.CAP_PROP_FRAME_COUNT))

            try:
                duration = frameCount / fps
            except ZeroDivisionError:
                raise ValueError("Failed to retrieve video duration")

            numSampleFrames = min(int(duration * sampleFps), frameCount)
            numSampleFrames &= ~1  # Force even frame count by rounding down
            numSampleFrames = min(max(numSampleFrames, 2), maxFrames)
            sampleFps = numSampleFrames / duration

            frames = list[np.ndarray]()
            posFeed = duration / (numSampleFrames-1)
            for i in range(numSampleFrames):
                pos = int(1000 * i * posFeed)
                cap.set(cv.CAP_PROP_POS_MSEC, pos)
                ret, frame = cap.read()
                if ret:
                    frame[..., :3] = frame[..., 2::-1] # Convert BGR(A) -> RGB(A)
                    frames.append(frame)
                else:
                    break

        finally:
            cap.release()

        if not frames:
            raise RuntimeError("Failed to extract video frames")

        metadata = {
            "fps": sampleFps,
            "frames_indices": [i for i in range(len(frames))],
            "total_num_frames": len(frames),
            "duration": duration
        }

        images = [Image.fromarray(mat) for mat in frames]
        return images, metadata



# ========== Qt ==========
try:
    from PySide6.QtCore import Signal, Slot, QRectF, QSize, QProcess
    from PySide6.QtGui import QImage, QPolygonF, QTransform
    import math, time
    from lib import qtlib

    def thumbnailVideoQImage(path: str, maxWidth: int, tiling: int) -> tuple[QImage, tuple[int, int]]:
        mat, size = thumbnailVideo(path, maxWidth, tiling)
        return qtlib.numpyToQImage(mat, fromRGB=True), size


    class VideoExportProcess(QProcess):
        OVERWRITE_FLAG = '-y'  # '-n'

        done     = Signal(str, str) # srcFile, destFile
        progress = Signal(str)      # msg
        fail     = Signal(str)      # msg

        def __init__(
            self, parent,
            srcFile: str, srcSize: QSize, srcPosMs: int, srcFps: float,
            destFile: str, poly: QPolygonF | None, targetSize: QSize, rotation: float,
            numFrames: int, targetFps: float, speed: float = 1.0
        ):
            super().__init__(parent)
            self.srcFile  = srcFile
            self.destFile = destFile
            self.tStart   = 0

            videoFilters = self._getVideoFilters(srcSize, poly, targetSize, rotation, speed, srcFps, targetFps)
            audioFilters = None

            durationWrite = durationRead = numFrames / targetFps
            if abs(speed - 1.0) > 0.001:
                durationRead = durationWrite * speed
                videoFilters = [f'setpts=PTS/{speed}'] + videoFilters
                audioFilters = self._getAudioFilters(speed)

            keyframeInterval = round(targetFps)
            refFrames = '4'  # Prevents exceeding decode surface limit when playing these videos (preset veryslow uses 16 refs)

            args = ['-nostdin', self.OVERWRITE_FLAG, '-v', 'error', '-ss', f"{srcPosMs}ms"]

            if numFrames > 0:
                args += ['-t', str(durationRead), '-i', srcFile, '-ss', '0', '-t', str(durationWrite), '-frames:v', str(numFrames)]
            else:
                args += ['-i', srcFile, '-ss', '0']

            args += ['-vf', ','.join(videoFilters)]

            if audioFilters:
                args += ['-af', ','.join(audioFilters)]

            args += [
                '-c:v', 'libx264', '-preset', 'veryslow', '-crf', '17', '-movflags', '+faststart',
                '-c:a', 'aac', '-b:a', '192k',
                '-refs', refFrames, '-g', str(keyframeInterval),
                '-pix_fmt', 'yuv420p', '-avoid_negative_ts', 'make_zero',
                destFile
            ]

            #print(f"ffmpeg args: {args}")

            self.setProgram("ffmpeg")
            self.setArguments(args)

            self.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
            self.started.connect(self._onProcessStarted)
            self.finished.connect(self._onProcessEnded)
            self.errorOccurred.connect(self._onProcessError)

        @staticmethod
        def _getAudioFilters(speed: float) -> list[str]:
            # atempo with speed>2 will skip samples instead of blending, so chain multiple filters (max 10)
            atempoCount = math.ceil(speed/2.0) if speed <= 20.0 else 1
            atempoVal = pow(speed, 1.0/atempoCount)
            return [f'atempo={atempoVal}'] * atempoCount

        @classmethod
        def _getVideoFilters(
            cls, srcSize: QSize, poly: QPolygonF | None, targetSize: QSize, rotation: float, speed: float, srcFps: float, targetFps: float
        ) -> list[str]:
            bbox, crop = cls.calcRotatedCrop(srcSize, poly, rotation)
            filters = list[str]()

            if rotation != 0.0:
                rotRad = math.radians(rotation)
                filters.append( f'rotate={rotRad}:ow={bbox.width()}:oh={bbox.height()}:fillcolor=black@0' )

            if crop != bbox:
                filters.append( f'crop={crop.width()}:{crop.height()}:{crop.x()}:{crop.y()}' )

            targetSize = cls._evenSize(targetSize)
            if crop.size() != targetSize:
                filters.append( f'scale={targetSize.width()}:{targetSize.height()}:flags=lanczos' )  # TODO: Use interpolation settings from preset?

            scaledSrcFps = srcFps * speed
            if targetFps > scaledSrcFps * 1.33:
                filters.append( f"minterpolate=fps={targetFps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:me=epzs:vsbmc=1" )
                print(f"Upsampling FPS from {round(srcFps, 4)} (speed: {speed:.2f}, effective FPS: {round(scaledSrcFps, 4)}) "
                      f"to {round(targetFps, 4)} (x{targetFps/scaledSrcFps:.3f}) using minterpolate filter. This can take a minute.")
            elif targetFps > scaledSrcFps:
                filters.append( f'fps={targetFps}' )      # Duplicates frames: Do this last
            else:
                filters = [f'fps={targetFps}'] + filters  # Drops frames: Do this first

            return filters

        @staticmethod
        def calcRotatedCrop(srcSize: QSize, poly: QPolygonF | None, rotation: float) -> tuple[QRectF, QRectF]:
            rotTrans = QTransform().rotate(rotation)                                 # Rotation around 0/0
            bbox = rotTrans.mapRect(QRectF(0, 0, srcSize.width(), srcSize.height())) # Bounding box of rotated image

            if poly is not None:
                crop = rotTrans.map(poly).boundingRect() # Rotate selection from image-space to view-space and align with axes
                crop.translate(-bbox.topLeft())          # Make crop window relative to bbox
                return bbox, crop
            else:
                return bbox, bbox

        @staticmethod
        def _evenSize(size: QSize) -> QSize:
            # ffmpeg needs target size divisible by 2
            w, h = size.toTuple()
            if (w & 1) or (h & 1):
                w -= (w & 1)
                h -= (h & 1)
                print(f"Video size must be even. Reducing from {size.width()}x{size.height()} to {w}x{h}.")
                return QSize(w, h)

            return size


        @Slot()
        def _onProcessStarted(self):
            self.tStart = time.monotonic_ns()
            self.progress.emit("Saving video...")

        @Slot(int, QProcess.ExitStatus)
        def _onProcessEnded(self, exitCode: int, exitStatus: QProcess.ExitStatus):
            t = (time.monotonic_ns() - self.tStart) / 1_000_000_000

            if exitCode == 0:
                print(f"Video export took {t:.3f} s")
                self.done.emit(self.srcFile, self.destFile)
            else:
                msg = f"ffmpeg call failed with exit code {exitCode}, {exitStatus}"
                print(f"Video export failed: {msg}")
                self.fail.emit(msg)

            self.readAllStandardOutput()
            self.readAllStandardError()
            self.deleteLater()

        @Slot()
        def _onProcessError(self, error: QProcess.ProcessError):
            msg = f"ffmpeg error ({error.name})"
            print(f"Video export failed: {msg}")
            self.fail.emit(msg)

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
