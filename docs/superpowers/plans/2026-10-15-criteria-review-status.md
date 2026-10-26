# Criteria REVIEW Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename final comparison result status `BLANK` to `REVIEW` in active Python and `Prompt_AI_BEM_v11` without changing source-document `BLANK` values.

**Architecture:** Keep `BLANK` as an extraction/evidence value for missing signature data. Change final `CriteriaStatus` outputs and prompt wording/schema. Separate the internal LLM-routing sentinel so the new public `REVIEW` result does not unexpectedly invoke an LLM.

**Tech Stack:** Python 3, unittest, SQL prompt files.

## Global Constraints

- Do not commit changes.
- Do not modify archived Python code.
- Preserve all unrelated wording and logic.
- Public result statuses are `OK`, `NG`, and `REVIEW`.
- Source signature values remain `VALID`, `INVALID`, and `BLANK`.

---

### Task 1: Add Contract Tests

- [ ] Test missing-data results return `REVIEW`.
- [ ] Test every criteria prompt uses `OK | NG | REVIEW`.
- [ ] Test source signature `BLANK` remains accepted.
- [ ] Run tests and verify failure before implementation.

### Task 2: Update Active Python

- [ ] Change final missing-data `CriteriaStatus` outputs to `REVIEW`.
- [ ] Preserve source signature normalization as `BLANK`.
- [ ] Separate internal LLM routing from public `REVIEW`.
- [ ] Run focused tests.

### Task 3: Update Prompt Configurations

- [ ] Change final status wording and schemas to `REVIEW`.
- [ ] Preserve raw signature evidence references to `BLANK`.
- [ ] Run the prompt contract scan.

### Task 4: Verify Scope

- [ ] Run focused unittests.
- [ ] Compile modified Python files.
- [ ] Scan for obsolete result schemas.
- [ ] Review the diff for unrelated changes.
