from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import cv2
import numpy as np

from .orientation import VALID_ANGLES, rotate_quarter_turn


@dataclass(frozen=True)
class VerificationResult:
    angle: int
    passed: bool
    detected_box_count: int
    retained_crop_count: int
    horizontal_ratio: float
    upright_vote: float
    reason: str


@dataclass(frozen=True)
class OrientationVerifierConfig:
    det_side_len: int = 640
    min_lines: int = 3
    upright_vote: float = 0.20
    horizontal_ratio: float = 0.60
    line_aspect: float = 1.20
    batch_size: int = 8


def _ordered_quad(points: np.ndarray) -> np.ndarray:
    quad = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if quad.shape != (4, 2) or not np.isfinite(quad).all():
        raise ValueError("text polygon must contain four finite points")
    ordered = np.empty((4, 2), dtype=np.float32)
    coordinate_sum = quad.sum(axis=1)
    coordinate_diff = np.diff(quad, axis=1).reshape(-1)
    ordered[0] = quad[np.argmin(coordinate_sum)]
    ordered[2] = quad[np.argmax(coordinate_sum)]
    ordered[1] = quad[np.argmin(coordinate_diff)]
    ordered[3] = quad[np.argmax(coordinate_diff)]
    return ordered


def _quad_dimensions(points: np.ndarray) -> tuple[float, float]:
    top_left, top_right, bottom_right, bottom_left = _ordered_quad(points)
    width = max(
        float(np.linalg.norm(top_right - top_left)),
        float(np.linalg.norm(bottom_right - bottom_left)),
    )
    height = max(
        float(np.linalg.norm(bottom_left - top_left)),
        float(np.linalg.norm(bottom_right - top_right)),
    )
    return width, height


