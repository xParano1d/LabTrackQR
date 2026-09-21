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
import time
import json
import ctypes
from PIL import Image
from tkinter import filedialog, messagebox
from config import NETWORK_SYNC_PATH, SYNC_INTERVAL_SECONDS
from local_storage import CsvStorage
from overlay import NotificationManager
from server_api import LabTrackAPI

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
APP_NAME = "LabTrackServer"

def set_autostart(enable):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            exe_path = os.path.abspath(sys.argv[0])
            exe_path = f'"{exe_path}"' if exe_path.endswith('.exe') else f'"{sys.executable}" "{exe_path}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        else:
            try: winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError: pass
        winreg.CloseKey(key)
    except Exception as e: print(f"Registry Error: {e}")

def is_autostart_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError: return False

def is_taskbar_dark_mode():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except FileNotFoundError: return True 

state = {'autostart': is_autostart_enabled()}

def setup_tray(root, api_server):
    try:
        if is_taskbar_dark_mode():
            image = Image.open(resource_path("icon_white.ico")).convert("RGBA")
        else:
            image = Image.open(resource_path("icon_black.ico")).convert("RGBA")
    except FileNotFoundError:
        image = Image.new('RGB', (64, 64), color = (73, 109, 137))

    def trigger_log_viewer(icon, item): message_queue.put("COMMAND:OPEN_LOG_VIEWER")
    def trigger_user_manager(icon, item): message_queue.put("COMMAND:OPEN_USER_MANAGER")
    
    def toggle_theme(icon, item):
        current_mode = ctk.get_appearance_mode()
        new_mode = "Light" if current_mode == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        icon.update_menu() # Forces the tray text to refresh instantly!

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
        pystray.MenuItem("View Logs History", trigger_log_viewer), 
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Employees Management", trigger_user_manager),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(get_theme_text, toggle_theme),
        pystray.MenuItem("Run on Windows Startup", toggle_autostart, checked=lambda item: state['autostart']),
        pystray.MenuItem("Quit Server", on_quit)
    )
    icon = pystray.Icon("LabTrackQR_Server", image, "LabTrack Server", menu)

    def tray_updater():
        while True:
            time.sleep(2)
            if api_server:
                count = api_server.get_active_client_count()
                icon.title = f"Live Clients: {count} | LabTrack Server"
                icon.update_menu()

    threading.Thread(target=tray_updater, daemon=True).start()
    icon.run()

# --- FIRST LAUNCH SETUP LOGIC ---
SETTINGS_FILE = "server_settings.json"

