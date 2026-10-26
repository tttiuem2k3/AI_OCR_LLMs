from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np


logger = logging.getLogger("ocr_app.orientation")


VALID_ANGLES = {0, 90, 180, 270}


@dataclass(frozen=True)
class OrientationDecision:
    predicted_angle: int
    top_score: float
    runner_up_score: float
    margin: float
    should_rotate: bool
    applied_angle: int
    upright_scores: tuple[tuple[int, float], ...] = ()
    original_upright_score: float = 0.0
    original_gain: float = 0.0
    decision_source: str = "one_pass"


@dataclass(frozen=True)
class OrientationVerificationTrace:
    selected: object | None = None
    opposite: object | None = None
    error: Exception | None = None


def apply_verified_orientations(
    source_images: Sequence[np.ndarray],
    decisions: Sequence[OrientationDecision],
    verifier: Callable[[np.ndarray, int], object],
) -> tuple[
    list[np.ndarray],
    list[OrientationDecision],
    list[OrientationVerificationTrace],
]:
    if len(source_images) != len(decisions):
        raise ValueError("source images and decisions must have equal length")

    final_images: list[np.ndarray] = []
    final_decisions: list[OrientationDecision] = []
    traces: list[OrientationVerificationTrace] = []
    for source_image, decision in zip(source_images, decisions):
        candidate_angle = int(decision.predicted_angle)
        if candidate_angle == 0:
            final_images.append(np.ascontiguousarray(source_image))
            final_decisions.append(decision)
            traces.append(OrientationVerificationTrace())
            continue

        selected_result = None
        opposite_result = None
        verification_error = None
        applied_angle = 0
        decision_source = "keep_unverified"
        try:
            selected_result = verifier(source_image, candidate_angle)
            if bool(getattr(selected_result, "passed", False)):
                applied_angle = candidate_angle
                decision_source = (
                    "ambiguous_verified"
                    if decision.decision_source == "keep_ambiguous"
                    else "four_way_verified"
                )
            elif candidate_angle in (90, 270):
                opposite_angle = (360 - candidate_angle) % 360
                opposite_result = verifier(source_image, opposite_angle)
                if bool(getattr(opposite_result, "passed", False)):
                    applied_angle = opposite_angle
                    decision_source = "opposite_verified"
        except Exception as exc:
            verification_error = exc

        final_images.append(rotate_quarter_turn(source_image, applied_angle))
        final_decisions.append(
            replace(
                decision,
                should_rotate=applied_angle != 0,
                applied_angle=applied_angle,
                decision_source=decision_source,
            )
        )
        traces.append(
            OrientationVerificationTrace(
                selected=selected_result,
                opposite=opposite_result,
                error=verification_error,
            )
        )

    return final_images, final_decisions, traces


def verify_prepared_orientations(
    prepared_images: Sequence[np.ndarray],
    decisions: Sequence[OrientationDecision],
    verifier: Callable[[np.ndarray, int], object],
) -> tuple[
    list[np.ndarray],
    list[OrientationDecision],
    list[OrientationVerificationTrace],
]:
    if len(prepared_images) != len(decisions):
        raise ValueError("prepared images and decisions must have equal length")
    source_images = [
        rotate_quarter_turn(image, (360 - int(decision.applied_angle)) % 360)
        for image, decision in zip(prepared_images, decisions)
    ]
    return apply_verified_orientations(source_images, decisions, verifier)


def decide_four_way_orientation(
    upright_scores: Mapping[object, object],
    *,
    min_upright_score: float,
    min_margin: float,
    min_original_gain: float,
) -> OrientationDecision:
    normalized_scores = {
        int(str(angle)): float(score)
        for angle, score in dict(upright_scores).items()
    }
    if set(normalized_scores) != VALID_ANGLES:
        raise ValueError(
            f"upright scores must contain exactly {sorted(VALID_ANGLES)}"
        )

    ranked = sorted(
        normalized_scores.items(),
        key=lambda item: (-item[1], item[0] != 0, item[0]),
    )
    best_angle, best_score = ranked[0]
    runner_up_score = ranked[1][1]
    margin = best_score - runner_up_score
    original_score = normalized_scores[0]
    original_gain = best_score - original_score
    should_rotate = bool(
        best_angle != 0
        and best_score >= float(min_upright_score)
        and margin >= float(min_margin)
        and original_gain >= float(min_original_gain)
    )
    return OrientationDecision(
        predicted_angle=best_angle,
        top_score=best_score,
        runner_up_score=runner_up_score,
        margin=margin,
        should_rotate=should_rotate,
        applied_angle=best_angle if should_rotate else 0,
        upright_scores=tuple(
            (angle, normalized_scores[angle]) for angle in sorted(VALID_ANGLES)
        ),
        original_upright_score=original_score,
        original_gain=original_gain,
        decision_source="four_way" if best_angle == 0 or should_rotate else "keep_ambiguous",
    )


