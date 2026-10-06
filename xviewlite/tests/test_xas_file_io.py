"""Regression checks for the patched readers; run these in the Pixi environment."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("xas"), "Requires the Pixi application environment")
class TestWhitespaceReaders(unittest.TestCase):
    def test_data_columns_values_and_energy_sorting(self):
        from xas.file_io import load_binned_df_from_file, load_interpolated_df_from_file

        for reader in (load_binned_df_from_file, load_interpolated_df_from_file):
            for separator in (" ", "   ", "\t", " \t "):
                with self.subTest(
                    reader=reader.__name__, separator=separator
                ), tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "sample.dat"
                    header = "# Test scan\n# energy i0 it iff\n"
                    rows = [(7113, 100, 40, 5), (7112, 200, 80, 10)]
                    path.write_text(header + "\n".join(separator.join(map(str, row)) for row in rows) + "\n")
                    data, actual_header = reader(str(path))
                    self.assertEqual(actual_header, header)
                    self.assertEqual(list(data.columns), ["energy", "i0", "it", "iff"])
                    self.assertEqual(data.to_numpy().tolist(), [list(rows[1]), list(rows[0])])


if __name__ == "__main__":
    unittest.main()
