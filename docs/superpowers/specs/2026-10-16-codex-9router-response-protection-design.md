# Codex 9Router Response Protection Compatibility Design

## Problem

Codex threads containing historical `web_search_call` items fail when a later request omits the `web_search` tool declaration. The local 9Router endpoint returns `response protection is unavailable`, which Codex surfaces as `stream closed before response.completed`.

## Design

Run a loopback-only Node.js proxy on `127.0.0.1:20129` in front of 9Router on `127.0.0.1:20128`. For JSON Responses API requests, the proxy detects historical `web_search_call` input. If the request does not declare `web_search`, it appends `{ "type": "web_search" }` and sets `tool_choice` to `none`. All other traffic passes through unchanged.

The proxy does not persist request or response bodies. A per-user Windows Startup launcher starts it hidden at login. Codex points its custom provider at port `20129`.

## Validation

- Unpatched request: reproduces six failed attempts with `response protection is unavailable`.
- Patched request: completes with `EXIT=0` on the same thread history.
- Verify startup launcher, listening port, direct health behavior, and a final fork of the affected thread.
