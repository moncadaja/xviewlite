"""Keep original metadata while accepting old and new Larch header casing."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def scan_metadata():
    path = Path(__file__).resolve().parents[2] / ".vendor/xview/xview/_metadata.py"
    if not path.exists():
        pytest.skip("Run python scripts/prepare_dependencies.py")
    spec = importlib.util.spec_from_file_location("scan_metadata", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scan_metadata


@pytest.mark.parametrize(
    "beamline,field",
    [("ISS (8-ID)", "Scan_edge_energy_eV"), ("ISS (8-ID)", "scan_edge_energy_ev"), ("QAS", "E0"), ("QAS", "e0")],
)
def test_edge_energy_case(scan_metadata, beamline, field):
    metadata = {"Beamline_name": beamline, field: "7112", "Scan_uid": "example"}
    result = scan_metadata(metadata)
    assert result == {**metadata, "e0": "7112"}
    assert metadata[field] == "7112"


def test_missing_edge_is_not_invented(scan_metadata):
    metadata = {"Beamline_name": "ISS (8-ID)", "Scan_uid": "example"}
    assert scan_metadata(metadata) == metadata
