# xviewlite

XAFS data analysis package.

The existing PyQt application now includes an **XAS tools** tab with foil
calibration, reference/sample alignment, deglitching, linear combination fitting,
PCA, fluorescence self-absorption correction, and normalization comparison.
Operations provide previews, plots, result tables and JSON export; corrections
can be added as new project datasets with processing history.
See [the Larch review and widget guide](docs/larch-review.md) for workflows,
model assumptions, implementation notes and tests.

Prepare the patched source dependencies, install the locked environment, then launch:

```bash
python scripts/prepare_dependencies.py
pixi install --locked
pixi run start
```

The setup script checks out the revisions in `patches/sources.json` into `.vendor/`
and applies the tracked patches. It is safe to rerun and refuses to replace a
checkout at a different revision. These local checkouts are required by Pixi;
keep them alongside the project.

The patches replace `pkg_resources` in XView, ISS cloud tools, ISS factor tools,
and ISS tools with `importlib.resources`, allowing setuptools 84. Extracted
resources remain available until process exit so Qt can keep using their paths.
XView's RIXS widget also uses the current `matplotlib.colormaps` registry instead
of the removed `matplotlib.cm.get_cmap` API, allowing Matplotlib 3.11.2.
The XAS file readers use `sep=r"\s+"` instead of the removed pandas
`delim_whitespace` argument, so data files load with pandas 3.
XAS flattening uses a pointwise post-edge mask compatible with NumPy 2. This
fixes normalization failures that left `e0` unset and `flat` missing. Dataset
processing calls Larch's Python API without starting its interpreter, avoiding
the wx/Qt event-loop conflict in IPython. Scan metadata accepts both old and new
Larch header capitalization.
The patches can also be applied to the corresponding upstream repositories.
Each source's `patches` list records the order in which they are applied.

The application dependencies are recorded in `pixi.toml` and `pixi.lock`;
patched source revisions are pinned in `patches/sources.json`.
Development and documentation tools are pinned separately in
`requirements-dev.txt` and tested with Python 3.12–3.14 in CI.

Compatibility constraints retained during the dependency update:

- PyQt remains on version 5 because the application imports `PyQt5`.
- `sitka-spruce`, `jeepney`, and `mkl_fft` are explicit dependencies because the
  updated Larch/wxutils Conda packages omit them from their dependency metadata.

Conda provides `pyshortcuts` 1.9.8, but that package reports version 0.0.0 in its
Python distribution metadata. Consequently, `pip check` reports version conflicts
for it even though the required release is installed.

To test the resource refactor after preparing the sources, install
`requirements-dev.txt` and run `python -m pytest`. The resource tests cover both
regular and ZIP-packaged files and check their lifetime and cleanup.

Test the XAS whitespace readers in the application environment with
`pixi run python -m unittest xviewlite.tests.test_xas_file_io -v`.
Test normalization, flattening, background subtraction, and Fourier transforms
with `pixi run python -m unittest xviewlite.tests.test_xas_processing -v`.

Cloud integration is optional: an inaccessible beamline Slack/Dropbox token
disables cloud services but does not prevent local data processing.
