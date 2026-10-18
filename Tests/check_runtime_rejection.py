"""Run under an unsupported interpreter to verify early, side-effect-free refusal."""
from pathlib import Path
import subprocess
import sys
import tempfile


def check():
    if sys.version_info >= (3, 13):
        raise AssertionError('This check must run on Python older than 3.13')
    entrypoints = list((Path(__file__).resolve().parent.parent / 'bin').glob('*-mcp-adapter'))
    assert len(entrypoints) == 1
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / 'vendor-started'
        vendor = Path(directory) / 'vendor'
        vendor.write_text('#!/bin/sh\n: > "' + str(marker) + '"\n')
        vendor.chmod(0o755)
        result = subprocess.run([sys.executable, str(entrypoints[0]), '--executable', str(vendor)],
                                input=b'', capture_output=True, timeout=5, cwd=directory)
        assert result.returncode != 0
        assert b'Python 3.13+' in result.stderr, result.stderr
        assert not result.stdout
        assert not marker.exists()
    print('Unsupported Python refused before native execution')


if __name__ == '__main__':
    check()
