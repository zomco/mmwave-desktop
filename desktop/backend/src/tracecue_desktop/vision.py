"""Optional event-scoped ONNX detection and deterministic rule geometry validation."""

from __future__ import annotations

import hashlib
import importlib.util
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence


SUPPORTED_EVENT_TYPES = {"line_crossing", "region_intrusion"}
TARGET_CLASS_NAMES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


class VisionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class Detection:
    class_name: str
    confidence: float
    box: tuple[float, float, float, float]

    @property
    def ground_point(self) -> tuple[float, float]:
        left, _top, right, bottom = self.box
        return ((left + right) / 2.0, bottom)


@dataclass(slots=True)
class Track:
    id: int
    class_name: str
    last_box: tuple[float, float, float, float]
    last_frame: int
    points: list[tuple[int, float, float, float]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class VisualAnalysisResult:
    verdict: str
    reason_code: str
    confidence: float | None
    trigger_offset_ms: int | None
    target_classes: tuple[str, ...]
    track_count: int
    frame_count: int
    detection_count: int
    model_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "confidence": self.confidence,
            "trigger_offset_ms": self.trigger_offset_ms,
            "target_classes": list(self.target_classes),
            "track_count": self.track_count,
            "frame_count": self.frame_count,
            "detection_count": self.detection_count,
            "model_id": self.model_id,
        }


class VisualAnalyzer(Protocol):
    def availability(self) -> dict[str, Any]: ...

    def analyze(
        self,
        *,
        frames: Sequence[bytes],
        width: int,
        height: int,
        fps: float,
        event_type: str,
        overlays: Sequence[dict[str, Any]],
    ) -> VisualAnalysisResult: ...


class UnavailableVisualAnalyzer:
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def availability(self) -> dict[str, Any]:
        return {
            "available": False,
            "code": self.code,
            "message": self.message,
            "model_id": None,
            "supported_event_types": sorted(SUPPORTED_EVENT_TYPES),
            "target_classes": sorted(set(TARGET_CLASS_NAMES.values())),
        }

    def analyze(self, **_values: Any) -> VisualAnalysisResult:
        raise VisionError(self.code, self.message)


