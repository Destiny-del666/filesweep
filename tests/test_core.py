from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filesweep.core import (  # noqa: E402
    apply_plan,
    build_plan,
    category_for,
    human_size,
    latest_log,
    undo_log,
)


def touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class BuildPlanTests(TempDirCase):
    def test_by_ext(self) -> None:
        a = touch(self.root / "a.txt")
        b = touch(self.root / "b.PDF")
        c = touch(self.root / "no_extension")
        touch(self.root / "sub" / "nested.txt")

        plan = build_plan(self.root, by="ext")
        self.assertEqual(plan.total, 3)
        self.assertEqual({m.src for m in plan.moves}, {a, b, c})
        apply_plan(plan)

        self.assertTrue((self.root / "txt" / "a.txt").exists())
        self.assertTrue((self.root / "pdf" / "b.PDF").exists())
        self.assertTrue((self.root / "_noext" / "no_extension").exists())
        # 子目录不参与整理
        self.assertTrue((self.root / "sub" / "nested.txt").exists())

    def test_by_type(self) -> None:
        touch(self.root / "photo.jpg")
        touch(self.root / "notes.md")
        touch(self.root / "song.mp3")
        touch(self.root / "blob.xyz")

        plan = build_plan(self.root, by="type")
        apply_plan(plan)

        self.assertTrue((self.root / "Images" / "photo.jpg").exists())
        self.assertTrue((self.root / "Documents" / "notes.md").exists())
        self.assertTrue((self.root / "Audio" / "song.mp3").exists())
        self.assertTrue((self.root / "Other" / "blob.xyz").exists())

    def test_by_date(self) -> None:
        old = touch(self.root / "old.txt")
        new = touch(self.root / "new.txt")
        stamp_old = datetime(2024, 3, 5, 12, 0).timestamp()
        stamp_new = datetime(2025, 12, 31, 23, 30).timestamp()
        os.utime(old, (stamp_old, stamp_old))
        os.utime(new, (stamp_new, stamp_new))

        plan = build_plan(self.root, by="date")
        apply_plan(plan)

        self.assertTrue((self.root / "2024" / "03" / "old.txt").exists())
        self.assertTrue((self.root / "2025" / "12" / "new.txt").exists())

    def test_collision_gets_suffix(self) -> None:
        touch(self.root / "txt" / "a.txt", b"old")
        touch(self.root / "a.txt", b"new")

        plan = build_plan(self.root, by="ext")
        apply_plan(plan)

        self.assertEqual((self.root / "txt" / "a.txt").read_bytes(), b"old")
        self.assertEqual((self.root / "txt" / "a (1).txt").read_bytes(), b"new")

    def test_dest_directory(self) -> None:
        touch(self.root / "incoming" / "x.png")
        out = self.root / "archive"

        plan = build_plan(self.root / "incoming", by="ext", dest=out)
        apply_plan(plan)

        self.assertTrue((out / "png" / "x.png").exists())
        self.assertFalse((self.root / "incoming" / "x.png").exists())

    def test_dry_run_does_not_touch_files(self) -> None:
        a = touch(self.root / "a.txt")
        build_plan(self.root, by="ext")
        self.assertTrue(a.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["a.txt"])

    def test_second_run_is_empty(self) -> None:
        touch(self.root / "a.txt")
        apply_plan(build_plan(self.root, by="ext"))
        again = build_plan(self.root, by="ext")
        self.assertTrue(again.is_empty())

    def test_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            build_plan(self.root, by="colour")

    def test_missing_directory(self) -> None:
        with self.assertRaises(NotADirectoryError):
            build_plan(self.root / "nope")

    def test_symlink_is_skipped(self) -> None:
        target = touch(self.root / "real.txt")
        link = self.root / "link.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted on this platform")

        plan = build_plan(self.root, by="ext")
        self.assertEqual({m.src for m in plan.moves}, {target})


class ApplyAndUndoTests(TempDirCase):
    def test_apply_writes_log(self) -> None:
        touch(self.root / "a.txt")
        log = apply_plan(build_plan(self.root, by="ext"))
        self.assertIsNotNone(log)
        payload = json.loads(Path(log).read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertEqual(len(payload["moves"]), 1)

    def test_apply_empty_plan_returns_none(self) -> None:
        self.assertIsNone(apply_plan(build_plan(self.root, by="ext")))

    def test_undo_restores_files(self) -> None:
        touch(self.root / "a.txt", b"a")
        touch(self.root / "b.png", b"b")
        log = apply_plan(build_plan(self.root, by="ext"))
        self.assertTrue((self.root / "txt" / "a.txt").exists())

        restored, failed = undo_log(log)  # type: ignore[arg-type]

        self.assertEqual(len(restored), 2)
        self.assertEqual(failed, [])
        self.assertEqual((self.root / "a.txt").read_bytes(), b"a")
        self.assertEqual((self.root / "b.png").read_bytes(), b"b")

    def test_undo_reports_missing_file(self) -> None:
        touch(self.root / "a.txt")
        log = apply_plan(build_plan(self.root, by="ext"))
        (self.root / "txt" / "a.txt").unlink()

        restored, failed = undo_log(log)  # type: ignore[arg-type]

        self.assertEqual(restored, [])
        self.assertEqual(len(failed), 1)

    def test_latest_log(self) -> None:
        touch(self.root / "a.txt")
        log = apply_plan(build_plan(self.root, by="ext"))
        self.assertEqual(latest_log(self.root), Path(log))  # type: ignore[arg-type]
        self.assertIsNone(latest_log(self.root / "empty"))

    def test_log_dir_override(self) -> None:
        logs = self.root / "logs"
        touch(self.root / "a.txt")
        log = apply_plan(build_plan(self.root, by="ext"), log_dir=logs)
        self.assertEqual(Path(log).parent, logs)  # type: ignore[arg-type]
        self.assertEqual(latest_log(self.root), None)


class HelperTests(unittest.TestCase):
    def test_category_for(self) -> None:
        self.assertEqual(category_for(Path("x.JPG")), "Images")
        self.assertEqual(category_for(Path("x.unknownext")), "Other")
        self.assertEqual(category_for(Path("noext")), "Other")

    def test_human_size(self) -> None:
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(999), "999 B")
        self.assertEqual(human_size(1536), "1.5 KB")
        self.assertEqual(human_size(5 * 1024 * 1024), "5.0 MB")


if __name__ == "__main__":
    unittest.main()
