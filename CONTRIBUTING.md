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

Manifest caller requirements must agree with the actual adapter catalog; run
`python3 -m unittest discover -s tests -p 'test_declarations.py' -v` and
`python3 -m unittest discover -s tests -p 'test_host_source.py' -v` for focused checks.
The exact-source consumer and separate archive identity check are documented in the
[installation guide](docs/Reference/Installation.md). Use only clean reviewed full-SHA
pairs; never direct plugin commands to an implicit App control socket. The deterministic
fixture preserves native permission choices and does not establish authentication or
real-model sandbox suitability. The required CI job runs the registered Cursor suite
at the candidate revision and fetches [the pinned Host SHA](.github/computer-mcp-host.sha)
from the public Host repository.
