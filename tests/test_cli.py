from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filesweep.cli import main  # noqa: E402


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def test_organize_and_undo(self) -> None:
        (self.root / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "b.jpg").write_text("b", encoding="utf-8")

        code, out = self.run_cli("organize", str(self.root), "-y")
        self.assertEqual(code, 0)
        self.assertIn("moved 2 file(s)", out)

        self.assertTrue((self.root / "txt" / "a.txt").exists())
        self.assertTrue((self.root / "jpg" / "b.jpg").exists())

        code, out = self.run_cli("undo", "--root", str(self.root), "-y")
        self.assertEqual(code, 0)
        self.assertIn("restored 2 file(s)", out)
        self.assertTrue((self.root / "a.txt").exists())
        self.assertTrue((self.root / "b.jpg").exists())

    def test_dry_run(self) -> None:
        (self.root / "a.txt").write_text("a", encoding="utf-8")

        code, out = self.run_cli("organize", str(self.root), "--dry-run")

        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertTrue((self.root / "a.txt").exists())

    def test_by_type_and_dest(self) -> None:
        (self.root / "shot.png").write_text("p", encoding="utf-8")
        out_dir = self.root / "sorted"

        code, _ = self.run_cli(
            "organize", str(self.root), "--by", "type", "--dest", str(out_dir), "-y"
        )

        self.assertEqual(code, 0)
        self.assertTrue((out_dir / "Images" / "shot.png").exists())

    def test_undo_without_log(self) -> None:
        code, _ = self.run_cli("undo", "--root", str(self.root), "-y")
        self.assertEqual(code, 2)

    def test_version(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as ctx:
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("filesweep", buf.getvalue())

    def test_non_interactive_requires_yes(self) -> None:
        (self.root / "a.txt").write_text("a", encoding="utf-8")
        stdin = sys.stdin
        sys.stdin = io.StringIO("")  # 没有 tty
        try:
            code, _ = self.run_cli("organize", str(self.root))
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 1)
        self.assertTrue((self.root / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()
