# Package architecture

The package is independently maintained and distributed. Computer MCP owns registration, authorization, workspace selection, CLI argument encoding and audit; this repository owns the Cursor CLI description and ACP-to-MCP translation. No host module, private database or optional Host Services callback is required.

`computer-mcp-plugin.toml` composes the file-backed CLI tree, the packaged stdio adapter and Skills. `cli-tree.json` is the sole native command/version description. Adapter request schemas remain vendor-specific rather than imposing an Agent framework on the host.

`bin/cursor-mcp-adapter` owns native sessions, one active operation per session, bounded events and pending permission/question/plan responses. `bin/plugin_runtime.py` is a package-private standard-library implementation of bounded MCP framing/validation, process ownership and retention; it is distributed with this plugin, not installed into or imported from Computer MCP. Each package can update independently. Python 3.13+ is a runtime dependency selected by the launch PATH.

The supervisor lifeline and cleanup receipt are private implementation channels, not plugin-host protocol extensions. Vendor subprocesses inherit neither channel nor host private descriptors. Explicit cleanup acknowledgement is separate from exit status. Runtime errors do not authorize retries or privilege escalation.

Scripts provide deterministic packaging, non-model native interface checks and isolated unchanged-host integration checks. Tests exercise deterministic peers and lifecycle failures. The distribution excludes build/test/evidence files. No full native GUI, Windows backend or hosted API is claimed by this package.
