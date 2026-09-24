"""Build a deterministic Cursor Computer MCP plugin archive."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tomllib
import zipfile

INCLUDE = (
    "computer-mcp-plugin.toml",
    "cli-tree.json",
    "bin",
    "skills",
    "README.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "Documentation",
    "Examples",
)


def package_bytes(root: Path):
    pending = [root / name for name in INCLUDE]
    contents = {}
    count = 0
    total = 0
    while pending:
        path = pending.pop()
        relative = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts) or path.suffix in (".pyc", ".pyo"):
            continue
        count += 1
        if count > 512:
            raise ValueError("Package contains too many entries")
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            with os.scandir(path) as children:
                pending.extend(Path(child.path) for child in children)
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(
                "Package source must contain only regular files and directories"
            )
        data = path.read_bytes()
        if len(data) > 1_048_576:
            raise ValueError("Package source file exceeds 1 MiB")
        total += len(data)
        if total > 8_388_608:
            raise ValueError("Package source exceeds 8 MiB")
        contents[path.relative_to(root).as_posix()] = data

    manifest = tomllib.loads(contents["computer-mcp-plugin.toml"].decode())
    if manifest["id"] != "cursor":
        raise ValueError("Unexpected plugin identity")
    json.loads(contents["cli-tree.json"])

    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        for name, data in sorted(contents.items()):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            permissions = 0o755 if name.startswith("bin/") and data.startswith(b"#!") else 0o644
            entry.external_attr = (stat.S_IFREG | permissions) << 16
            archive.writestr(entry, data)
    return output.getvalue(), manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    data, manifest = package_bytes(root)

    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / "cursor.zip"
    if artifact.exists() or artifact.is_symlink():
        if (
            artifact.is_symlink()
            or not artifact.is_file()
            or artifact.read_bytes() != data
        ):
            raise ValueError("Output differs; use a new directory")
    else:
        with artifact.open("xb") as destination:
            destination.write(data)

    print(
        json.dumps(
            {
                "id": manifest["id"],
                "version": manifest["version"],
                "archive": str(artifact),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
