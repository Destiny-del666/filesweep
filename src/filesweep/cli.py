"""命令行入口：filesweep organize / undo。

用户可见的文案统一用英文：这类工具会被人在各种编码的终端里跑，
英文帮助信息不会因为 GBK / cp437 之类的代码页变成乱码。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import (
    BY_CHOICES,
    Plan,
    apply_plan,
    build_plan,
    human_size,
    latest_log,
    plan_summary,
    undo_log,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="filesweep",
        description=(
            "Tidy a messy folder by extension, file type or date. "
            "Every run is logged and can be undone."
        ),
    )
    parser.add_argument("--version", action="version", version=f"filesweep {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    organize = sub.add_parser("organize", help="move files into sub-folders")
    organize.add_argument("path", help="directory to tidy (only its top-level files are moved)")
    organize.add_argument(
        "--by",
        choices=BY_CHOICES,
        default="ext",
        help="group by ext=extension (default), type=file category, date=year/month",
    )
    organize.add_argument("--dest", help="archive root (default: inside PATH itself)")
    organize.add_argument(
        "-n", "--dry-run", action="store_true", help="show the plan, move nothing"
    )
    organize.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    organize.add_argument(
        "--log-dir", help="where to write the undo log (default: PATH/.filesweep)"
    )
    organize.set_defaults(func=cmd_organize)

    undo = sub.add_parser("undo", help="revert a previous organize run")
    undo.add_argument("--log", help="undo log to apply (default: newest in ROOT/.filesweep)")
    undo.add_argument(
        "--root", dest="root_dir", help="where to look for the newest log (default: .)"
    )
    undo.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    undo.set_defaults(func=cmd_undo)

    return parser


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("refusing to run non-interactively without -y/--yes", file=sys.stderr)
        return False
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _print_plan(plan: Plan) -> None:
    print(f"mode: {plan.by}")
    for line in plan_summary(plan):
        print(line)
    for path, reason in plan.skipped:
        print(f"  skip {path.name}: {reason}")
    if plan.is_empty():
        print("nothing to do: no files need moving")


def cmd_organize(args: argparse.Namespace) -> int:
    plan = build_plan(args.path, by=args.by, dest=args.dest)
    _print_plan(plan)
    if plan.is_empty():
        return 0

    if args.dry_run:
        print(f"dry run: {plan.total} file(s) would move; nothing changed")
        return 0

    if not _confirm(f"move {plan.total} file(s)?", args.yes):
        print("aborted")
        return 1

    log_path = apply_plan(plan, log_dir=args.log_dir)
    total_bytes = sum(m.dst.stat().st_size for m in plan.moves if m.dst.exists())
    print(f"moved {plan.total} file(s), {human_size(total_bytes)}")
    if log_path:
        print(f"undo log: {log_path}")
        print(f'revert with: filesweep undo --log "{log_path}"')
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    log_path = Path(args.log) if args.log else latest_log(args.root_dir or ".")
    if log_path is None:
        print("no undo log found (looked for .filesweep/undo-*.json)", file=sys.stderr)
        return 2
    if not Path(log_path).is_file():
        print(f"undo log not found: {log_path}", file=sys.stderr)
        return 2

    if not _confirm(f"restore files from {log_path}?", args.yes):
        print("aborted")
        return 1

    restored, failed = undo_log(log_path)
    print(f"restored {len(restored)} file(s)")
    for path, reason in failed:
        print(f"  fail {path}: {reason}")
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
