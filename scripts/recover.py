#!/usr/bin/env python3
import argparse
import gzip
import io
import os
import re
import tarfile
from pathlib import Path

FIRST_PART = re.compile(r"^(?P<prefix>.+\.tar\.gz)\.part-aaaa$")


class PartReader(io.RawIOBase):
    def __init__(self, parts):
        self.parts = iter(parts)
        self.current = None

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            if self.current is None:
                try:
                    self.current = next(self.parts).open("rb")
                except StopIteration:
                    return 0
            data = self.current.read(len(buffer))
            if data:
                buffer[:len(data)] = data
                return len(data)
            self.current.close()
            self.current = None

    def close(self):
        if self.current is not None:
            self.current.close()
            self.current = None
        super().close()


def part_sets(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            match = FIRST_PART.match(name)
            if not match:
                continue
            prefix = Path(dirpath) / match.group("prefix")
            yield sorted(prefix.parent.glob(f"{prefix.name}.part-*"))


def selected_roots(root: Path, names: list[str]):
    if not names:
        return [root]

    roots = []
    seen = set()
    for name in names:
        modset = Path(name)
        if modset.is_absolute() or len(modset.parts) != 1:
            raise ValueError(f"modset must be a top-level directory name: {name}")

        path = root / name
        if not path.is_dir():
            raise FileNotFoundError(f"modset not found: {name}")
        if name not in seen:
            seen.add(name)
            roots.append(path)
    return roots


def safe_members(archive: tarfile.TarFile, root: Path):
    root = root.resolve()
    for member in archive:
        if not (member.isfile() or member.isdir()):
            raise ValueError(f"unsupported archive member: {member.name}")
        target = (root / member.name).resolve()
        if not (target == root or root in target.parents):
            raise ValueError(f"unsafe archive path: {member.name}")
        yield member


def recover(parts, root: Path, keep: bool, force: bool, dry_run: bool) -> bool:
    if not parts:
        return False
    if dry_run:
        print(parts[0])
        return False

    try:
        extracted = recover_tar(parts, root, force)
    except tarfile.TarError:
        extracted = recover_gzip(parts, root, force)

    if not keep:
        for part in parts:
            part.unlink()
    for target in extracted:
        print(target)
    return bool(extracted)


def recover_tar(parts, root: Path, force: bool):
    reader = io.BufferedReader(PartReader(parts))
    extracted = []
    try:
        with tarfile.open(fileobj=reader, mode="r|gz") as archive:
            for member in safe_members(archive, root):
                target = root / member.name
                if target.exists() and not force:
                    raise FileExistsError(f"{target} exists; use --force to overwrite")
                archive.extract(member, path=root)
                extracted.append(target)
    finally:
        reader.close()
    return extracted


def recover_gzip(parts, root: Path, force: bool):
    prefix = parts[0].name.removesuffix(".part-aaaa")
    target = parts[0].with_name(prefix.removesuffix(".tar.gz"))
    if target.exists() and not force:
        raise FileExistsError(f"{target} exists; use --force to overwrite")

    target.parent.mkdir(parents=True, exist_ok=True)
    reader = io.BufferedReader(PartReader(parts))
    try:
        with gzip.GzipFile(fileobj=reader) as source:
            with target.open("wb") as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    destination.write(chunk)
    finally:
        reader.close()
    return [target]


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover .tar.gz.part-* files produced by scripts/compress.py.")
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument(
        "--modset",
        action="append",
        metavar="NAME",
        help="recover only a named top-level modset directory; repeat to recover more than one",
    )
    parser.add_argument("--keep-parts", action="store_true", help="keep part files after recovery")
    parser.add_argument("--force", action="store_true", help="overwrite existing recovered files")
    parser.add_argument("--dry-run", action="store_true", help="list first parts that would be recovered")
    args = parser.parse_args()

    root = args.root.resolve()
    changed = False
    try:
        roots = selected_roots(root, args.modset)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))

    for search_root in roots:
        for parts in part_sets(search_root):
            changed = recover(parts, root, args.keep_parts, args.force, args.dry_run) or changed
    if not changed and not args.dry_run:
        print("no split files to recover")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
