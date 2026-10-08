"""One-sentence, domain-specific hover help for native XView controls and titles."""

import re

from PyQt5 import QtWidgets

FORM_HELP = {
    "Foil scan": (
        "Choose the measured foil whose energy offset will be applied to the selected scans; use "
        "a clean foil of the same element and edge."
    ),
    "Calibration method": (
        "Choose Larch to assign an edge feature or ISS to fit a calibrated foil spectrum; start "
        "with Larch unless a trusted reference spectrum is available."
    ),
    "Use the foil scan's simultaneous -log(ir/it) channel": (
        "Use the simultaneous reference channel instead of the scan's main mu; enable only when "
        "ir and it measured the foil."
    ),
    "Assigned foil energy (eV)": (
        "Assign the accepted energy of the chosen foil feature in eV; use the reference value for "
        "that element and edge rather than a universal energy."
    ),
    "Reference edge / fit center (eV)": (
        "Center the ISS fit on the calibrated reference edge in eV; use that foil's accepted edge "
        "energy within both measured scans."
    ),
    "Measured feature (eV; blank = Larch edge finder)": (
        "Specify the observed foil feature within the measured energy range, or leave blank to "
        "start with Larch's edge finder."
    ),
    "Calibrated reference foil (ISS)": (
        "Choose a separate foil spectrum on a trusted energy scale; use the same element and edge "
        "as the measured foil."
    ),
    "ISS fit half-window about reference edge (eV)": (
        "Fit the reference within this distance on either side of its edge; start at 25 eV and "
        "keep the entire interval within both scans."
    ),
    "Alignment standard": (
        "Choose the spectrum defining the desired energy scale; use a clean foil or a chemically "
        "equivalent sample at the same edge."
    ),
    "Align simultaneous -log(ir/it) reference channels": (
        "Align each sample through its simultaneous foil rather than its sample edge; enable when "
        "all selected scans and the standard have valid ir/it references."
    ),
    "Fit signal": (
        "Choose the spectral representation for fitting; start with normalized mu for linear "
        "combinations or the derivative for energy alignment."
    ),
    "Signal": (
        "Choose the spectral representation for PCA; start with normalized mu and use the same "
        "normalization convention for all spectra."
    ),
    "Window start relative to standard E0 (eV)": (
        "Set the alignment window's lower offset from the standard E0; start at -15 eV and keep "
        "it within the common measured range."
    ),
    "Window end relative to standard E0 (eV)": (
        "Set the alignment window's upper offset from the standard E0; start at +35 eV and "
        "include a clear edge feature."
    ),
    "Method": (
        "Choose single-point removal, multiple-point removal, range removal or median "
        "replacement; start with manually identified glitches to preserve real spectral features."
    ),
    "Point / range start (eV)": (
        "Choose a measured point or the start of a glitch interval in eV; keep the selection "
        "inside the scan and as narrow as the glitch permits."
    ),
    "Range end (eV)": (
        "Choose the last energy included in the removed interval; use a value at or above its "
        "start and inside every selected scan."
    ),
    "Selected point energies (eV; comma separated)": (
        "List the energies to remove or click to toggle them on the plot; choose only isolated "
        "glitches within every selected scan."
    ),
    "Median window (odd number of points)": (
        "Set the local median window for automatic spike replacement; start with an odd 3–7 "
        "points and keep it narrower than real spectral features."
    ),
    "Spike threshold (sigma)": (
        "Set the amplitude threshold for Larch's median spike detector; start at 3–5 sigma and "
        "inspect every proposed replacement."
    ),
    "Spectrum to fit": (
        "Choose the unknown spectrum for linear combination fitting; use a target separate from "
        "the selected standards at the same absorption edge."
    ),
    "Fit start (eV; blank = shared start)": (
        "Set the absolute lower fit energy or leave blank for the shared start; a typical XANES "
        "interval begins 20–50 eV below E0."
    ),
    "Fit end (eV; blank = shared end)": (
        "Set the absolute upper fit energy or leave blank for the shared end; a typical XANES "
        "interval ends 50–150 eV above E0."
    ),
    "Constrain weights to sum to one": (
        "Constrain the standard weights to total one while each stays between 0 and 1; normally "
        "enable for consistently normalized spectra."
    ),
    "Autoalign standards to the target before fitting": (
        "Align copies of the standards to the target before fitting; leave disabled when genuine "
        "chemical edge shifts must be preserved."
    ),
    "Autoalignment start relative to target E0 (eV)": (
        "Set the autoalignment window's lower offset from the target E0; start at -15 eV within "
        "the shared measured range."
    ),
    "Autoalignment end relative to target E0 (eV)": (
        "Set the autoalignment window's upper offset from the target E0; start at +35 eV or "
        "narrow it to a common edge feature."
    ),
    "Start (eV; blank = shared start)": (
        "Set the PCA interval's lower absolute energy or leave blank for shared support; start "
        "roughly 20–50 eV below the edge for XANES."
    ),
    "End (eV; blank = shared end)": (
        "Set the PCA interval's upper absolute energy or leave blank for shared support; start "
        "roughly 50–150 eV above the edge for XANES."
    ),
    "Components for reconstruction": (
        "Choose the number of PCA components used to reconstruct spectra; start with 1–3 and keep "
        "the count below the number of selected spectra."
    ),
    "Sample formula / stoichiometry": (
        "Enter the complete sample composition including diluent for FLUO; use measured "
        "stoichiometry such as CuO rather than only the absorber symbol."
    ),
    "Absorbing element": (
        "Enter the absorbing element's chemical symbol; use the element whose edge lies inside "
        "the selected scan."
    ),
    "Edge": (
        "Select the measured absorption edge; normally use K for a K-edge scan or the matching L "
        "edge for an L-edge scan."
    ),
    "Detected fluorescence line": (
        "Select the emission line collected by the detector; normally use Ka for a K edge or the "
        "matching L line for an L edge."
    ),
    "Incidence angle from surface (degrees)": (
        "Enter the beam angle measured from the sample surface in (0, 90] degrees; use the "
        "measured geometry, commonly 45 degrees."
    ),
    "Exit angle from surface (degrees)": (
        "Enter the detector exit angle measured from the sample surface in (0, 90] degrees; use "
        "the measured geometry, commonly 45 degrees."
    ),
    "Selected mu values are fluorescence intensity / incident intensity": (
        "Confirm that the input is fluorescence divided by incident intensity; enable only for "
        "fluorescence data from a homogeneous optically thick sample."
    ),
    "Edge energy E0 (eV)": (
        "Set the normalization edge energy inside the measured scan or leave blank for Larch's "
        "estimate; start near the expected absorption edge."
    ),
    "Pre-edge start relative to E0 (eV)": (
        "Set the lower pre-edge baseline offset from E0; typically start between -200 and -100 eV "
        "where the baseline is smooth."
    ),
    "Pre-edge end relative to E0 (eV)": (
        "Set the upper pre-edge baseline offset from E0; typically use -50 to -20 eV and exclude "
        "edge or pre-edge peaks."
    ),
    "Post-edge start relative to E0 (eV)": (
        "Set the lower normalization-fit offset from E0; typically use +50 to +150 eV beyond the "
        "near-edge structure."
    ),
    "Post-edge end relative to E0 (eV)": (
        "Set the upper normalization-fit offset from E0; typically use +400 to +1000 eV when "
        "measured, without exceeding the scan."
    ),
    "Normalization polynomial order": (
        "Choose the post-edge polynomial degree; start with Automatic or degree 1–2 and avoid "
        "unnecessary high-order curvature."
    ),
    "Flattening": (
        "Choose Larch or the existing XView flattening convention; start with Larch for new "
        "analyses and keep one convention across all fitted spectra."
    ),
}


