#!/usr/bin/env python3
import argparse
import os
import sys
import tarfile
from pathlib import Path

LIMIT = 50_000_000
PART_CHARS = "abcdefghijklmnopqrstuvwxyz"


class SplitWriter:
    def __init__(self, prefix: Path, part_size: int):
        self.prefix = prefix
        self.part_size = part_size
        self.part_index = 0
        self.part = None
        self.used = 0
        self.parts = []

    def write(self, data: bytes) -> int:
        offset = 0
        while offset < len(data):
            if self.part is None or self.used == self.part_size:
                self._next_part()
            size = min(len(data) - offset, self.part_size - self.used)
            self.part.write(data[offset:offset + size])
            self.used += size
            offset += size
        return len(data)

    def close(self):
        if self.part is not None:
            self.part.close()
            self.part = None

    def _next_part(self):
        if self.part is not None:
            self.part.close()
        name = self.prefix.with_name(f"{self.prefix.name}.part-{suffix(self.part_index)}")
        self.part_index += 1
        self.parts.append(name)
        self.part = name.open("wb")
        self.used = 0


def suffix(index: int) -> str:
    if index >= len(PART_CHARS) ** 4:
        raise ValueError("too many parts for 4-letter suffixes")
    chars = []
    for power in (3, 2, 1, 0):
        value = len(PART_CHARS) ** power
        chars.append(PART_CHARS[index // value])
        index %= value
    return "".join(chars)


def candidates(root: Path, limit: int):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = Path(dirpath) / name
            if ".tar.gz.part-" in name:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > limit:
                yield path


def compress(path: Path, root: Path, limit: int, keep: bool, dry_run: bool) -> bool:
    prefix = path.with_name(f"{path.name}.tar.gz")
    if any(prefix.parent.glob(f"{prefix.name}.part-*")):
        print(f"skip existing parts: {path}", file=sys.stderr)
        return False

    if dry_run:
        print(path)
        return False

    writer = SplitWriter(prefix, limit)
    try:
        with tarfile.open(fileobj=writer, mode="w|gz") as archive:
            archive.add(path, arcname=path.relative_to(root))
    except Exception:
        writer.close()
        for part in writer.parts:
            part.unlink(missing_ok=True)
        raise
    writer.close()

    if not keep:
        path.unlink()
    print(f"{path} -> {len(writer.parts)} part(s)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Split files larger than 50MB into .tar.gz.part-* files.")
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--limit", type=int, default=LIMIT, help="byte limit for source files and output parts")
    parser.add_argument("--keep", action="store_true", help="keep original files after writing parts")
    parser.add_argument("--dry-run", action="store_true", help="list files that would be split")
    args = parser.parse_args()

    root = args.root.resolve()
    changed = False
    for path in candidates(root, args.limit):
        changed = compress(path, root, args.limit, args.keep, args.dry_run) or changed
    if not changed and not args.dry_run:
        print("no files over limit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
