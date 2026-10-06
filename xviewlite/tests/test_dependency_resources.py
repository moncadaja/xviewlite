"""Exercise resource paths used by the patched upstream Qt applications."""

import importlib
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("dependency", ["xview", "isscloudtools", "issfactortools", "isstools"])
@pytest.mark.parametrize("zipped", [False, True])
def test_resource_path_lifetime(dependency, zipped, tmp_path, monkeypatch):
    helper = ROOT / ".vendor" / dependency / dependency / "_resources.py"
    if not helper.exists():
        pytest.skip("Run python scripts/prepare_dependencies.py to test upstream patches")

    package_name = f"resource_fixture_{dependency}_{int(zipped)}"
    package = tmp_path / package_name
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "_resources.py").write_text(helper.read_text())
    (package / "ui").mkdir()
    (package / "ui" / "dialog.ui").write_text("<ui>example</ui>")
    import_path = tmp_path
    if zipped:
        import_path = tmp_path / "resources.zip"
        with zipfile.ZipFile(import_path, "w") as archive:
            for path in package.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(tmp_path))

    monkeypatch.syspath_prepend(str(import_path))
    module = importlib.import_module(f"{package_name}._resources")
    try:
        resource = module.resource_filename("ui/dialog.ui")
        assert isinstance(resource, str)  # Qt expects a filesystem path.
        assert Path(resource).read_text() == "<ui>example</ui>"
        assert module.resource_filename("ui/dialog.ui") == resource
        module._resources.close()
        assert Path(resource).exists() is not zipped
    finally:
        module._resources.close()
        sys.modules.pop(f"{package_name}._resources", None)
        sys.modules.pop(package_name, None)
