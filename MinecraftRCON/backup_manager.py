#!/usr/bin/env python3
"""Scheduled world snapshots and guarded restore operations."""

import json
import io
import os
import shutil
import tarfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


BACKUP_ITEMS = (
    "worlds",
    "structures",
    "server.properties",
    "permissions.json",
    "allowlist.json",
    "behavior_packs",
    "resource_packs",
)
SCHEDULED_PREFIX = "scheduled-"
RESTORE_JOURNAL_DIR = ".restore-rollback"
RESTORE_JOURNAL_NAME = "transaction.json"
MAINTENANCE_FILE = ".maintenance"


class BackupError(RuntimeError):
    pass


def _archive_manifest(server_dir: Path) -> dict:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "items": [name for name in BACKUP_ITEMS if (server_dir / name).exists()],
    }


def _write_archive(server_dir: Path, backup_dir: Path, prefix: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    final_path = backup_dir / f"{prefix}{timestamp}-{uuid.uuid4().hex[:8]}.tar.gz"
    temp_path = final_path.with_suffix(final_path.suffix + ".tmp")
    manifest = _archive_manifest(server_dir)
    try:
        with tarfile.open(temp_path, "w:gz") as archive:
            for name in manifest["items"]:
                archive.add(server_dir / name, arcname=name, recursive=True)
            info = tarfile.TarInfo("backup_manifest.json")
            payload = json.dumps(manifest, indent=2).encode("utf-8")
            info.size = len(payload)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(payload))
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, final_path)
        return final_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def create_scheduled_backup(
    server_dir: Path,
    backup_dir: Path,
    keep_count: int,
    hold_saving,
    resume_saving,
) -> Path:
    keep_count = max(1, min(int(keep_count), 90))
    if not (server_dir / "worlds").is_dir():
        raise BackupError("Worlds folder is missing; refusing to create a world backup")
    held = False
    snapshot_dir = backup_dir / f".snapshot-{uuid.uuid4().hex}"
    try:
        if not hold_saving():
            raise BackupError("Could not place Bedrock in save-hold mode")
        held = True
        time.sleep(1)
        snapshot_dir.mkdir(parents=True)
        for name in BACKUP_ITEMS:
            source = server_dir / name
            if not source.exists():
                continue
            destination = snapshot_dir / name
            if source.is_dir():
                shutil.copytree(source, destination, symlinks=False)
            else:
                shutil.copy2(source, destination)
    except Exception:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise
    finally:
        try:
            if held and not resume_saving():
                raise BackupError("Backup snapshot was copied but Bedrock save-resume could not be sent")
        except Exception:
            shutil.rmtree(snapshot_dir, ignore_errors=True)
            raise

    try:
        path = _write_archive(snapshot_dir, backup_dir, SCHEDULED_PREFIX)
    finally:
        shutil.rmtree(snapshot_dir, ignore_errors=True)

    backups = sorted(
        backup_dir.glob(f"{SCHEDULED_PREFIX}*.tar.gz"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[max(1, keep_count) :]:
        old_backup.unlink(missing_ok=True)
    return path


def list_scheduled_backups(backup_dir: Path) -> list[dict]:
    results = []
    for path in sorted(backup_dir.glob(f"{SCHEDULED_PREFIX}*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
        results.append({
            "id": path.name,
            "size_bytes": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    return results


def _safe_member_path(name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise BackupError(f"Unsafe path in backup: {name}")
    if relative.parts[0] not in (*BACKUP_ITEMS, "backup_manifest.json"):
        raise BackupError(f"Unexpected item in backup: {name}")
    return Path(*relative.parts)


def _extract_validated(archive_path: Path, staging_dir: Path) -> set[str]:
    allowed_items = set(BACKUP_ITEMS)
    items: set[str] = set()
    staging_dir.mkdir(parents=True)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                relative = _safe_member_path(member.name)
                if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                    raise BackupError(f"Unsupported archive entry: {member.name}")
                if relative.parts[0] in allowed_items:
                    items.add(relative.parts[0])
                target = staging_dir / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise BackupError(f"Could not read archive entry: {member.name}")
                with source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                os.chmod(target, member.mode & 0o777)

        manifest_path = staging_dir / "backup_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_items = manifest.get("items")
        if not isinstance(manifest_items, list) or not set(manifest_items) <= allowed_items:
            raise BackupError("Backup manifest is invalid")
        if set(manifest_items) != items:
            raise BackupError("Backup manifest does not match the archive contents")
        if "worlds" not in manifest_items or not (staging_dir / "worlds").is_dir():
            raise BackupError("Backup does not contain a worlds folder")
        return set(manifest_items)
    except (OSError, tarfile.TarError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise BackupError(f"Invalid or incomplete backup: {error}") from error


def recover_restore(server_dir: Path) -> bool:
    transaction_dir = server_dir / RESTORE_JOURNAL_DIR
    journal_path = transaction_dir / RESTORE_JOURNAL_NAME
    if not journal_path.exists():
        if transaction_dir.exists():
            shutil.rmtree(transaction_dir)
        (server_dir / MAINTENANCE_FILE).unlink(missing_ok=True)
        return False

    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        entries = journal["entries"]
        if not isinstance(entries, list):
            raise BackupError("Invalid restore journal")
        for entry in reversed(entries):
            name = entry["name"]
            if name not in BACKUP_ITEMS:
                raise BackupError(f"Invalid restore target: {name}")
            target = server_dir / name
            old_path = transaction_dir / "old" / name
            if entry.get("had_old"):
                if old_path.exists():
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(old_path, target)
                elif not target.exists():
                    raise BackupError(f"Previous restore item is missing: {name}")
            elif target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
        shutil.rmtree(transaction_dir)
        (server_dir / MAINTENANCE_FILE).unlink(missing_ok=True)
        return True
    except Exception as error:
        raise BackupError(f"Could not recover interrupted restore: {error}") from error


def restore_backup(backup_id: str, server_dir: Path, backup_dir: Path) -> Path:
    if Path(backup_id).name != backup_id or not backup_id.startswith(SCHEDULED_PREFIX) or not backup_id.endswith(".tar.gz"):
        raise BackupError("Invalid scheduled backup ID")
    archive_path = backup_dir / backup_id
    if archive_path.is_symlink() or not archive_path.is_file():
        raise BackupError("Scheduled backup was not found")
    if (server_dir / MAINTENANCE_FILE).is_file() is False:
        raise BackupError("Restore is allowed only while Bedrock maintenance mode is active")
    if (server_dir / RESTORE_JOURNAL_DIR).exists():
        recover_restore(server_dir)

    rollback_path = _write_archive(server_dir, backup_dir, "pre-restore-")
    rollback_archives = sorted(
        backup_dir.glob("pre-restore-*.tar.gz"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in rollback_archives[3:]:
        old_backup.unlink(missing_ok=True)
    staging_dir = server_dir / f".restore-staging-{uuid.uuid4().hex}"
    transaction_dir = server_dir / RESTORE_JOURNAL_DIR
    try:
        restore_items = _extract_validated(archive_path, staging_dir)
        transaction_dir.mkdir()
        entries = [{"name": name, "had_old": (server_dir / name).exists()} for name in BACKUP_ITEMS]
        journal_tmp = transaction_dir / (RESTORE_JOURNAL_NAME + ".tmp")
        journal_tmp.write_text(json.dumps({"entries": entries, "rollback": rollback_path.name}, indent=2), encoding="utf-8")
        os.replace(journal_tmp, transaction_dir / RESTORE_JOURNAL_NAME)

        for entry in entries:
            name = entry["name"]
            target = server_dir / name
            if entry["had_old"]:
                old_path = transaction_dir / "old" / name
                old_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, old_path)
            if name in restore_items:
                os.replace(staging_dir / name, target)

        if not (server_dir / "worlds").is_dir():
            raise BackupError("Restored backup did not produce a worlds folder")
        shutil.rmtree(transaction_dir)
        shutil.rmtree(staging_dir)
        (server_dir / MAINTENANCE_FILE).unlink(missing_ok=True)
        return rollback_path
    except Exception as error:
        if (transaction_dir / RESTORE_JOURNAL_NAME).exists():
            try:
                recover_restore(server_dir)
            except Exception as rollback_error:
                raise BackupError(f"Restore failed ({error}); rollback failed ({rollback_error})") from rollback_error
        else:
            shutil.rmtree(transaction_dir, ignore_errors=True)
            (server_dir / MAINTENANCE_FILE).unlink(missing_ok=True)
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise BackupError(f"Restore failed; the previous data was restored: {error}") from error
