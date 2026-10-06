# .ipython/profile_default/startup/00-startup.py
import IPython
from PyQt5 import QtCore, QtWidgets

# Configure scaling before the IPython input hook can create the application.
if QtWidgets.QApplication.instance() is None:
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

# 2. Crucial: Tell IPython to manage the Qt event loop in the background
ip = IPython.get_ipython()
if ip is not None:
    ip.run_line_magic("gui", "qt5")

print("Portable Xview IPython environment loaded. Ready to launch GUI!")
