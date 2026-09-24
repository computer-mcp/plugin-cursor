# Installation and validation

## Dependencies and configuration

Install and authenticate Cursor separately. The native executable version must match `cli-tree.json`; its `executable_checks` are applied before CLI calls and before adapter execution. The package does not install/update a vendor, perform interactive login, or copy credentials.

Provide Python 3.11 or newer as `python3` on the environment PATH that launches Computer MCP. The packaged executable uses `#!/usr/bin/env python3`. A host dependency binding alone does not rewrite this interpreter lookup. A supported interpreter is required even when the vendor executable is explicitly bound.

Install the ZIP through Computer MCP's plugin UI or owner CLI. Installation is not activation or a permission grant. Use `plugins list/show` to obtain the current revision and installation identity. Review `Examples/settings.json`, replace its placeholder paths, then configure the plugin through the same UI or `plugins configure` command. The CLI dependency binding selects the vendor for the CLI contribution; the MCP launch `args` independently supply `--executable` for the adapter. These two choices should normally point to the same verified installation.

The example exposes this plugin's complete MCP tool catalog with no extra prefix. It is a host choice, not authorization embedded in the package. Authorize the desired tools/registration and workspace in the calling profile. Obtain projected CLI and MCP names from the actual host `tools/list`, rather than constructing names. `plugins doctor` checks files and configuration; an MCP connection check verifies initialization/catalog, not model execution.

On Computer MCP 1.2.2, plugin activation/selection changes require idle Gateway client admission. Finish or safely pause clients before production installation changes. No host binary replacement or host release is required. Do not restart the active development control connection merely to test installation.

## Build

```sh
python3 -m unittest discover -s Tests -p 'test_*.py' -v
python3 Scripts/validate_native.py --executable /absolute/path/to/agent
python3 Scripts/build_package.py /new/output/directory
```

The builder produces `cursor.zip` and prints an ID/version/SHA-256 receipt. Identical source bytes produce identical archive bytes. It refuses to overwrite a different existing artifact. The archive contains the manifest, canonical CLI tree, adapters, Skills, examples, manuals and notices. It excludes tests, build scripts, local evidence, caches and credentials. Only executable entrypoints receive executable mode.

CI runs deterministic fixture tests and packaging; it does not install a vendor or invoke a model. Native validation checks the actual version/help and required flags only. ACP initialization without authentication is a separate non-model protocol probe for Cursor. Full authenticated prompt execution remains a separately authorized acceptance run because it can consume subscription/API usage and perform vendor actions.

## Isolated host interoperability

After packaging, validate the exact ZIP with an unchanged installed Computer MCP 1.2.2 binary:

```sh
python3 Scripts/validate_host.py \
  --host "/Applications/Computer MCP.app/Contents/Resources/computer-mcp" \
  --archive /output/PLUGIN.zip \
  --output /new/evidence/directory
```

Replace `PLUGIN.zip` with the package's actual archive name. This uses a temporary directory and the installed host's archive worker and standalone MCP entrypoint. It does not connect to the production App's control socket or database. Vendor tool execution is replaced with inert fixtures; the native version/help check is a separate command. A new evidence directory is required to avoid overwriting an earlier run.

A real ACP handshake can be checked independently, without authenticating, opening a conversation or invoking a model:

```sh
python3 Scripts/probe_acp.py --executable /absolute/path/to/agent --output /output/acp-probe.json
```

## Result interpretation

Fixture success proves adapter protocol/ownership behavior against the tested peer, not a real account or model. A native version/help check proves the installed command surface, not backend availability. An unchanged-host isolated catalog/call check proves interoperability for that tested configuration; it is not production installation or public release evidence. Keep these results separate in delivery receipts.
