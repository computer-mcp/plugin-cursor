# plugin-cursor Agent Guide

Read `README.md`, `computer-mcp-plugin.toml`, and `Documentation/Reference/Interface.md` before editing.

Keep vendor installation, authentication, subscription usage, and updates outside this repository. The external Cursor Agent is a dependency, not bundled code. Do not run authenticated model prompts merely to validate package structure.

`cli-tree.json` is publisher-owned static interface data for the pinned Cursor Agent baseline. Update it only after verifying the real native `--help` and `--version`. Keep coverage explicitly partial.

`bin/cursor-mcp-adapter` owns ACP-to-MCP translation only. It must use the host-selected current working directory, bound input/output, terminate owned child processes, and never invent approval or interactive answers. `reject-once` remains the default Cursor permission response. Explicit manual responses must match one active request and the choices actually offered. Preserve opaque native session IDs separately from adapter handles.

Use Python standard library only unless a dependency demonstrably removes required complexity. Tests must cover MCP initialization, tool discovery, ACP framing, permission response, deterministic package contents, and executable archive mode.

Before handoff run the unit tests, native non-model interface check, deterministic package build, Computer MCP package validation/doctor where available, and git status. Do not publish or create a release implicitly.
