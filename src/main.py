# main.py
import tkinter as tk
import threading
import queue
import pystray
import sys
import os
import winreg
from PIL import Image

from config import ALLOWED_VIDS, ALLOWED_PIDS, SAVE_PATH, EMPLOYEES_PATH, HISTORY_DIR, NETWORK_SYNC_PATH, SYNC_INTERVAL_SECONDS
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

# --- WINDOWS STARTUP REGISTRY LOGIC ---
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LabTrackQR"

def set_autostart(enable):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            # Safely handles both Python scripts and compiled .exe files
            exe_path = os.path.abspath(sys.argv[0])
            if not exe_path.endswith('.exe'):
                exe_path = f'"{sys.executable}" "{exe_path}"'
            else:
                exe_path = f'"{exe_path}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Registry Error: {e}")

def is_autostart_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False

# Application State
state = {'autostart': is_autostart_enabled()}

def setup_tray(root, scanner_mgr):
    try:
        img_path = resource_path("icon.ico") 
        image = Image.open(img_path)
    except FileNotFoundError:
        image = Image.new('RGB', (64, 64), color = (73, 109, 137))

    def trigger_new_sample_form(icon, item): message_queue.put("COMMAND:OPEN_FORM")
    def trigger_removal_mode(icon, item): 
        scanner_mgr.removal_mode = True
        message_queue.put("COMMAND:WAITING_FOR_REMOVAL_SCAN")
    def trigger_log_viewer(icon, item): message_queue.put("COMMAND:OPEN_LOG_VIEWER")
    def trigger_user_manager(icon, item): message_queue.put("COMMAND:OPEN_USER_MANAGER")
    
    def toggle_autostart(icon, item):
        state['autostart'] = not state['autostart']
        set_autostart(state['autostart'])

    def on_quit(icon, item):
        icon.stop()
        root.quit() 
        os._exit(0) 

    menu = pystray.Menu(
        pystray.MenuItem("Add New Sample", trigger_new_sample_form),
        pystray.MenuItem("Remove Sample", trigger_removal_mode), 
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Manage Employee Badges", trigger_user_manager),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("View Logs & History", trigger_log_viewer), 
        pystray.Menu.SEPARATOR,
        # Native checked toggle for Startup
        pystray.MenuItem("Run on Windows Startup", toggle_autostart, checked=lambda item: state['autostart']),
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR", image, "LabTrackQR", menu)
    icon.run()
    
if __name__ == "__main__":
    storage = CsvStorage(SAVE_PATH, EMPLOYEES_PATH, HISTORY_DIR, NETWORK_SYNC_PATH, SYNC_INTERVAL_SECONDS)
    scanner_mgr = ScannerManager(ALLOWED_VIDS, ALLOWED_PIDS, message_queue, storage)
    scanner_mgr.start_monitoring()

    app = NotificationManager(message_queue, storage, scanner_mgr)
    threading.Thread(target=setup_tray, args=(app.root, scanner_mgr), daemon=True).start()
    
    app.run()