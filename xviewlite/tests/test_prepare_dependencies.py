"""Preparation must handle overlapping patches without losing checkout edits."""

import difflib
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_dependencies import git, pending_patches


class TestPatchPreparation(unittest.TestCase):
    def test_fresh_partial_and_complete_stack(self):
        versions = ["one\ntwo\nthree\n", "one\nTWO\nthree\n", "one\nTWO\nTHREE\n"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            checkout = root / "checkout"
            checkout.mkdir()
            patches = []
            for index, (before, after) in enumerate(zip(versions, versions[1:])):
                patch = root / f"{index}.patch"
                patch.write_text("".join(difflib.unified_diff(
                    before.splitlines(True), after.splitlines(True),
                    fromfile="a/sample.txt", tofile="b/sample.txt",
                )))
                patches.append(str(patch))

            local_edit = checkout / "local.txt"
            local_edit.write_text("Keep my work\n")
            sample = checkout / "sample.txt"
            for count, version in enumerate(versions):
                with self.subTest(applied=count):
                    sample.write_text(version)
                    pending = pending_patches(checkout, patches)
                    self.assertEqual(pending, patches[count:])
                    self.assertEqual(sample.read_text(), version)
                    for patch in pending:
                        git(checkout, "apply", patch)
                    self.assertEqual(sample.read_text(), versions[-1])
                    self.assertEqual(local_edit.read_text(), "Keep my work\n")

            sample.write_text("Conflicting local edit\n")
            with self.assertRaises(subprocess.CalledProcessError):
                pending_patches(checkout, patches)
            self.assertEqual(sample.read_text(), "Conflicting local edit\n")


if __name__ == "__main__":
    unittest.main()
