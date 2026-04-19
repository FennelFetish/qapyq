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


# Read metadata with OpenCV because AV doesn't account for rotation (would need to decode frames)
def readSize(path: str) -> tuple[int, int]:
    cap = cv.VideoCapture(path)
    try:
        if cap.isOpened():
            return cvGetFrameSize(cap)
    except:
        pass
    finally:
        cap.release()

    return -1, -1

def readMetadata(path: str) -> tuple[int, int, float, int, int]:
    'w, h, fps, frame count, duration (ms)'
    cap = cv.VideoCapture(path)
    try:
        if cap.isOpened():
            w, h = cvGetFrameSize(cap)
            frameCount = int(cap.get(cv.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv.CAP_PROP_FPS)
            duration = int(1000 * frameCount / fps)
            return w, h, fps, frameCount, duration
    except:
        pass
    finally:
        cap.release()

    return -1, -1, 0.0, 0, 0

def cvGetFrameSize(cap: cv.VideoCapture) -> tuple[int, int]:
    w = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))

    sarNum = cap.get(cv.CAP_PROP_SAR_NUM)
    sarDen = cap.get(cv.CAP_PROP_SAR_DEN)
    try:
        sar = sarNum / sarDen
        if sar >= 1.0:
            w = round(w * sar)
        else:
            h = round(h / sar)
    except ZeroDivisionError:
        pass

    return w, h



