# Release

This guide covers `release.yml` and notification of the official plugin catalog.
[Versioning and Release](../Architecture/VersioningAndRelease.md) owns this
repository's version sources and acceptance checks. The organization's
[VERSIONING.md](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md)
owns shared versioning, release contents, immutability and recovery rules.

The repository owner must enable GitHub release immutability before the first
release. The release workflow refuses publication unless it can verify that
setting; enabling it is a prerequisite to publishing.

## Publish

1. Confirm that `version` in `computer-mcp-plugin.toml` has not been released
   and that the reviewed `master` commit has successful `ci.yml` from a `push`.
   Its exact archive artifact name is `cursor-plugin-<full-commit-sha>-3.13`.
2. Dispatch `.github/workflows/release.yml` with `ref` set to that full commit
   SHA and `publish: false` (the default). The pinned organization workflow
   runs `python3 Scripts/build_package.py` with an output-directory argument,
   verifies the CI source and artifact digest, and requires the rebuilt
   `cursor.zip` to match the CI archive byte for byte.
3. Inspect the `plugin-release-<run-id>-<attempt>` Actions artifact. Its
   `assets/` directory contains `cursor.zip`, the generated
   `release-receipt.json` and `SHA256SUMS`. An untagged dry run reports the
   signed annotated tag still needed for publication.
4. Run the native version/help, ACP initialization and isolated host checks in
   [Installation](Installation.md#isolated-host-interoperability) against that
   exact archive. Record the manual acceptance results and their limits in the
   draft Release notes. Create and push the signed annotated `vX.Y.Z` tag on
   the accepted commit, and target the draft Release at that full commit SHA.
5. Dispatch `release.yml` with `ref` set to that version tag and `publish: true`.
   The workflow verifies the tag signature and manifest version, repeats the
   source and archive checks, completes and verifies the draft assets, and
   publishes. Its dependent notifier runs only when `publish` is true and the
   shared workflow reports `published: true`.

The shared workflow generates the deterministic receipt and checksums under the
organization's [release contents contract](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md#plugin-release-contents).
Manual acceptance evidence belongs in the Release notes.

## Catalog notification

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

## Retry

For a failed publication, use **Re-run failed jobs**. Recovery preserves the
receipt's frozen CI provenance and retains matching draft assets. Follow the
organization's [release recovery guide](https://github.com/computer-mcp/.github/blob/master/Documentation/Reference/PluginRelease.md#run-and-recover)
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
