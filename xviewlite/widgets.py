"""Native PyQt widgets for the XView project, backed by xviewlite.analysis."""

import hashlib
import json
import re

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt5 import QtCore, QtWidgets

from . import analysis
from .tooltips import form_help, install_control_help


def signature(ds):
    digest = hashlib.sha256()
    for values in (ds.energy, ds.mu):
        digest.update(np.asarray(values, dtype=float).tobytes())
    frame = getattr(ds, "df", None)
    if frame is not None:
        for key in ("energy", "mur"):
            if key in frame:
                digest.update(np.asarray(frame[key], dtype=float).tobytes())
    digest.update(repr(analysis.normalization_options(ds)).encode())
    digest.update(str(ds.name).encode())
    for key in ("kmin", "kmax", "kmin_ft", "kmax_ft", "kweight", "rbkg", "clamp_lo", "clamp_hi"):
        digest.update(repr(getattr(ds, key, None)).encode())
    digest.update(str(getattr(ds, "flatten_method", "legacy")).encode())
    return digest.digest()


def curve(x, y, label, **style):
    return {"x": np.asarray(x), "y": np.asarray(y), "label": label, "style": style}


def plot_spec(title, curves, xlabel="Energy (eV)", ylabel="Normalized mu"):
    return {"title": title, "curves": curves, "xlabel": xlabel, "ylabel": ylabel}


def correction_result(sources, outputs, details):
    curves = []
    for source, output in zip(sources, outputs):
        curves.append(curve(source.energy, analysis.normalized_group(source).norm, source.name + " / before"))
        curves.append(curve(output.energy, output.norm, output.name))
    report = {
        "details": details,
        "history": [ds.analysis_history for ds in outputs],
        "processing": [{"dataset": ds.name, **analysis.normalization_options(ds)} for ds in outputs],
    }
    return outputs, report, [plot_spec("Before / after", curves)]


