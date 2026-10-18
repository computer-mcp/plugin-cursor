# Versioning and Release

Release status: partly manual. CI builds and checks candidate archives on every
pull request and `master` push; tagging, acceptance and publication are manual
steps described in [Release](../Reference/Release.md).

This document owns the current version and release rules for plugin-cursor.

## Components and Version Authority

| Shipped component | Version meaning | Authoritative source | Derived fields | Update and read-only check |
| --- | --- | --- | --- | --- |
| `cursor.zip` plugin package | SemVer 2.0.0 package version | `version` in `computer-mcp-plugin.toml` | adapter `--version`, builder receipt, tag `vX.Y.Z`, `release-receipt.json`, catalog entry | Edit the manifest; `Tests/test_package.py` checks the packaged adapter's `--version` |

While the version is `0.x`, compatible fixes advance the patch number, and new
features or incompatible changes advance the minor number. Compatibility is
established by review and tests, not by comparing version numbers.

The archive contains the manifest, `cli-tree.json`, `bin/`, `skills/`, the README,
contribution guide, license, notices, `Documentation/` and `Examples/`. Any change
to those files ships only under a new version; a published version is never
rebuilt from different bytes. Changes to tests, scripts or workflows alone do not
change the archive and do not require a release.

## Dependencies and Verified Combinations

The package uses the Python standard library only and requires Python 3.13 or
newer on the host launch PATH. CI runs the tests on Python 3.13 and 3.14 and
checks that 3.11 and 3.12 are rejected before any vendor process starts.

`[compatibility]` in the manifest declares the minimum Computer MCP host and the
supported architectures. Raise `minimum_host` only when the package needs a newer
host contract, after validating against that host.

`cli-tree.json` pins the exact Cursor Agent version through its
`executable_checks`, which the host applies before every CLI and adapter call. A
different vendor version requires a reviewed update of the tree, verified with
`Scripts/validate_native.py` against the real executable.

## Derived Metadata and Drift Checks

`Scripts/build_package.py` verifies the plugin ID, parses the CLI tree, and
produces the same archive bytes from the same source. Its receipt prints the ID,
version and SHA-256. Agreement between the manifest version and the release tag
is checked manually when tagging.

## Candidate, Acceptance and Publication

The candidate is the CI artifact for a reviewed `master` commit. Acceptance
requires a byte-identical local rebuild, the native version and help check, the
ACP initialization probe with `Scripts/probe_acp.py`, and the isolated host check
with `Scripts/validate_host.py` against the selected Computer MCP release.
Authenticated model execution and production installation are separate checks
and are never implied by these results.

A signed annotated `vX.Y.Z` tag binds the accepted commit, and the GitHub
Release publishes that exact archive with `SHA256SUMS` and
`release-receipt.json`. Published tags and archives are immutable; a defect is
fixed in a new version. Publishing triggers the catalog notification.

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
| Status and interrupted-run recovery | Rerun the failed CI job or check; outputs go to new directories | Repository Actions |
| Acceptance and publication | Manual steps in [Release](../Reference/Release.md) | Signing key and release write access |
| Cleanup | Delete local output and evidence directories | Local checkout |

The builder refuses to overwrite a different archive, and `validate_host.py`
requires a new evidence directory, so earlier results stay intact. Keep local
evidence outside the repository.