def get_master_directory():
    SETTINGS_FILE_PATH = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR', 'server_settings.json')
    if os.path.exists(SETTINGS_FILE_PATH):
        try:
            with open(SETTINGS_FILE_PATH, 'r') as f:
                data = json.load(f)
                saved_path = data.get("PARENT_FOLDER")
                if saved_path and os.path.exists(saved_path):
                    return saved_path
        except Exception:
            pass

    theme_path = resource_path("BW_theme.json")
    if os.path.exists(theme_path):
        ctk.set_default_color_theme(theme_path)

    setup_root = ctk.CTk()
    setup_root.title("Server Setup")
    try:
        setup_root.after(200, lambda: setup_root.iconbitmap(resource_path("icon_white.ico")))
    except Exception: pass
    setup_root.overrideredirect(True)
    
    bg_color = "#051728" if ctk.get_appearance_mode() == "Dark" else "#F2F0EB"
    border_color = "#0E8187" if ctk.get_appearance_mode() == "Dark" else "#00386C"
    setup_root.configure(bg=bg_color, highlightthickness=2, highlightbackground=border_color)
    setup_root.attributes("-topmost", True)

    # --- PURE MATH CENTERING ---
    width, height = 430, 210
    setup_root.update_idletasks()
    
    screen_w = setup_root.winfo_screenwidth()
    screen_h = setup_root.winfo_screenheight()
    
    x = int((screen_w / 2) - (width / 2))
    y = int((screen_h / 2) - (height / 2))
    
    setup_root.geometry(f"{width}x{height}+{x}+{y}")
    # ---------------------------

    ctk.CTkLabel(setup_root, text="Server Configuration", font=("Segoe UI", 18, "bold")).pack(pady=(20, 5))
    ctk.CTkLabel(setup_root, text="Master Database Directory not found.\nPlease select the folder to store inventory and logs.", font=("Segoe UI", 12)).pack(pady=(0, 15))

    path_var = tk.StringVar()
    
    input_frame = ctk.CTkFrame(setup_root, fg_color="transparent")
    input_frame.pack(pady=(0, 5)) 
    
    path_entry = ctk.CTkEntry(input_frame, textvariable=path_var, font=("Segoe UI", 12), width=240)
    path_entry.configure(state="disabled")
    path_entry.pack(side=tk.LEFT, padx=(0, 10))

    def browse_folder():
        folder = filedialog.askdirectory(title="Select Master Directory")
        if folder:
            path_entry.configure(state="normal")
            path_var.set(folder)
            path_entry.configure(state="disabled")

    ctk.CTkButton(input_frame, text="Browse...", command=browse_folder, fg_color=ctk.ThemeManager.theme["CTkSegmentedButton"]["unselected_color"], hover_color=ctk.ThemeManager.theme["CTkSegmentedButton"]["unselected_hover_color"], font=("Segoe UI", 12, "bold"), width=80).pack(side=tk.LEFT)

    def save_and_start():
        selected_path = path_var.get()
        if selected_path and os.path.exists(selected_path):
            os.makedirs(os.path.dirname(SETTINGS_FILE_PATH), exist_ok=True)
            with open(SETTINGS_FILE_PATH, 'w') as f:
                json.dump({"PARENT_FOLDER": selected_path}, f)
            setup_root.destroy()
        else:
            tk.messagebox.showwarning("Invalid Path", "Please select a valid directory to continue.", parent=setup_root)

    def cancel_setup():
        setup_root.destroy()
        sys.exit(0)

    btn_frame = ctk.CTkFrame(setup_root, fg_color="transparent")
    btn_frame.pack(pady=20)
    ctk.CTkButton(btn_frame, text="Quit", command=cancel_setup, fg_color="#d9534f", hover_color="#c9302c", font=("Segoe UI", 12, "bold"), width=120).pack(side=tk.LEFT, padx=10)
    ctk.CTkButton(btn_frame, text="Save & Start", command=save_and_start, fg_color=["#217346", "#09ce66"], hover_color=["#2a8f57", "#2EFAD9"], font=("Segoe UI", 12, "bold"), width=140).pack(side=tk.LEFT, padx=10)

    setup_root.mainloop()
    return get_master_directory()

if __name__ == "__main__":
    mutex_name = "Global\\LabTrackQR_Server_Instance_Lock"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    
    if ctypes.windll.kernel32.GetLastError() == 183: 
        err_root = ctk.CTk()
        err_root.withdraw()
        err_root.attributes("-topmost", True) 
        messagebox.showwarning(
            "LabTrack Server Already Running", 
            "The LabTrack Server is already running in the background!\n\nPlease check your system tray (near the clock) to access it."
        )
        sys.exit(0)

    parent_folder = get_master_directory()
    
    save_path = os.path.join(parent_folder, "inventory.csv")
    employees_path = os.path.join(parent_folder, "employees.json")
    history_dir = os.path.join(parent_folder, "history_logs")
    
    storage = CsvStorage(save_path, employees_path, history_dir, NETWORK_SYNC_PATH, SYNC_INTERVAL_SECONDS)
    
    api_server = LabTrackAPI(storage)
    api_server.start_server(host='0.0.0.0', port=5000)

    app = NotificationManager(message_queue, storage, scanner_mgr=None)
    threading.Thread(target=setup_tray, args=(app.root, api_server), daemon=True).start()
    
    app.run()