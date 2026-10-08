"""ISS XAFS analysis tools."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("xviewlite")
except PackageNotFoundError:
    __version__ = "0+unknown"
