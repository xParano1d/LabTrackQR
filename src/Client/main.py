# main.py
import customtkinter as ctk
ctk.ScalingTracker.deactivate_automatic_dpi_awareness = True # THE MASTER FIX

import tkinter as tk
import threading
import queue
import pystray
import sys
import os
import winreg
import ctypes
import getpass
import requests
from PIL import Image
from tkinter import messagebox
from config import ALLOWED_VIDS, ALLOWED_PIDS, SERVER_URL
from local_storage import ApiStorage
from scanner import ScannerManager
from overlay import NotificationManager


message_queue = queue.Queue()

def resource_path(file_name):
    try:
        base_path = sys._MEIPASS
        return os.path.join(base_path, file_name)
    except Exception:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "..", "..", "img", file_name)

# --- WINDOWS STARTUP REGISTRY LOGIC ---
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LabTrackQR"

def set_autostart(enable):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_ALL_ACCESS)
        if enable:
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

# --- THEME REGISTRY LOGIC ---
THEME_REG_PATH = r"Software\LabTrackQR"

def save_theme_preference(theme_name):
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, THEME_REG_PATH)
        winreg.SetValueEx(key, "Theme", 0, winreg.REG_SZ, theme_name)
        winreg.CloseKey(key)
    except Exception: pass

def load_theme_preference():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_REG_PATH, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, "Theme")
        winreg.CloseKey(key)
        return value
    except FileNotFoundError:
        return None

# --- DETECT TASKBAR THEME ---
def is_taskbar_dark_mode():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except FileNotFoundError:
        return True 

state = {'autostart': is_autostart_enabled()}

def setup_tray(root, scanner_mgr):
    try:        
        if is_taskbar_dark_mode():
            img_path = resource_path("icon_white.ico") 
            image = Image.open(img_path).convert("RGBA")
        else:
            img_path = resource_path("icon_black.ico") 
            image = Image.open(img_path).convert("RGBA")
            
    except FileNotFoundError:
        image = Image.new('RGB', (64, 64), color = (73, 109, 137))

    def trigger_new_sample_form(icon, item): message_queue.put("COMMAND:OPEN_FORM")
    def trigger_removal_mode(icon, item): 
        scanner_mgr.removal_mode = True
        message_queue.put("COMMAND:WAITING_FOR_REMOVAL_SCAN")
    def trigger_log_viewer(icon, item): message_queue.put("COMMAND:OPEN_LOG_VIEWER")
    def trigger_map_viewer(icon, item): message_queue.put("COMMAND:OPEN_MAP_VIEWER")
    def trigger_user_manager(icon, item): message_queue.put("COMMAND:OPEN_USER_MANAGER")
    
    def toggle_theme(icon, item):
        current_mode = ctk.get_appearance_mode()
        new_mode = "Light" if current_mode == "Dark" else "Dark"
        save_theme_preference(new_mode)
        ctk.set_appearance_mode(new_mode)
        icon.update_menu()

    def get_theme_text(item):
        return "Change theme to Light" if ctk.get_appearance_mode() == "Dark" else "Change theme to Dark"

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
        pystray.MenuItem("View Logs and History", trigger_log_viewer), 
        pystray.MenuItem("Laboratory Map", trigger_map_viewer),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Manage Employee Badges", trigger_user_manager),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(get_theme_text, toggle_theme),
        pystray.MenuItem("Run on Windows Startup", toggle_autostart, checked=lambda item: state['autostart']),
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR", image, "LabTrackQR", menu)
    icon.run()

def notify_func(*args):
    if not args: return
    
    action = args[0]
    if action == "OPEN_NEW_VIEWER":
        if 'app' in globals() and hasattr(app, 'open_log_viewer'):
            app.open_log_viewer()
    else:
        if 'app' in globals() and hasattr(app, 'spawn_notification'):
            app.spawn_notification(action)

if __name__ == "__main__":
    # --- LOAD SAVED THEME BEFORE UI SPAWNS ---
    saved_theme = load_theme_preference()
    if saved_theme in ["Dark", "Light"]:
        ctk.set_appearance_mode(saved_theme)
        
    mutex_name = "Global\\LabTrackQR_Client_Instance_Lock"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)

    if ctypes.windll.kernel32.GetLastError() == 183: 
        err_root = ctk.CTk()
        err_root.withdraw()
        try:
            err_root.iconbitmap(resource_path("iconApp.ico"))
        except Exception: pass
        err_root.attributes("-topmost", True) 
        messagebox.showwarning(
            "LabTrackQR Already Running", 
            "LabTrack is already running in the background!\n\nPlease check your system tray (near the clock) to access it."
        )
        sys.exit(0) 

    storage = ApiStorage(SERVER_URL)
    
    ad_username = getpass.getuser()
    ad_employee_data = storage.get_employee_by_ad(ad_username)

    scanner_mgr = ScannerManager(ALLOWED_VIDS, ALLOWED_PIDS, message_queue, storage)

    if ad_employee_data:
        scanner_mgr.ad_fallback_name = ad_employee_data.get('full_name')
        if storage.is_offline_mode:
            message_queue.put("SERVER OFFLINE\nUsing cached profile.\nData will be saved locally.")
    else:
        if storage.is_offline_mode:
            message_queue.put("SERVER OFFLINE\nCannot register new users.\n")
        else:
            message_queue.put(f"COMMAND:REGISTER_AD_USER:{ad_username}")

    scanner_mgr.start_monitoring()

    app = NotificationManager(message_queue, storage, scanner_mgr)
    threading.Thread(target=setup_tray, args=(app.root, scanner_mgr), daemon=True).start()
    
    app.run()   