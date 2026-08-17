import unittest

import numpy as np

from App.OCR_BE.orientation import (
    decide_orientation,
    pad_to_square,
    prepare_oriented_inputs,
    rotate_quarter_turn,
)


class FastDocumentOrientationTests(unittest.TestCase):
    def test_keeps_original_when_nonzero_prediction_is_below_score_threshold(self):
        decision = decide_orientation(
            labels=["270", "0"],
            scores=[0.76803, 0.15886],
            min_score=0.95,
            min_margin=0.20,
        )
        self.assertEqual(decision.predicted_angle, 270)
        self.assertFalse(decision.should_rotate)
        self.assertEqual(decision.applied_angle, 0)

    def test_rotates_when_nonzero_prediction_is_confident_and_separated(self):
        decision = decide_orientation(
            labels=["180", "0"],
            scores=[0.98, 0.01],
            min_score=0.95,
            min_margin=0.20,
        )
        self.assertTrue(decision.should_rotate)
        self.assertEqual(decision.applied_angle, 180)

    def test_never_rotates_when_zero_is_top_prediction(self):
        decision = decide_orientation(
            labels=["0", "180"],
            scores=[0.99, 0.005],
            min_score=0.95,
            min_margin=0.20,
        )
        self.assertFalse(decision.should_rotate)
        self.assertEqual(decision.applied_angle, 0)

    def test_rotates_counterclockwise_using_paddle_angle_convention(self):
        image = np.array(
            [[[1], [2], [3]], [[4], [5], [6]]],
            dtype=np.uint8,
        )
        rotated = rotate_quarter_turn(image, 90)
        self.assertEqual(rotated[:, :, 0].tolist(), [[3, 6], [2, 5], [1, 4]])

    def test_pads_portrait_image_to_square_without_resizing_content(self):
        image = np.array(
            [[[1], [2]], [[3], [4]], [[5], [6]], [[7], [8]]],
            dtype=np.uint8,
        )

        padded = pad_to_square(image, fill_value=255)

        self.assertEqual(padded.shape, (4, 4, 1))
        self.assertEqual(padded[:, 0, 0].tolist(), [255, 255, 255, 255])
        self.assertEqual(padded[:, 1:3, 0].tolist(), image[:, :, 0].tolist())

    def test_prepares_each_page_using_confidence_gate(self):
        upright = np.array(
            [[[1], [2], [3]], [[4], [5], [6]]],
            dtype=np.uint8,
        )
        upside_down = np.array(
            [[[7], [8]], [[9], [10]], [[11], [12]]],
            dtype=np.uint8,
        )

        class FakeModel:
            def predict(self, input_path, batch_size, topk):
                self.calls = getattr(self, "calls", [])
                self.calls.append((input_path, batch_size, topk))
                if isinstance(input_path, str):
                    return iter(
                        [
                            {"input_img": upright},
                            {"input_img": upside_down},
                        ]
                    )
                return iter(
                    [
                        {"label_names": ["0", "270"], "scores": [0.93, 0.02]},
                        {"label_names": ["180", "0"], "scores": [0.94, 0.02]},
                    ]
                )

        model = FakeModel()
        images, decisions = prepare_oriented_inputs(
            model,
            "sample.pdf",
            min_score=0.90,
            min_margin=0.20,
        )

        self.assertEqual(model.calls[0], ("sample.pdf", 1, 1))
        self.assertEqual(model.calls[1][1:], (1, 2))
        self.assertEqual(
            [image.shape for image in model.calls[1][0]],
            [upright.shape, upside_down.shape],
        )
        self.assertEqual(images[0].tolist(), upright.tolist())
        self.assertEqual(images[1].tolist(), rotate_quarter_turn(upside_down, 180).tolist())
        self.assertEqual([item.applied_angle for item in decisions], [0, 180])


if __name__ == "__main__":
    unittest.main()