def decide_orientation(
    labels: Sequence[object],
    scores: Sequence[object],
    *,
    min_score: float,
    min_margin: float,
) -> OrientationDecision:
    normalized_labels = [int(str(value)) for value in list(labels)]
    normalized_scores = [float(value) for value in list(scores)]
    if not normalized_labels or not normalized_scores:
        raise ValueError("orientation result must contain labels and scores")
    if len(normalized_labels) != len(normalized_scores):
        raise ValueError("orientation labels and scores must have equal length")

    predicted_angle = normalized_labels[0]
    if predicted_angle not in VALID_ANGLES:
        raise ValueError(f"unsupported orientation angle: {predicted_angle}")

    top_score = normalized_scores[0]
    runner_up_score = normalized_scores[1] if len(normalized_scores) > 1 else 0.0
    margin = top_score - runner_up_score
    should_rotate = bool(
        predicted_angle != 0
        and top_score >= float(min_score)
        and margin >= float(min_margin)
    )
    return OrientationDecision(
        predicted_angle=predicted_angle,
        top_score=top_score,
        runner_up_score=runner_up_score,
        margin=margin,
        should_rotate=should_rotate,
        applied_angle=predicted_angle if should_rotate else 0,
    )


def rotate_quarter_turn(image: np.ndarray, angle: int) -> np.ndarray:
    normalized_angle = int(angle) % 360
    if normalized_angle not in VALID_ANGLES:
        raise ValueError(f"angle must be one of {sorted(VALID_ANGLES)}")
    if normalized_angle == 0:
        return np.ascontiguousarray(image)
    return np.ascontiguousarray(np.rot90(image, k=normalized_angle // 90))


def pad_to_square(image: np.ndarray, fill_value: int = 255) -> np.ndarray:
    source = np.asarray(image)
    if source.ndim not in (2, 3):
        raise ValueError("image must have 2 or 3 dimensions")
    height, width = source.shape[:2]
    side = max(height, width)
    output_shape = (side, side) + source.shape[2:]
    padded = np.full(output_shape, fill_value, dtype=source.dtype)
    top = (side - height) // 2
    left = (side - width) // 2
    padded[top : top + height, left : left + width] = source
    return np.ascontiguousarray(padded)


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0 or values.size != weights.size:
        raise ValueError("values and weights must be non-empty and equal length")
    order = np.argsort(values)
    ordered_values = values[order]
    ordered_weights = weights[order]
    total_weight = float(ordered_weights.sum())
    if total_weight <= 0.0:
        raise ValueError("weights must have a positive sum")
    cutoff = total_weight * 0.5
    index = int(np.searchsorted(np.cumsum(ordered_weights), cutoff, side="left"))
    return float(ordered_values[min(index, ordered_values.size - 1)])


def _detect_skew_lines_cv2(image: np.ndarray) -> list[tuple[float, float, float, float]]:
    import cv2

    source = np.asarray(image)
    if source.ndim == 2:
        grayscale = source
    elif source.ndim == 3:
        grayscale = cv2.cvtColor(source[:, :, :3], cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError("image must have 2 or 3 dimensions")

    height, width = grayscale.shape[:2]
    if height <= 0 or width <= 0:
        return []
    analysis_height = max(1, round(height * 0.82))
    grayscale = grayscale[:analysis_height, :]

    _, binary = cv2.threshold(
        grayscale,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    connect_width = max(3, round(width * 0.015))
    connect_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (connect_width, 1),
    )
    connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, connect_kernel)
    edges = cv2.Canny(connected, 50, 150, apertureSize=3)
    min_line_length = max(40, round(width * 0.12))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 360.0,
        threshold=max(30, round(width * 0.05)),
        minLineLength=min_line_length,
        maxLineGap=max(8, round(width * 0.02)),
    )
    if lines is None:
        return []
    return [tuple(float(value) for value in line[0]) for line in lines]


def estimate_skew_angle_fast(
    image: np.ndarray,
    *,
    max_side: int = 800,
    min_line_length_ratio: float = 0.12,
    max_candidate_angle: float = 30.0,
    max_angle_spread: float = 5.0,
    min_lines: int = 3,
    line_detector: Callable[
        [np.ndarray], Sequence[Sequence[float]]
    ] | None = None,
) -> float | None:
    source = np.asarray(image)
    if source.ndim not in (2, 3):
        raise ValueError("image must have 2 or 3 dimensions")
    height, width = source.shape[:2]
    if height <= 0 or width <= 0:
        return None

    long_side = max(height, width)
    prepared = source
    if long_side > int(max_side):
        import cv2

        scale = float(max_side) / float(long_side)
        resized_width = max(1, round(width * scale))
        resized_height = max(1, round(height * scale))
        prepared = cv2.resize(
            source,
            (resized_width, resized_height),
            interpolation=cv2.INTER_AREA,
        )

    detector = line_detector or _detect_skew_lines_cv2
    lines = detector(prepared)
    prepared_width = prepared.shape[1]
    min_length = max(1.0, float(prepared_width) * float(min_line_length_ratio))
    angles: list[float] = []
    weights: list[float] = []
    for raw_line in lines:
        if len(raw_line) < 4:
            continue
        x1, y1, x2, y2 = (float(value) for value in raw_line[:4])
        delta_x = x2 - x1
        delta_y = y2 - y1
        length = float(np.hypot(delta_x, delta_y))
        if length < min_length:
            continue
        angle = float(np.degrees(np.arctan2(delta_y, delta_x)))
        if angle > 90.0:
            angle -= 180.0
        elif angle < -90.0:
            angle += 180.0
        if abs(angle) > float(max_candidate_angle):
            continue
        angles.append(angle)
        weights.append(length)

    if len(angles) < int(min_lines):
        return None
    angle_values = np.asarray(angles, dtype=np.float64)
    weight_values = np.asarray(weights, dtype=np.float64)
    median_angle = _weighted_median(angle_values, weight_values)
    angle_spread = _weighted_median(
        np.abs(angle_values - median_angle),
        weight_values,
    )
    if angle_spread > float(max_angle_spread):
        return None
    return median_angle


def should_use_doc_unwarping(
    image: np.ndarray,
    *,
    threshold_degrees: float = 10.0,
    line_detector: Callable[
        [np.ndarray], Sequence[Sequence[float]]
    ] | None = None,
) -> tuple[bool, float | None]:
    angle = estimate_skew_angle_fast(image, line_detector=line_detector)
    if angle is None:
        return True, None
    return abs(angle) > float(threshold_degrees), angle


def normalize_low_resolution_pages(
    images: Sequence[np.ndarray],
    *,
    target_short_side: int = 960,
    low_resolution_long_side: int = 1200,
    max_long_side: int = 1600,
    resize_image: Callable[[np.ndarray, tuple[int, int]], np.ndarray] | None = None,
) -> list[np.ndarray]:
    normalized_images: list[np.ndarray] = []
    for page_index, image in enumerate(images, start=1):
        source = np.asarray(image)
        height, width = source.shape[:2]
        short_side = min(width, height)
        long_side = max(width, height)

        if (
            height <= width
            or long_side >= low_resolution_long_side
            or short_side >= target_short_side
        ):
            normalized_images.append(source)
            continue

        scale = min(target_short_side / short_side, max_long_side / long_side)
        if scale <= 1:
            normalized_images.append(source)
            continue

        resized_width = round(width * scale)
        resized_height = round(height * scale)
        if resize_image is None:
            import cv2

            resized = cv2.resize(
                source,
                (resized_width, resized_height),
                interpolation=cv2.INTER_CUBIC,
            )
        else:
            resized = resize_image(source, (resized_width, resized_height))

        logger.info(
            "OCR low-res page upscale page=%d %dx%d -> %dx%d",
            page_index,
            width,
            height,
            resized_width,
            resized_height,
        )
        normalized_images.append(np.ascontiguousarray(resized))
    return normalized_images


def add_unwarping_safety_padding(
    images: Sequence[np.ndarray],
    *,
    small_short_side: int = 960,
    small_long_side: int = 1400,
    edge_ratio: float = 0.05,
    ink_threshold: int = 245,
    ink_ratio_threshold: float = 0.001,
    padding_ratio: float = 0.05,
    min_padding: int = 48,
    max_padding: int = 128,
    fill_value: int = 255,
) -> list[np.ndarray]:
    padded_images: list[np.ndarray] = []
    for page_index, image in enumerate(images, start=1):
        source = np.asarray(image)
        height, width = source.shape[:2]
        short_side = min(width, height)
        long_side = max(width, height)
        is_small_page = short_side < small_short_side or long_side < small_long_side

        edge_size = max(1, round(min(width, height) * edge_ratio))
        grayscale = source if source.ndim == 2 else source[:, :, :3].mean(axis=2)
        edge_pixels = np.concatenate(
            (
                grayscale[:edge_size, :].ravel(),
                grayscale[-edge_size:, :].ravel(),
                grayscale[:, :edge_size].ravel(),
                grayscale[:, -edge_size:].ravel(),
            )
        )
        edge_ink_ratio = float(np.mean(edge_pixels < ink_threshold)) if edge_pixels.size else 0.0
        has_edge_content = edge_ink_ratio >= ink_ratio_threshold
        if not (is_small_page or has_edge_content):
            padded_images.append(source)
            continue

        padding = round(long_side * padding_ratio)
        padding = max(min_padding, min(max_padding, padding))
        output_shape = (height + padding * 2, width + padding * 2, *source.shape[2:])
        padded = np.full(output_shape, fill_value, dtype=source.dtype)
        padded[padding : padding + height, padding : padding + width] = source
        logger.info(
            "OCR unwarping safety padding page=%d %dx%d -> %dx%d reason=%s edge_ink=%.4f",
            page_index,
            width,
            height,
            width + padding * 2,
            height + padding * 2,
            "small" if is_small_page else "edge_content",
            edge_ink_ratio,
        )
        padded_images.append(np.ascontiguousarray(padded))
    return padded_images


def _prediction_score_map(prediction: Mapping[str, object]) -> dict[int, float]:
    labels = prediction.get("label_names")
    scores = prediction.get("scores")
    if labels is None or scores is None:
        raise ValueError("orientation result is missing labels or scores")
    normalized_labels = [int(str(value)) for value in list(labels)]
    normalized_scores = [float(value) for value in list(scores)]
    if len(normalized_labels) != len(normalized_scores):
        raise ValueError("orientation labels and scores must have equal length")
    score_map = dict(zip(normalized_labels, normalized_scores))
    if not set(score_map).issubset(VALID_ANGLES):
        raise ValueError("orientation result contains an unsupported angle")
    return score_map


def prepare_oriented_inputs(
    model,
    input_path: str,
    *,
    min_score: float,
    min_margin: float,
    four_way_enabled: bool = False,
    upright_min_score: float = 0.60,
    original_gain: float = 0.20,
    orientation_batch_size: int = 4,
) -> tuple[list[np.ndarray], list[OrientationDecision]]:
    source_images: list[np.ndarray] = []
    source_predictions: Iterable[dict] = model.predict(
        input_path,
        batch_size=1,
        topk=4 if four_way_enabled else 1,
    )
    source_score_maps: list[dict[int, float]] = []
    for prediction in source_predictions:
        image = prediction.get("input_img")
        if image is None:
            raise ValueError("orientation result is missing input_img")
        source_images.append(np.asarray(image))
        if four_way_enabled:
            source_score_maps.append(_prediction_score_map(prediction))

    if not source_images:
        raise ValueError("orientation model returned no pages")

    if four_way_enabled:
        if int(orientation_batch_size) <= 0:
            raise ValueError("orientation_batch_size must be positive")
        candidate_angles = (90, 180, 270)
        candidate_predictions: list[dict] = []
        page_chunk_size = int(orientation_batch_size)
        for page_start in range(0, len(source_images), page_chunk_size):
            page_chunk = source_images[page_start : page_start + page_chunk_size]
            candidate_images = [
                rotate_quarter_turn(image, angle)
                for image in page_chunk
                for angle in candidate_angles
            ]
            chunk_predictions = list(
                model.predict(
                    candidate_images,
                    batch_size=int(orientation_batch_size),
                    topk=4,
                )
            )
            if len(chunk_predictions) != len(candidate_images):
                raise ValueError("orientation model returned incomplete candidate results")
            candidate_predictions.extend(chunk_predictions)

        images: list[np.ndarray] = []
        decisions: list[OrientationDecision] = []
        for page_index, image in enumerate(source_images):
            upright_scores = {0: source_score_maps[page_index].get(0, 0.0)}
            candidate_offset = page_index * len(candidate_angles)
            for angle_index, angle in enumerate(candidate_angles):
                score_map = _prediction_score_map(
                    candidate_predictions[candidate_offset + angle_index]
                )
                upright_scores[angle] = score_map.get(0, 0.0)
            decision = decide_four_way_orientation(
                upright_scores,
                min_upright_score=upright_min_score,
                min_margin=min_margin,
                min_original_gain=original_gain,
            )
            images.append(rotate_quarter_turn(image, decision.applied_angle))
            decisions.append(decision)
        return images, decisions

    predictions: Iterable[dict] = model.predict(
        source_images,
        batch_size=1,
        topk=2,
    )
    images: list[np.ndarray] = []
    decisions: list[OrientationDecision] = []
    for image, prediction in zip(source_images, predictions):
        labels = prediction.get("label_names")
        scores = prediction.get("scores")
        if labels is None or scores is None:
            raise ValueError("orientation result is missing labels or scores")

        decision = decide_orientation(
            labels,
            scores,
            min_score=min_score,
            min_margin=min_margin,
        )
        images.append(rotate_quarter_turn(image, decision.applied_angle))
        decisions.append(decision)

    if len(images) != len(source_images):
        raise ValueError("orientation model returned an incomplete page result")
    return images, decisions
