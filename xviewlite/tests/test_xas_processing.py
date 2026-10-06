"""Exercise the dataset processing used by XView with the locked dependencies."""

import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec("xas"), "Requires the Pixi application environment")
class TestXASProcessing(unittest.TestCase):
    def test_flatten_correction_and_edge_boundaries(self):
        import numpy as np
        from xas.xasproject import XASDataSet

        ds = XASDataSet(process=False)
        ds.energy = np.array([10.0, 20.0, 30.0, 40.0])
        ds.norm = np.array([0.0, 0.5, 1.2, 1.3])
        ds.pre_edge = np.zeros(4)
        ds.post_edge = np.array([1.0, 1.1, 1.2, 1.3])
        ds.edge_step = 1.0
        for edge, expected in (
            (20.0, [0.0, 0.5, 1.0, 1.0]),
            (np.array([20.0]), [0.0, 0.5, 1.0, 1.0]),
            (40.0, [0.0, 0.5, 1.2, 1.3]),
            (5.0, [0.0, 0.4, 1.0, 1.0]),
        ):
            with self.subTest(edge=edge):
                ds.e0 = edge
                ds.flatten()
                np.testing.assert_allclose(ds.flat, expected)

    def test_normalization_background_and_fourier_transform(self):
        import numpy as np
        from xas.xasproject import XASDataSet

        energy = np.linspace(8700.0, 9900.0, 601)
        mu = 0.0001 * (energy - 8700) + 1 / (1 + np.exp(-(energy - 8979) / 2))
        ds = XASDataSet(energy=energy, mu=mu, md={"e0": 8979})
        self.assertIsNotNone(ds.e0)
        self.assertAlmostEqual(ds.e0, 8979, delta=3)
        np.testing.assert_allclose(ds.flat[energy > 9100], 1, atol=0.01)
        self.assertEqual(ds.mu_deriv.size, energy.size - 1)

        # Additional channels copy the first dataset's processing parameters.
        copied = XASDataSet(energy=energy, mu=mu * 2, process=False, xasdataset=ds)
        for dataset in (ds, copied):
            dataset.normalize_force()
            dataset.extract_chi_force()
            dataset.extract_ft_force()
            for field in ("norm", "flat", "bkg", "k", "chi", "r", "chir_mag"):
                with self.subTest(dataset=dataset, field=field):
                    values = getattr(dataset, field)
                    self.assertGreater(values.size, 0)
                    self.assertTrue(np.isfinite(values).all())


if __name__ == "__main__":
    unittest.main()
