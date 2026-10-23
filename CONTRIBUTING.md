# Contributing

Read the [architecture](docs/Architecture/README.md) and [interface contract](docs/Reference/Interface.md). Keep vendor-specific behavior in this repository and preserve the host manifest/CLITree/MCP boundaries.

CI runs these checks on Python 3.13 and 3.14; run them before opening a pull request:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/build_package.py /new/output/directory
```

CI also runs `python3 tests/check_runtime_rejection.py` on Python 3.11 and 3.12 to confirm that unsupported interpreters are refused. When changing the native interface, inspect the matching real executable and run `scripts/validate_native.py --executable PATH`. Never use authenticated model calls as ordinary unit tests.

Do not commit caches, local credentials or generated runtime state. Publishing a repository or release is a separate explicit action.

Contributions are licensed under this repository's [LICENSE](LICENSE),
FSL-1.1-ALv2.