class YoloXOnnxVisualAnalyzer:
    """YOLOX-Nano ONNX inference with a bounded short-window tracker.

    FFmpeg supplies fixed-size BGR24 frames. This class performs tensor
    conversion and inference only; it does not decode or render video.
    """

    def __init__(
        self,
        model_path: Path,
        *,
        confidence_threshold: float = 0.20,
        nms_threshold: float = 0.45,
        decode_output: bool = True,
    ):
        self.model_path = model_path.resolve()
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.decode_output = decode_output
        self._session: Any | None = None
        self._np: Any | None = None
        self._model_id: str | None = None

    def availability(self) -> dict[str, Any]:
        if not self.model_path.is_file():
            return UnavailableVisualAnalyzer(
                "VISION_MODEL_NOT_FOUND", "The configured visual-analysis model was not found."
            ).availability()
        if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("onnxruntime") is None:
            return UnavailableVisualAnalyzer(
                "VISION_RUNTIME_NOT_INSTALLED",
                "Install the optional TraceCue visual-analysis runtime to enable local validation.",
            ).availability()
        return {
            "available": True,
            "code": None,
            "message": "Local event visual validation is available.",
            "model_id": self.model_id,
            "supported_event_types": sorted(SUPPORTED_EVENT_TYPES),
            "target_classes": sorted(set(TARGET_CLASS_NAMES.values())),
        }

    @property
    def model_id(self) -> str:
        if self._model_id is None:
            digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:16]
            self._model_id = f"yolox-nano-onnx:{digest}"
        return self._model_id

    def analyze(
        self,
        *,
        frames: Sequence[bytes],
        width: int,
        height: int,
        fps: float,
        event_type: str,
        overlays: Sequence[dict[str, Any]],
    ) -> VisualAnalysisResult:
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise VisionError("VISION_EVENT_TYPE_UNSUPPORTED", "This event type has no visual validator.")
        if width <= 0 or height <= 0 or fps <= 0 or not frames:
            raise VisionError("VISION_FRAMES_INVALID", "The event window produced no analyzable frames.")
        geometry = _geometry_for_event(event_type, overlays)
        if not geometry:
            return VisualAnalysisResult(
                "uncertain", "rule_geometry_unavailable", None, None, (), 0,
                len(frames), 0, self.model_id,
            )
        session, np = self._load_runtime()
        input_name = session.get_inputs()[0].name
        detections_by_frame: list[list[Detection]] = []
        expected_bytes = width * height * 3
        for frame in frames:
            if len(frame) != expected_bytes:
                raise VisionError("VISION_FRAME_SIZE_INVALID", "FFmpeg returned an unexpected frame size.")
            image = np.frombuffer(frame, dtype=np.uint8).reshape(height, width, 3)
            tensor = np.ascontiguousarray(image.transpose(2, 0, 1), dtype=np.float32)[None, ...]
            output = session.run(None, {input_name: tensor})[0]
            detections_by_frame.append(self._detections(output, width, height, np))
        tracks = build_tracks(detections_by_frame, width=width, height=height)
        detection_count = sum(len(items) for items in detections_by_frame)
        return evaluate_tracks(
            tracks,
            event_type=event_type,
            overlays=geometry,
            fps=fps,
            frame_count=len(frames),
            detection_count=detection_count,
            model_id=self.model_id,
        )

    def _load_runtime(self) -> tuple[Any, Any]:
        available = self.availability()
        if not available["available"]:
            raise VisionError(str(available["code"]), str(available["message"]))
        if self._session is None:
            import numpy as np
            import onnxruntime as ort

            self._np = np
            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
        return self._session, self._np

    def _detections(self, output: Any, width: int, height: int, np: Any) -> list[Detection]:
        predictions = output[0] if getattr(output, "ndim", 0) == 3 else output
        if predictions.ndim != 2 or predictions.shape[1] < 6:
            raise VisionError("VISION_MODEL_OUTPUT_INVALID", "The ONNX model output is not YOLOX-compatible.")
        if self.decode_output:
            predictions = _decode_yolox(predictions, width, height, np)
        boxes = predictions[:, :4].copy()
        boxes[:, 0] = predictions[:, 0] - predictions[:, 2] / 2
        boxes[:, 1] = predictions[:, 1] - predictions[:, 3] / 2
        boxes[:, 2] = predictions[:, 0] + predictions[:, 2] / 2
        boxes[:, 3] = predictions[:, 1] + predictions[:, 3] / 2
        class_scores = predictions[:, 4:5] * predictions[:, 5:]
        class_ids = class_scores.argmax(1)
        scores = class_scores.max(1)
        candidates: list[tuple[int, float, tuple[float, float, float, float]]] = []
        for index in np.where(scores >= self.confidence_threshold)[0].tolist():
            class_id = int(class_ids[index])
            if class_id not in TARGET_CLASS_NAMES:
                continue
            left, top, right, bottom = (float(value) for value in boxes[index])
            candidates.append(
                (
                    class_id,
                    float(scores[index]),
                    (
                        max(0.0, min(float(width), left)),
                        max(0.0, min(float(height), top)),
                        max(0.0, min(float(width), right)),
                        max(0.0, min(float(height), bottom)),
                    ),
                )
            )
        kept: list[Detection] = []
        for class_id in TARGET_CLASS_NAMES:
            class_candidates = [item for item in candidates if item[0] == class_id]
            class_candidates.sort(key=lambda item: item[1], reverse=True)
            while class_candidates and len(kept) < 100:
                current = class_candidates.pop(0)
                kept.append(Detection(TARGET_CLASS_NAMES[class_id], current[1], current[2]))
                class_candidates = [
                    item for item in class_candidates
                    if _intersection_over_union(current[2], item[2]) < self.nms_threshold
                ]
        return kept


def build_visual_analyzer(model_path: Path | None) -> VisualAnalyzer:
    if model_path is None:
        return UnavailableVisualAnalyzer(
            "VISION_MODEL_NOT_CONFIGURED",
            "Install and configure the optional local visual-analysis model.",
        )
    return YoloXOnnxVisualAnalyzer(model_path)


def build_tracks(
    detections_by_frame: Sequence[Sequence[Detection]], *, width: int, height: int
) -> list[Track]:
    tracks: list[Track] = []
    next_id = 1
    for frame_index, detections in enumerate(detections_by_frame):
        available = [track for track in tracks if frame_index - track.last_frame <= 2]
        assignments: set[int] = set()
        for detection in sorted(detections, key=lambda item: item.confidence, reverse=True):
            best: Track | None = None
            best_score = -1.0
            pixel_point = detection.ground_point
            point = (pixel_point[0] / max(1.0, width), pixel_point[1] / max(1.0, height))
            for track in available:
                if track.id in assignments or track.class_name != detection.class_name:
                    continue
                overlap = _intersection_over_union(track.last_box, detection.box)
                previous = track.points[-1]
                distance = math.hypot(point[0] - previous[1], point[1] - previous[2])
                score = overlap if overlap >= 0.10 else (0.15 - distance)
                if (overlap >= 0.10 or distance <= 0.15) and score > best_score:
                    best, best_score = track, score
            if best is None:
                best = Track(next_id, detection.class_name, detection.box, frame_index)
                next_id += 1
                tracks.append(best)
            best.last_box = detection.box
            best.last_frame = frame_index
            best.points.append((frame_index, point[0], point[1], detection.confidence))
            assignments.add(best.id)
    return [track for track in tracks if len(track.points) >= 2]


