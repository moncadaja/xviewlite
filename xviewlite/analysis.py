"""Validated, non-destructive XAS operations using Larch's Python API.

The GUI passes XASDataSet objects; all calculations use detached Larch groups.
Corrections return new datasets so raw data and earlier processing stay available.
"""

import json
from copy import copy, deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
from larch import Group
from larch.math import lincombo_fit
from larch.math.deglitch import remove_spikes_scipy
from larch.math.pca import pca_fit, pca_train_sklearn
from larch.xafs import energy_align, find_e0, fluo_corr, pre_edge
from xraydb import chemparse, material_mu, xray_edge, xray_line


def arrays(energy, mu):
    """Reject ambiguous grids and nonfinite data instead of silently repairing them."""
    x, y = np.asarray(energy, dtype=float), np.asarray(mu, dtype=float)
    if x.ndim != 1 or y.shape != x.shape or x.size < 8:
        raise ValueError("A spectrum needs at least eight energy/mu pairs.")
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError("Energy and mu must be finite. Remove invalid points before analysis.")
    if np.any(np.diff(x) <= 0):
        raise ValueError("Energy must be strictly increasing with no duplicate points.")
    return x.copy(), y.copy()


def spectrum(ds, reference=False):
    if reference:
        frame = getattr(ds, "df", None)
        if frame is None or "mur" not in frame or "energy" not in frame:
            raise ValueError(f"{ds.name}: no simultaneous reference (-log(ir/it)) is available.")
        return arrays(frame["energy"], frame["mur"])
    return arrays(ds.energy, ds.mu)


def normalization_options(ds):
    return {
        key: getattr(ds, key)
        for key in ("e0", "pre1", "pre2", "norm1", "norm2", "nnorm")
        if getattr(ds, key, None) is not None
    }


def normalized_group(ds, reference=False):
    x, y = spectrum(ds, reference)
    group = Group(energy=x, mu=y, filename=ds.name)
    # A reference channel has its own edge and normalization, not the sample's.
    pre_edge(group, **({} if reference else normalization_options(ds)))
    if not np.isfinite(group.norm).all() or abs(group.edge_step) < 1.0e-12:
        raise ValueError(f"{ds.name}: normalization failed or has a zero edge step.")
    if not reference and getattr(ds, "flatten_method", "legacy") == "legacy":
        group.flat = group.norm + (x > group.e0) * (1 - (group.post_edge - group.pre_edge) / group.edge_step)
    return group


