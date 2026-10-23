# Release

Release status: [CI](https://github.com/computer-mcp/plugin-cursor/blob/master/.github/workflows/ci.yml)
builds candidate archives on pull requests, `master` pushes and manual runs.
[`release.yml`](https://github.com/computer-mcp/plugin-cursor/blob/master/.github/workflows/release.yml)
implements dry runs and publication; native and host acceptance are manual.

The organization [VERSIONING](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md)
owns version rules, including tags, version choice and the changelog. This
reference records this repository's version sources, compatibility, release
procedure and checks. The shared
[release workflow guide](https://github.com/computer-mcp/github-workflows/blob/master/docs/plugin-release.md)
describes workflow verification and recovery.

## Components and Version Sources

| Shipped component | Version meaning | Version source | Mirrors and derived fields | Update and read-only check |
| --- | --- | --- | --- | --- |
| `cursor.zip` plugin package | Package version | `version` in [`computer-mcp-plugin.toml`](../../computer-mcp-plugin.toml) | adapter `--version`, builder receipt, release tag, `release-receipt.json`, catalog entry | Edit the manifest; `tests/test_package.py` checks the packaged adapter's `--version` |

The archive contains the manifest, `cli-tree.json`, `bin/`, `skills/`, the README,
contribution guide, license, notices, `docs/`, `Examples/`, and the README images
`.github/assets/logo/logo-light.png` and `.github/assets/logo/logo-dark.png`.
Tests, build scripts and workflows are excluded from the archive.

## Compatibility Surface

The package contributes a file-backed CLI tree, stdio MCP adapter and Skills.
[Interface](Interface.md) owns the CLI argv and output mapping, MCP tools and
resources, session and permission semantics, retention, cancellation and errors.
The manifest owns `plugin_api` and the minimum host and architecture declarations
in `[compatibility]`. Validate changes to those bounds against the selected host.

## Dependencies and Verified Combinations

The package uses the Python standard library only and requires Python 3.13 or
newer on the host launch PATH. CI runs the tests on Python 3.13 and 3.14 and
checks that 3.11 and 3.12 are rejected before any vendor process starts.

`cli-tree.json` pins the exact Cursor Agent version through its
`executable_checks`, applied before projected CLI calls and new ACP sessions.
A different vendor version requires a reviewed tree update verified with
`scripts/validate_native.py` against the real executable. ACP initialization
uses the separate `scripts/probe_acp.py` check. Native version/help, fixture
protocol, selected-host interoperability and authenticated execution are
separate evidence classes; see [Installation](Installation.md).

## Derived Metadata and Drift Checks

`scripts/build_package.py` verifies the plugin ID, parses the CLI tree, and
produces the same archive bytes from the same source. Its builder receipt prints
the ID, version and SHA-256. The release caller passes this builder to the shared
release workflow.

`bin/plugin_runtime.py` is copied from the organization's canonical runtime.
The `runtime` job in `ci.yml` verifies its digest against the pinned
`plugin-runtime.yml`; runtime updates and that workflow pin move together.
Adapter and probe callers extract the native assertion from the CLI tree with
`expected_version` before calling `verify_version`.

## Candidate, Acceptance and Publication

Publication depends on the repository's GitHub release immutability setting.
The shared workflow checks that setting before writing a Release.

### Publish

1. Confirm that `version` in `computer-mcp-plugin.toml` has not been released
   and that the reviewed `master` commit has successful `ci.yml` from a `push`.
   Its exact archive artifact name is `cursor-plugin-<full-commit-sha>-3.13`.
2. Dispatch `.github/workflows/release.yml` with `ref` set to that full commit
   SHA and `publish: false` (the default). The pinned organization workflow
   runs `python3 scripts/build_package.py` with an output-directory argument,
   verifies the CI source and artifact digest, and requires the rebuilt
   `cursor.zip` to match the CI archive byte for byte.
3. Inspect the `plugin-release-<run-id>-<attempt>` Actions artifact. Its
   `assets/` directory contains `cursor.zip`, the generated
   `release-receipt.json` and `SHA256SUMS`. An untagged dry run reports the
   signed annotated tag still needed for publication.
4. Run the native version/help, ACP initialization and isolated host checks in
   [Installation](Installation.md#isolated-host-interoperability) against that
   exact archive. Record the manual acceptance results and their limits in the
   draft Release notes. Create and push the version tag that
   [VERSIONING](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md) requires on the accepted commit, and target the draft
   Release at that full commit SHA.
5. Dispatch `release.yml` with `ref` set to that version tag and `publish: true`.
   The workflow verifies the tag signature and manifest version, repeats the
   source and archive checks, completes and verifies the draft assets, and
   publishes. Its dependent notifier runs only when `publish` is true and the
   shared workflow reports `published: true`.

The shared workflow generates the receipt and checksums; CI's
`package-receipt.json` remains builder metadata in the source CI artifact.

### Catalog notification

`notify-catalog.yml` runs when a release is published, edited, released,
unpublished or deleted, and on manual dispatch. It asks the website to reconcile
the complete catalog. The website verifies the actual GitHub releases rather
than the event payload, keeps verified history, and applies its own withdrawal
policy; an event never withdraws a release by itself.

The workflow authenticates as the receiver-scoped catalog GitHub App through
the `CATALOG_APP_CLIENT_ID` variable and the `CATALOG_APP_PRIVATE_KEY` secret.
The App needs Actions write access to `computer-mcp/computer-mcp.github.io` only.
The job checks this repository's immutable ID, does not check out package code,
and grants its own token no repository permissions. Missing or rejected
authority fails the run visibly.

The website's notification action is pinned to a reviewed full commit. Publish
that website commit first, then update the pin here when adopting a change to
the notification contract.

A release published with a repository `GITHUB_TOKEN` does not trigger
release-event workflows. `release.yml` calls `notify-catalog.yml` as a dependent
job after confirmed publication. Only the notifier receives
`CATALOG_APP_PRIVATE_KEY`; the reusable release workflow receives no catalog
secret. Dry runs do not notify the catalog.

## Evidence Reuse and Invalidation

The CI artifact name identifies the source commit and Python version. The release
workflow verifies CI provenance and artifact digests; `release-receipt.json`
records the commit, CI run and attempt, artifact digest and archive SHA-256.

An archive with the accepted digest keeps its archive acceptance for the tested
combination. Reuse of manual results is reviewed against the native dependency,
selected host, check definitions and relevant environment recorded with them.
Changes to packaged files produce a new archive and require the affected checks
again. A check-only change can reuse unchanged archive bytes with fresh affected
checks. Source tests do not replace installation, native or authenticated
execution evidence. Keep failed-check output and result limits with the manual
acceptance record.

## Entry Points and Artifact Retention

| Operation | Existing command or explicit manual procedure | Required access |
| --- | --- | --- |
| Version update and check | Edit `computer-mcp-plugin.toml`; `python3 -m unittest discover -s tests -p 'test_*.py'` | Local checkout |
| Candidate validation and build | `ci.yml`; locally `python3 scripts/build_package.py dist` | CI or local checkout |
| Native acceptance | `python3 scripts/validate_native.py --executable <agent>`; `python3 scripts/probe_acp.py --executable <agent> --output <probe-receipt.json>` | User-installed native executable |
| Exact archive host acceptance | `python3 scripts/validate_host.py --host <computer-mcp> --expected-host-version X.Y.Z --archive dist/cursor.zip --output <new-evidence-directory>`; see [Installation](Installation.md#isolated-host-interoperability) | Selected host binary and candidate archive |
| Acceptance and publication | Manual checks above; dispatch `release.yml`, dry run first | Repository Actions; publication also needs a signing key and release write access |
| Status and interrupted-run recovery | Inspect CI or `release.yml`; follow [Retry](#retry) | Repository Actions |
| Cleanup | Delete obsolete output and evidence under ignored `dist/`, and `package-receipt.json` | Local checkout |

The builder refuses to overwrite a different archive, and `validate_host.py`
requires a new evidence directory. Remove obsolete build output before rebuilding
changed source. Keep local output and evidence under ignored `dist/`; remove
them after use unless an acceptance record requires retention. CI sets no
per-artifact retention override.

### Retry

For a failed publication, use **Re-run failed jobs**. Recovery preserves the
receipt's frozen CI provenance and retains matching draft assets. Follow the
organization's [release recovery guide](https://github.com/computer-mcp/github-workflows/blob/master/docs/plugin-release.md#run-and-recover)
for conflicts or unavailable source artifacts. Published releases are verified
without changing their assets.

For a missed or failed notification, rerun only the notifier or dispatch:

```sh
gh workflow run notify-catalog.yml --repo computer-mcp/plugin-cursor --ref master
```

A successful dispatch only proves the request was accepted. Follow the run's
`run_url` output to the website run, confirm it succeeded, and confirm the public
index lists the expected release. Retrying never requires changing or
republishing the release: reconciliation is idempotent, and the website's
hourly schedule also repairs missed notifications.

The website's
[catalog publication and notification contract](https://github.com/computer-mcp/computer-mcp.github.io/blob/master/docs/plugin-catalog.md)
covers provenance, credentials, retry bounds and deployment.