class Calculation(QtCore.QThread):
    succeeded = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.succeeded.emit(self.function())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class AnalysisPage(QtWidgets.QWidget):
    """Common preview, worker, export and add-as-copy controls."""

    def __init__(self, owner, instructions):
        super().__init__(owner)
        self.owner = owner
        self.pending = []
        self.report = None
        self.inputs = []
        self.worker = None
        self.last_added = []
        self.layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(instructions)
        label.setWordWrap(True)
        self.layout.addWidget(label)
        self.controls = QtWidgets.QWidget()
        self.form = QtWidgets.QFormLayout(self.controls)
        self.layout.addWidget(self.controls)
        buttons = QtWidgets.QHBoxLayout()
        self.plot_button = QtWidgets.QPushButton("Plot inputs")
        self.run_button = QtWidgets.QPushButton("Preview / calculate")
        self.add_button = QtWidgets.QPushButton("Add results as new datasets")
        self.undo_button = QtWidgets.QPushButton("Undo last addition")
        self.export_button = QtWidgets.QPushButton("Export results (JSON)")
        for button in (self.plot_button, self.run_button, self.add_button, self.undo_button, self.export_button):
            buttons.addWidget(button)
        self.layout.addLayout(buttons)
        self.figure = Figure(figsize=(7, 4), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.addWidget(self.canvas)
        self.result_tabs = QtWidgets.QTabWidget()
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.result_tabs.addTab(self.table, "Results")
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.result_tabs.addTab(self.summary, "Details")
        splitter.addWidget(self.result_tabs)
        splitter.setSizes([450, 120])
        self.layout.addWidget(splitter, 1)
        self.plot_button.clicked.connect(self.show_inputs)
        self.run_button.clicked.connect(self.start)
        self.add_button.clicked.connect(self.add_results)
        self.undo_button.clicked.connect(self.undo_addition)
        self.export_button.clicked.connect(self.export)
        self.canvas.mpl_connect("button_press_event", self.pick)
        self.add_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.undo_button.setEnabled(False)

    def field(self, label, default=""):
        control = QtWidgets.QLineEdit(str(default))
        self.form.addRow(label, control)
        self.set_help(control, label)
        control.textChanged.connect(self.invalidate)
        return control

    def choice(self, label, options):
        control = QtWidgets.QComboBox()
        for text, value in options:
            control.addItem(text, value)
        self.form.addRow(label, control)
        self.set_help(control, label)
        control.currentIndexChanged.connect(self.invalidate)
        return control

    def check(self, label, checked=False):
        control = QtWidgets.QCheckBox(label)
        control.setChecked(checked)
        self.form.addRow(control)
        self.set_help(control, label)
        control.toggled.connect(self.invalidate)
        return control

    def dataset_choice(self, label):
        control = QtWidgets.QComboBox()
        self.form.addRow(label, control)
        self.set_help(control, label)
        self.owner.dataset_combos.append(control)
        control.currentIndexChanged.connect(self.invalidate)
        return control

    def set_help(self, control, title):
        message = form_help(title)
        control.setToolTip(message)
        label = self.form.labelForField(control)
        if label is not None:
            label.setToolTip(message)

    @staticmethod
    def number(control, optional=False):
        text = control.text().strip()
        if not text and optional:
            return None
        value = float(text)
        if not np.isfinite(value):
            raise ValueError("Numeric values must be finite.")
        return value

    def selected(self):
        result = self.owner.selected()
        if not result:
            raise ValueError("Select project datasets in the list on the left.")
        return result

    def invalidate(self, *args):
        self.pending = []
        self.report = None
        self.add_button.setEnabled(False)
        self.export_button.setEnabled(False)
        if hasattr(self, "summary"):
            self.table.setRowCount(0)
            self.summary.setPlainText("Inputs changed. Calculate again to update the preview.")
            self.result_tabs.setCurrentWidget(self.summary)

    def show_error(self, message):
        self.pending = []
        self.report = None
        self.add_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.summary.setPlainText(message)
        self.table.setRowCount(0)
        self.result_tabs.setCurrentWidget(self.summary)

    def start(self):
        if self.worker is not None:
            return
        try:
            # Snapshot every project input, so later edits cannot change a running
            # fit or cause an old preview to be applied to newly edited data.
            self.inputs = [(ds, signature(ds)) for ds in self.owner.project.datasets]
            job = self.job()
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.invalidate()
        self.owner.set_busy(True)
        self.summary.setPlainText("Calculating…")
        self.worker = Calculation(job, self)
        self.worker.succeeded.connect(self.receive)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.owner.set_busy(False)

    def receive(self, result):
        if not self.inputs_unchanged():
            self.show_error("Project inputs changed during calculation. Calculate again.")
            return
        self.pending, report, plots = result
        self.report = {**report, "plots": plots}
        self.draw(plots)
        self.summary.setPlainText(json.dumps(report, default=lambda v: v.tolist(), indent=2))
        self.show_table(report)
        self.add_button.setEnabled(bool(self.pending))
        self.export_button.setEnabled(True)

    def show_table(self, report):
        if "weights" in report:
            headers = ["Standard", "Weight", "Standard error"]
            rows = [
                [name, weight, report["weight_stderr"].get(name)] for name, weight in report["weights"].items()
            ]
        elif "explained_variance_ratio" in report:
            headers = ["Component", "Explained variance", "Cumulative variance"]
            ratios = report["explained_variance_ratio"]
            rows = [[i + 1, value, total] for i, (value, total) in enumerate(zip(ratios, np.cumsum(ratios)))]
        else:
            details = report.get("details", {})
            if isinstance(details, dict):
                details = [details]
            headers = ["Dataset / parameter", "Value"]
            rows = []
            for detail in details:
                rows.extend([[key, value] for key, value in detail.items()])
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                if isinstance(value, (float, np.floating)):
                    text = f"{value:.7g}"
                elif value is None:
                    text = "Not estimated"
                else:
                    text = str(value)
                self.table.setItem(i, j, QtWidgets.QTableWidgetItem(text))
        self.result_tabs.setCurrentWidget(self.table)

    def inputs_unchanged(self):
        current = {id(ds) for ds in self.owner.project.datasets}
        return all(id(ds) in current and signature(ds) == stamp for ds, stamp in self.inputs)

    def add_results(self):
        if not self.pending:
            return
        if not self.inputs_unchanged():
            self.show_error("Source data or normalization changed. Calculate again before adding results.")
            return
        outputs = self.pending[:]
        report = self.report
        names = {ds.name for ds in self.owner.project.datasets}
        for ds in outputs:
            stem, number = ds.name, 2
            while ds.name in names:
                ds.name = f"{stem} ({number})"
                number += 1
            names.add(ds.name)
            self.owner.project.append(ds)
        self.last_added = outputs
        self.report = report
        self.export_button.setEnabled(report is not None)
        self.undo_button.setEnabled(True)
        self.summary.setPlainText(f"Added {len(outputs)} new dataset(s). Originals are preserved.")

    def undo_addition(self):
        ids = {id(ds) for ds in self.last_added}
        for i in reversed(range(len(self.owner.project.datasets))):
            if id(self.owner.project.datasets[i]) in ids:
                self.owner.project.removeDatasetIndex(i)
        self.last_added = []
        self.undo_button.setEnabled(False)
        self.summary.setPlainText("Removed the last results added by this widget.")

    def export(self):
        if self.report is None:
            return
        if not self.inputs_unchanged():
            self.show_error("Inputs changed. Calculate again before exporting.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export analysis", "analysis.json", "JSON (*.json)")
        if path:
            try:
                analysis.export_report(path, self.report)
            except Exception as exc:
                self.summary.setPlainText(f"Could not export: {exc}")

    def draw(self, plots):
        self.figure.clear()
        for i, spec in enumerate(plots):
            ax = self.figure.add_subplot(len(plots), 1, i + 1)
            for item in spec["curves"]:
                ax.plot(item["x"], item["y"], label=item["label"], **item.get("style", {}))
            ax.set(title=spec["title"], xlabel=spec["xlabel"], ylabel=spec["ylabel"])
            if "xlim" in spec:
                ax.set_xlim(spec["xlim"])
            ax.legend(fontsize="small")
            ax.grid(alpha=0.2)
        self.canvas.draw_idle()

    def show_inputs(self):
        try:
            self.draw(
                [
                    plot_spec(
                        "Selected spectra",
                        [curve(ds.energy, analysis.normalized_group(ds).norm, ds.name) for ds in self.selected()],
                    )
                ]
            )
        except Exception as exc:
            self.show_error(str(exc))

    def pick(self, event):
        pass


class CalibrationWidget(AnalysisPage):
    def __init__(self, owner):
        super().__init__(
            owner,
            "Select datasets to shift and choose the measured foil scan or its simultaneous reference. "
            "Larch assigns an edge feature to a known energy; ISS fits a separately loaded calibrated foil. "
            "Include the measured foil in the left selection if you also want a calibrated copy of it.",
        )
        self.foil = self.dataset_choice("Foil scan")
        self.method = self.choice(
            "Calibration method", [("Larch edge feature", "larch"), ("ISS reference-spectrum fit", "iss")]
        )
        self.reference = self.check("Use the foil scan's simultaneous -log(ir/it) channel")
        self.target = self.field("Assigned foil energy (eV)")
        self.measured = self.field("Measured feature (eV; blank = Larch edge finder)")
        self.standard = self.dataset_choice("Calibrated reference foil (ISS)")
        self.window = self.field("ISS fit half-window about reference edge (eV)", 25)
        self.method.currentIndexChanged.connect(self.update_method)
        self.update_method()

    def update_method(self):
        iss = self.method.currentData() == "iss"
        self.measured.setEnabled(not iss)
        self.standard.setEnabled(iss)
        self.window.setEnabled(iss)
        self.form.labelForField(self.target).setText(
            "Reference edge / fit center (eV)" if iss else "Assigned foil energy (eV)"
        )
        self.set_help(self.target, "Reference edge / fit center (eV)" if iss else "Assigned foil energy (eV)")

    def show_inputs(self):
        try:
            foil = self.foil.currentData()
            group = analysis.normalized_group(foil, self.reference.isChecked())
            if self.method.currentData() == "iss":
                standard = self.standard.currentData()
                ref = analysis.normalized_group(standard)
                self.draw(
                    [
                        plot_spec(
                            "Measured and calibrated reference foils",
                            [
                                curve(group.energy, group.flat, foil.name),
                                curve(ref.energy, ref.flat, standard.name + " / reference"),
                            ],
                            ylabel="Flattened mu",
                        )
                    ]
                )
                return
            self.draw(
                [
                    plot_spec(
                        "Foil derivative — click to choose the measured feature",
                        [curve(group.energy, group.dmude, foil.name)],
                        ylabel="d(norm mu)/dE",
                    )
                ]
            )
        except Exception as exc:
            self.show_error(str(exc))

    def pick(self, event):
        if (
            self.method.currentData() == "larch"
            and self.controls.isEnabled()
            and event.inaxes
            and event.button == 1
            and not self.canvas.toolbar.mode
        ):
            self.measured.setText(f"{event.xdata:.4f}")

    def job(self):
        sources = [analysis.snapshot(ds) for ds in self.selected()]
        foil = analysis.snapshot(self.foil.currentData())
        method = self.method.currentData()
        if method == "iss" and self.standard.currentData() is self.foil.currentData():
            raise ValueError("Choose a separate, calibrated reference foil for ISS calibration.")
        target = self.number(self.target)
        measured = self.number(self.measured, True) if method == "larch" else None
        standard = analysis.snapshot(self.standard.currentData()) if method == "iss" else None
        window = self.number(self.window) if method == "iss" else 25.0
        reference = self.reference.isChecked()

        def calculate():
            outputs, details = analysis.calibrate(
                sources, foil, target, measured, reference, method=method, standard=standard, window=window
            )
            result = correction_result(sources, outputs, details)
            if "fit" in details:
                fit = details["fit"]
                result[2].append(
                    plot_spec(
                        "ISS reference fit",
                        [
                            curve(fit["energy"], fit["reference"], "Reference"),
                            curve(fit["energy"], fit["fitted"], "Fitted foil"),
                        ],
                        ylabel="Flattened mu",
                    )
                )
            return result

        return calculate


class AlignmentWidget(AnalysisPage):
    def __init__(self, owner):
        super().__init__(
            owner,
            "Select scans to align and a standard. With simultaneous references enabled, "
            "each scan's foil is aligned and that shift is applied to its sample. Without them, "
            "alignment fits the selected sample spectra directly.",
        )
        self.standard = self.dataset_choice("Alignment standard")
        self.reference = self.check("Align simultaneous -log(ir/it) reference channels")
        self.array = self.choice(
            "Fit signal", [("Derivative", "dmude"), ("Normalized mu", "norm"), ("Raw mu", "mu")]
        )
        self.lower = self.field("Window start relative to standard E0 (eV)", -15)
        self.upper = self.field("Window end relative to standard E0 (eV)", 35)

    def job(self):
        sources = [analysis.snapshot(ds) for ds in self.selected()]
        standard = analysis.snapshot(self.standard.currentData())
        lo, hi = self.number(self.lower), self.number(self.upper)
        reference, array = self.reference.isChecked(), self.array.currentData()

        def calculate():
            outputs, details = analysis.align(sources, standard, lo, hi, reference, array)
            result = correction_result(sources, outputs, details)
            ref = analysis.normalized_group(standard, reference)
            curves = [curve(ref.energy, getattr(ref, array), standard.name + " / standard")]
            for source, output in zip(sources, outputs):
                for ds in (source, output):
                    group = analysis.normalized_group(ds, reference)
                    curves.append(curve(group.energy, getattr(group, array), ds.name))
            result[2].append(plot_spec("Alignment signals", curves, ylabel=array))
            return result

        return calculate


class DeglitchWidget(AnalysisPage):
    def __init__(self, owner):
        super().__init__(
            owner,
            "Plot inputs, choose one or multiple points, and click to mark samples with red crosses; "
            "click a marked point again to unmark it. Range mode uses two clicks. "
            "The cleaned-only preview shows the remaining samples separately from the original.",
        )
        self.mode = self.choice(
            "Method",
            [
                ("Remove one point", "point"),
                ("Remove multiple points", "points"),
                ("Remove energy range", "range"),
                ("Larch median spike replacement", "automatic"),
            ],
        )
        self.lower = self.field("Point / range start (eV)")
        self.upper = self.field("Range end (eV)")
        self.points = self.field("Selected point energies (eV; comma separated)")
        self.clear_button = QtWidgets.QPushButton("Clear marked points")
        self.clear_button.setToolTip("Clear the selected point energies without editing any project data.")
        self.form.addRow(self.clear_button)
        self.clear_button.clicked.connect(self.points.clear)
        self.window = self.field("Median window (odd number of points)", 5)
        self.threshold = self.field("Spike threshold (sigma)", 3)
        self.next_end = False
        self.mode.currentIndexChanged.connect(self.change_mode)
        for control in (self.lower, self.upper, self.points):
            control.textChanged.connect(self.refresh_marks)
        owner.dataset_list.itemSelectionChanged.connect(self.reset_selection)
        self.change_mode()

    def change_mode(self):
        mode = self.mode.currentData()
        self.next_end = False
        for control, enabled in (
            (self.lower, mode in ("point", "range")),
            (self.upper, mode == "range"),
            (self.points, mode == "points"),
            (self.clear_button, mode == "points"),
            (self.window, mode == "automatic"),
            (self.threshold, mode == "automatic"),
        ):
            control.setEnabled(enabled)
        self.refresh_marks()

    def reset_selection(self):
        self.points.clear()
        self.next_end = False
        self.refresh_marks()

    def selection_options(self):
        mode = self.mode.currentData()
        if mode == "points":
            points = [float(value) for value in re.split(r"[,;\s]+", self.points.text().strip()) if value]
            return dict(points=points)
        if mode == "point":
            return dict(point=self.number(self.lower))
        return dict(lower=self.number(self.lower), upper=self.number(self.upper))

    @staticmethod
    def marked_curves(ds, mask):
        return [
            curve(ds.energy, ds.mu, ds.name + " / original", color="0.6", linewidth=0.8),
            curve(
                ds.energy[~mask],
                ds.mu[~mask],
                ds.name + " / marked",
                color="crimson",
                marker="x",
                linestyle="None",
                markersize=8,
                markeredgewidth=2,
            ),
        ]

    def refresh_marks(self, *args):
        if self.figure.axes and self.owner.selected() and self.controls.isEnabled():
            limits = self.figure.axes[0].get_xlim()
            self.show_inputs()
            for ax in self.figure.axes:
                ax.set_xlim(limits)
            self.canvas.draw_idle()

    def show_inputs(self):
        try:
            curves = []
            for ds in self.selected():
                try:
                    mask = analysis.removal_mask(ds.energy, **self.selection_options())
                except ValueError:
                    mask = np.ones(len(ds.energy), dtype=bool)
                if self.mode.currentData() == "automatic":
                    mask[:] = True
                curves.extend(self.marked_curves(ds, mask))
            self.draw([plot_spec("Raw data — red crosses mark samples to remove", curves, ylabel="mu")])
        except Exception as exc:
            self.show_error(str(exc))

    def pick(self, event):
        if self.controls.isEnabled() and event.inaxes and event.button == 1 and not self.canvas.toolbar.mode:
            if self.mode.currentData() == "automatic" or not self.owner.selected():
                return
            if self.mode.currentData() == "points":
                x = np.asarray(self.selected()[0].energy)
                if not x[0] <= event.xdata <= x[-1]:
                    return
                index = int(np.argmin(abs(x - event.xdata)))
                try:
                    current = self.selection_options()["points"]
                except ValueError:
                    current = []
                indices = {int(np.argmin(abs(x - energy))) for energy in current}
                indices.symmetric_difference_update({index})
                self.points.setText(", ".join(f"{x[i]:.12g}" for i in sorted(indices)))
                return
            control = self.upper if self.mode.currentData() == "range" and self.next_end else self.lower
            control.setText(f"{event.xdata:.4f}")
            self.next_end = not self.next_end

    def job(self):
        sources = [analysis.snapshot(ds) for ds in self.selected()]
        mode = self.mode.currentData()
        opts = {}
        if mode == "automatic":
            window = self.number(self.window)
            if not window.is_integer():
                raise ValueError("Median window must be an integer.")
            opts = dict(automatic=True, window=int(window), threshold=self.number(self.threshold))
        else:
            opts = self.selection_options()
        limits = self.figure.axes[0].get_xlim() if self.figure.axes else None

        def calculate():
            results = [analysis.deglitch(ds, **opts) for ds in sources]
            outputs, details = zip(*results)
            marked = []
            for ds, detail in zip(sources, details):
                mask = analysis.removal_mask(ds.energy, points=detail["energies_eV"])
                marked.extend(self.marked_curves(ds, mask))
            plots = [
                plot_spec("Original — removed/replaced samples marked", marked, ylabel="mu"),
                plot_spec(
                    "Cleaned data only — dots are remaining samples",
                    [curve(ds.energy, ds.mu, ds.name, marker=".", markersize=3) for ds in outputs],
                    ylabel="mu",
                ),
            ]
            if limits is not None:
                for spec in plots:
                    spec["xlim"] = limits
            return (
                list(outputs),
                {"details": details},
                plots,
            )

        return calculate


class LinearCombinationWidget(AnalysisPage):
    def __init__(self, owner):
        super().__init__(
            owner,
            "Select two or more standards in the left list. Choose the target below. "
            "Weights are bounded between 0 and 1. Align and normalize all spectra before fitting; "
            "blank bounds use their shared energy range.",
        )
        self.target = self.dataset_choice("Spectrum to fit")
        self.array = self.choice(
            "Fit signal", [("Normalized mu", "norm"), ("Flattened mu", "flat"), ("Derivative", "dmude")]
        )
        self.lower = self.field("Fit start (eV; blank = shared start)")
        self.upper = self.field("Fit end (eV; blank = shared end)")
        self.sum_one = self.check("Constrain weights to sum to one", True)
        self.autoalign = self.check("Autoalign standards to the target before fitting")
        self.alignment_lower = self.field("Autoalignment start relative to target E0 (eV)", -15)
        self.alignment_upper = self.field("Autoalignment end relative to target E0 (eV)", 35)

    def job(self):
        standards, target = self.selected(), self.target.currentData()
        if any(ds is target for ds in standards):
            raise ValueError("Select only standards in the left list; the target must be separate.")
        standards, target = [analysis.snapshot(ds) for ds in standards], analysis.snapshot(target)
        lo, hi = self.number(self.lower, True), self.number(self.upper, True)
        array, sum_one = self.array.currentData(), self.sum_one.isChecked()
        autoalign = self.autoalign.isChecked()
        align_lo = self.number(self.alignment_lower) if autoalign else -15.0
        align_hi = self.number(self.alignment_upper) if autoalign else 35.0

        def calculate():
            result = analysis.linear_combination(
                target,
                standards,
                lo,
                hi,
                array,
                sum_one,
                autoalign=autoalign,
                alignment_emin=align_lo,
                alignment_emax=align_hi,
            )
            report = {
                "provenance": result.provenance,
                "weights": result.weights,
                "weight_stderr": {key: value.stderr for key, value in result.params.items()},
                "r_factor": result.rfactor,
                "chi_square": result.chisqr,
                "reduced_chi_square": result.redchi,
                "alignment_shifts": result.alignment_shifts,
            }
            curves = [curve(result.xdata, result.ydata, "Target"), curve(result.xdata, result.yfit, "Fit")]
            curves += [curve(result.xdata, value, key) for key, value in result.ycomps.items()]
            return (
                [],
                report,
                [
                    plot_spec("Linear combination fit", curves, ylabel=array),
                    plot_spec(
                        "Residual",
                        [curve(result.xdata, result.ydata - result.yfit, "Target - fit")],
                        ylabel="Residual",
                    ),
                ],
            )

        return calculate


class PCAWidget(AnalysisPage):
    def __init__(self, owner):
        super().__init__(
            owner,
            "Select at least three aligned spectra. PCA is mean centered without scaling "
            "each scan to unit variance. Inspect explained variance and reconstruction errors when "
            "choosing a component count; components are mathematical patterns, not chemical standards.",
        )
        self.array = self.choice(
            "Signal", [("Normalized mu", "norm"), ("Flattened mu", "flat"), ("Derivative", "dmude")]
        )
        self.lower = self.field("Start (eV; blank = shared start)")
        self.upper = self.field("End (eV; blank = shared end)")
        self.components = self.field("Components for reconstruction", 2)

    def job(self):
        sources = [analysis.snapshot(ds) for ds in self.selected()]
        lo, hi = self.number(self.lower, True), self.number(self.upper, True)
        count = self.number(self.components)
        if not count.is_integer():
            raise ValueError("Component count must be an integer.")
        array = self.array.currentData()

        def calculate():
            model = analysis.principal_components(sources, lo, hi, array, int(count))
            report = {
                "provenance": model.provenance,
                "labels": model.labels,
                "explained_variance_ratio": model.variances,
                "scores": model.scores,
                "reconstruction_rms": [float(np.sqrt(np.mean((fit.ydat - fit.yfit) ** 2))) for fit in model.fits],
            }
            plots = [
                plot_spec(
                    "Explained variance",
                    [curve(np.arange(1, len(model.variances) + 1), model.variances, "Variance fraction")],
                    "Component",
                    "Fraction",
                ),
                plot_spec(
                    "Principal components",
                    [
                        curve(model.x, values, f"PC {i + 1}")
                        for i, values in enumerate(model.components[: int(count)])
                    ],
                    ylabel="Component amplitude",
                ),
                plot_spec(
                    "Scores",
                    [
                        curve(np.arange(1, len(sources) + 1), model.scores[:, i], f"PC {i + 1}")
                        for i in range(int(count))
                    ],
                    "Spectrum index (see Results / Details for names)",
                    "Score",
                ),
                plot_spec(
                    "Reconstructions",
                    [
                        curve(fit.x, values, f"{label} / {kind}")
                        for label, fit in zip(model.labels, model.fits)
                        for kind, values in (("input", fit.ydat), ("reconstruction", fit.yfit))
                    ],
                    ylabel=array,
                ),
            ]
            return [], report, plots

        return calculate


class SelfAbsorptionWidget(AnalysisPage):
    def __init__(self, owner):
        super().__init__(
            owner,
            "Select fluorescence spectra. FLUO corrects over-absorption for a homogeneous, "
            "optically thick sample. Supply the full sample composition (including diluent) and "
            "angles measured from the sample surface. This model does not account for finite thickness.",
        )
        self.formula = self.field("Sample formula / stoichiometry")
        self.element = self.field("Absorbing element")
        self.edge = self.choice("Edge", [(x, x) for x in ("K", "L3", "L2", "L1")])
        self.line = self.choice("Detected fluorescence line", [(x, x) for x in ("Ka", "Kb", "La", "Lb")])
        self.angle_in = self.field("Incidence angle from surface (degrees)", 45)
        self.angle_out = self.field("Exit angle from surface (degrees)", 45)
        self.fluorescence = self.check("Selected mu values are fluorescence intensity / incident intensity")

    def job(self):
        if not self.fluorescence.isChecked():
            raise ValueError("Select fluorescence mu data and confirm the signal type above.")
        sources = [analysis.snapshot(ds) for ds in self.selected()]
        opts = dict(
            formula=self.formula.text().strip(),
            element=self.element.text().strip().capitalize(),
            edge=self.edge.currentData(),
            line=self.line.currentData(),
            angle_in=self.number(self.angle_in),
            angle_out=self.number(self.angle_out),
        )

        def calculate():
            results = [analysis.self_absorption(ds, **opts) for ds in sources]
            outputs, details = zip(*results)
            return correction_result(sources, list(outputs), details)

        return calculate


class NormalizationWidget(AnalysisPage):
    def __init__(self, owner):
        super().__init__(
            owner,
            "Preview Larch normalization on selected spectra. Pre/post-edge limits are "
            "relative to E0. Blank fields let Larch choose defaults. Existing project processing "
            "is retained until you add a new copy.",
        )
        self.fields = {
            key: self.field(label)
            for key, label in (
                ("e0", "Edge energy E0 (eV)"),
                ("pre1", "Pre-edge start relative to E0 (eV)"),
                ("pre2", "Pre-edge end relative to E0 (eV)"),
                ("norm1", "Post-edge start relative to E0 (eV)"),
                ("norm2", "Post-edge end relative to E0 (eV)"),
            )
        }
        self.order = self.choice(
            "Normalization polynomial order", [("Automatic", None)] + [(str(n), n) for n in range(4)]
        )
        self.flattening = self.choice("Flattening", [("Larch", "larch"), ("Existing XView convention", "legacy")])

    def job(self):
        sources = [analysis.snapshot(ds) for ds in self.selected()]
        options = {key: self.number(control, True) for key, control in self.fields.items()}
        options.update(nnorm=self.order.currentData(), flatten_method=self.flattening.currentData())
        for lo, hi in (("pre1", "pre2"), ("norm1", "norm2")):
            if options[lo] is not None and options[hi] is not None and options[lo] >= options[hi]:
                raise ValueError("Normalization range start must be below its end.")

        def calculate():
            outputs = [
                analysis.derived(ds, ds.energy, ds.mu, "normalized", options, options=options) for ds in sources
            ]
            result = correction_result(sources, outputs, options)
            result[2].append(
                plot_spec("Flattened spectra", [curve(ds.energy, ds.flat, ds.name) for ds in outputs])
            )
            return result

        return calculate


class XASToolsWidget(QtWidgets.QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.dataset_combos = []
        layout = QtWidgets.QHBoxLayout(self)
        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter)
        sidebar = QtWidgets.QWidget()
        side = QtWidgets.QVBoxLayout(sidebar)
        label = QtWidgets.QLabel("Project datasets\nCtrl/Shift-click to select multiple")
        label.setToolTip(
            "Select inputs for the active tool; choose standards for LCA or spectra to process for other tools."
        )
        side.addWidget(label)
        self.dataset_list = QtWidgets.QListWidget()
        self.dataset_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        side.addWidget(self.dataset_list)
        splitter.addWidget(sidebar)
        self.tabs = QtWidgets.QTabWidget()
        splitter.addWidget(self.tabs)
        splitter.setSizes([250, 1050])
        splitter.setStretchFactor(1, 1)
        self.pages = []
        for title, cls in (
            ("Calibration", CalibrationWidget),
            ("Alignment", AlignmentWidget),
            ("Deglitch", DeglitchWidget),
            ("Linear combination", LinearCombinationWidget),
            ("PCA", PCAWidget),
            ("Self absorption", SelfAbsorptionWidget),
            ("Normalization", NormalizationWidget),
        ):
            page = cls(self)
            self.pages.append(page)
            self.tabs.addTab(page, title)
        self.dataset_list.itemSelectionChanged.connect(self.invalidate)
        project.datasets_changed.connect(self.refresh)
        self.refresh()

    def selected(self):
        return [item.data(QtCore.Qt.UserRole) for item in self.dataset_list.selectedItems()]

    def invalidate(self):
        for page in self.pages:
            page.invalidate()

    def refresh(self, *args):
        selected = {id(ds) for ds in self.selected()}
        self.dataset_list.blockSignals(True)
        self.dataset_list.clear()
        for ds in self.project.datasets:
            item = QtWidgets.QListWidgetItem(ds.name)
            item.setData(QtCore.Qt.UserRole, ds)
            self.dataset_list.addItem(item)
            item.setSelected(id(ds) in selected)
        self.dataset_list.blockSignals(False)
        for combo in self.dataset_combos:
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for ds in self.project.datasets:
                combo.addItem(ds.name, ds)
                if ds is current:
                    combo.setCurrentIndex(combo.count() - 1)
            combo.blockSignals(False)
        self.invalidate()

    def set_busy(self, busy):
        self.dataset_list.setEnabled(not busy)
        for page in self.pages:
            page.controls.setEnabled(not busy)
            page.run_button.setEnabled(not busy)
            page.plot_button.setEnabled(not busy)
            page.undo_button.setEnabled(not busy and bool(page.last_added))
        # Keep exports/adding results disabled while any calculation is running.
        if busy:
            for page in self.pages:
                page.add_button.setEnabled(False)
                page.export_button.setEnabled(False)
        else:
            for page in self.pages:
                page.add_button.setEnabled(bool(page.pending))
                page.export_button.setEnabled(page.report is not None)

    def wait_for_workers(self):
        # QApplication shutdown must not destroy a running QThread.
        for page in self.pages:
            if page.worker is not None:
                page.worker.wait()


def install_xas_tools(gui):
    """Attach native analysis widgets to an existing XviewGui instance."""
    if not hasattr(gui, "widget_xas_tools"):
        gui.widget_xas_tools = XASToolsWidget(gui.project, gui)
        gui.tabWidget_xfit.addTab(gui.widget_xas_tools, "XAS tools")
        QtWidgets.QApplication.instance().aboutToQuit.connect(gui.widget_xas_tools.wait_for_workers)
    install_control_help(gui)
    return gui.widget_xas_tools
