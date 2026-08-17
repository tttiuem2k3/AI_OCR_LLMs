# Fast Document Orientation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add confidence-gated document orientation before PPStructureV3 inference.

**Architecture:** A pure helper decides and applies quarter-turn rotations. `OCREngine` owns one lightweight orientation predictor and supplies prepared page arrays to PPStructureV3.

**Tech Stack:** Python, NumPy, PaddleX, PaddleOCR, unittest.

---

### Task 1: Orientation helper

**Files:**
- Create: `App/OCR_BE/orientation.py`
- Create: `tests/test_ocr_orientation.py`

- [x] Write failing decision and rotation tests.
- [x] Implement confidence and margin gating.
- [x] Verify focused tests pass.

### Task 2: Runtime integration

**Files:**
- Modify: `App/settings_all.py`
- Modify: `App/OCR_BE/ocr_engine_iis.py`

- [x] Add experimental settings.
- [x] Load the local orientation model once.
- [x] Prepare page arrays before OCR inference.
- [x] Log decisions and fall back on preprocessing errors.

### Task 3: Verification

- [ ] Run the focused unit test suite.
- [ ] Run the regression PDF through the target Paddle environment.
- [ ] Inspect the generated annotation orientation.
