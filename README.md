<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo/logo-dark.png">
    <img src=".github/assets/logo/logo-light.png" width="128" height="128" alt="">
  </picture>
</p>

<h1 align="center">Cursor</h1>

<p align="center">Computer MCP family plugin for Cursor Agent CLI and ACP integration.</p>

<p align="center">
  <a href="https://github.com/computer-mcp/plugin-cursor/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/computer-mcp/plugin-cursor/ci.yml?branch=master&label=CI&style=flat"></a>
  <img alt="Python 3.13 or newer" src="https://img.shields.io/badge/Python-3.13%2B-blue?style=flat">
  <img alt="Architecture: arm64" src="https://img.shields.io/badge/architecture-arm64-lightgrey?style=flat">
  <a href="LICENSE"><img alt="License: FSL-1.1-ALv2" src="https://img.shields.io/badge/license-FSL--1.1--ALv2-blue?style=flat"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#usage">Usage</a> ·
  <a href="docs/Reference/Interface.md">Interface</a> ·
  <a href="docs/README.md">Documentation</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

## Overview

An independent [Computer MCP](https://computer-mcp.github.io/) plugin for Cursor. One package
contributes a canonical CLI tree, a stdio MCP adapter that speaks the Agent Client Protocol (ACP)
to Cursor Agent, and client-neutral usage skills. It does not link Computer MCP Core, and adding
vendor behavior needs no host release.

The CLI contribution describes verified non-interactive commands; the native baseline and its
exact version assertion live in `cli-tree.json`. It is deliberately partial: interactive setup,
installation and unsupported administrative flows are not callable tools. The adapter owns
streaming and session and run state. The host owns registration, profile grants, the initial
working directory and audit.

## Quick look

| Contribution | What it adds |
| --- | --- |
| `agent` CLI | Typed tools for the verified non-interactive Cursor Agent commands |
| `acp` MCP server | Twelve `cursor.acp.*` tools: open or load a session, prompt it repeatedly or in the background, list, change mode, cancel and close sessions, read paginated events and answer permission, question and plan requests; `cursor.acp.prompt` is the one-shot path |
| `cursor-agent` skill | Guidance for choosing the CLI or the ACP tools safely |

Install the archive in the host, bind the `agent` executable, and configure both contributions
from `Examples/settings.json`.

## Install

1. Install and authenticate Cursor Agent yourself, and provide Python 3.13 or newer on the
   Computer MCP launch `PATH`. The plugin installs neither and never copies credentials.
2. Build the archive:

   ```sh
   python3 scripts/build_package.py /new/output/directory
   ```

3. Install the ZIP through Computer MCP's plugin UI or the owner CLI. Installation is neither
   activation nor a permission grant.
4. Review `Examples/settings.json`, replace its placeholder paths, and configure the plugin
   through the same UI or `plugins configure`. The CLI dependency binding selects the executable
   for the CLI contribution; the MCP launch `args` supply `--executable` for the adapter. Point
   both at the same verified installation.

See the [installation guide](docs/Reference/Installation.md) for revisions, configuration
publication and validation.

## Usage

Discovery lists the twelve tools without starting a vendor process. For workflows with
permission requests, questions or plans, use `cursor.acp.session.open` with
`cursor.acp.session.prompt.start`.

`permission_policy` defaults to `reject-once`. `allow-once` and `allow-always` are explicit
native decisions and only select options Cursor offers; `manual` exposes pending permission
requests for an explicit response. Questions and plans always need an explicit response, and no
answer is invented.

The work resource reports the connection's sessions until cleanup is confirmed, including idle
sessions, background prompts and interactive requests, so hosts can account for work after a tool
reply. It needs no private Host Services permission and does not enable host configuration
changes.

The working directory is not an operating-system sandbox. Vendor configuration, credentials and
tools keep their own authority; host authorization does not silently approve vendor actions. See
the [interface contract](docs/Reference/Interface.md) for retention, cancellation and error
semantics.

## Requirements

- Computer MCP on an arm64 computer.
- Cursor Agent (`agent`), installed and authenticated separately; its version must match
  `cli-tree.json`.
- Python 3.13 or newer.

## Documentation

The [documentation index](docs/README.md) links the architecture, the interface, the installation
guide and the [release process](docs/Reference/Release.md). To validate a checkout:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/validate_native.py --executable /absolute/path/to/agent
```

Tests use deterministic peers, not a model. Authenticated execution and production activation are
separate acceptance steps.

## Contributing

See the [contributor guide](CONTRIBUTING.md).

## License

Computer MCP-owned code and resources use the
[Functional Source License 1.1, Apache 2.0 Future License](LICENSE) (FSL-1.1-ALv2). Cursor Agent is
external software; see the [third-party notices](THIRD_PARTY_NOTICES.md).
