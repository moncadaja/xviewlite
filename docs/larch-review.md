# Larch review and PyQt analysis tools

Reviewed against **xraylarch 2026.3.1**, the release installed by `pixi.lock`, on
2026-10-07. This records the behavior of that installed release; it is not a
claim that every function or every subsequent Larch release has been validated.
The calculations use its Python API and do not start a Larch/wx GUI or interpreter.

## Existing processing

| Path | Finding and change |
| --- | --- |
| Normalization (`pre_edge`) | Already uses the supported group API. Copy the actual polynomial order and fitted ranges back from `pre_edge_details`, so the GUI and subsequent reprocessing agree with the calculation. |
| Flattening | Preserve the existing XView convention for old datasets. The new Normalization widget offers Larch's `group.flat` as an explicit alternative. These conventions can give different baselines and should not be mixed indiscriminately in fits. |
| Background removal (`autobk`) | Retain the existing controls. Initial extraction now exposes `k` alongside `chi`. Corrected datasets discard stale background and transform arrays; the Project plots recompute them. |
| Fourier transform (`xftf`) | Fix reversed real/imaginary assignments. Honor the configured k-weight and preserve the selected transform upper bound. |
| R-weight control | Larch's forward `xftf` ignores the old `rweight` keyword (R weighting belongs to the inverse transform API). Apply this existing GUI control to the plotted R-space curves, keeping the underlying complex transform unweighted. Correct the axis label. |
| Reference-channel import | Build `mut`, `muf`, and `mur` independently. A scan without `iff` now retains its simultaneous foil `mur = -log(ir/it)`. |
| FEFF path simulation | Existing code uses `feffpath`, `ff2chi`, `xftf`, and `get_feff_pathinfo`. This work does not add a nonlinear FEFF fitting interface or validate external FEFF executables/Materials Project services. |
| Statistics/MCR and RIXS | The old Statistics tab is mostly inactive code, so the new PCA widget lives in XAS tools. MCR and RIXS primarily use other packages. R-space fixes apply to the active XAS Project widget. |

The adapter is in `xviewlite/analysis.py`; the native widgets are in
`xviewlite/widgets.py`. `launch_xview_gui.py` attaches them to the existing window.
Dependency changes are retained as ordered patches, not untracked edits inside
the Pixi installation.

## Using the widgets

Start with `pixi run start`. Load scans into **XAS Project**, then open the new
**XAS tools** tab. The dataset list follows project additions and removals.
Ctrl/Shift-click selects several datasets. Each operation has its own widget,
inputs, plot, result table, and export button.
Hover over an edit/select control or its title for one-sentence help and starting
ranges where applicable; these are starting points, not universal fit limits,
and all intervals must remain within the measured data.

Calculations run in a worker thread. **Preview / calculate** does not change the
project. For corrections, **Add results as new datasets** creates named copies;
**Undo last addition** removes those copies. Original data remain available.
Changing inputs invalidates a preview, and edits to source arrays or normalization
are checked again before applying it. Errors are shown in the Details panel.

Corrected copies retain source filenames, reference channels, normalization
parameters and an `analysis_history` containing operation settings, source names,
UTC time and the Larch version. Energy shifts also move E0 and reference-channel
coordinates. Point removal masks the reference channel on the same grid.
Extended detector arrays remain on the source dataset; corrected copies omit
them rather than attach arrays with potentially inconsistent coordinates.

Save corrected copies through the existing Project save function. Fit/PCA results
are exported separately with **Export results (JSON)**, including numerical plot
arrays, parameters, weights/scores and statistics. Matplotlib's toolbar exports
figures. Reloading an exported analysis report into the widget is not implemented.

### Foil calibration

1. Select all scans that should receive the same energy offset.
2. Select **Larch edge feature** and choose the foil scan; enable its simultaneous reference option if the foil is
   represented by `-log(ir/it)` rather than the scan's main mu array.
3. Enter the assigned foil energy. Use **Plot inputs** and click the measured
   derivative feature, enter that energy directly, or leave it blank to use
   Larch's `find_e0`.
4. Preview, inspect the shift, and add copies. Include the foil in the selection
   if it should also be saved on the calibrated scale.

The applied shift is `assigned - measured`, added to every selected energy axis.
Calibration does not confuse choosing a normalization E0 with moving the energy
axis. The choice of reference feature/accepted foil energy is explicit; no foil
energy table or universal inflection convention is imposed.

