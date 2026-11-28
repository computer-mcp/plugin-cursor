# Installation and validation

## Dependencies and configuration

The process supervisor requires the macOS `os.waitid` interface exposed by Python 3.13+. Older interpreters are rejected before any vendor process is started.

Install Cursor Agent separately and sign in on your computer using Cursor.
The plugin bridges Cursor Agent to Computer MCP. The installed provider runs
in a Host-provisioned container, so signing in on your computer does not
establish that Cursor Agent can use that session from the container.
[Cursor CLI authentication](https://cursor.com/docs/cli/reference/authentication)

The native executable version must match `cli-tree.json`. Its `executable_checks`
apply before CLI calls and adapter execution.

Provide Python 3.13 or newer. Computer MCP can resolve the declared `python-runtime`
dependency for the packaged adapter. A direct standalone launch uses the adapter's
`#!/usr/bin/env python3` shebang and the launch environment's PATH.

Install the ZIP through the plugin UI or owner CLI of a Computer MCP host that
supports managed vendor execution. Installation is separate from activation and
permission review. Use `plugins list/show` to obtain the current revision and
installation identity. Review `Examples/settings.json`, replace its placeholder
path, then configure the plugin through the same UI or `plugins configure`.
The `cursor-agent` dependency binding selects one verified executable for the CLI
and managed ACP contributions.

The example exposes this plugin's complete MCP tool catalog with no extra prefix. It is a host choice, not authorization embedded in the package. Authorize the desired tools/registration and project in the calling profile. Obtain projected CLI and MCP names from the actual host `tools/list`, rather than constructing names. `plugins doctor` checks files and configuration; an MCP connection check verifies initialization/catalog, not model execution.

Computer MCP publishes plugin configuration changes to connected clients atomically. New calls use the current configuration; existing work keeps its owning runtime until release. Installation does not grant access, and later calls use current authorization.

Use the isolated checks below to verify a candidate without restarting the active
development control connection.

## Build

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/validate_native.py --executable /absolute/path/to/agent
python3 scripts/build_package.py /new/output/directory
```

The builder produces `cursor.zip` and prints an ID/version/SHA-256 receipt. Identical source bytes produce identical archive bytes. It refuses to overwrite a different existing artifact. The archive contains the manifest, canonical CLI tree, vendor launch signature, adapters, Skills, examples, manuals and notices. It excludes tests, build scripts, local evidence, caches and credentials. Only executable entrypoints receive executable mode.

CI runs deterministic fixture tests and packaging; it does not install a vendor or invoke a model. Native validation checks the actual version/help and required flags only. ACP initialization without authentication is a separate non-model protocol probe for Cursor. Full authenticated prompt execution remains a separately authorized acceptance run because it can consume subscription/API usage and perform vendor actions.

## Deterministic source consumer

Use explicit clean host and plugin repository roots and full lowercase 40-character
commit SHAs. Choose a fresh absolute output path outside both checkouts and their
ancestors. The driver verifies both HEADs and clean status, exports committed sources
into the output directory, and injects the companion fixture into the isolated
host snapshot. It uses the real package identity, declaration review, provider grants,
separate consumer profiles and host-owned worktrees. No installed App, production control
socket or moving ref is used. The host test target must provide its
committed `FixedHostFixture`, permission fixtures and standalone generation API.

```sh
python3 scripts/validate_host_source.py \
  --host-source /absolute/path/to/host --host-sha FULL_HOST_SHA \
  --plugin-source /absolute/path/to/plugin-cursor --plugin-sha FULL_PLUGIN_SHA \
  --output /absolute/path/to/validation-runs/cursor-source-run
```

Replace both SHA placeholders with reviewed commits. The registered CI job uses
the plugin commit under test and fetches [the pinned Host SHA](../../.github/computer-mcp-host.sha)
from the public Host repository. The SHA must be publicly fetchable before CI can pass.
CI writes the run to the runner's temporary directory and uploads its receipt, case
evidence and logs.
Python is the driver's current interpreter
(recorded with its hash); the host launch environment must independently supply Python
3.13+ for the adapter. The driver does not alter PATH or install dependencies.

Fresh nonzero case evidence is required before a receipt can pass. The suite exercises
CLI, ACP and Skills, dual authority/read-versus-write admission, container persistence,
selected-worktree writes, protected sentinels, manual native responses, retained turns,
cancellation, scoped client revocation and host removal with joined process ownership.
The driver bounds subprocess groups and logs, removes source/build snapshots, and retains
only logs, case evidence and a pair-specific receipt. Failure receipts distinguish
export cleanup from unverified fixture-process cleanup. Source/runtime acceptance must
be run by the integration owner after the draft is committed; lint alone proves no
runtime behavior.

Run the same command with `--suite vendor-stop` and a fresh output directory
to select `CursorSourceIntegrationTests/registeredVendorStop`. This builds the
archive from the staged plugin commit, installs it using the Host's archive
worker in an isolated fixture store, and records the archive digest. The test
exercises child acquisition, native settlement, pending permission cleanup,
independent retirement, lost start replies and closure during startup. The
default `--suite source` selects `CursorSourceIntegrationTests/sourceConsumer`.

## Packaged identity check

After packaging, validate the exact ZIP through the selected host's bounded archive
worker. This checks extraction, manifest, signature and runtime file identity, executable mode and cache exclusion;
it does not establish package-principal runtime admission or container behavior.

```sh
python3 scripts/validate_host.py \
  --host /absolute/path/to/computer-mcp --expected-host-version X.Y.Z \
  --archive /output/cursor.zip --output /new/evidence/directory
```

A real ACP handshake can be checked independently, without authenticating, opening a conversation or invoking a model:

```sh
python3 scripts/probe_acp.py --executable /absolute/path/to/agent --output /output/acp-probe.json
```

## Result interpretation

Fixture success proves adapter protocol/ownership behavior against the tested peer, not a real account or model. A native version/help check proves the installed command surface, not backend availability. A clean-source consumer proves deterministic interoperability only for its recorded source pair; it is not production installation or public release evidence. Keep these results separate in delivery receipts.
