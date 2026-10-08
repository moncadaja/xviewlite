"""Launch the application from either a console or an IPython session."""

import argparse
import sys


def create_window():
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication.instance() or QApplication(sys.argv)
    from xview.xview import XviewGui
    from xviewlite.widgets import install_xas_tools

    window = XviewGui()
    install_xas_tools(window)
    return app, window


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="open briefly and exit")
    args = parser.parse_args(argv)
    app, window = create_window()
    window.show()
    if args.smoke_test:
        from PyQt5.QtCore import QTimer

        QTimer.singleShot(500, window.close)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
