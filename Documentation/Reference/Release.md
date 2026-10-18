# Release

This guide covers publishing an accepted package and notifying the official
plugin catalog. [Versioning and Release](../Architecture/VersioningAndRelease.md)
owns the version, acceptance and immutability rules.

## Publish

1. Confirm that `version` in `computer-mcp-plugin.toml` has not been released
   and that the reviewed `master` commit has a successful CI run.
2. Download that run's `cursor-plugin-<commit>-3.13` artifact. Rebuild the same
   commit with `python3 Scripts/build_package.py <new directory>` and confirm the
   two `cursor.zip` files are byte-identical.
3. Run the native, ACP initialization and isolated host checks in
   [Installation](Installation.md#isolated-host-interoperability) against that
   exact archive.
4. Create a signed annotated tag `vX.Y.Z` on the accepted commit and push it.
5. Create the GitHub Release for the tag with `cursor.zip`, `SHA256SUMS` and
   `release-receipt.json`, then publish it.

`release-receipt.json` is written by the publisher; no script generates it. It
records the plugin ID and version, tag, source commit, archive name, size and
SHA-256, the source CI run and artifact digest, the declared compatibility, and
the validation results with their limits. `SHA256SUMS` covers the archive and the
receipt.

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
release-event workflows. Automation that publishes that way calls the workflow
as a dependent of the job that makes the release public:

```yaml
notify-catalog:
  needs: publish
  uses: ./.github/workflows/notify-catalog.yml
  secrets:
    CATALOG_APP_PRIVATE_KEY: ${{ secrets.CATALOG_APP_PRIVATE_KEY }}
```

## Retry

For an operator-driven publication or a missed or failed notification, dispatch:

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
