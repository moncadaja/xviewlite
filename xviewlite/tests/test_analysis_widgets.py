"""Offscreen PyQt interaction tests with real datasets and Larch calculations."""

import importlib.util
import os
import time
import unittest


@unittest.skipUnless(importlib.util.find_spec("xas"), "Requires the Pixi application environment")
class TestAnalysisWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5 import QtWidgets
        from xas.xasproject import XASProject

        from xviewlite.tests.test_analysis import TestAnalysis
        from xviewlite.widgets import XASToolsWidget

        TestAnalysis.setUpClass()
        cls.data = TestAnalysis
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.Project, cls.Widget = XASProject, XASToolsWidget

    def setUp(self):
        self.project = self.Project()
        for name, peak in (("standard A", 0.1), ("standard B", 0.5), ("mixture", 0.3)):
            self.project.append(self.data.sample(name, peak=peak))
        self.widget = self.Widget(self.project)

    def tearDown(self):
        self.widget.wait_for_workers()
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def select(self, *rows):
        self.widget.dataset_list.clearSelection()
        for row in rows:
            self.widget.dataset_list.item(row).setSelected(True)

    def calculate(self, page):
        page.start()
        deadline = time.monotonic() + 30
        while page.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertIsNone(page.worker, "Worker did not complete")
        self.assertIsNotNone(page.report, page.summary.toPlainText())
        self.assertTrue(page.figure.axes)
        self.assertTrue(page.export_button.isEnabled())

    def test_all_widgets_calculate_with_real_larch(self):
        calibration, alignment, deglitch, lcf, pca, absorption, norm = self.widget.pages
        self.assertEqual(self.widget.tabs.count(), 7)
        self.select(0)
        calibration.target.setText("8980")
        calibration.measured.setText("8979")
        self.calculate(calibration)
        self.calculate(alignment)
        deglitch.lower.setText("9010")
        self.calculate(deglitch)
        self.select(0, 1)
        lcf.target.setCurrentIndex(2)
        lcf.lower.setText("8950")
        lcf.upper.setText("9070")
        self.calculate(lcf)
        self.assertFalse(lcf.add_button.isEnabled())
        self.select(0, 1, 2)
        pca.components.setText("1")
        self.calculate(pca)
        self.select(0)
        absorption.formula.setText("CuO")
        absorption.element.setText("Cu")
        absorption.fluorescence.setChecked(True)
        self.calculate(absorption)
        self.calculate(norm)

    def test_preview_add_undo_and_control_invalidation(self):
        page = self.widget.pages[0]
        self.select(0)
        page.target.setText("8980")
        page.measured.setText("8979")
        self.calculate(page)
        self.assertEqual(len(self.project.datasets), 3)
        page.add_results()
        self.assertEqual(len(self.project.datasets), 4)
        self.assertEqual(self.project.datasets[-1].analysis_history[-1]["parameters"]["shift_eV"], 1)
        page.undo_addition()
        self.assertEqual(len(self.project.datasets), 3)
        self.calculate(page)
        page.target.setText("8982")
        self.assertFalse(page.add_button.isEnabled())
        self.assertIsNone(page.report)

    def test_external_mutation_rejects_stale_preview(self):
        page = self.widget.pages[0]
        self.select(0)
        page.target.setText("8980")
        page.measured.setText("8979")
        self.calculate(page)
        self.project.datasets[0].mu[20] += 0.1
        page.add_results()
        self.assertEqual(len(self.project.datasets), 3)
        self.assertIn("changed", page.summary.toPlainText())

    def test_errors_are_visible_and_do_not_add_partial_results(self):
        page = self.widget.pages[0]
        page.start()
        self.assertIn("Select", page.summary.toPlainText())
        self.select(0)
        page.target.setText("nan")
        page.start()
        self.assertIsNone(page.worker)
        self.assertFalse(page.add_button.isEnabled())
        self.assertEqual(len(self.project.datasets), 3)

    def test_form_controls_and_titles_have_hover_help(self):
        from PyQt5 import QtWidgets

        for page in self.widget.pages:
            for control in page.controls.findChildren(QtWidgets.QWidget):
                if isinstance(control, (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QCheckBox)):
                    self.assertTrue(control.toolTip(), (type(page).__name__, control.objectName()))
                    label = page.form.labelForField(control)
                    if label is not None:
                        self.assertEqual(label.toolTip(), control.toolTip())

    def test_multiple_point_clicks_marks_and_cleaned_only_preview(self):
        from matplotlib.backend_bases import MouseEvent

        page = self.widget.pages[2]
        self.select(0)
        ds = self.project.datasets[0]
        ds.mu[400] += 15
        ds.mu[450] += 12
        page.mode.setCurrentIndex(page.mode.findData("points"))
        page.show_inputs()
        page.figure.axes[0].set_xlim(9050, 9200)

        def click(index):
            page.canvas.draw()
            ax = page.figure.axes[0]
            x, y = ax.transData.transform((ds.energy[index], ds.mu[index]))
            event = MouseEvent("button_press_event", page.canvas, x, y, button=1)
            page.canvas.callbacks.process("button_press_event", event)

        click(400)
        click(450)
        self.assertEqual(len(page.selection_options()["points"]), 2)
        click(400)
        self.assertEqual(len(page.selection_options()["points"]), 1)
        click(400)
        marked = page.figure.axes[0].lines[1]
        self.assertEqual(marked.get_marker(), "x")
        self.assertEqual(len(marked.get_xdata()), 2)
        self.calculate(page)
        self.assertEqual(len(page.figure.axes), 2)
        cleaned = page.figure.axes[1].lines
        self.assertEqual(len(cleaned), 1)  # Original spikes cannot obscure the cleaned curve.
        self.assertEqual(len(cleaned[0].get_xdata()), len(ds.energy) - 2)
        self.assertLess(max(cleaned[0].get_ydata()), 2)
        self.assertEqual(tuple(page.figure.axes[1].get_xlim()), (9050, 9200))
        self.assertEqual(len(self.project.datasets), 3)
        page.clear_button.click()
        self.assertEqual(page.points.text(), "")
        self.assertFalse(page.add_button.isEnabled())

    def test_iss_method_and_autoalignment_widgets(self):
        page = self.widget.pages[0]
        self.project.append(self.data.sample("shifted", shift=3))
        self.select(3)
        page.foil.setCurrentIndex(3)
        page.standard.setCurrentIndex(0)
        page.target.setText("8979")
        page.method.setCurrentIndex(page.method.findData("iss"))
        self.assertFalse(page.measured.isEnabled())
        self.assertTrue(page.standard.isEnabled())
        self.calculate(page)
        self.assertAlmostEqual(page.report["details"]["shift_eV"], -3, places=4)
        lcf = self.widget.pages[3]
        self.select(0, 1)
        lcf.target.setCurrentIndex(2)
        lcf.autoalign.setChecked(True)
        lcf.alignment_lower.setText("-10")
        lcf.alignment_upper.setText("10")
        self.calculate(lcf)
        self.assertEqual(len(lcf.report["alignment_shifts"]), 2)


if __name__ == "__main__":
    unittest.main()
