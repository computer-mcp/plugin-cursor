# Package architecture

The package is independently maintained and distributed. Computer MCP owns registration, authorization, project selection, CLI argument encoding and audit. This repository owns the Cursor CLI description, the reviewed vendor launch signature and ACP-to-MCP translation.

`computer-mcp-plugin.toml` composes the file-backed CLI tree, the packaged stdio adapter and Skills. `cli-tree.json` is the sole native command/version description. Adapter request schemas remain vendor-specific rather than imposing an Agent framework on the host.

`bin/cursor-mcp-adapter` owns native sessions, one active operation per session, bounded events and pending permission/question/plan responses. `bin/plugin_runtime.py` is a package-private standard-library implementation of bounded MCP framing/validation, process ownership and retention; it is distributed with this plugin, not installed into or imported from Computer MCP. Each package can update independently. Python 3.13+ is a runtime dependency selected by the launch PATH.

The standard MCP work resource projects these same session owners. The adapter
binds each session to its creation request's host correlation and supplies live
or uncertain state; the MCP server bounds and versions complete snapshots.
Background threads and unconfirmed cleanup remain owned even after the creating
tool returns. Host configuration generations and continuation routing remain
host responsibilities. The resource does not introduce another task lifecycle.

The managed adapter uses `bin/cursor_vendor_execution.py` to correlate the Host's
version probe, workload and cleanup receipts. The Host owns those processes.
Standalone execution uses the shared runtime's local supervisor and lifeline.
Vendor subprocesses do not inherit the managed channel or the local supervisor
lifeline. Explicit cleanup acknowledgment is separate from exit status.

Scripts provide deterministic packaging, non-model native interface checks and isolated exact-source consumer checks and separate archive identity checks. Tests exercise deterministic peers and lifecycle failures. The distribution excludes build/test/evidence files. No full native GUI, Windows backend or hosted API is claimed by this package.

The manifest owns provider purposes and MCP caller default/exact-name requirements.
The host owns review, dual-authority admission, persistent provider containers, selected
worktrees and lifecycle. Source consumer fixtures use separate owner/admin and caller
profiles and generation-aware host lifecycle dispatch; they never import vendor login
state or authorize native choices. The offline sandbox declaration is omitted pending
native environment evidence and the owner's runtime decision.