Alternatively, choose **ISS reference-spectrum fit** and select a separate,
calibrated foil from the project as the reference. Enter its accepted edge energy
as the fit center and a half-window (start at 25 eV). This follows
[`NSLS2/iss-profile-collection`'s monochromator calibration](https://github.com/NSLS2/iss-profile-collection/blob/b2c6b292c51ec4983d041165aff6b6ce641bd13a/startup/70-beamline_plans.py#L97):
`get_energy_offset` first matches the half-height and then calls
`xas.energy_calibration.compute_shift_between_spectra` to fit a shift, scale and
cubic baseline. The widget reuses that pure fitter from the pinned XAS dependency,
with project foil spectra replacing beamline database/library access and no
hardware operations. The reported net shift is **added** to the energy axis;
it has the opposite sign to the fitter's subtracted residual shift. A reference
fit plot shows the match, and the original spectra remain unchanged.

### Alignment

Choose a standard and an interval expressed as signed offsets from its E0.
Derivative, normalized mu and raw mu fitting are available via `energy_align`.
For reference-based alignment, enable simultaneous channels: each sample's foil
is fitted to the standard's foil and its shift is transferred to the sample.
This preserves genuine chemical differences in the sample spectrum. For separate
foil files, calibrate/align those as spectra, then use the measured shift in the
calibration workflow to transfer it to the associated samples.

Larch 2026.3.1 implements its lower limit as `reference.e0 - emin`, despite the
docstring describing signed offsets. The adapter changes the sign of that
argument so a displayed -15 to +35 eV interval includes the edge. Recheck this
adapter when upgrading Larch. Larch also catches optimizer errors internally;
the adapter rejects boundary shifts near +/-50 eV, missing overlap, featureless
windows and fits with a relative RMS mismatch above 0.25. Inspect the overlaid
alignment signals; a numerically good match does not establish chemical identity.

### Deglitching

Remove a single point, select multiple points, remove an inclusive energy interval, or preview spike
replacement using `larch.math.deglitch.remove_spikes_scipy`. **Plot inputs** shows
raw mu. In **Remove multiple points** mode, clicking toggles the nearest measured
point and updates a comma-separated energy list; red crosses mark every selected
sample, and **Clear marked points** clears the list. The same selected energies
are resolved to the nearest measured samples in every selected scan. In range
mode successive clicks fill start/end. The calculated preview separates the
original data with marked removals from a **cleaned-data-only** plot whose dots
are the remaining samples, so the original glitches cannot hide the correction.
The current energy zoom is retained while marking and previewing.
Automatic mode takes an odd median window and a sigma threshold. It uses Larch's
threshold definition, not a robust local noise estimator. Inspect it carefully
around narrow edge features. Point removal keeps the remaining measured values;
the automatic method replaces detected spikes with the local median.

### Linear combination fitting

Select standards in the left list and choose a separate target in the widget.
Use normalized mu, flattened mu, or the normalized derivative. Bounds are
absolute energies; blank bounds use the common measured support. Data are
interpolated onto the target grid within that support before `lincombo_fit`.
Weights are bounded to [0, 1], with an optional sum-to-one constraint. Rank-deficient
standards and failed constraints are rejected.

The result table shows weights and estimated standard errors; Details includes
R-factor, chi-square and reduced chi-square. Plots show the target, fit, weighted
standards and residual. These are unweighted fits: no measurement-error model is
assumed, so standard errors and chi-square are not a complete uncertainty budget.
The optional **Autoalign standards to the target before fitting** checkbox aligns
copies of the standards with Larch's derivative fit, then performs LCA on those
copies. Its default window is -15 to +35 eV relative to the target E0 and can be
adjusted independently of the LCA fit interval. Details and exported provenance
record each standard's shift. It is off by default because aligning chemically
different standards can remove real chemical shifts and bias their weights.
Exhaustive standard-combination searches and jointly fitting shifts and weights
are not implemented; choose the candidate standards explicitly.

### PCA

Select at least three aligned spectra, an energy range, a signal and a component
count. The widget uses Larch's `pca_train_sklearn` and `pca_fit(rescale=False)`.
It performs conventional mean-centered PCA without per-spectrum variance scaling.
This handles a spectrum equal to the ensemble mean; Larch 2026.3.1's separate
`pca_train` implementation divides that case by a zero standard deviation.

Results include explained/cumulative variance, component spectra, scores and
reconstructions with RMS errors. Component count must be below the number of
spectra. Component signs are arbitrary, and components are not chemical species
or concentration fractions. Automatic component-count selection and independent
target-transform testing are not implemented.

### Fluorescence self-absorption

`fluo_corr` implements Haskel's FLUO correction for homogeneous, optically thick
samples. Supply the full composition (including diluent), absorbing element,
edge, detected emission line, and incidence/exit angles measured from the sample
surface. Confirm that the selected signal is fluorescence/incident intensity.
The GUI cannot reliably infer this from old project metadata.

The adapter checks composition, edge coverage, line shell, positive edge step,
angles and the correction's singularity. Preview the corrected normalized signal
and add a copy only after reviewing the assumptions. This is not a finite-thickness
correction, and it is not applicable to transmission mu.

### Normalization comparison

The extra Normalization widget exposes E0, relative pre/post-edge ranges,
polynomial order and Larch versus legacy flattening. Blank values use Larch's
defaults. It produces new datasets whose parameters remain editable in XAS Project.

## Validation

Run in the application environment:

```bash
pixi run python -m unittest xviewlite.tests.test_analysis xviewlite.tests.test_analysis_widgets xviewlite.tests.test_xas_processing xviewlite.tests.test_xas_file_io xviewlite.tests.test_prepare_dependencies -v
```

Tests cover known shifts (including foil-to-sample transfer), original-data
preservation, point/automatic deglitching, known mixture weights, rank-one PCA
reconstruction including a mean spectrum, shared-grid bounds, FLUO agreement with
Larch, complex FT components, normalization synchronization, report export and
all seven native widgets, including ISS reference calibration, LCA autoalignment,
mouse-driven multiple-point marking, cleaned-only curves and hover help for form titles.
A full offscreen launcher check also exercises importing
a scan without `iff`, calibrated-copy insertion and E/K/R plotting. These checks
use synthetic spectra; scientific validation on representative beamline data is
still needed before relying on results for an experiment.

API reference: [Larch documentation](https://xraypy.github.io/xraylarch/).
Implementation details were checked in the installed `larch/xafs/pre_edge.py`,
`xafsft.py`, `fluo.py`, `math/lincombo_fitting.py`, `math/pca.py`, and
`math/deglitch.py`.
