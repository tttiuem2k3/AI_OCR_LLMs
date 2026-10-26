# NVL AFTER INVOICE Aliases Implementation Plan

> Use executing-plans to continue inline in this session.

**Goal:** Recognize invoice-date aliases while retaining existing NVL deadline semantics.
**Architecture:** Central alias catalog and display formats in rules_ai_bem_meiko.py; reuse invoice-anchor calculation and business-day adjustment.
**Tech Stack:** Python, re, datetime, unittest.

## Constraints
Preserve API/schema, BEMT2009, AMS/AFTER_BL behavior and unrelated dirty-tree changes. Continue in the existing checkout; no commits, branches, database writes or LLM calls.

## Task 1: Parser and source behavior
Files: tests/test_rules_ai_bem_meiko_payment_deadline.py; App/Rules_BE/rules_ai_bem_meiko.py.
Interface: _parse_payment_term_key(value) returns (family, days) or None; _build_nguyenvatlieu_payment_deadline_source(content_text) returns the existing dict.
- [x] Add literal expected keys/dates/evidence tests detecting rejected or misclassified aliases and incorrect customs-date anchors.
- [x] Run AI_BEM/Scripts/python.exe -m unittest tests.test_rules_ai_bem_meiko_payment_deadline -v and confirm AFTER_INVOICE failures before implementation.
- [x] Add family regex aliases, unique-family validation and display formats; include AFTER INVOICE in diagnostics. Preserve day-count/date policies.
- [x] Re-run focused tests and confirm GREEN.

## Task 2: Integration and regression
Files: tests/test_rules_ai_bem_meiko_payment_deadline.py; temporary controlled holiday calendar only.
- [x] Verify 30/60/90-day dates, OK/NG status and evidence through source/result integration, plus process_ai_llms_models_rules for the 30-day alias with an LLM callback that raises if invoked.
- [x] Run payment, description, construction, message and NVL regressions; compile the modified module.
- [x] Review focused changes and record exact results; leave unrelated failures untouched.

## Validation results (2026-10-14)
- RED: 6 expected failures (including alias subtests) before implementation.
- GREEN: 161 tests pass across payment deadline, description, message contract, NVL engine, delivery term, config repository and execution routing suites.
- The modified production module and test module compile successfully.
- Construction-only suite: 13 tests, 5 failures and 3 errors. Reconstructed pre-change payment logic in memory produces the same counts; the three errors are pre-existing NameError for invalid_anchor_file_names in the unrelated construction branch. Not changed in this task.
- Changes remain local; no deployment, database changes, branches or commits.