# ========== AV ==========
try:
    import av
    from av.container import InputContainer
    from av.video.reformatter import VideoReformatter, Interpolation
    from typing import Callable

    FrameConvertFunc = Callable[[av.VideoFrame], np.ndarray]
    ConverterFactory = Callable[[int, int], FrameConvertFunc]

    CV_ROT_SWAP = {
        -90:  (cv.ROTATE_90_CLOCKWISE, True),
        90:   (cv.ROTATE_90_COUNTERCLOCKWISE, True),
        -180: (cv.ROTATE_180, False),
        180:  (cv.ROTATE_180, False),
        -270: (cv.ROTATE_90_COUNTERCLOCKWISE, True),
        270:  (cv.ROTATE_90_CLOCKWISE, True)
    }

    def createFrameConverter(
        w: int|None = None, h: int|None = None, rotate: bool = True,
        interpolation: Interpolation = None, format: str = "rgb24", threads: int = 0
    ) -> FrameConvertFunc:
        reformatter = VideoReformatter()
        rotSwapMap = CV_ROT_SWAP if rotate else {}

        def convert(frame: av.VideoFrame) -> np.ndarray:
            rotation = frame.rotation
            frame = reformatter.reformat(frame, w, h, format, interpolation=interpolation, threads=threads)
            mat = frame.to_ndarray()

            if rotSwap := rotSwapMap.get(rotation):
                mat = cv.rotate(mat, rotSwap[0])

            return mat

        return convert


    def avGetFrameSize(stream: av.VideoStream) -> tuple[int, int]:
        w = stream.width
        h = stream.height

        try:
            sar = stream.sample_aspect_ratio
            if sar is not None:
                sar = float(sar)
                if sar >= 1.0:
                    w = round(w * sar)
                else:
                    h = round(h / sar)
        except:
            pass

        return w, h

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

    def iterKeyframes(container: InputContainer, numFrames: int, posFunc: Callable[[int], float]):
        'posFunc: Must return position as [0.0, 1.0]'

        duration = float(container.duration / av.time_base)
        stream = container.streams.video[0]
        tb = stream.time_base

        i = 0
        try:
            lastPts = -1
            for i in range(numFrames):
                targetPts = int((posFunc(i) * duration) / tb)
                container.seek(targetPts, stream=stream)

                frame = next(container.decode(stream))
                pts = frame.pts #or 0
                if pts > lastPts:
                    lastPts = pts
                    yield frame
                else:
                    raise NotSeekableException()

        except NotSeekableException:
            duration = min(duration, 60.0)

            for i in range(i, numFrames):
                targetPts = int((posFunc(i) * duration) / tb)

                frame = None
                for frame in container.decode(stream):
                    if frame.pts >= targetPts:
                        yield frame
                        break
                else:
                    if frame:
                        yield frame
                    break

    def iterFrames(container: InputContainer, numFrames: int, posFunc: Callable[[int], float], seek: bool = True):
        'posFunc: Must return position as seconds'

        stream = container.streams.video[0]
        tb = stream.time_base
        lastSeekPts = -1

        for i in range(numFrames):
            targetPts = int(posFunc(i) / tb)
            if seek:
                container.seek(targetPts, stream=stream)

            frame = None
            for f, frame in enumerate(container.decode(stream)):
                pts = frame.pts #or 0
                if f == 0 and seek:
                    # Disable seeking if it didn't move forward
                    if pts > lastSeekPts:
                        lastSeekPts = pts
                    else:
                        seek = False

                if pts >= targetPts:
                    yield frame
                    break
            else:
                if frame:
                    yield frame
                break


    def thumbnailVideo(path: str, maxWidth: int, tiling: int) -> tuple[np.ndarray, tuple[int, int]]:
        with av.open(path, 'r') as container:
            stream = container.streams.video[0]

            origW, origH = avGetFrameSize(stream)
            w = origW
            h = origH

            maxWidth = round(maxWidth / tiling)
            tiles: np.ndarray = None
            convert: FrameConvertFunc = None

            rotation: int | None = None
            swap: bool = False

            def prepareTiles(frame: av.VideoFrame):
                nonlocal w, h, rotation, swap, tiles, convert
                rotation, swap = CV_ROT_SWAP.get(frame.rotation, (None, False))
                if swap:
                    if h > maxWidth:
                        w = round(w * maxWidth/h)
                        h = maxWidth
                else:
                    if w > maxWidth:
                        h = round(h * maxWidth/w)
                        w = maxWidth

                convert = createFrameConverter(w, h, False, Interpolation.AREA, threads=2)
                tiles = np.zeros((h*tiling, w*tiling, 3), dtype=np.uint8)

            def addTile(i: int, frame: av.VideoFrame):
                if i == 1:
                    prepareTiles(frame)

                y, x = divmod(i-1, tiling)
                x *= w
                y *= h

                tiles[y:y+h, x:x+w, :] = convert(frame)

            # Extract evenly spaced frames
            numIntervals = tiling*tiling + 1
            posFunc = lambda i: (i+1) / numIntervals

            try:
                for i, frame in enumerate(iterKeyframes(container, numIntervals-1, posFunc), 1):
                    addTile(i, frame)
            except Exception as ex:
                print(f"Video thumbnail incomplete: {ex} ({type(ex).__name__})")

        if rotation is not None:
            tiles = cv.rotate(tiles, rotation)
            if swap:
                origW, origH = origH, origW

        return tiles, (origW, origH)


    # For captioning models
    def extractFramesPIL(source, sampleFps: float, maxFrames: int = 32) -> tuple[list[Image.Image], dict]:
        with av.open(source, 'r') as container:
            stream = container.streams.video[0]

            w, h = avGetFrameSize(stream)
            convert = createFrameConverter(w, h)

            duration = float(container.duration / av.time_base)
            fps = float(stream.average_rate or 0)
            frameCount = stream.frames or int(duration * fps)

            numSampleFrames = min(int(duration * sampleFps), frameCount)
            numSampleFrames &= ~1  # Force even frame count by rounding down
            numSampleFrames = min(max(numSampleFrames, 2), maxFrames)
            sampleFps = numSampleFrames / duration

            posFeed = duration / (numSampleFrames-1) if numSampleFrames < frameCount-1 else 0
            seek = (posFeed * fps > 24)
            posFunc = lambda i: i * posFeed

            frames = list[Image.Image]()
            try:
                for frame in iterFrames(container, numSampleFrames, posFunc, seek):
                    frames.append(Image.fromarray(convert(frame)))
            except Exception as ex:
                print(f"Warning: {ex} ({type(ex).__name__})")

        if not frames:
            raise RuntimeError("Failed to extract video frames")
        elif len(frames) < numSampleFrames:
            print(f"Warning: Could not extract all frames from video ({len(frames)}/{numSampleFrames})")

        metadata = {
            "fps": sampleFps,
            "frames_indices": [i for i in range(len(frames))],
            "total_num_frames": len(frames),
            "duration": duration
        }

        return frames, metadata


    # For tagging models
    def extractFramesMat(source, sampleFps: float, maxFrames: int, converterFactory: ConverterFactory) -> list[np.ndarray]:
        with av.open(source, 'r') as container:
            stream = container.streams.video[0]

            w, h = avGetFrameSize(stream)
            convert = converterFactory(w, h)

            duration = float(container.duration / av.time_base)
            fps = float(stream.average_rate or 0)
            frameCount = stream.frames or int(duration * fps)

            numSampleFrames = min(round(duration * sampleFps), frameCount)
            numSampleFrames = min(max(numSampleFrames, 3), maxFrames)

            frames = list[np.ndarray]()
            try:
                # Short videos: Exact seeking, include first and last frame
                if duration <= 10.0:
                    posFunc = lambda i: duration * i / (numSampleFrames-1)
                    for frame in iterFrames(container, numSampleFrames, posFunc):
                        frames.append(convert(frame))

                # Long videos: Seek to keyframes only, exclude first and last interval
                else:
                    numIntervals = numSampleFrames + 1
                    posFunc = lambda i: (i+1) / numIntervals
                    for frame in iterKeyframes(container, numSampleFrames, posFunc):
                        frames.append(convert(frame))

            except Exception as ex:
                print(f"Warning: {ex} ({type(ex).__name__})")

        if not frames:
            raise RuntimeError("Failed to extract video frames")
        elif len(frames) < numSampleFrames:
            print(f"Warning: Could not extract all frames from video ({len(frames)}/{numSampleFrames})")

        return frames



# ========== OpenCV ==========
except ImportError:

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


    def extractFramesPIL(path: str, sampleFps: float, maxFrames: int = 32) -> tuple[list[Image.Image], dict]:
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
            # minimum tempo argument is 0.5
            if speed >= 0.5:
                atempoCount = math.ceil(speed/2.0) if speed <= 20.0 else 1
            else:
                atempoCount = math.ceil(0.5/speed)

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
