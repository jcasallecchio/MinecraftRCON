#!/usr/bin/env python3
"""Transactional file promotion and recovery for Bedrock server updates."""

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path, PurePosixPath


JOURNAL_DIR = ".update-rollback"
JOURNAL_NAME = "transaction.json"
MANAGED_FILES_NAME = ".bedrock-managed-files.json"
PERSISTENT_TOP_LEVEL = {
    "worlds",
    "structures",
    "server.properties",
    "permissions.json",
    "allowlist.json",
}


class TransactionError(RuntimeError):
    pass


def _safe_relative(value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise TransactionError(f"Unsafe update path: {value}")
    return Path(*relative.parts)


def _atomic_json_write(path: Path, payload: dict) -> None:
    temp_path = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _is_persistent_path(relative: Path) -> bool:
    return bool(relative.parts) and relative.parts[0] in PERSISTENT_TOP_LEVEL


def _read_managed_paths(server_dir: Path) -> set[Path]:
    path = server_dir / MANAGED_FILES_NAME
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload["files"]
        if not isinstance(values, list):
            raise ValueError("files must be an array")
        return {
            _safe_relative(value)
            for value in values
            if isinstance(value, str) and not _is_persistent_path(_safe_relative(value))
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise TransactionError(f"Installed file manifest is invalid: {error}") from error


def recover(server_dir: Path) -> bool:
    transaction_dir = server_dir / JOURNAL_DIR
    journal_path = transaction_dir / JOURNAL_NAME
    if not journal_path.exists():
        if transaction_dir.exists():
            # A crash before the journal is committed cannot have promoted files.
            shutil.rmtree(transaction_dir)
        return False

    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        entries = journal["entries"]
        if not isinstance(entries, list):
            raise TransactionError("Invalid update journal")

        for entry in reversed(entries):
            relative = _safe_relative(entry["path"])
            destination = server_dir / relative
            if entry.get("had_old"):
                backup = transaction_dir / "old" / relative
                if not backup.is_file():
                    raise TransactionError(f"Rollback file missing: {relative}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp_path = destination.with_name(destination.name + f".{uuid.uuid4().hex}.rollback")
                shutil.copy2(backup, temp_path)
                os.replace(temp_path, destination)
            else:
                destination.unlink(missing_ok=True)
                parent = destination.parent
                while parent != server_dir and parent.exists():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent

        shutil.rmtree(transaction_dir)
        print("Recovered the previous Bedrock server files after an interrupted update.")
        return True
    except Exception as error:
        raise TransactionError(f"Could not recover interrupted update: {error}") from error


def apply(staging_dir: Path, server_dir: Path) -> None:
    transaction_dir = server_dir / JOURNAL_DIR
    if transaction_dir.exists():
        recover(server_dir)

    staged_files = []
    for source in sorted(staging_dir.rglob("*")):
        if source.is_symlink():
            raise TransactionError(f"Symbolic links are not accepted in update archives: {source}")
        if source.is_file():
            relative = source.relative_to(staging_dir)
            if relative.is_absolute() or ".." in relative.parts:
                raise TransactionError(f"Unsafe staged path: {relative}")
            if relative == Path(MANAGED_FILES_NAME):
                raise TransactionError(f"Update archive uses a reserved path: {relative}")
            staged_files.append((source, relative))

    if not any(relative == Path("bedrock_server") for _, relative in staged_files):
        raise TransactionError("Staging directory does not contain bedrock_server")

    new_managed_paths = {
        relative for _, relative in staged_files if not _is_persistent_path(relative)
    }
    stale_paths = _read_managed_paths(server_dir) - new_managed_paths
    manifest_relative = Path(MANAGED_FILES_NAME)
    transaction_paths = {relative for _, relative in staged_files} | stale_paths | {manifest_relative}

    transaction_dir.mkdir(parents=True)
    entries = []
    try:
        for relative in sorted(transaction_paths):
            destination = server_dir / relative
            for parent in reversed(relative.parents):
                if parent == Path("."):
                    continue
                if (server_dir / parent).is_symlink():
                    raise TransactionError(f"Refusing to write through a symbolic-link directory: {parent}")
            if destination.is_symlink():
                raise TransactionError(f"Refusing to replace a symbolic link: {relative}")
            if destination.exists() and not destination.is_file():
                raise TransactionError(f"Update file conflicts with a directory: {relative}")
            had_old = destination.is_file()
            entries.append({"path": relative.as_posix(), "had_old": had_old})
            if had_old:
                backup = transaction_dir / "old" / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)

        _atomic_json_write(transaction_dir / JOURNAL_NAME, {"entries": entries})

        for source, relative in staged_files:
            destination = server_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_path = destination.with_name(destination.name + f".{uuid.uuid4().hex}.new")
            shutil.copy2(source, temp_path)
            os.replace(temp_path, destination)

        for relative in stale_paths:
            (server_dir / relative).unlink(missing_ok=True)

        _atomic_json_write(
            server_dir / MANAGED_FILES_NAME,
            {"files": sorted(path.as_posix() for path in new_managed_paths)},
        )

        if not (server_dir / "bedrock_server").is_file() or (server_dir / "bedrock_server").stat().st_size == 0:
            raise TransactionError("Promoted bedrock_server is missing or empty")
    except Exception as error:
        if (transaction_dir / JOURNAL_NAME).exists():
            try:
                recover(server_dir)
            except Exception as recovery_error:
                raise TransactionError(
                    f"Update failed ({error}) and rollback failed ({recovery_error})"
                ) from recovery_error
        else:
            shutil.rmtree(transaction_dir, ignore_errors=True)
        raise TransactionError(f"Update was not applied: {error}") from error


def commit(server_dir: Path) -> None:
    transaction_dir = server_dir / JOURNAL_DIR
    if not (transaction_dir / JOURNAL_NAME).is_file():
        raise TransactionError("No active update transaction to commit")
    shutil.rmtree(transaction_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("recover", "commit"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--server-dir", type=Path, required=True)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--server-dir", type=Path, required=True)
    apply_parser.add_argument("--staging-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "recover":
            recover(args.server_dir)
        elif args.command == "apply":
            apply(args.staging_dir, args.server_dir)
        else:
            commit(args.server_dir)
        return 0
    except TransactionError as error:
        print(f"[UPDATE] {error}", file=sys.stderr)
        return 20 if "rollback failed" in str(error).lower() or "could not recover" in str(error).lower() else 1


if __name__ == "__main__":
    raise SystemExit(main())
