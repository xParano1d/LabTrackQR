# main.py
import tkinter as tk
import threading
import queue
import pystray
import sys
import os
import winreg
from PIL import Image
import json
from tkinter import filedialog, messagebox

from config import NETWORK_SYNC_PATH, SYNC_INTERVAL_SECONDS
from local_storage import CsvStorage
from overlay import NotificationManager
from server_api import LabTrackAPI


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

def setup_tray(root):
    try:        
        if is_taskbar_dark_mode():
            image = Image.open(resource_path("icon_white.ico")).convert("RGBA")
        else:
            image = Image.open(resource_path("icon_black.ico")).convert("RGBA")
    except FileNotFoundError:
        image = Image.new('RGB', (64, 64), color = (73, 109, 137))

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
        pystray.MenuItem("View Logs & History", trigger_log_viewer), 
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Manage Employee Badges", trigger_user_manager),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Run on Windows Startup", toggle_autostart, checked=lambda item: state['autostart']),
        pystray.MenuItem("Quit Server", on_quit)
    )
    
    icon = pystray.Icon("LabTrackQR_Server", image, "LabTrack Server", menu)
    icon.run()

# --- FIRST LAUNCH SETUP LOGIC ---
SETTINGS_FILE = "server_settings.json"

def get_master_directory():
    SETTINGS_FILE_PATH = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR', 'server_settings.json')
    """Checks for saved path. If missing or invalid, launches the Setup UI."""
    if os.path.exists(SETTINGS_FILE_PATH):
        try:
            with open(SETTINGS_FILE_PATH, 'r') as f:
                data = json.load(f)
                saved_path = data.get("PARENT_FOLDER")
                if saved_path and os.path.exists(saved_path):
                    return saved_path
        except Exception:
            pass

    # If we reach here, the path is missing or invalid. Launch Setup UI.
    setup_root = tk.Tk()
    setup_root.title("Server Setup")
    setup_root.geometry("450x220")
    setup_root.overrideredirect(True)
    setup_root.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#011528")
    setup_root.attributes("-topmost", True)

    setup_root.update_idletasks()
    x = (setup_root.winfo_screenwidth() // 2) - (450 // 2)
    y = (setup_root.winfo_screenheight() // 2) - (220 // 2)
    setup_root.geometry(f'+{x}+{y}')

    tk.Label(setup_root, text="Server Configuration", bg="#ffffff", fg="#011528", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
    tk.Label(setup_root, text="Master Database Directory not found.\nPlease select the folder to store inventory and logs.", bg="#ffffff", fg="#555555", font=("Segoe UI", 10)).pack(pady=(0, 15))

    path_var = tk.StringVar()
    
    # By removing fill=tk.X, the frame shrinks to fit the entry and button, and centers automatically
    input_frame = tk.Frame(setup_root, bg="#ffffff")
    input_frame.pack(pady=(0, 5)) 
    
    path_entry = tk.Entry(input_frame, textvariable=path_var, font=("Segoe UI", 10), state="readonly", width=32, relief="solid", bd=1)
    path_entry.pack(side=tk.LEFT, ipady=4, padx=(0, 10))

    def browse_folder():
        folder = filedialog.askdirectory(title="Select Master Directory")
        if folder:
            path_var.set(folder)

    tk.Button(input_frame, text="Browse...", command=browse_folder, bg="#aaaaaa", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10).pack(side=tk.LEFT)

    def save_and_start():
        selected_path = path_var.get()
        if selected_path and os.path.exists(selected_path):
            # Ensure the directory exists in LocalAppData before saving the JSON
            os.makedirs(os.path.dirname(SETTINGS_FILE_PATH), exist_ok=True)
            
            with open(SETTINGS_FILE_PATH, 'w') as f:
                json.dump({"PARENT_FOLDER": selected_path}, f)
            setup_root.destroy()
        else:
            tk.messagebox.showwarning("Invalid Path", "Please select a valid directory to continue.", parent=setup_root)

    def cancel_setup():
        setup_root.destroy()
        sys.exit(0)

    btn_frame = tk.Frame(setup_root, bg="#ffffff")
    btn_frame.pack(pady=20)
    tk.Button(btn_frame, text="Quit", command=cancel_setup, bg="#d9534f", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame, text="Save & Start", command=save_and_start, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=15).pack(side=tk.LEFT, padx=10)

    setup_root.mainloop()
    
    # After mainloop is destroyed, recursively call to verify and return the newly saved path
    return get_master_directory()

if __name__ == "__main__":
    # 1. Ensure configuration exists
    parent_folder = get_master_directory()
    
    # 2. Dynamically build the database paths
    save_path = os.path.join(parent_folder, "inventory.csv")
    employees_path = os.path.join(parent_folder, "employees.json")
    history_dir = os.path.join(parent_folder, "history_logs")
    
    # 3. Initialize Master Storage with dynamic paths
    storage = CsvStorage(save_path, employees_path, history_dir, NETWORK_SYNC_PATH, SYNC_INTERVAL_SECONDS)
    
    # 4. Start the Background Flask API Server
    api_server = LabTrackAPI(storage)
    api_server.start_server(host='0.0.0.0', port=5000)

    # 5. Start the UI Dashboard
    app = NotificationManager(message_queue, storage, scanner_mgr=None)
    threading.Thread(target=setup_tray, args=(app.root,), daemon=True).start()
    
    app.run()