"""核心逻辑：扫描 -> 生成计划 -> 执行 -> 可撤销。

设计原则：
- 只做「计划」和「执行」两件事，中间产物 Plan 可以被 dry-run 安全展示。
- 每一步移动都写进 JSON 日志，因此任何一次整理都能被 undo 还原。
- 不删除任何文件；重名时自动加 (1)、(2) 后缀，绝不覆盖。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

LOG_DIR_NAME = ".filesweep"
LOG_VERSION = 1

#: 按「类型」归档时使用的分类表。未命中的扩展名归入 Other。
CATEGORIES: dict[str, set[str]] = {
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff",
        ".svg", ".ico", ".heic", ".raw", ".psd", ".ai",
    },
    "Documents": {
        ".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".pages",
        ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".epub", ".mobi", ".tex",
    },
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".aiff"},
    "Video": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".m4v"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Code": {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".h",
        ".cpp", ".hpp", ".cs", ".rb", ".php", ".sh", ".ps1", ".html", ".css",
        ".json", ".yaml", ".yml", ".toml", ".sql",
    },
}

_EXT_TO_CATEGORY: dict[str, str] = {
    ext: name for name, exts in CATEGORIES.items() for ext in exts
}

BY_CHOICES = ("ext", "type", "date")


@dataclass(frozen=True)
class Move:
    """一次移动：从 src 到 dst（两者都是绝对路径）。"""

    src: Path
    dst: Path

    def to_dict(self) -> dict[str, str]:
        return {"src": str(self.src), "dst": str(self.dst)}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "Move":
        return cls(Path(data["src"]), Path(data["dst"]))


@dataclass
class Plan:
    """一次整理的完整计划。"""

    root: Path
    by: str
    moves: list[Move] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.moves)

    def is_empty(self) -> bool:
        return not self.moves

    def targets(self) -> list[Path]:
        return sorted({m.dst.parent for m in self.moves})


def category_for(path: Path) -> str:
    """返回文件所属类别，未知扩展名返回 "Other"。"""
    return _EXT_TO_CATEGORY.get(path.suffix.lower(), "Other")


def _free_target(target: Path) -> Path:
    """若 target 已存在，返回一个带 (1)/(2) 后缀的空闲路径。"""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    index = 1
    while True:
        candidate = target.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _iter_files(root: Path) -> Iterable[Path]:
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir():
            continue  # 只整理文件，目录原样保留
        if entry.is_symlink():
            continue  # 不碰符号链接，避免搬走链接目标或制造悬空链接
        yield entry


def _target_dir(path: Path, dest: Path, by: str, mtime: float) -> Path:
    if by == "ext":
        suffix = path.suffix.lower().lstrip(".")
        return dest / (suffix if suffix else "_noext")
    if by == "type":
        return dest / category_for(path)
    if by == "date":
        stamp = datetime.fromtimestamp(mtime)
        return dest / f"{stamp.year:04d}" / f"{stamp.month:02d}"
    raise ValueError(f"unknown mode: {by!r} (choose from {', '.join(BY_CHOICES)})")


def build_plan(
    root: str | os.PathLike[str],
    by: str = "ext",
    dest: str | os.PathLike[str] | None = None,
) -> Plan:
    """扫描 root 下的文件并生成整理计划（不移动任何东西）。"""
    if by not in BY_CHOICES:
        raise ValueError(f"unknown mode: {by!r} (choose from {', '.join(BY_CHOICES)})")

    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"not a directory: {root_path}")

    dest_path = Path(dest).expanduser().resolve() if dest else root_path
    dest_path.mkdir(parents=True, exist_ok=True)

    plan = Plan(root=root_path, by=by)
    reserved: set[Path] = set()

    for path in _iter_files(root_path):
        mtime = path.stat().st_mtime
        target_dir = _target_dir(path, dest_path, by, mtime)
        if target_dir == path.parent:
            plan.skipped.append((path, "already in place"))
            continue

        target = _free_target(target_dir / path.name)
        # 保险：同一批次里若出现同名目标（例如日后支持递归时），也不会互相覆盖。
        while target in reserved:
            target = _free_target(target)
        reserved.add(target)
        plan.moves.append(Move(src=path, dst=target))

    return plan


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def apply_plan(
    plan: Plan,
    log_dir: str | os.PathLike[str] | None = None,
) -> Path | None:
    """执行计划，返回写入的日志路径（没有移动时返回 None）。"""
    if plan.is_empty():
        return None

    done: list[Move] = []
    for move in plan.moves:
        move.dst.parent.mkdir(parents=True, exist_ok=True)

        # 执行阶段再确认一次目标未被占用，避免与外部操作竞态。
        target = move.dst
        if target.exists():
            target = _free_target(target)
        shutil.move(str(move.src), str(target))
        done.append(Move(src=move.src, dst=target))

    plan.moves = done

    log_root = Path(log_dir).expanduser().resolve() if log_dir else plan.root / LOG_DIR_NAME
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / f"undo-{_now_stamp()}-{os.getpid()}.json"
    payload = {
        "version": LOG_VERSION,
        "created": datetime.now(timezone.utc).isoformat(),
        "root": str(plan.root),
        "by": plan.by,
        "moves": [m.to_dict() for m in done],
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_path


def latest_log(root: str | os.PathLike[str]) -> Path | None:
    """返回某目录下最近一次的撤销日志。"""
    log_dir = Path(root).expanduser().resolve() / LOG_DIR_NAME
    if not log_dir.is_dir():
        return None
    logs = sorted(log_dir.glob("undo-*.json"))
    return logs[-1] if logs else None


def undo_log(log_path: str | os.PathLike[str]) -> tuple[list[Move], list[tuple[Path, str]]]:
    """按日志把文件搬回原位，返回 (已还原, 失败列表)。"""
    path = Path(log_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != LOG_VERSION:
        raise ValueError(f"unsupported log version: {payload.get('version')!r}")

    restored: list[Move] = []
    failed: list[tuple[Path, str]] = []

    # 逆序还原，处理同一目标目录下多次移动的情况更稳妥。
    for entry in reversed(payload.get("moves", [])):
        move = Move.from_dict(entry)
        if not move.dst.exists():
            failed.append((move.dst, "missing (moved or deleted manually?)"))
            continue
        if move.src.exists():
            failed.append((move.src, "original path already occupied"))
            continue
        move.src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move.dst), str(move.src))
        restored.append(move)

    return restored, failed


def human_size(num_bytes: int) -> str:
    """把字节数格式化成可读字符串。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def plan_summary(plan: Plan) -> list[str]:
    """给 CLI 用的摘要行。"""
    lines = []
    for target in plan.targets():
        count = sum(1 for m in plan.moves if m.dst.parent == target)
        lines.append(f"  {target.name if target != plan.root else '.'}/  <- {count} file(s)")
    return lines
