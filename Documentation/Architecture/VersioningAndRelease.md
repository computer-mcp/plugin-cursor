# Versioning and Release

CI builds and checks candidate archives on every pull request and `master`
push. `release.yml` verifies and publishes accepted archives after manual
acceptance, as described in [Release](../Reference/Release.md).

This document owns plugin-cursor's version sources and acceptance checks. The
organization's [VERSIONING.md](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md)
owns shared versioning, plugin compatibility, tags, release contents and
recovery rules.

## Components and Version Authority

| Shipped component | Version meaning | Authoritative source | Derived fields | Update and read-only check |
| --- | --- | --- | --- | --- |
| `cursor.zip` plugin package | Package version under the shared versioning rules | `version` in `computer-mcp-plugin.toml` | adapter `--version`, builder receipt, release tag, `release-receipt.json`, catalog entry | Edit the manifest; `Tests/test_package.py` checks the packaged adapter's `--version` |

The archive contains the manifest, `cli-tree.json`, `bin/`, `skills/`, the README,
contribution guide, license, notices, `Documentation/` and `Examples/`. Changes
to these packaged files change the release bytes. Tests, scripts and workflows
are outside the archive.

## Dependencies and Verified Combinations

The package uses the Python standard library only and requires Python 3.13 or
newer on the host launch PATH. CI runs the tests on Python 3.13 and 3.14 and
checks that 3.11 and 3.12 are rejected before any vendor process starts.

`bin/plugin_runtime.py` is copied from the organization's canonical runtime.
The `runtime` job in `ci.yml` checks it against the pinned shared workflow's
digest. Adapter and probe callers extract the native assertion from the CLI
tree with `expected_version` before calling `verify_version`.

`computer-mcp-plugin.toml` declares the plugin API and host and architecture
compatibility. Validate host-specific requirements against the selected host
before changing the host bounds.

`cli-tree.json` pins the exact Cursor Agent version through its
`executable_checks`, which the host applies before every CLI and adapter call. A
different vendor version requires a reviewed update of the tree, verified with
`Scripts/validate_native.py` against the real executable.

## Derived Metadata and Drift Checks

`Scripts/build_package.py` verifies the plugin ID, parses the CLI tree, and
produces the same archive bytes from the same source. Its receipt prints the ID,
version and SHA-256. `release.yml` calls the pinned organization release workflow
with `python3 Scripts/build_package.py` and selects the exact
`cursor-plugin-${commit}-3.13` CI artifact. The shared workflow checks the source
and manifest, rebuilds the archive and compares its bytes with that artifact.

## Candidate, Acceptance and Publication

The candidate is the Python 3.13 CI artifact for a reviewed `master` commit.
Run `release.yml` with `publish: false` first. Manual acceptance requires the
native version and help check with `Scripts/validate_native.py`, the ACP
initialization probe with `Scripts/probe_acp.py`, and the isolated host check
with `Scripts/validate_host.py` against the selected Computer MCP release and
the exact archive verified by the dry run.
Authenticated model execution and production installation are separate checks
and are never implied by these results.

Record the manual results and their limits in the draft Release notes. Dispatch
`release.yml` with the accepted version tag and `publish: true` to publish.
Only a reported publication enables its dependent catalog notification job;
only that job receives the catalog secret.

## Evidence Reuse and Invalidation

The CI artifact name binds the source commit and Python version, and the release
receipt binds the commit, CI run, artifact digest and archive SHA-256. An archive
whose digest matches the accepted one keeps its acceptance. Any change to a
packaged file produces a new archive that needs the affected checks again.

## Entry Points and Artifact Retention

| Operation | Existing command or explicit manual procedure | Required access |
| --- | --- | --- |
| Version update and check | Edit `computer-mcp-plugin.toml`; `python3 -m unittest discover -s Tests -p 'test_*.py'` | Local checkout |
| Candidate validation and build | `ci.yml`; locally `python3 Scripts/build_package.py <new directory>` | CI or local checkout |
| Status and interrupted-run recovery | Inspect CI or `release.yml`; follow [Release](../Reference/Release.md#retry) | Repository Actions |
| Acceptance and publication | Manual checks and `release.yml` in [Release](../Reference/Release.md) | Signing key and release write access |
| Cleanup | Delete local output and evidence directories | Local checkout |

The builder refuses to overwrite a different archive, and `validate_host.py`
requires a new evidence directory. Keep local build and evidence outputs under
ignored `dist/` paths and remove them after use.
