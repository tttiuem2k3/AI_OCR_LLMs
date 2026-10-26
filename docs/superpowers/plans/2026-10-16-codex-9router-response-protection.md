# Codex 9Router Response Protection Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep Codex threads with historical web-search calls usable through 9Router.

**Architecture:** A loopback Node.js proxy performs one narrow request compatibility transformation before forwarding to the existing 9Router service. A hidden per-user startup launcher keeps the proxy available after sign-in.

**Tech Stack:** Node.js HTTP, VBScript Startup launcher, Codex TOML configuration, PowerShell verification.

## Global Constraints

- Listen only on `127.0.0.1:20129`.
- Forward only to `127.0.0.1:20128`.
- Never persist conversation request or response bodies.
- Modify requests only when `web_search_call` exists and `web_search` is absent.

---

### Task 1: Install the compatibility proxy

**Files:**
- Create: `C:\Users\tanthinh\.codex\9router_compat_proxy.js`
- Create: `C:\Users\tanthinh\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\codex-9router-compat-proxy.vbs`

- [ ] Create the loopback proxy with the validated conditional transformation.
- [ ] Add hidden startup launch behavior and duplicate-listener handling.
- [ ] Start the installed proxy and verify port `20129` is listening.

### Task 2: Route Codex through the proxy

**Files:**
- Modify: `C:\Users\tanthinh\.codex\config.toml`

- [ ] Back up the current configuration.
- [ ] Change the 9Router `base_url` from port `20128` to `20129`.
- [ ] Confirm the authorization header remains unchanged and redacted from output.

### Task 3: Verify the affected history

- [ ] Fork `01a142a3-b0e5-7bb3-b5b2-8bc499d319b0` through the installed proxy.
- [ ] Require `EXIT=0`, a completed turn, and no protection or disconnect error.
- [ ] Archive diagnostic fork threads and remove the temporary diagnostic proxy process.
