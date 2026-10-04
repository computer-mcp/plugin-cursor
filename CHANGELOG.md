# Changelog

All notable user-visible changes to the Cursor plugin are documented here.

## Unreleased

- Licensed under FSL-1.1-ALv2 (Functional Source License 1.1, Apache 2.0
  future license): any use other than a competing product or service is
  permitted, and each release becomes available under Apache-2.0 two years
  after publication. Published releases keep their original license.

## 0.1.1 — 2026-09-29

- Preserve ACP session ownership across background prompts, interactive requests
  and uncertain cleanup.
- Bind permission, question and plan replies to the current native request.
- Expose owned sessions through the standard MCP work resource, so a compatible
  host can account for work after a tool reply and across live configuration
  changes.
- Bound events and continuation handling while keeping native session identity
  explicit.

## 0.1.0 — 2026-09-24

- First release: a canonical CLI tree for the headless Cursor Agent surface, a
  stdio MCP adapter with twelve tools for ACP sessions, resumed conversations,
  synchronous and background prompts, events, cancellation and explicit
  permission, question and plan responses, and usage Skills.
- Requires Computer MCP 1.2.2 or later on Apple Silicon, Python 3.13 or newer,
  and Cursor Agent 2026.05.04-08e5280.
