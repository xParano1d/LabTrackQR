# main.py
import tkinter as tk
import threading
import queue
import pystray
import subprocess
from PIL import Image
import sys
import os
from datetime import datetime

from config import ALLOWED_VIDS, ALLOWED_PIDS, SAVE_PATH
from local_storage import CsvStorage
from scanner import ScannerManager
from overlay import NotificationManager

message_queue = queue.Queue()

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def setup_tray(root, scanner_mgr):
    try:
        img_path = resource_path("icon.png") 
        image = Image.open(img_path)
    except FileNotFoundError:
        image = Image.new('RGB', (64, 64), color = (73, 109, 137))

    def trigger_new_sample_form(icon, item):
        message_queue.put("COMMAND:OPEN_FORM")

    def trigger_removal_mode(icon, item):
        scanner_mgr.removal_mode = True
        message_queue.put("COMMAND:WAITING_FOR_REMOVAL_SCAN")

    def trigger_log_viewer(icon, item):
        message_queue.put("COMMAND:OPEN_LOG_VIEWER")

    def trigger_user_manager(icon, item):
        message_queue.put("COMMAND:OPEN_USER_MANAGER")

    def on_quit(icon, item):
        icon.stop()
        root.quit() 
        os._exit(0) 

    menu = pystray.Menu(
        pystray.MenuItem("Add New Sample", trigger_new_sample_form),
        pystray.MenuItem("Remove Sample", trigger_removal_mode), 
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Manage Employees (QR Codes)", trigger_user_manager),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("View Logs", trigger_log_viewer), 
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR", image, "LabTrackQR", menu)
    icon.run()
    
if __name__ == "__main__":
    storage = CsvStorage(SAVE_PATH)
    scanner_mgr = ScannerManager(ALLOWED_VIDS, ALLOWED_PIDS, message_queue, storage)
    scanner_mgr.start_monitoring()

    app = NotificationManager(message_queue, storage, scanner_mgr)
    threading.Thread(target=setup_tray, args=(app.root, scanner_mgr), daemon=True).start()
    
    app.run()