def rectify_quad(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    source = np.asarray(image)
    if source.ndim not in (2, 3):
        raise ValueError("image must have 2 or 3 dimensions")
    ordered = _ordered_quad(points)
    width, height = _quad_dimensions(ordered)
    output_width = max(1, int(round(width)))
    output_height = max(1, int(round(height)))
    target = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(ordered, target)
    crop = cv2.warpPerspective(
        source,
        transform,
        (output_width, output_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return np.ascontiguousarray(crop)


def build_horizontal_crops(
    image: np.ndarray,
    polygons: Sequence[object],
    detector_scores: Sequence[object],
    *,
    min_aspect: float,
) -> tuple[list[np.ndarray], list[float], float]:
    if len(polygons) != len(detector_scores):
        raise ValueError("detector polygons and scores must have equal length")
    crops: list[np.ndarray] = []
    retained_scores: list[float] = []
    weighted_total_area = 0.0
    weighted_horizontal_area = 0.0
    for polygon, raw_score in zip(polygons, detector_scores):
        score = max(0.0, float(raw_score))
        try:
            quad = _ordered_quad(np.asarray(polygon, dtype=np.float32))
            area = abs(float(cv2.contourArea(quad)))
            width, height = _quad_dimensions(quad)
        except (TypeError, ValueError, cv2.error):
            continue
        if area <= 0.0 or width <= 0.0 or height <= 0.0:
            continue
        weighted_area = score * area
        weighted_total_area += weighted_area
        if width / height < float(min_aspect):
            continue
        try:
            crop = rectify_quad(image, quad)
        except (TypeError, ValueError, cv2.error):
            continue
        if crop.size == 0:
            continue
        crops.append(crop)
        retained_scores.append(score)
        weighted_horizontal_area += weighted_area
    horizontal_ratio = (
        weighted_horizontal_area / weighted_total_area
        if weighted_total_area > 0.0
        else 0.0
    )
    return crops, retained_scores, horizontal_ratio


def weighted_upright_vote(
    detector_scores: Sequence[object],
    upright_probabilities: Sequence[object],
    upside_down_probabilities: Sequence[object],
) -> float:
    if not (
        len(detector_scores)
        == len(upright_probabilities)
        == len(upside_down_probabilities)
    ):
        raise ValueError("vote inputs must have equal length")
    weights = np.asarray(detector_scores, dtype=np.float64)
    upright = np.asarray(upright_probabilities, dtype=np.float64)
    upside_down = np.asarray(upside_down_probabilities, dtype=np.float64)
    weight_sum = float(weights.sum())
    if weight_sum <= 0.0:
        return 0.0
    return float(np.sum(weights * (upright - upside_down)) / weight_sum)


def evaluate_candidate(
    *,
    angle: int,
    detected_box_count: int,
    retained_crop_count: int,
    horizontal_ratio: float,
    upright_vote: float,
    config: OrientationVerifierConfig,
) -> VerificationResult:
    normalized_angle = int(angle) % 360
    if normalized_angle not in VALID_ANGLES or normalized_angle == 0:
        raise ValueError("verification angle must be 90, 180, or 270")
    reason = "verified"
    passed = True
    if int(retained_crop_count) < int(config.min_lines):
        passed = False
        reason = "insufficient_lines"
    elif float(upright_vote) < float(config.upright_vote):
        passed = False
        reason = "low_upright_vote"
    elif normalized_angle in (90, 270) and float(horizontal_ratio) < float(
        config.horizontal_ratio
    ):
        passed = False
        reason = "low_horizontal_ratio"
    return VerificationResult(
        angle=normalized_angle,
        passed=passed,
        detected_box_count=int(detected_box_count),
        retained_crop_count=int(retained_crop_count),
        horizontal_ratio=float(horizontal_ratio),
        upright_vote=float(upright_vote),
        reason=reason,
    )


def _result_mapping(result: object) -> Mapping[str, object]:
    if isinstance(result, Mapping):
        return result
    json_value = getattr(result, "json", None)
    if isinstance(json_value, Mapping):
        return json_value
    raise ValueError("prediction result is not a mapping")


def _invoke_predictor(model, inputs, *, batch_size: int, topk: int | None = None, **kwargs):
    predict = getattr(model, "predict", None)
    if callable(predict):
        call_kwargs = {"batch_size": batch_size, **kwargs}
        if topk is not None:
            call_kwargs["topk"] = topk
        return predict(inputs, **call_kwargs)
    if callable(model):
        return model(input=inputs, batch_size=batch_size, **kwargs)
    raise TypeError("prediction model is not callable")


def _textline_probabilities(
    predictions: Iterable[object],
) -> tuple[list[float], list[float]]:
    upright: list[float] = []
    upside_down: list[float] = []
    for raw_prediction in predictions:
        prediction = _result_mapping(raw_prediction)
        label_values = prediction.get("label_names")
        score_values = prediction.get("scores")
        labels = [] if label_values is None else list(label_values)
        scores = [] if score_values is None else list(score_values)
        if len(labels) != len(scores):
            raise ValueError("text-line labels and scores must have equal length")
        score_map = {
            str(label).strip().lower(): float(score)
            for label, score in zip(labels, scores)
        }
        if "0_degree" not in score_map or "180_degree" not in score_map:
            raise ValueError("text-line result is missing orientation probabilities")
        upright.append(score_map["0_degree"])
        upside_down.append(score_map["180_degree"])
    return upright, upside_down


class TextLineOrientationVerifier:
    def __init__(
        self,
        detector,
        textline_model,
        config: OrientationVerifierConfig | None = None,
    ):
        self.detector = detector
        self.textline_model = textline_model
        self.config = config or OrientationVerifierConfig()

    def verify(self, source_image: np.ndarray, angle: int) -> VerificationResult:
        normalized_angle = int(angle) % 360
        detected_box_count = 0
        retained_crop_count = 0
        horizontal_ratio = 0.0
        try:
            candidate = rotate_quarter_turn(source_image, normalized_angle)
            detector_results = list(
                _invoke_predictor(
                    self.detector,
                    candidate,
                    batch_size=1,
                    limit_side_len=int(self.config.det_side_len),
                    limit_type="max",
                    thresh=0.30,
                    box_thresh=0.45,
                    unclip_ratio=1.6,
                )
            )
            if len(detector_results) != 1:
                raise ValueError("detector returned an incomplete page result")
            detector_result = _result_mapping(detector_results[0])
            polygon_values = detector_result.get("dt_polys")
            score_values = detector_result.get("dt_scores")
            polygons = [] if polygon_values is None else list(polygon_values)
            scores = [] if score_values is None else list(score_values)
            detected_box_count = len(polygons)
            crops, crop_scores, horizontal_ratio = build_horizontal_crops(
                candidate,
                polygons,
                scores,
                min_aspect=float(self.config.line_aspect),
            )
            retained_crop_count = len(crops)
            if retained_crop_count < int(self.config.min_lines):
                return evaluate_candidate(
                    angle=normalized_angle,
                    detected_box_count=detected_box_count,
                    retained_crop_count=retained_crop_count,
                    horizontal_ratio=horizontal_ratio,
                    upright_vote=0.0,
                    config=self.config,
                )
            predictions = list(
                _invoke_predictor(
                    self.textline_model,
                    crops,
                    batch_size=int(self.config.batch_size),
                    topk=2,
                )
            )
            if len(predictions) != retained_crop_count:
                return VerificationResult(
                    angle=normalized_angle,
                    passed=False,
                    detected_box_count=detected_box_count,
                    retained_crop_count=retained_crop_count,
                    horizontal_ratio=horizontal_ratio,
                    upright_vote=0.0,
                    reason="incomplete_predictions",
                )
            upright, upside_down = _textline_probabilities(predictions)
            vote = weighted_upright_vote(crop_scores, upright, upside_down)
            return evaluate_candidate(
                angle=normalized_angle,
                detected_box_count=detected_box_count,
                retained_crop_count=retained_crop_count,
                horizontal_ratio=horizontal_ratio,
                upright_vote=vote,
                config=self.config,
            )
        except Exception:
            return VerificationResult(
                angle=normalized_angle,
                passed=False,
                detected_box_count=detected_box_count,
                retained_crop_count=retained_crop_count,
                horizontal_ratio=horizontal_ratio,
                upright_vote=0.0,
                reason="verification_error",
            )
