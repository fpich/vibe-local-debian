from __future__ import annotations

import argparse
from email.parser import BytesParser
import os
from pathlib import Path
import re
import runpy
import tempfile
import zipfile


def version_from_sha(sha: str) -> str:
    # PEP 440 normalizes numeric local versions by dropping leading zeros.
    return f"0.0.0+{int(sha) if sha.isdecimal() else sha}"


def stamp_version(version: str) -> None:
    targets = {
        "pyproject.toml": r"""(?m)^(\s*version\s*=\s*)['"][^'"]*['"]""",
        "vibe/__init__.py": r"""(?m)^(__version__\s*=\s*)['"][^'"]*['"]""",
    }
    updates: dict[Path, str] = {}
    for name, pattern in targets.items():
        path = Path(name)
        content, count = re.subn(
            pattern,
            lambda match: f'{match.group(1)}"{version}"',
            path.read_text(encoding="utf-8"),
        )
        if count != 1:
            raise SystemExit(
                f"ERROR: expected one version line in {path}, found {count}"
            )
        updates[path] = content
    for path, content in updates.items():
        path.write_text(content, encoding="utf-8")
        print(f"Updated {path} to {version}")


def verify_wheel(version: str) -> None:
    pattern = "*.whl"
    (wheel_path,) = Path("dist").glob(pattern)
    with zipfile.ZipFile(wheel_path) as wheel, tempfile.TemporaryDirectory() as tmp:
        metadata_path = next(
            path for path in wheel.namelist() if path.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(wheel.read(metadata_path))
        python_source = wheel.extract("vibe/__init__.py", tmp)
        python_version = runpy.run_path(python_source)["__version__"]
        if metadata["Version"] != version or python_version != version:
            raise SystemExit(
                f"Version mismatch: expected {version}, "
                f"metadata={metadata['Version']}, Python={python_version}"
            )
    print(f"Wheel versions match {version}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stamp", "verify"))

    args = parser.parse_args()
    version = version_from_sha(os.environ["SHORT_SHA"])
    match args.action:
        case "stamp":
            stamp_version(version)
        case "verify":
            verify_wheel(version)


if __name__ == "__main__":
    main()