def record(operation, sources, **parameters):
    return {
        "operation": operation,
        "sources": [ds.name for ds in sources],
        "parameters": parameters,
        "xraylarch": version("xraylarch"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }


def snapshot(ds):
    """Copy the XAS data without duplicating unrelated detector image stacks."""
    shallow = copy(ds)
    shallow.__dict__.pop("ext_data", None)
    return deepcopy(shallow)


def derived(ds, energy, mu, operation, parameters, *, mask=None, shift=0, options=None):
    """Reprocess a copy, keeping reference data on the corrected energy grid."""
    from xas.xasproject import XASDataSet

    x, y = arrays(energy, mu)
    out = snapshot(ds)
    # Older datasets without supplied metadata inherit XASDataSet._md at class
    # level. Give the copy its own mapping before updating the processing E0.
    out._md = deepcopy(ds.md)
    out.name = f"{ds.name} [{operation}]"
    out.energy = x
    out.larch = Group(energy=x.copy(), mu=y.copy())
    out.mu = y
    for attr in ("norm", "flat", "bkg", "k", "chi", "r", "chir", "chir_mag", "chir_re", "chir_im", "kwin"):
        out.__dict__.pop(attr, None)
    if getattr(out, "e0", None) is not None:
        out.e0 += shift
    if "e0" in out.md and out.md["e0"] is not None:
        out.md["e0"] = float(out.md["e0"]) + shift
    frame = getattr(out, "df", None)
    if frame is not None:
        if mask is not None:
            if len(frame) != len(mask) or not np.allclose(frame["energy"], ds.energy):
                raise ValueError("Reference data and spectrum must share a grid for point removal.")
            frame = frame.iloc[np.flatnonzero(mask)].copy()
        if "energy" in frame:
            frame["energy"] = frame["energy"] + shift
        out.df = frame
    # Extended detector arrays may have unrelated axes. Leave them on the source
    # rather than attaching potentially stale scan coordinates to a corrected copy.
    out.__dict__.pop("ext_data", None)
    for key, value in (options or {}).items():
        setattr(out, key, value)
    out.update_larch()
    out.normalize_force()
    out.deriv()
    out.md["e0"] = float(out.e0)
    if not np.isfinite(out.norm).all():
        raise ValueError("Corrected spectrum could not be normalized.")
    out.analysis_history = deepcopy(getattr(ds, "analysis_history", []))
    out.analysis_history.append(record(operation, [ds], **parameters))
    # Guarantee the public dataset contract rather than retaining a partial copy.
    if not isinstance(out, XASDataSet):
        raise TypeError("Expected an XASDataSet.")
    return out


def calibrate(datasets, foil, target, measured=None, reference=False, method="larch", standard=None, window=25.0):
    """Assign a measured foil feature to a known energy, applying one shift."""
    if method == "iss":
        return calibrate_iss(datasets, foil, standard, target, window, reference)
    if method != "larch":
        raise ValueError("Choose the Larch or ISS calibration method.")
    x, y = spectrum(foil, reference)
    target = float(target)
    observed = float(find_e0(x, y)) if measured is None else float(measured)
    if not np.isfinite([target, observed]).all() or target <= 0 or not x[0] < observed < x[-1]:
        raise ValueError("Enter a positive target and a measured feature within the foil scan.")
    shift = target - observed
    params = {
        "method": "Larch edge feature",
        "foil": foil.name,
        "reference_channel": reference,
        "target_eV": target,
        "measured_eV": observed,
        "shift_eV": shift,
    }
    return [
        derived(ds, np.asarray(ds.energy) + shift, ds.mu, "calibrated", params, shift=shift) for ds in datasets
    ], params


def calibrate_iss(datasets, foil, standard, edge_energy, window=25.0, reference=False):
    """Offline counterpart of ISS get_energy_offset, using its exact pure fitter."""
    from xas.energy_calibration import compute_shift_between_spectra

    if standard is None:
        raise ValueError("ISS calibration needs a separately loaded, calibrated foil reference.")
    if not np.isfinite([edge_energy, window]).all() or edge_energy <= 0 or window <= 0:
        raise ValueError("Use a positive reference edge energy and fit half-window.")
    source = normalized_group(foil, reference)
    ref = normalized_group(standard)
    # Match get_energy_offset: flattened measured foil, a half-height coarse
    # offset, then the shift/scale/cubic-baseline least-squares refinement.
    x, mu, xr, yr = source.energy, source.flat, ref.energy, ref.flat
    selected = (xr >= edge_energy - window) & (xr <= edge_energy + window)
    if selected.sum() < 8 or xr[0] > edge_energy - window or xr[-1] < edge_energy + window:
        raise ValueError("Reference foil must cover the entire calibration window with at least eight points.")
    roi, expected = xr[selected], yr[selected]
    if np.ptp(expected) < 0.1:
        raise ValueError("The reference window must contain a varying absorption edge.")
    coarse = float(xr[np.argmin(abs(yr - 0.5))] - x[np.argmin(abs(mu - 0.5))])
    if roi[0] < x[0] + coarse or roi[-1] > x[-1] + coarse:
        raise ValueError("The measured foil does not cover the reference window after the coarse shift.")
    residual_shift, fitted = compute_shift_between_spectra(x + coarse, mu, roi, expected)
    # The upstream fitter subtracts its shift from the input energy; our GUI
    # reports the net shift to ADD to every selected sample energy axis.
    shift = float(coarse - residual_shift)
    if not np.isfinite(shift) or roi[0] < x[0] + shift or roi[-1] > x[-1] + shift:
        raise ValueError("ISS calibration would extrapolate outside the measured foil.")
    rms = float(np.linalg.norm(fitted - expected) / max(np.linalg.norm(expected), 1.0e-30))
    if not np.isfinite(rms) or rms > 0.25:
        raise ValueError("ISS calibration fit is poor; inspect the reference and calibration window.")
    params = {
        "method": "ISS half-height + shift/scale/cubic baseline",
        "foil": foil.name,
        "standard": standard.name,
        "reference_channel": reference,
        "edge_eV": edge_energy,
        "half_window_eV": window,
        "coarse_shift_eV": coarse,
        "shift_eV": shift,
        "relative_rms": rms,
    }
    outputs = [
        derived(ds, np.asarray(ds.energy) + shift, ds.mu, "calibrated", params, shift=shift) for ds in datasets
    ]
    return outputs, {**params, "fit": {"energy": roi, "reference": expected, "fitted": fitted}}


def align(datasets, standard, emin=-15.0, emax=35.0, reference=False, array="dmude"):
    """Fit an energy shift for each spectrum or its simultaneous reference."""
    if array not in ("dmude", "norm", "mu"):
        raise ValueError("Choose derivative, normalized mu, or raw mu for alignment.")
    if not np.isfinite([emin, emax]).all() or emin >= emax:
        raise ValueError("Alignment limits must be increasing offsets from the reference E0.")
    ref = normalized_group(standard, reference)
    lower, upper = ref.e0 + emin, ref.e0 + emax
    if lower < ref.energy[0] or upper > ref.energy[-1]:
        raise ValueError("The alignment window extends outside the reference scan.")
    outputs, reports = [], []
    for ds in datasets:
        group = normalized_group(ds, reference)
        if lower < group.energy[0] or upper > group.energy[-1]:
            raise ValueError(f"{ds.name}: the alignment window is outside the scan.")
        selected = (ref.energy >= lower) & (ref.energy <= upper)
        if selected.sum() < 8 or np.ptp(getattr(ref, array)[selected]) < 1.0e-10:
            raise ValueError("Choose a window with at least eight points and a varying edge feature.")
        # Larch 2026.3.1 subtracts emin internally despite documenting signed
        # offsets. Convert here so the visible window is the one actually fitted.
        shift = float(energy_align(group, ref, array=array, emin=-emin, emax=emax))
        if not np.isfinite(shift) or abs(shift) >= 49.9:
            raise ValueError(f"{ds.name}: alignment reached Larch's +/-50 eV limit; calibrate first.")
        if lower < group.energy[0] + shift or upper > group.energy[-1] + shift:
            raise ValueError("Alignment would extrapolate outside the shifted scan.")
        # energy_align catches optimizer errors internally. Independently assess
        # the returned shift, rejecting a fit that cannot reproduce the feature.
        from scipy.interpolate import CubicSpline

        target = getattr(ref, array)[selected]
        fitted = CubicSpline(group.energy + shift, getattr(group, array))(ref.energy[selected])
        scale = np.dot(fitted, target) / max(np.dot(fitted, fitted), 1.0e-30)
        relative_rms = np.linalg.norm(scale * fitted - target) / max(np.linalg.norm(target), 1.0e-30)
        if relative_rms > 0.25:
            raise ValueError(
                f"{ds.name}: poor alignment fit (relative RMS {relative_rms:.3f}); inspect the window."
            )
        params = {
            "standard": standard.name,
            "reference_channel": reference,
            "array": array,
            "emin": emin,
            "emax": emax,
            "shift_eV": shift,
            "relative_rms": float(relative_rms),
        }
        outputs.append(derived(ds, np.asarray(ds.energy) + shift, ds.mu, "aligned", params, shift=shift))
        reports.append({"dataset": ds.name, **params})
    return outputs, reports


def removal_mask(energy, *, point=None, points=None, lower=None, upper=None):
    """Resolve chosen energies to measured samples, once per input grid."""
    x = np.asarray(energy)
    mask = np.ones(len(x), dtype=bool)
    if points is not None or point is not None:
        selected = np.asarray(points if points is not None else [point], dtype=float)
        if selected.ndim != 1 or not selected.size or not np.isfinite(selected).all():
            raise ValueError("Select one or more finite point energies.")
        if np.any(selected < x[0]) or np.any(selected > x[-1]):
            raise ValueError("A selected point is outside the scan.")
        mask[np.unique([np.argmin(abs(x - value)) for value in selected])] = False
    else:
        if lower is None or upper is None or not np.isfinite([lower, upper]).all() or lower > upper:
            raise ValueError("Select points or an increasing energy range to remove.")
        mask[(x >= lower) & (x <= upper)] = False
    if mask.all():
        raise ValueError("No data points lie in the selected range.")
    return mask


def deglitch(ds, lower=None, upper=None, point=None, automatic=False, window=5, threshold=3.0, points=None):
    """Remove selected points or propose Larch median-filter replacements."""
    x, y = spectrum(ds)
    if automatic:
        if window < 3 or window % 2 != 1 or window >= len(y) or not np.isfinite(threshold) or threshold <= 0:
            raise ValueError("Use an odd window of at least 3 points and a positive threshold.")
        clean = remove_spikes_scipy(y, window=window, threshold=threshold)
        changed = clean != y
        if not changed.any():
            raise ValueError("No spikes found with these settings.")
        params = {
            "method": "Larch median replacement",
            "window": window,
            "threshold": threshold,
            "energies_eV": x[changed].tolist(),
        }
        return derived(ds, x, clean, "deglitched", params), params
    mask = removal_mask(x, point=point, points=points, lower=lower, upper=upper)
    params = {
        "method": "point removal",
        "energies_eV": x[~mask].tolist(),
        "indices": np.flatnonzero(~mask).tolist(),
    }
    return derived(ds, x[mask], y[mask], "deglitched", params, mask=mask), params


def common_groups(datasets, lower, upper, array="norm"):
    """Interpolate only within every input's support, with explicit fit bounds."""
    if array not in ("norm", "flat", "dmude"):
        raise ValueError("Choose normalized, flattened, or derivative data.")
    groups = [normalized_group(ds) for ds in datasets]
    if not groups:
        raise ValueError("Select datasets first.")
    lo, hi = max(g.energy[0] for g in groups), min(g.energy[-1] for g in groups)
    lower = lo if lower is None else float(lower)
    upper = hi if upper is None else float(upper)
    if not np.isfinite([lower, upper]).all() or lower >= upper or lower < lo or upper > hi:
        raise ValueError(f"Use a shared energy interval within {lo:.2f} to {hi:.2f} eV.")
    grid = groups[0].energy
    grid = grid[(grid >= lower) & (grid <= upper)]
    if len(grid) < max(8, len(groups) + 2):
        raise ValueError("The fit interval contains too few data points.")
    from scipy.interpolate import CubicSpline

    for i, group in enumerate(groups):
        values = CubicSpline(group.energy, getattr(group, array))(grid)
        group.energy = grid.copy()
        setattr(group, array, values)
        group.filename = f"{i + 1}: {datasets[i].name}"
    return groups


def linear_combination(
    target,
    standards,
    lower=None,
    upper=None,
    array="norm",
    sum_to_one=True,
    autoalign=False,
    alignment_emin=-15.0,
    alignment_emax=35.0,
):
    if len(standards) < 2 or len({id(ds) for ds in standards}) != len(standards):
        raise ValueError("Select at least two distinct standards.")
    if any(ds is target for ds in standards):
        raise ValueError("The target cannot also be one of its standards.")
    fit_standards = standards
    shifts = []
    if autoalign:
        fit_standards, shifts = align(standards, target, emin=alignment_emin, emax=alignment_emax)
        for original, aligned in zip(standards, fit_standards):
            aligned.name = original.name
    groups = common_groups([target, *fit_standards], lower, upper, array)
    matrix = np.column_stack([getattr(group, array) for group in groups[1:]])
    if np.linalg.matrix_rank(matrix) < len(standards):
        raise ValueError("Standards are linearly dependent in this interval; remove redundant standards.")
    result = lincombo_fit(
        groups[0],
        groups[1:],
        arrayname=array,
        minvals=[0.0] * len(standards),
        maxvals=[1.0] * len(standards),
        sum_to_one=sum_to_one,
        vary_e0=False,
    )
    weights = np.array(list(result.weights.values()))
    if (
        not result.result.success
        or not np.isfinite(result.yfit).all()
        or not np.isfinite(weights).all()
        or np.any(weights < -1.0e-8)
        or np.any(weights > 1 + 1.0e-8)
        or (sum_to_one and not np.isclose(weights.sum(), 1.0, atol=1.0e-5))
    ):
        raise ValueError("The constrained fit did not converge. Review the standards and energy interval.")
    result.provenance = record(
        "linear combination",
        [target, *standards],
        array=array,
        lower=float(result.xdata[0]),
        upper=float(result.xdata[-1]),
        sum_to_one=sum_to_one,
        bounds=[0.0, 1.0],
        autoalignment=autoalign,
        alignment_shifts=shifts,
    )
    result.alignment_shifts = shifts
    return result


def principal_components(datasets, lower=None, upper=None, array="norm", ncomponents=2):
    if len(datasets) < 3:
        raise ValueError("Select at least three spectra for PCA.")
    if not 1 <= ncomponents < len(datasets):
        raise ValueError("Use at least one component and fewer components than spectra.")
    groups = common_groups(datasets, lower, upper, array)
    matrix = np.array([getattr(group, array) for group in groups])
    if np.linalg.norm(matrix - matrix.mean(axis=0)) < 1.0e-10:
        raise ValueError("PCA requires variation between spectra.")
    # The sklearn wrapper implements conventional mean-centered PCA and handles
    # spectra equal to the ensemble mean (pca_train divides those by zero).
    model = pca_train_sklearn(groups, arrayname=array)
    fits = []
    for group in groups:
        pca_fit(group, model, ncomps=ncomponents, rescale=False)
        fits.append(group.pca_result)
    model.scores = model.model.transform(model.ydat)
    model.fits = fits
    model.ncomponents = ncomponents
    model.provenance = record(
        "PCA",
        datasets,
        array=array,
        lower=float(model.x[0]),
        upper=float(model.x[-1]),
        ncomponents=ncomponents,
        method="Larch sklearn wrapper, mean centered, no rescaling",
    )
    return model


def self_absorption(ds, formula, element, edge="K", line="Ka", angle_in=45.0, angle_out=45.0):
    """FLUO correction for a homogeneous, optically thick fluorescence sample."""
    if not (0 < angle_in <= 90 and 0 < angle_out <= 90):
        raise ValueError("Incidence and exit angles must be in (0, 90] degrees from the sample surface.")
    try:
        composition = chemparse(formula)
        edge_info, line_info = xray_edge(element, edge), xray_line(element, line)
        if element not in composition or composition[element] <= 0 or edge_info is None or line_info is None:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ValueError("Enter a valid formula containing the absorber, edge, and fluorescence line.") from None
    if not line.upper().startswith(edge[0].upper()):
        raise ValueError("The fluorescence line must belong to the selected edge shell.")
    group = normalized_group(ds)
    if not group.energy[0] < edge_info.energy < group.energy[-1]:
        raise ValueError("The selected absorption edge is outside this scan.")
    if group.edge_step <= 0:
        raise ValueError("Fluorescence correction requires a positive absorption edge step.")
    # Reject the pole of the FLUO correction even if it happens to produce
    # finite, sign-inverted values at every sampled energy.
    coefficients = material_mu(
        formula, [line_info.energy, edge_info.energy - 10, edge_info.energy + 10], density=1
    )
    jump = coefficients[2] - coefficients[1]
    if jump <= 0:
        raise ValueError("The composition has no positive absorption jump at the chosen edge.")
    alpha = (
        coefficients[0] * np.sin(np.deg2rad(angle_in)) / np.sin(np.deg2rad(angle_out)) + coefficients[1]
    ) / jump
    if np.any(alpha + 1 - group.norm <= 0):
        raise ValueError("FLUO correction is singular for this spectrum, composition, and geometry.")
    fluo_corr(
        group.energy,
        group.mu,
        formula,
        element,
        group=group,
        edge=edge,
        line=line,
        anginp=angle_in,
        angout=angle_out,
        **normalization_options(ds),
    )
    if not np.isfinite(group.mu_corr).all() or not np.isfinite(group.norm_corr).all():
        raise ValueError("The correction is singular for this composition and geometry.")
    params = {
        "formula": formula,
        "element": element,
        "edge": edge,
        "line": line,
        "angle_in": angle_in,
        "angle_out": angle_out,
        "model": "FLUO, homogeneous optically thick sample",
    }
    return derived(ds, group.energy, group.mu_corr, "self-absorption corrected", params), params


def export_report(path, report):
    """Write portable analysis parameters and numerical results (not a pickle)."""

    def encode(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(f"Cannot export {type(value).__name__}")

    Path(path).write_text(json.dumps(report, default=encode, indent=2, allow_nan=False) + "\n")
