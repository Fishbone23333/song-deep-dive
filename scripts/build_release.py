#!/usr/bin/env python3
"""Build an allowlisted Skill ZIP without personal data or development artifacts."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent.parent


def release_files(root: Path) -> list[Path]:
    files = [root / "SKILL.md", root / "README.md", root / "scripts" / "memory.py"]
    files.extend(sorted((root / "references").glob("*.md")))
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or unsafe release source: {path.name}")
    return files


def build(root: Path, output: Path) -> Path:
    files = release_files(root)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            info = ZipInfo((Path("song-deep-dive") / path.relative_to(root)).as_posix(), date_time=(2026, 10, 25, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "song-deep-dive.zip")
    args = parser.parse_args()
    print(build(ROOT, args.output))


if __name__ == "__main__":
    main()
