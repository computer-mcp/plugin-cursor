# Cursor Plugin

An independent Computer MCP plugin for Cursor. The same package contributes a canonical CLI Tree, a stdio MCP adapter and client-neutral usage Skills. It does not link Computer MCP Core or require a host release to add vendor behavior.

The CLI contribution describes verified non-interactive commands. The native baseline and its exact version assertion live in `cli-tree.json`. It is deliberately partial: interactive setup, installation and unsupported administrative flows are not represented as callable tools. The adapter separately owns streaming and session/run state; the host owns registration, profile grants, initial working-directory selection and audit.

## MCP capabilities

The adapter provides ACP session open/load, repeated prompts, background prompt start/result, session listing/mode/cancel/close, cursor-paginated events and explicit responses to permission/question/plan requests. `cursor.acp.prompt` remains the one-shot convenience path. Twelve tools are discovered through MCP; discovery does not start a vendor process.

`permission_policy` defaults to `reject-once`. `allow-once` and `allow-always` are explicit native decisions and only select offered options. `manual` exposes pending permission requests for an explicit response. Questions and plans always require an explicit response; no answer is invented. Use `session.open` plus `session.prompt.start` for these workflows.

## Use and verify

The external `agent` executable, Python 3.11+ and vendor credentials are user-owned. Install neither through this plugin. Configure the two contributions using the [installation guide](Documentation/Reference/Installation.md) and `Examples/settings.json`.

```sh
python3 -m unittest discover -s Tests -p 'test_*.py' -v
python3 Scripts/validate_native.py --executable /absolute/path/to/agent
python3 Scripts/build_package.py /new/output/directory
```

Normal tests use deterministic peers, not a model. Authenticated execution and production activation are separate acceptance steps. See the [interface contract](Documentation/Reference/Interface.md) for retention, cancellation and error semantics and the [documentation index](Documentation/README.md) for ownership.

The working directory is not an operating-system sandbox. Vendor configuration, credentials and tools retain their own authority; host authorization does not silently approve vendor actions.
