# Contributing

Read the [architecture](Documentation/Architecture/README.md) and [interface contract](Documentation/Reference/Interface.md). Keep vendor-specific behavior in this repository and preserve the host manifest/CLITree/MCP boundaries.

Run `python3 -m unittest discover -s Tests -p 'test_*.py' -v` and package into a new output directory with `python3 Scripts/build_package.py`. When changing the native interface, inspect the matching real executable and run `Scripts/validate_native.py --executable PATH`. Never use authenticated model calls as ordinary unit tests.

Do not commit caches, local credentials, generated runtime state or `.agent` evidence. Publishing a repository or release is a separate explicit action.

## Repository closeout

Use the default branch for daily integration and a task branch or isolated
worktree for changes. Before cleanup, inspect local changes, worktree owners,
open pull requests and the accepted source revision. Preserve unrelated source,
credentials, runtime state and non-generated ignored files; never reset, clean
or stash another task's work to make a checkout appear clean.

After delivery, fast-forward only a clean integration checkout. Retire a task
branch only when its tip is in the accepted default branch or its exact head
matches a merged pull request whose merge is reachable there. Preserve unique
work with a documented reconciliation and independently verified recovery
bundle before retiring its directory. Remove owned worktrees through Git, or
through the managing application's archive operation for managed worktrees.

Build caches in the daily checkout may remain useful. Remove inactive duplicate
task caches, package staging and disposable test outputs after checking their
owner and running references. Preserve source inputs, immutable release
artifacts, necessary failure/acceptance evidence and required rollback state.
Keep local progress and recovery inventories under ignored `.agent/`; current
product behavior must remain understandable from committed documentation.

A merged source change, a validated package and a published release have
different identities. Record the exact source and artifact/check evidence at
handoff. Documentation or repository cleanup alone does not require a product
release; published tags and assets remain immutable. Active dependency-update
pull requests are reviewed maintenance work, not disposable cleanup residue.
