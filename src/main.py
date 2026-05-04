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

def setup_tray(root):
    try:
        img_path = resource_path("icon.png") 
        image = Image.open(img_path)
    except FileNotFoundError:
        image = Image.new('RGB', (64, 64), color = (73, 109, 137))

    def trigger_new_sample_form(icon, item):
        message_queue.put("COMMAND:OPEN_FORM")

    # Opens the live state
    def open_inventory(icon, item):
        try:
            os.startfile(SAVE_PATH)
        except Exception as e:
            print(f"[Error] Could not open inventory file: {e}")

    # Dynamically opens this month's log
    def open_logs(icon, item):
        month_str = datetime.now().strftime("%Y_%m")
        history_file = f"history_log_{month_str}.csv"
        try:
            os.startfile(history_file)
        except Exception:
            # If the file hasn't been created yet this month
            message_queue.put(f"No logs yet for {month_str}")

    def on_quit(icon, item):
        icon.stop()
        root.quit() 
        os._exit(0) 

    menu = pystray.Menu(
        pystray.MenuItem("Add new item", trigger_new_sample_form),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("View Inventory", open_inventory),
        pystray.MenuItem("View History Logs", open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR", image, "LabTrackQR", menu)
    icon.run()
    
if __name__ == "__main__":
    # 1. Initialize Local CSV Storage & Hardware
    storage = CsvStorage(SAVE_PATH)
    scanner_mgr = ScannerManager(ALLOWED_VIDS, ALLOWED_PIDS, message_queue, storage)
    
    scanner_mgr.start_monitoring()

    # 2. Setup the Notification Manager
    app = NotificationManager(message_queue, storage)

    # 3. Start System Tray
    threading.Thread(target=setup_tray, args=(app.root,), daemon=True).start()

    # 4. Run the UI Loop
    app.run()