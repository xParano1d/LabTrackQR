# main.py
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
from logviewer import LogViewerWindow
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
        pystray.MenuItem("View Logs History", trigger_log_viewer), 
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Manage Employee Badges", trigger_user_manager),
        pystray.Menu.SEPARATOR,
        # Native checked toggle for Startup
        pystray.MenuItem("Run on Windows Startup", toggle_autostart, checked=lambda item: state['autostart']),
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR", image, "LabTrackQR", menu)
    icon.run()

def check_for_stale_samples(root_window, storage_manager, current_user_name, logviewer_class, notify_func):
        """Silently checks for neglected samples and prompts the user to resolve them."""
        from datetime import datetime
        
        def run_check():
            try:
                # Fetch Active Inventory from the API
                target_url = getattr(storage_manager, 'server_url', "http://127.0.0.1:5000")
                response = requests.get(f"{target_url}/api/view_data", params={"source": "inventory"}, timeout=5)
                
                if response.status_code == 200:
                    data = response.json().get("results", [])
                    stale_count = 0
                    now = datetime.now()
                    
                    # Scan for samples that belong to THIS user and are 14+ days old
                    for row in data:
                        if len(row) >= 7 and row[6].lower() == current_user_name.lower() and "removed" not in row[2].lower():
                            try:
                                row_date = datetime.strptime(str(row[0]), "%Y-%m-%d")
                                if (now - row_date).days >= 14:
                                    stale_count += 1
                            except Exception:
                                pass
                                
                    if stale_count > 0:
                        show_hard_stop_popup(stale_count)
            except Exception:
                pass # Silently fail if network is down
        
        def show_hard_stop_popup(count):
            popup = tk.Toplevel(root_window)
            popup.title("Attention Required")
            popup.geometry("420x220") 
            
            # --- THE THEME UPGRADE ---
            popup.overrideredirect(True) # Removes the ugly Windows title bar
            popup.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#d9534f") # Clean white with red alert border
            popup.attributes('-topmost', True) 
            
            # Center the window perfectly on the screen
            popup.update_idletasks()
            x = (popup.winfo_screenwidth() // 2) - (420 // 2)
            y = (popup.winfo_screenheight() // 2) - (220 // 2)
            popup.geometry(f'+{x}+{y}')
            
            # Disable closing via alt-f4
            popup.protocol("WM_DELETE_WINDOW", lambda: None)
            
            # Clean, enterprise text styling
            tk.Label(popup, text="⚠️ Action Required ⚠️", bg="#ffffff", fg="#d9534f", font=("Segoe UI", 16, "bold")).pack(pady=(25, 5))
            tk.Label(popup, text=f"You currently have {count} samples left unattended\nin the system for over 14 days.", bg="#ffffff", fg="#333333", font=("Segoe UI", 11)).pack(pady=10)
            
            def open_viewer():
                popup.destroy()
                # Opens LogViewer and automatically injects the search terms
                logviewer_class(root_window, storage_manager, notify_func, is_server=False, current_user=current_user_name, initial_filters=["ME", "old"])
                
            # Crisp red button to match the theme
            btn_frame = tk.Frame(popup, bg="#ffffff")
            btn_frame.pack(pady=(10, 0))
            tk.Button(btn_frame, text="Show Samples", command=open_viewer, bg="#d9534f", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20, cursor="hand2").pack()

        # Start the 15-minute stealth countdown (900,000 ms)
        root_window.after(5000, run_check)

if __name__ == "__main__":
    # --- 1. SINGLE INSTANCE LOCK (MUTEX) ---
    mutex_name = "Global\\LabTrackQR_Client_Instance_Lock"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)

    if ctypes.windll.kernel32.GetLastError() == 183: 
        err_root = tk.Tk()
        err_root.withdraw()
        err_root.attributes("-topmost", True) 
        messagebox.showwarning(
            "LabTrackQR Already Running", 
            "LabTrack is already running in the background!\n\nPlease check your system tray (near the clock) to access it."
        )
        sys.exit(0) # Instantly kill this duplicate instance

    storage = ApiStorage(SERVER_URL)
    
    # --- THE AD AUTO-LOGIN LOGIC ---
    ad_username = getpass.getuser()
    ad_employee_data = storage.get_employee_by_ad(ad_username)

    scanner_mgr = ScannerManager(ALLOWED_VIDS, ALLOWED_PIDS, message_queue, storage)

    # Inject AD user if they exist in the DB (or cache!), otherwise queue Registration
    if ad_employee_data:
        scanner_mgr.ad_fallback_name = ad_employee_data.get('full_name')
        
        # Notify the user of the network state on boot
        if storage.is_offline_mode:
            message_queue.put("⚠️ SERVER OFFLINE ⚠️\nUsing cached profile.\nData will be saved locally.")
    else:
        # If they are completely new AND offline, we can't register them
        if storage.is_offline_mode:
            message_queue.put("⚠️ SERVER OFFLINE ⚠️\nCannot register new users.\n")
        else:
            # User is brand new. Queue a specialized prompt to register their Windows account.
            message_queue.put(f"COMMAND:REGISTER_AD_USER:{ad_username}")

    scanner_mgr.start_monitoring()

    app = NotificationManager(message_queue, storage, scanner_mgr)
    threading.Thread(target=setup_tray, args=(app.root, scanner_mgr), daemon=True).start()

    # Disable the stale check if we are offline (it relies on fresh server data)
    if scanner_mgr.ad_fallback_name and not storage.is_offline_mode:
        check_for_stale_samples(root_window=app.root, storage_manager=storage, current_user_name=scanner_mgr.ad_fallback_name, logviewer_class=LogViewerWindow, notify_func=app.spawn_notification)

    app.run()