def evaluate_tracks(
    tracks: Sequence[Track], *, event_type: str, overlays: Sequence[dict[str, Any]], fps: float,
    frame_count: int, detection_count: int, model_id: str,
) -> VisualAnalysisResult:
    classes = tuple(sorted({track.class_name for track in tracks}))
    if not tracks:
        return VisualAnalysisResult(
            "no_supported_target_detected", "no_supported_target", None, None, (), 0,
            frame_count, detection_count, model_id,
        )
    best: tuple[int, float] | None = None
    for track in tracks:
        for overlay in overlays:
            trigger = (
                _line_trigger(track, overlay)
                if event_type == "line_crossing"
                else _polygon_trigger(track, overlay)
            )
            if trigger is not None and (best is None or trigger[1] > best[1]):
                best = trigger
    if best is None:
        return VisualAnalysisResult(
            "target_present_no_trigger", "target_tracks_do_not_match_rule", None, None,
            classes, len(tracks), frame_count, detection_count, model_id,
        )
    frame_index, confidence = best
    return VisualAnalysisResult(
        "confirmed_trigger", "trajectory_matches_rule", confidence,
        int(round(frame_index * 1000 / fps)), classes, len(tracks), frame_count,
        detection_count, model_id,
    )


def _geometry_for_event(event_type: str, overlays: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    kind = "line" if event_type == "line_crossing" else "polygon"
    return [
        overlay for overlay in overlays
        if overlay.get("kind") == kind and len(overlay.get("points") or []) >= (2 if kind == "line" else 3)
    ]


def _line_trigger(track: Track, overlay: dict[str, Any]) -> tuple[int, float] | None:
    width = float(overlay.get("width") or 1)
    height = float(overlay.get("height") or 1)
    first, second = overlay["points"][:2]
    line_length = math.hypot(float(second[0]) - float(first[0]), float(second[1]) - float(first[1]))
    if line_length <= 0:
        return None
    dead_zone = max(width, height) * 0.01
    previous: tuple[int, int, float, float, float] | None = None
    for frame_index, x, y, confidence in track.points:
        px, py = x * width, y * height
        side = ((float(second[0]) - float(first[0])) * (py - float(first[1]))
                - (float(second[1]) - float(first[1])) * (px - float(first[0]))) / line_length
        if abs(side) <= dead_zone:
            continue
        sign = 1 if side > 0 else -1
        if previous is not None and sign != previous[1]:
            movement = math.hypot(px - previous[2], py - previous[3]) / max(width, height)
            if movement >= 0.015 and _segments_intersect(
                (previous[2], previous[3]),
                (px, py),
                (float(first[0]), float(first[1])),
                (float(second[0]), float(second[1])),
            ):
                return frame_index, min(confidence, previous[4])
        previous = (frame_index, sign, px, py, confidence)
    return None


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    first_vector = (first_end[0] - first_start[0], first_end[1] - first_start[1])
    second_vector = (second_end[0] - second_start[0], second_end[1] - second_start[1])
    delta = (second_start[0] - first_start[0], second_start[1] - first_start[1])
    denominator = first_vector[0] * second_vector[1] - first_vector[1] * second_vector[0]
    if abs(denominator) < 1e-9:
        return False
    first_parameter = (delta[0] * second_vector[1] - delta[1] * second_vector[0]) / denominator
    second_parameter = (delta[0] * first_vector[1] - delta[1] * first_vector[0]) / denominator
    tolerance = 1e-9
    return (
        -tolerance <= first_parameter <= 1 + tolerance
        and -tolerance <= second_parameter <= 1 + tolerance
    )


def _polygon_trigger(track: Track, overlay: dict[str, Any]) -> tuple[int, float] | None:
    width = float(overlay.get("width") or 1)
    height = float(overlay.get("height") or 1)
    previous_inside: bool | None = None
    for frame_index, x, y, confidence in track.points:
        inside = _point_in_polygon((x * width, y * height), overlay["points"])
        if previous_inside is False and inside:
            return frame_index, confidence
        previous_inside = inside
    return None


def _point_in_polygon(point: tuple[float, float], polygon: Sequence[Sequence[float]]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, current in enumerate(polygon):
        xi, yi = float(current[0]), float(current[1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        if (yi > y) != (yj > y):
            intersection = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            if x < intersection:
                inside = not inside
        j = i
    return inside


def _decode_yolox(predictions: Any, width: int, height: int, np: Any) -> Any:
    strides = [8, 16, 32]
    shapes = [(height // stride, width // stride) for stride in strides]
    expected = sum(rows * columns for rows, columns in shapes)
    if predictions.shape[0] != expected:
        return predictions
    grids = []
    expanded_strides = []
    for (rows, columns), stride in zip(shapes, strides):
        yv, xv = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(np.full((*grid.shape[:2], 1), stride))
    grid = np.concatenate(grids, axis=1)[0]
    stride_values = np.concatenate(expanded_strides, axis=1)[0]
    decoded = predictions.copy()
    decoded[:, :2] = (decoded[:, :2] + grid) * stride_values
    decoded[:, 2:4] = np.exp(decoded[:, 2:4]) * stride_values
    return decoded


def _intersection_over_union(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0
