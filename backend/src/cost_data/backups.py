from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cost_data.config import get_settings


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_backup(target_directory: Path, kind: str = "manual") -> dict[str, Any]:
    settings = get_settings()
    backup_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    folder_name = f"{created_at.strftime('%Y%m%d-%H%M%S')}-{kind}-{backup_id[:8]}"
    temp_dir = target_directory.expanduser().resolve() / f".{folder_name}.tmp"
    final_dir = target_directory.expanduser().resolve() / folder_name
    temp_dir.mkdir(parents=True, exist_ok=False)
    snapshot = temp_dir / "cost-data.sqlite3"
    source = sqlite3.connect(settings.database_path)
    destination = sqlite3.connect(snapshot)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    raw_destination = temp_dir / "raw"
    if settings.raw_dir.exists():
        shutil.copytree(settings.raw_dir, raw_destination)
    files: list[dict[str, Any]] = []
    for path in sorted(raw_destination.rglob("*")) if raw_destination.exists() else []:
        if path.is_file():
            files.append(
                {
                    "path": str(path.relative_to(temp_dir)),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    manifest = {
        "id": backup_id,
        "kind": kind,
        "created_at": created_at.isoformat(),
        "database_sha256": _sha256(snapshot),
        "file_count": len(files),
        "files": files,
        "status": "complete",
    }
    (temp_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_dir.rename(final_dir)
    return {**manifest, "path": str(final_dir)}


def prune_backups(target_directory: Path, daily: int = 7, weekly: int = 4) -> None:
    grouped: dict[str, list[Path]] = {"daily": [], "weekly": []}
    for manifest_path in target_directory.expanduser().glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if manifest.get("kind") in grouped:
            grouped[manifest["kind"]].append(manifest_path.parent)
    for kind, keep in (("daily", daily), ("weekly", weekly)):
        for folder in sorted(grouped[kind], reverse=True)[keep:]:
            shutil.rmtree(folder)


def validate_backup(backup_path: Path) -> dict[str, Any]:
    folder = backup_path.expanduser().resolve()
    manifest_path = folder / "manifest.json"
    snapshot = folder / "cost-data.sqlite3"
    if not manifest_path.exists() or not snapshot.exists():
        raise ValueError("备份目录不完整")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256(snapshot) != manifest["database_sha256"]:
        raise ValueError("数据库快照校验失败")
    for entry in manifest.get("files", []):
        path = folder / entry["path"]
        if not path.exists() or _sha256(path) != entry["sha256"]:
            raise ValueError(f"原始文件校验失败: {entry['path']}")
    connection = sqlite3.connect(snapshot)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("SQLite 完整性检查失败")
    finally:
        connection.close()
    return {**manifest, "path": str(folder)}


def stage_restore(backup_path: Path) -> dict[str, Any]:
    manifest = validate_backup(backup_path)
    marker = get_settings().data_home / "pending-restore.json"
    marker.write_text(json.dumps({"backup_path": manifest["path"]}, ensure_ascii=False), encoding="utf-8")
    return manifest


def apply_pending_restore() -> bool:
    settings = get_settings()
    marker = settings.data_home / "pending-restore.json"
    if not marker.exists():
        return False
    payload = json.loads(marker.read_text(encoding="utf-8"))
    backup_path = Path(payload["backup_path"])
    validate_backup(backup_path)
    emergency = settings.database_dir / "pre-restore.sqlite3"
    if settings.database_path.exists():
        shutil.copy2(settings.database_path, emergency)
    shutil.copy2(backup_path / "cost-data.sqlite3", settings.database_path)
    source_raw = backup_path / "raw"
    if source_raw.exists():
        shutil.copytree(source_raw, settings.raw_dir, dirs_exist_ok=True)
    marker.unlink()
    return True
