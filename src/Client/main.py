# main.py
import tkinter as tk
import threading
import queue
import pystray
import sys
import os
import winreg
from PIL import Image
import getpass

from config import ALLOWED_VIDS, ALLOWED_PIDS, SERVER_URL
from local_storage import ApiStorage
from scanner import ScannerManager
from overlay import NotificationManager

message_queue = queue.Queue()

def resource_path(file_name):
    try:
        # COMPILED .exe MODE: PyInstaller extracts everything to the root of _MEIPASS
        base_path = sys._MEIPASS
        return os.path.join(base_path, file_name)
    except Exception:
        # DEVELOPMENT MODE: Calculate path from this script (src/Client) up to the img folder
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "..", "..", "img", file_name)

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

# --- NEW: DETECT TASKBAR THEME ---
def is_taskbar_dark_mode():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        # If SystemUsesLightTheme is 0, the taskbar is dark.
        return value == 0
    except FileNotFoundError:
        return True # Default to dark mode if the registry key doesn't exist

# Application State
state = {'autostart': is_autostart_enabled()}

def setup_tray(root, scanner_mgr):
    try:        
        # If the user has a Light Mode taskbar, invert the white logo to black
        if is_taskbar_dark_mode():
            img_path = resource_path("icon_white.ico") 
            # Convert to RGBA to ensure we have the transparency (Alpha) channel
            image = Image.open(img_path).convert("RGBA")
        else:
            img_path = resource_path("icon_black.ico") 
            # Convert to RGBA to ensure we have the transparency (Alpha) channel
            image = Image.open(img_path).convert("RGBA")
            
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
        pystray.MenuItem("View Logs & History", trigger_log_viewer), 
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Manage Employee Badges", trigger_user_manager),
        pystray.Menu.SEPARATOR,
        # Native checked toggle for Startup
        pystray.MenuItem("Run on Windows Startup", toggle_autostart, checked=lambda item: state['autostart']),
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR", image, "LabTrackQR", menu)
    icon.run()
    
if __name__ == "__main__":
    storage = ApiStorage(SERVER_URL)
    
    # --- THE AD AUTO-LOGIN LOGIC ---
    ad_username = getpass.getuser()
    ad_employee_data = storage.get_employee_by_ad(ad_username)
    
    scanner_mgr = ScannerManager(ALLOWED_VIDS, ALLOWED_PIDS, message_queue, storage)
    
    # Inject AD user if they exist in the DB, otherwise queue Registration
    if ad_employee_data:
        scanner_mgr.ad_fallback_name = ad_employee_data.get('full_name')
    else:
        # User is brand new. Queue a specialized prompt to register their Windows account.
        message_queue.put(f"COMMAND:REGISTER_AD_USER:{ad_username}")

    scanner_mgr.start_monitoring()

    app = NotificationManager(message_queue, storage, scanner_mgr)
    threading.Thread(target=setup_tray, args=(app.root, scanner_mgr), daemon=True).start()
    
    app.run()