def form_help(title):
    return FORM_HELP[title]


LEGACY_HELP = {
    "lineEdit_e0": FORM_HELP["Edge energy E0 (eV)"],
    "lineEdit_preedge_lo": FORM_HELP["Pre-edge start relative to E0 (eV)"],
    "lineEdit_preedge_hi": FORM_HELP["Pre-edge end relative to E0 (eV)"],
    "lineEdit_postedge_lo": FORM_HELP["Post-edge start relative to E0 (eV)"],
    "lineEdit_postedge_hi": FORM_HELP["Post-edge end relative to E0 (eV)"],
    "lineEdit_postedge_nnorm": FORM_HELP["Normalization polynomial order"],
    "lineEdit_spline_lo": (
        "Set the minimum k used by the background spline in inverse angstroms; start at 0–3 and "
        "stay below the measured upper k limit."
    ),
    "lineEdit_spline_hi": (
        "Set the maximum k used by the background spline in inverse angstroms; start at 8–12 if "
        "the signal supports it and never exceed the measured range."
    ),
    "lineEdit_clamp_lo": (
        "Set the low-k spline clamp strength; start at 0–1 and increase only to address visible "
        "endpoint artifacts."
    ),
    "lineEdit_clamp_hi": (
        "Set the high-k spline clamp strength; start at 0–1 and inspect the background before " "increasing it."
    ),
    "lineEdit_rbkg": (
        "Set the background cutoff radius in angstroms; start near 1 and keep it below the first "
        "physical coordination-shell peak."
    ),
    "spinBox_k_weight": (
        "Multiply chi(k) by this power of k for analysis; " "normally use integer weights 1–3, starting at 2."
    ),
    "spinBox_r_weight": (
        "Multiply the displayed chi(R) by this power of R; start at 0 for an unweighted transform "
        "or 1–2 to emphasize distant shells."
    ),
    "lineEdit_window_tapering": (
        "Set the Fourier-window taper width in inverse angstroms; start at 1–2 and keep it "
        "smaller than the selected k interval."
    ),
    "lineEdit_k_ft_lo": (
        "Set the lower Fourier-transform k limit in inverse angstroms; start at 2–3 to exclude "
        "the near-edge region."
    ),
    "lineEdit_k_ft_hi": (
        "Set the upper Fourier-transform k limit in inverse angstroms; typically use 8–12 or the "
        "highest range with useful signal."
    ),
    "comboBox_window": (
        "Choose the Fourier-window shape; start with Hanning or Kaiser and use the same window " "for comparisons."
    ),
    "lineEdit_truncate_at": (
        "Choose the truncation boundary in the currently plotted energy or k coordinates; keep it "
        "inside the measured range and retain the region needed for fitting."
    ),
    "lineEdit_range_E_lo": (
        "Set the plotted lower energy offset from E0 in eV; start at -50 for an edge overview or "
        "extend to the measured pre-edge baseline."
    ),
    "lineEdit_range_E_hi": (
        "Set the plotted upper energy offset from E0 in eV; start at +150 for XANES or extend to "
        "the measured EXAFS range."
    ),
    "lineEdit_range_k_lo": (
        "Set the plotted lower k limit in inverse angstroms; normally start at 0–3 within the " "measured range."
    ),
    "lineEdit_range_k_hi": (
        "Set the plotted upper k limit in inverse angstroms; normally use 8–12 when useful signal " "is present."
    ),
    "lineEdit_range_R_lo": (
        "Set the plotted lower R limit in angstroms; start at 0 to see residual background and "
        "the first coordination shell."
    ),
    "lineEdit_range_R_hi": (
        "Set the plotted upper R limit in angstroms; start at 5–6 to inspect the first few " "coordination shells."
    ),
    "lineEdit_default_path": (
        "Choose the root folder containing year, cycle and proposal subfolders; use an existing "
        "readable data directory."
    ),
    "comboBox_year": "Choose the experiment year; select the year recorded in the data directory.",
    "comboBox_cycle": "Choose the experiment cycle; select an available cycle for the chosen year.",
    "comboBox_proposal": "Choose the proposal directory; select the proposal that contains the scans to load.",
    "comboBox_sort_files_by": (
        "Choose how files are sorted; use Time for acquisition order or Name for grouped scan names."
    ),
    "comboBox_data_numerator": (
        "Choose the RIXS signal channel; use the measured detector or emission channel of interest."
    ),
    "comboBox_data_bkg": (
        "Choose the RIXS background channel to subtract; use a physically matched background measurement."
    ),
    "comboBox_data_denominator": (
        "Choose the RIXS normalization channel; normally use incident intensity when its values "
        "are valid and nonzero."
    ),
    "spinBox_contourf_n": (
        "Set the number of contour levels; start at 20–50 and increase only when finer intensity "
        "gradations are useful."
    ),
    "doubleSpinBox_contourf_vmin": (
        "Set the lower contour intensity bound; start at the background level or the finite data minimum."
    ),
    "doubleSpinBox_contourf_vmax": (
        "Set the upper contour intensity bound; start at the finite signal maximum and keep it "
        "above the lower bound."
    ),
    "lineEdit_formula": (
        "Enter the chemical formula used to search reference structures; use the sample "
        "composition, such as CuO."
    ),
    "lineEdit_absorbing_atom": FORM_HELP["Absorbing element"],
    "lineEdit_edge": FORM_HELP["Edge"],
    "lineEdit_tol_increase": (
        "Set the allowed relative increase in MCR fit error; start with a small tolerance around "
        "0–0.01 and inspect convergence."
    ),
    "lineEdit_max_iter": (
        "Set the maximum number of MCR iterations; start around 100–500 and check whether the "
        "residual has converged."
    ),
    "lineEdit_proposal": (
        "Filter scans by proposal identifier; enter the exact proposal number or leave blank for no filter."
    ),
    "lineEdit_pi": "Filter scans by principal investigator; use the recorded name or leave blank for no filter.",
    "lineEdit_element": "Filter scans by absorbing element; use its chemical symbol or leave blank for no filter.",
}
for name, original in {
    "spinBox_kweight_sim": "spinBox_k_weight",
    "comboBox_window_sim": "comboBox_window",
    "doubleSpinBox_kmin_sim": "lineEdit_k_ft_lo",
    "doubleSpinBox_kmax_sim": "lineEdit_k_ft_hi",
}.items():
    LEGACY_HELP[name] = LEGACY_HELP[original]

