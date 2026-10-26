# BEMT2009 Rule Engine Config Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Mapping and Rule Engine configuration from `dbo.ONT1043` to `dbo.BEMT2009` without changing the API-AI to Python comparison contract.

**Architecture:** A SQL Server migration creates `BEMT2009` with the same schema, constraints and indexes as `ONT1043`, copies the 33 active configuration rows, validates the copy, then drops `ONT1043` in the same transaction. Python changes only the repository query to load `BEMT2009`.

**Tech Stack:** SQL Server, Python, `pyodbc`, `unittest`.

## Global Constraints

- Preserve all columns, values, defaults, primary key and runtime indexes.
- The script must be idempotent after a successful migration.
- Do not change ERP/API-AI request or response payloads.
- Validate the six NVL criteria from stored `BEMT2002` snapshots after migration.

### Task 1: Add the database migration script

**Files:**
- Create: `scripts/sql/20261008_migrate_ont1043_to_bemt2009.sql`

- [ ] Create `dbo.BEMT2009` with the production schema and indexes.
- [ ] Copy rows from `dbo.ONT1043`, compare row counts and verify all source APK values exist in the target.
- [ ] Drop `dbo.ONT1043` only after validation succeeds; rollback on any error.

### Task 2: Point Python at BEMT2009

**Files:**
- Modify: `App/Rules_BE/rule_engine_config_repository.py`
- Modify: `tests/test_rule_engine_config_repository.py`

- [ ] Add a failing test asserting the runtime SQL reads `dbo.BEMT2009`.
- [ ] Update the repository query.
- [ ] Run the repository test.

### Task 3: Apply and validate

**Files:**
- Output: `E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Danh_gia_Mapping_RuleEngine_NVL_Snapshot_20261007.xlsx`

- [ ] Execute the SQL script on the configured DB.
- [ ] Verify `BEMT2009` has 33 rows and `ONT1043` no longer exists.
- [ ] Run the relevant Rule Engine unit tests.
- [ ] Run the 4,092-criterion snapshot validation and investigate remaining differences against rules/evidence.
