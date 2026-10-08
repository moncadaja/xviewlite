"""IPython entry point; use `xviewlite` for a standalone Qt event loop."""
from xviewlite.launch import create_window

app, xview_gui = create_window()


def xview():
    xview_gui.show()


xview()
# Integrate Qt with IPython, which owns the event loop in this launcher.
try:
    get_ipython().enable_gui("qt5")
except NameError:
    app.exec_()
