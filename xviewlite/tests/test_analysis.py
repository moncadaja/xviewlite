"""Numerical and data-integrity regressions for the Larch analysis workflows."""

import importlib.util
import json
import pickle
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("xas"), "Requires the Pixi application environment")
class TestAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        import pandas as pd
        from xas.xasproject import XASDataSet

        from xviewlite import analysis

        cls.np, cls.pd, cls.Dataset, cls.analysis = np, pd, XASDataSet, analysis

    @classmethod
    def sample(cls, name="sample", shift=0.0, peak=0.1, chemical_shift=0.0):
        np = cls.np
        energy = np.linspace(8700.0, 9900.0, 1201)
        foil = 0.0001 * (energy - 8700) + 1 / (1 + np.exp(-(energy - 8979) / 2))
        mu = (
            0.0001 * (energy - 8700)
            + 1 / (1 + np.exp(-(energy - 8979 - chemical_shift) / 2))
            + peak * np.exp(-(((energy - 9000) / 5) ** 2))
        )
        frame = cls.pd.DataFrame({"energy": energy + shift, "mur": foil})
        return cls.Dataset(name=name, energy=energy + shift, mu=mu, md={"e0": 8979 + shift}, df=frame)

    def test_calibration_shifts_sample_reference_and_e0_without_mutation(self):
        ds = self.sample()
        before = ds.energy.copy()
        outputs, details = self.analysis.calibrate([ds], ds, 8982, measured=8979)
        out = outputs[0]
        self.np.testing.assert_equal(ds.energy, before)
        self.np.testing.assert_equal(out.energy, before + 3)
        self.np.testing.assert_equal(out.df.energy, before + 3)
        self.np.testing.assert_equal(out.mu, ds.mu)
        self.assertEqual(out.e0, ds.e0 + 3)
        self.assertEqual(details["shift_eV"], 3)
        self.assertFalse(hasattr(out, "chi"))  # Never retain stale background/FT arrays.
        self.assertEqual(out.analysis_history[-1]["operation"], "calibrated")
        self.assertEqual(pickle.loads(pickle.dumps(out)).analysis_history, out.analysis_history)

    def test_auto_foil_feature(self):
        ds = self.sample()
        _, report = self.analysis.calibrate([ds], ds, 8979, reference=True)
        self.assertAlmostEqual(report["measured_eV"], 8979, delta=1.1)

    def test_iss_calibration_reuses_reference_fit_and_shift_sign(self):
        foil, reference = self.sample("measured", shift=3), self.sample("reference")
        original = foil.energy.copy()
        outputs, report = self.analysis.calibrate([foil], foil, 8979, method="iss", standard=reference)
        self.assertAlmostEqual(report["shift_eV"], -3, places=4)
        self.np.testing.assert_allclose(outputs[0].energy, reference.energy, atol=1.0e-4)
        self.np.testing.assert_equal(foil.energy, original)
        self.np.testing.assert_allclose(report["fit"]["reference"], report["fit"]["fitted"], atol=1.0e-5)
        with self.assertRaisesRegex(ValueError, "reference"):
            self.analysis.calibrate([foil], foil, 8979, method="iss")
        with self.assertRaisesRegex(ValueError, "window"):
            self.analysis.calibrate([foil], foil, 8979, method="iss", standard=reference, window=1000)

    def test_copy_does_not_mutate_inherited_metadata_or_detector_data(self):
        template = self.sample()
        ds = self.Dataset(name="no metadata", energy=template.energy, mu=template.mu)
        original_md = dict(ds.md)
        ds.ext_data = {"images": self.np.ones((3, 4, 5))}
        outputs, _ = self.analysis.calibrate([ds], template, 8980, measured=8979)
        self.assertEqual(ds.md, original_md)
        self.assertIsNot(outputs[0].md, ds.md)
        self.assertTrue(hasattr(ds, "ext_data"))
        self.assertFalse(hasattr(outputs[0], "ext_data"))

    def test_alignment_shift_direction_and_reference_channel(self):
        standard = self.sample("standard")
        shifted = self.sample("shifted", shift=3, chemical_shift=7)
        outputs, reports = self.analysis.align([shifted], standard, reference=True)
        self.assertAlmostEqual(reports[0]["shift_eV"], -3, places=3)
        self.np.testing.assert_allclose(outputs[0].energy, standard.energy, atol=0.001)
        # Alignment via foil preserves the sample's chemical features.
        self.np.testing.assert_equal(outputs[0].mu, shifted.mu)

    def test_alignment_preserves_zero_shift(self):
        ds = self.sample()
        _, reports = self.analysis.align([ds], ds)
        self.assertAlmostEqual(reports[0]["shift_eV"], 0, places=4)
        with self.assertRaisesRegex(ValueError, "window"):
            self.analysis.align([ds], ds, emin=-10000)

    def test_deglitch_range_keeps_reference_grid_and_original(self):
        ds = self.sample()
        out, report = self.analysis.deglitch(ds, lower=9010, upper=9012)
        self.assertEqual(report["energies_eV"], [9010, 9011, 9012])
        self.assertEqual(len(out.energy), len(ds.energy) - 3)
        self.np.testing.assert_equal(out.energy, out.df.energy)
        self.assertEqual(len(out.mu_deriv), len(out.energy) - 1)
        self.assertEqual(len(ds.energy), 1201)

    def test_deglitch_multiple_points_deduplicates_and_masks_reference(self):
        ds = self.sample()
        out, report = self.analysis.deglitch(ds, points=[9010.0, 9010.1, 9012.0, 9020.0])
        self.assertEqual(report["energies_eV"], [9010.0, 9012.0, 9020.0])
        self.assertEqual(len(out.energy), len(ds.energy) - 3)
        self.np.testing.assert_equal(out.energy, out.df.energy)
        self.assertFalse(self.np.isin(report["energies_eV"], out.energy).any())
        for values in ([], [float("nan")], [10000]):
            with self.assertRaises(ValueError):
                self.analysis.deglitch(ds, points=values)

    def test_auto_spike_replacement(self):
        ds = self.sample()
        original = ds.mu.copy()
        ds.mu = original.copy()
        ds.mu[400] += 15
        out, report = self.analysis.deglitch(ds, automatic=True, window=5, threshold=3)
        self.assertIn(ds.energy[400], report["energies_eV"])
        self.assertAlmostEqual(out.mu[400], original[400], places=3)
        self.assertGreater(ds.mu[400], 10)
        with self.assertRaisesRegex(ValueError, "odd window"):
            self.analysis.deglitch(ds, automatic=True, window=4)

    def test_known_linear_combination(self):
        a, b, mixed = self.sample("a", peak=0.1), self.sample("b", peak=0.5), self.sample("mix", peak=0.3)
        fit = self.analysis.linear_combination(mixed, [a, b], 8950, 9070)
        self.np.testing.assert_allclose(list(fit.weights.values()), [0.5, 0.5], atol=0.003)
        self.assertLess(fit.rfactor, 1.0e-10)
        self.assertAlmostEqual(sum(fit.weights.values()), 1)
        with self.assertRaisesRegex(ValueError, "linearly dependent"):
            self.analysis.linear_combination(mixed, [a, self.sample("same", peak=0.1)])
        with self.assertRaisesRegex(ValueError, "target cannot"):
            self.analysis.linear_combination(a, [a, b])

    def test_linear_combination_optional_alignment_preserves_inputs(self):
        a, b = self.sample("a", peak=0.1, shift=2), self.sample("b", peak=0.5, shift=-2)
        mixed = self.sample("mix", peak=0.3)
        before = [ds.energy.copy() for ds in (a, b, mixed)]
        fit = self.analysis.linear_combination(
            mixed, [a, b], 8950, 9070, autoalign=True, alignment_emin=-10, alignment_emax=10
        )
        self.np.testing.assert_allclose([row["shift_eV"] for row in fit.alignment_shifts], [-2, 2], atol=0.01)
        self.np.testing.assert_allclose(list(fit.weights.values()), [0.5, 0.5], atol=0.005)
        self.assertTrue(fit.provenance["parameters"]["autoalignment"])
        for original, ds in zip(before, (a, b, mixed)):
            self.np.testing.assert_equal(ds.energy, original)

    def test_pca_rank_one_mixture_including_mean_spectrum(self):
        datasets = [self.sample(str(i), peak=p) for i, p in enumerate((0.1, 0.2, 0.3, 0.4, 0.5))]
        model = self.analysis.principal_components(datasets, 8950, 9070, ncomponents=1)
        self.assertAlmostEqual(model.variances[0], 1, places=10)
        self.assertEqual(model.scores.shape, (5, 5))
        for fit in model.fits:
            self.np.testing.assert_allclose(fit.ydat, fit.yfit, atol=1.0e-10)
        with self.assertRaisesRegex(ValueError, "variation"):
            self.analysis.principal_components([datasets[0]] * 3)

    def test_common_grid_never_extrapolates(self):
        a, b = self.sample("a"), self.sample("b", shift=2)
        groups = self.analysis.common_groups([a, b], None, None)
        self.assertGreaterEqual(groups[0].energy[0], b.energy[0])
        self.assertLessEqual(groups[0].energy[-1], a.energy[-1])
        with self.assertRaisesRegex(ValueError, "shared energy"):
            self.analysis.common_groups([a, b], 8700, 9900)

    def test_self_absorption_matches_larch_and_rejects_invalid_geometry(self):
        from larch.xafs import fluo_corr

        ds = self.sample()
        out, report = self.analysis.self_absorption(ds, "CuO", "Cu")
        group = self.analysis.normalized_group(ds)
        fluo_corr(group.energy, group.mu, "CuO", "Cu", group=group, **self.analysis.normalization_options(ds))
        self.np.testing.assert_allclose(out.mu, group.mu_corr)
        self.assertIn("optically thick", report["model"])
        self.assertFalse(self.np.array_equal(ds.mu, out.mu))
        for opts in ({"angle_in": 0}, {"line": "La"}, {"element": "Fe"}, {"formula": "FeO"}):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                self.analysis.self_absorption(ds, **({"formula": "CuO", "element": "Cu"} | opts))

    def test_larch_normalization_and_ft_contract(self):
        ds = self.sample()
        self.assertEqual(ds.nnorm, ds.larch.pre_edge_details.nnorm)
        out = self.analysis.derived(
            ds, ds.energy, ds.mu, "normalized", {}, options={"flatten_method": "larch", "nnorm": 1}
        )
        self.np.testing.assert_equal(out.flat, out.larch.flat)
        self.assertEqual(out.nnorm, 1)
        out.extract_chi_force()
        out.extract_ft_force()
        self.np.testing.assert_equal(out.chir_re, out.chir.real)
        self.np.testing.assert_equal(out.chir_im, out.chir.imag)
        high = out.kmax_ft
        out.extract_ft()
        self.assertEqual(out.kmax_ft, high)

    def test_invalid_input_and_export(self):
        for x, y in (([1] * 8, [2] * 8), (range(8), [float("nan")] * 8), ([1, 2], [1, 2])):
            with self.assertRaises(ValueError):
                self.analysis.arrays(x, y)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            self.analysis.export_report(path, {"data": self.np.array([1.0, 2.0]), "parameters": {"shift": 3.0}})
            self.assertEqual(json.loads(path.read_text())["data"], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
