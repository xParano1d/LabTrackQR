# main.py
import tkinter as tk
import threading
import queue
import pystray
import subprocess
from PIL import Image
import sys
import os

from config import ALLOWED_VIDS, ALLOWED_PIDS, SAVE_PATH
from local_storage import TxtStorage
from scanner import ScannerManager
from overlay import NotificationManager

message_queue = queue.Queue()


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
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

    def open_logs(icon, item):
        try:
            # Popen opens the file in the background without freezing our app
            subprocess.Popen(['notepad.exe', SAVE_PATH])
        except Exception as e:
            print(f"[Error] Could not open log file: {e}")

    def on_quit(icon, item):
        icon.stop()
        root.quit() 
        os._exit(0) 

    menu = pystray.Menu(
        pystray.MenuItem("Running in Background", action=None, enabled=False),
        pystray.MenuItem("View Logs", open_logs),
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR", image, "LabTrackQR", menu)
    icon.run()

if __name__ == "__main__":
    # 1. Initialize Local TXT Storage & Hardware
    storage = TxtStorage(SAVE_PATH)
    scanner_mgr = ScannerManager(ALLOWED_VIDS, ALLOWED_PIDS, message_queue, storage)
    
    scanner_mgr.start_monitoring()

    # 2. Setup the Notification Manager
    app = NotificationManager(message_queue)

    # 3. Start System Tray (Pass the hidden root)
    threading.Thread(target=setup_tray, args=(app.root,), daemon=True).start()

    # 4. Run the UI Loop
    app.run()