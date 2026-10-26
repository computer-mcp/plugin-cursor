---
description: Keep the Cursor ACP adapter's translation bounded and its permission responses exact, and test its protocol paths.
---
# plugin-cursor Agent Guide

## Task Route

- Read `docs/Reference/Interface.md` before editing.
- Before handoff, run the unit tests and the native non-model interface check.

## Adapter

- `bin/cursor-mcp-adapter` owns ACP-to-MCP translation only. It uses the
  host-selected working directory, bounds input and output, terminates the
  child processes it owns, and never invents approvals or interactive answers.
- `reject-once` remains the default Cursor permission response. An explicit
  manual response must match one active request and the choices actually
  offered. Keep opaque native session IDs separate from adapter handles.
- Use the Python standard library unless a dependency demonstrably removes
  required complexity. Tests cover MCP initialization, tool discovery, ACP
  framing, permission responses, deterministic package contents and executable
  archive mode.