TITLE_HELP = {
    "E0": LEGACY_HELP["lineEdit_e0"],
    "Pre-edge range": LEGACY_HELP["lineEdit_preedge_lo"],
    "Post-edge range": LEGACY_HELP["lineEdit_postedge_lo"],
    "Polynom order": LEGACY_HELP["lineEdit_postedge_nnorm"],
    "Spline range": LEGACY_HELP["lineEdit_spline_lo"],
    "Spline clamping": LEGACY_HELP["lineEdit_clamp_lo"],
    "k-weight": LEGACY_HELP["spinBox_k_weight"],
    "k weight": LEGACY_HELP["spinBox_k_weight"],
    "Rbkg": LEGACY_HELP["lineEdit_rbkg"],
    "k-range": LEGACY_HELP["lineEdit_k_ft_lo"],
    "Tapering": LEGACY_HELP["lineEdit_window_tapering"],
    "Window": LEGACY_HELP["comboBox_window"],
    "window": LEGACY_HELP["comboBox_window"],
    "R-weight": LEGACY_HELP["spinBox_r_weight"],
    "R range": LEGACY_HELP["lineEdit_range_R_hi"],
    "k range": LEGACY_HELP["lineEdit_range_k_hi"],
    "E range": LEGACY_HELP["lineEdit_range_E_hi"],
    "Truncate": LEGACY_HELP["lineEdit_truncate_at"],
    "Enter Formula": LEGACY_HELP["lineEdit_formula"],
    "Absorbing Atom": FORM_HELP["Absorbing element"],
    "Edge": FORM_HELP["Edge"],
    "kmin": LEGACY_HELP["lineEdit_k_ft_lo"],
    "kmax": LEGACY_HELP["lineEdit_k_ft_hi"],
    "Sort by": LEGACY_HELP["comboBox_sort_files_by"],
    "n_cont": LEGACY_HELP["spinBox_contourf_n"],
    "vmin": LEGACY_HELP["doubleSpinBox_contourf_vmin"],
    "vmax": LEGACY_HELP["doubleSpinBox_contourf_vmax"],
    "max iter": LEGACY_HELP["lineEdit_max_iter"],
    "tol increase": LEGACY_HELP["lineEdit_tol_increase"],
}


