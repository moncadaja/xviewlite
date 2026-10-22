import databroker
from qtpy.QtWidgets import QApplication
from qtpy import uic, QtCore
import sys
from xview import xview
# from xview.spectra_db.db_io import get_spectrum_catalog
import os
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# plt.ion()

# db = databroker.Broker.named('iss')

# try:
#     db = databroker.Broker.named('iss')
# except Exception as e:
#     print(f'Failed to open ISS databroker: {e}')
#     db = None


# try:
#     from xas.handlers import register_all_handlers
#     register_all_handlers(db)
# except Exception as e:
#     pass

# # catalogs
# try:
#     db_archive_catalog = databroker.catalog['iss']
# except Exception as e:
#     print(f'Failed to open ISS archive databroker catalog: {e}')
#     db_archive_catalog = None

# try:
#     db_catalog = databroker.catalog['iss-local']
# except Exception as e:
#     print(f'Failed to open ISS databroker catalog: {e}')
#     db_catalog = None

# try:
#     db_proc = get_spectrum_catalog()
# except Exception as e:
#     print(f'Failed to open ISS processed database: {e}')
#     db_proc = None

import sys
sys.stdout.write('\33]0;XView terminal\a')
sys.stdout.flush()


# os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
db = None
db_proc = None
db_archive_catalog=None
db_catalog=None

app = QApplication(sys.argv)
if hasattr(QtCore.Qt, "AA_EnableHighDpiScaling"):  # Qt5 only; Qt6 is always high-DPI aware
    app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
xview_gui = xview.XviewGui(db=db, db_proc=db_proc, db_archive_catalog=db_archive_catalog, db_catalog=db_catalog)
# xview_gui = xview.XviewGui(db=None, db_proc=None, db_archive_catalog=None, db_catalog=None)

def xview():
    xview_gui.show()

xview()
