# Contributing

Read the [architecture](Documentation/Architecture/README.md) and [interface contract](Documentation/Reference/Interface.md). Keep vendor-specific behavior in this repository and preserve the host manifest/CLITree/MCP boundaries.

Run `python3 -m unittest discover -s Tests -p 'test_*.py' -v` and package into a new output directory with `python3 Scripts/build_package.py`. When changing the native interface, inspect the matching real executable and run `Scripts/validate_native.py --executable PATH`. Never use authenticated model calls as ordinary unit tests.

Do not commit caches, local credentials, generated runtime state or `.agent` evidence. Publishing a repository or release is a separate explicit action.