def install_control_help(root):
    """Attach help after the legacy .ui files and the new form widgets are built."""
    for control in root.findChildren(QtWidgets.QWidget):
        if control.toolTip():
            continue
        if isinstance(control, (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox)):
            message = LEGACY_HELP.get(control.objectName())
            if isinstance(control, QtWidgets.QComboBox) and control.findText("ConstraintNonneg") >= 0:
                message = (
                    "Choose the MCR constraint to apply to concentrations or spectra; start with "
                    "nonnegativity when physically appropriate and avoid unnecessary constraints."
                )
            if message is None and control.parentWidget() is not None:
                message = control.parentWidget().toolTip()
            if message:
                control.setToolTip(message)
        elif isinstance(control, QtWidgets.QLabel):
            title = re.sub(r"<[^>]+>", "", control.text()).strip()
            if title in TITLE_HELP:
                control.setToolTip(TITLE_HELP[title])
        elif isinstance(control, QtWidgets.QListWidget):
            control.setToolTip(
                (
                    "Choose datasets or channels for the active operation; use Ctrl/Shift-click to select "
                    "multiple entries where supported."
                )
            )
    project = getattr(root, "widget_project", None)
    if project is not None:
        for title, field in (("label_16", "lineEdit_clamp_lo"), ("label_29", "lineEdit_clamp_hi")):
            label = project.findChild(QtWidgets.QLabel, title)
            if label is not None:
                label.setToolTip(LEGACY_HELP[field])
