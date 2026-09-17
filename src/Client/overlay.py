# overlay.py (CLIENT VERSION)
import customtkinter as ctk
ctk.ScalingTracker.deactivate_automatic_dpi_awareness = True # THE MASTER FIX

import sys
import os
import ctypes
import qrcode
import tkinter as tk
import threading
import requests
from PIL import Image, ImageTk
from logviewer import LogViewerWindow

try:
    myappid = 'labtrack.qr.desktop.app.1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def resource_path(file_name):
    try:
        base_path = sys._MEIPASS
        return os.path.join(base_path, file_name)
    except Exception:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "..", "..", "img", file_name)

def get_theme_icon():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        return "icon_white.ico" if value == 0 else "icon_black.ico"
    except Exception:
        return "icon_white.ico"

class NotificationManager:
    def __init__(self, message_queue, storage=None, scanner_mgr=None):
        self.message_queue = message_queue
        self.storage = storage
        self.scanner_mgr = scanner_mgr
        self.active_notifications = []
        self.waiting_removal_win = None
        self.active_log_windows = []
        
        # --- LOAD CUSTOM THEME ---
        theme_path = resource_path("BW_theme.json")
        if os.path.exists(theme_path):
            ctk.set_default_color_theme(theme_path)

        self.root = ctk.CTk()
        try:
            icon_path = resource_path(get_theme_icon())
            self.root.iconbitmap(default=icon_path)
            self.root.after(200, lambda: self.root.iconbitmap(icon_path)) # Overrides the CTk default!
        except Exception:
            pass
            
        self.root.withdraw() 
        self.show_splash_screen()
        self.root.after(4500, self.check_queue)
        self.root.after(5000, self.send_heartbeat)

    def _get_dynamic_colors(self):
        bg_color = "#051728" if ctk.get_appearance_mode() == "Dark" else "#F2F0EB"
        border_color = "#0E8187" if ctk.get_appearance_mode() == "Dark" else "#00386C"
        return bg_color, border_color

    def center_window(self, window, width, height):
        window.update_idletasks()
        
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        
        x = int((screen_w / 2) - (width / 2))
        y = int((screen_h / 2) - (height / 2))
        
        window.geometry(f"{width}x{height}+{x}+{y}")

    def send_heartbeat(self):
        if self.storage:
            target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")
            def ping_server():
                try:
                    resp = requests.get(f"{target_url}/api/ping", timeout=2)
                    if resp.status_code == 200:
                        if getattr(self.storage, 'is_offline_mode', False):
                            self.storage.is_offline_mode = False
                            import winsound
                            winsound.MessageBeep(winsound.MB_ICONASTERISK)
                            self.message_queue.put("SERVER CONNECTED \nOnline mode active.\nSyncing data in background...")
                except Exception:
                    if not getattr(self.storage, 'is_offline_mode', True):
                        self.storage.is_offline_mode = True
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONHAND)
                        self.message_queue.put("⚠️ CONNECTION LOST ⚠️\nSwitched to Offline Mode.\nData will be saved locally.")

            threading.Thread(target=ping_server, daemon=True).start()
        self.root.after(5000, self.send_heartbeat)

    def show_splash_screen(self):
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.configure(bg="#011528", highlightthickness=2, highlightbackground="#ffffff")
        splash.attributes("-topmost", True)
        
        self.center_window(splash, 400, 240)
        
        try:
            original_img = Image.open(resource_path("icon_white.ico"))
            resized_img = original_img.resize((80, 80), Image.Resampling.LANCZOS)
            self.splash_logo = ImageTk.PhotoImage(resized_img)
            tk.Label(splash, image=self.splash_logo, bg="#011528").pack(pady=(35, 0))
        except Exception: pass

        tk.Label(splash, text="LabTrackQR", bg="#011528", fg="white", font=("Segoe UI", 26, "bold")).pack(pady=(5,0))
        tk.Label(splash, text="Connecting to hardware & network...", bg="#011528", fg="#9db2c6", font=("Segoe UI", 11, "italic")).pack()
        splash.after(2500, splash.destroy)

    def check_queue(self):
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            
            if msg == "COMMAND:OPEN_FORM": self.open_new_sample_form(); continue
            if msg == "COMMAND:OPEN_LOG_VIEWER": self.open_log_viewer(); continue
            if msg == "COMMAND:WAITING_FOR_REMOVAL_SCAN": self.open_waiting_for_removal(); continue
            if msg == "COMMAND:OPEN_USER_MANAGER": self.open_employee_directory(); continue
            if msg == "COMMAND:SHOW_LOCK_SCREEN": self.open_lock_screen(); continue
                
            if isinstance(msg, str) and msg.startswith("COMMAND:UNKNOWN_BADGE:"):
                self.open_register_badge(msg.replace("COMMAND:UNKNOWN_BADGE:", ""))
                continue
                
            if isinstance(msg, str) and msg.startswith("COMMAND:CONFIRM_REMOVE:"):
                if self.waiting_removal_win and self.waiting_removal_win.winfo_exists():
                    self.waiting_removal_win.destroy()
                parts = msg.replace("COMMAND:CONFIRM_REMOVE:", "").split("|")
                self.open_removal_confirmation(parts[0], parts[1] if len(parts) > 1 else "Unknown", parts[2] if len(parts) > 2 else "Unknown Sample")
                continue
                
            if isinstance(msg, str) and msg.startswith("COMMAND:REGISTER_AD_USER:"):
                self.open_register_badge(badge_id=None, ad_username=msg.replace("COMMAND:REGISTER_AD_USER:", ""))
                continue

            if isinstance(msg, str) and msg.startswith("COMMAND:CONFIRM_RELOG:"):
                self.open_relog_confirmation(msg.replace("COMMAND:CONFIRM_RELOG:", ""))
                continue

            if isinstance(msg, str):
                clean_msg = msg.strip()
                if clean_msg:
                    self.spawn_notification(clean_msg)

        self.root.after(50, self.check_queue)

    def open_log_viewer(self, initial_filters=None):
        self.active_log_windows = [w for w in self.active_log_windows if w.viewer.winfo_exists()]
        if len(self.active_log_windows) >= 2:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
            self.spawn_notification("Window Limit Reached:\nMaximum of 2 log windows allowed.")

            latest_viewer = self.active_log_windows[-1].viewer
            latest_viewer.deiconify()
            latest_viewer.lift()
            latest_viewer.attributes('-topmost', True)
            latest_viewer.after(100, lambda: latest_viewer.attributes('-topmost', False))
            latest_viewer.focus_force()
            return

        def viewer_router(msg):
            if msg == "OPEN_NEW_VIEWER": self.open_log_viewer()
            else: self.spawn_notification(msg)

        current_user = self.scanner_mgr.ad_fallback_name if self.scanner_mgr else ""
        viewer_instance = LogViewerWindow(self.root, self.storage, viewer_router, is_server=False, current_user=current_user, initial_filters=initial_filters)
        self.active_log_windows.append(viewer_instance)

    def start_stale_check(self, current_user_name):
        from datetime import datetime
        def run_check():
            try:
                target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")
                response = requests.get(f"{target_url}/api/view_data", params={"source": "inventory"}, timeout=5)
                if response.status_code == 200:
                    data = response.json().get("results", [])
                    stale_count = 0
                    now = datetime.now()
                    for row in data:
                        if len(row) >= 8 and row[7].lower() == current_user_name.lower() and "removed" not in row[2].lower() and "closed" not in row[2].lower():
                            try:
                                row_date = datetime.strptime(str(row[0]), "%Y-%m-%d")
                                if (now - row_date).days >= 14:
                                    stale_count += 1
                            except Exception: pass
                    if stale_count > 0:
                        self.show_hard_stop_popup(stale_count, current_user_name)
            except Exception: pass
            self.root.after(900000, run_check)
        self.root.after(5000, run_check)

    def show_hard_stop_popup(self, count, current_user_name):
        popup = tk.Toplevel(self.root)
        popup.title("Attention Required")
        popup.overrideredirect(True) 
        bg_color, border_color = self._get_dynamic_colors()
        popup.configure(bg=bg_color, highlightthickness=2, highlightbackground="#d9534f") 
        popup.attributes('-topmost', True) 
        
        self.center_window(popup, 420, 180)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)
        
        ctk.CTkLabel(popup, text="⚠️ Action Required ⚠️", text_color="#d9534f", font=("Segoe UI", 18, "bold")).pack(pady=(25, 5))
        ctk.CTkLabel(popup, text=f"You currently have {count} samples left unattended\nin the system for over 14 days.", font=("Segoe UI", 13)).pack(pady=10)
        
        def open_viewer():
            popup.destroy()
            self.open_log_viewer(initial_filters=["ME", "old"])
            
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=(10, 0))
        ctk.CTkButton(btn_frame, text="Show Samples", command=open_viewer, fg_color="#d9534f", hover_color="#c9302c", font=("Segoe UI", 12, "bold"), width=160).pack()

    def open_relog_confirmation(self, new_user):
        if hasattr(self, 'relog_win') and self.relog_win and self.relog_win.winfo_exists():
            self.relog_win.lift()
            return
            
        win = tk.Toplevel(self.root)
        self.relog_win = win
        win.title("Switch User")
        win.overrideredirect(True)
        bg_color, border_color = self._get_dynamic_colors()
        win.configure(bg=bg_color, highlightthickness=2, highlightbackground="#f39c12")
        win.attributes("-topmost", True)

        self.center_window(win, 400, 220)

        ctk.CTkLabel(win, text="Switch User?", text_color="#f39c12", font=("Segoe UI", 18, "bold")).pack(pady=(15, 2))
        ctk.CTkLabel(win, text=f"Do you want to log out the current user\nand log in as {new_user}?", font=("Segoe UI", 13)).pack(pady=2)

        revert_var = ctk.BooleanVar(value=True) 
        chk = ctk.CTkCheckBox(win, text="Revert to original user after 5 min of inactivity", variable=revert_var, font=("Segoe UI", 11, "italic"))
        chk.pack(pady=10)

        timeout_id = win.after(15000, lambda: cancel())

        def confirm():
            win.after_cancel(timeout_id)
            is_temporary = revert_var.get()
            if self.scanner_mgr:
                for node in self.scanner_mgr.active_scanners.values():
                    node.user = new_user
                    node.pending_samples.clear()
                    node.current_location = None
                    if node.revert_timer:
                        node.revert_timer.cancel()
                        node.revert_timer = None
                    if new_user == node.ad_fallback_name:
                        node.auto_revert = False
                    else:
                        node.auto_revert = is_temporary
                        node._start_ad_revert_timer()
            
            is_temp_now = False
            if self.scanner_mgr:
                for node in self.scanner_mgr.active_scanners.values():
                    if getattr(node, 'auto_revert', False): is_temp_now = True

            if is_temp_now: self.spawn_notification(f"Temp Login Active:\nWelcome {new_user}!\n(5m idle timer running)")
            else: self.spawn_notification(f"Login Successful:\nWelcome {new_user}!")
            win.destroy()

        def cancel():
            if win.winfo_exists():
                win.after_cancel(timeout_id)
                win.destroy()
            self.spawn_notification("User switch cancelled.")

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=5)
        ctk.CTkButton(btn_frame, text="Yes, Switch", command=confirm, fg_color="#f39c12", hover_color="#d68910", font=("Segoe UI", 12, "bold"), width=120).pack(side=tk.LEFT, padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", command=cancel, fg_color="#aaaaaa", hover_color="#888888", font=("Segoe UI", 12, "bold"), width=100).pack(side=tk.LEFT, padx=10)

    def open_register_badge(self, badge_id=None, ad_username=""):
        reg_win = tk.Toplevel(self.root)
        reg_win.title("Register New Employee")
        reg_win.overrideredirect(True)
        bg_color, border_color = self._get_dynamic_colors()
        reg_win.configure(bg=bg_color, highlightthickness=2, highlightbackground=["#217346", "#09ce66"][1 if ctk.get_appearance_mode() == "Dark" else 0])
        reg_win.attributes("-topmost", True)

        self.center_window(reg_win, 450, 450)
        
        title_text = "Windows AD Setup" if ad_username else "New ID Card Detected"
        accent_color = "#09ce66" if ctk.get_appearance_mode() == "Dark" else "#217346"
        ctk.CTkLabel(reg_win, text=title_text, text_color=accent_color, font=("Segoe UI", 18, "bold")).pack(pady=(20, 5))
        
        if ad_username:
            ctk.CTkLabel(reg_win, text=f"Linking to Windows account: {ad_username}", font=("Segoe UI", 11, "italic")).pack(pady=(0, 10))
            
        ctk.CTkLabel(reg_win, text="8-Digit Badge ID:", font=("Segoe UI", 12, "bold")).pack(pady=(5, 2))
        entry_badge = ctk.CTkEntry(reg_win, font=("Segoe UI", 14), justify="center", width=220)
        entry_badge.pack(pady=3)
        if badge_id:
            entry_badge.insert(0, badge_id)
            entry_badge.configure(state="disabled")
            
        ctk.CTkLabel(reg_win, text="First Name:", font=("Segoe UI", 12, "bold")).pack(pady=(15, 2))
        entry_first = ctk.CTkEntry(reg_win, font=("Segoe UI", 14), justify="center", width=220)
        entry_first.pack(pady=3)
        
        ctk.CTkLabel(reg_win, text="Last Name:", font=("Segoe UI", 12, "bold")).pack(pady=(10, 2))
        entry_last = ctk.CTkEntry(reg_win, font=("Segoe UI", 14), justify="center", width=220)
        entry_last.pack(pady=3)
        
        def save_badge():
            b_id = entry_badge.get().strip()
            f_name = entry_first.get().strip()
            l_name = entry_last.get().strip()

            if len(b_id) == 8 and b_id.isdigit() and f_name and l_name:
                full_name = f"{f_name} {l_name}"
                if self.storage:
                    success = self.storage.add_employee(b_id, f_name, l_name, ad_username)
                    if not success:
                        self.spawn_notification("Registration Failed:\nCould not reach server.")
                        return

                if self.scanner_mgr:
                    if ad_username: 
                        self.scanner_mgr.ad_fallback_name = full_name
                    for node in self.scanner_mgr.active_scanners.values():
                        if node.user is None or ad_username:
                            node.user = full_name
                            if ad_username: node.ad_fallback_name = full_name
                    self.message_queue.put(f"Login Successful:\nWelcome {full_name}!")

                self.spawn_notification(f"Registered Successfully:\n{full_name}")
                reg_win.destroy()
                if ad_username:
                    self.start_stale_check(full_name)
                
        def cancel(): reg_win.destroy()
            
        btn_frame = ctk.CTkFrame(reg_win, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", command=cancel, fg_color="#aaaaaa", hover_color="#888888", font=("Segoe UI", 12, "bold"), width=100).pack(side=tk.LEFT, padx=10)
        ctk.CTkButton(btn_frame, text="Assign & Save", command=save_badge, fg_color=["#217346", "#09ce66"], hover_color=["#2a8f57", "#2EFAD9"], font=("Segoe UI", 12, "bold"), width=120).pack(side=tk.LEFT, padx=10)

    def open_employee_directory(self):
        if hasattr(self, 'emp_dir_win') and self.emp_dir_win and self.emp_dir_win.winfo_exists():
            self.emp_dir_win.deiconify()
            self.emp_dir_win.lift()
            self.emp_dir_win.focus_force()
            return

        manager = tk.Toplevel(self.root)
        self.emp_dir_win = manager 
        manager.title("Employee Login Badges")
        manager.overrideredirect(True)
        bg_color, border_color = self._get_dynamic_colors()
        manager.configure(bg=bg_color, highlightthickness=2, highlightbackground=border_color)
        manager.attributes("-topmost", True)

        self.center_window(manager, 540, 580)

        close_btn = ctk.CTkButton(manager, text="✕", width=30, height=30, fg_color="transparent", text_color=["#999999", "#888888"], hover_color=["#ffcccc", "#662222"], command=manager.destroy)
        close_btn.place(relx=1.0, x=-5, y=5, anchor="ne")

        ctk.CTkLabel(manager, text="Employee Login Badges", font=("Segoe UI", 20, "bold")).pack(pady=(25, 5))
        ctk.CTkLabel(manager, text="Select a user to automatically generate their QR card", font=("Segoe UI", 11, "italic")).pack(pady=(0, 15))

        sel_frame = ctk.CTkFrame(manager, fg_color="transparent")
        sel_frame.pack(fill=tk.X, padx=40, pady=5)
        
        emp_dict = self.storage.get_employees() if self.storage else {}
        display_list = []
        for b_id, data in emp_dict.items():
            name_str = data.get("full_name", "Unknown") if isinstance(data, dict) else data
            display_list.append(f"{name_str} ({b_id})")
        display_list.sort()

        selected_user = tk.StringVar()
        combo = ctk.CTkComboBox(sel_frame, variable=selected_user, values=display_list, state="readonly", font=("Segoe UI", 13), width=320, justify="center")
        combo.pack(pady=5)

        qr_frame = ctk.CTkFrame(manager, width=280, height=280, fg_color="#f9f9f9", border_width=1, border_color="#e0e0e0")
        qr_frame.pack(pady=(15, 10))
        qr_frame.pack_propagate(False)

        qr_label = tk.Label(qr_frame, bg="#f9f9f9")
        qr_label.pack(expand=True)

        accent_color = "#09ce66" if ctk.get_appearance_mode() == "Dark" else "#217346"
        qr_text = ctk.CTkLabel(manager, text="", font=("Segoe UI", 14, "bold"), text_color=accent_color)
        qr_text.pack(pady=5)

        def generate_qr(event=None):
            selection = selected_user.get()
            if not selection: return
            badge_id = selection.split("(")[-1].replace(")", "").strip()
            
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(f"ID: {badge_id}")
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="#011528", back_color="#f9f9f9") 
            img = img.resize((260, 260), Image.Resampling.LANCZOS)
            
            tk_img = ImageTk.PhotoImage(img)
            qr_label.config(image=tk_img)
            qr_label.image = tk_img 
            qr_text.configure(text=f"Scan to login as: {selection.split('(')[0].strip()}")
            manager.focus_set()

        combo.configure(command=generate_qr)

        if display_list:
            combo.set(display_list[0])
            generate_qr()
            
    def open_waiting_for_removal(self):
        active_users = []
        if self.scanner_mgr:
            for node in list(self.scanner_mgr.active_scanners.values()):
                if node.user and node.user not in active_users:
                    active_users.append(node.user)
        
        if not active_users:
            if self.scanner_mgr:
                self.scanner_mgr.removal_mode = False 
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
            self.spawn_notification("Access Denied:\nPlease log in to a scanner first.")
            return

        if self.waiting_removal_win and self.waiting_removal_win.winfo_exists():
            return
            
        win = tk.Toplevel(self.root)
        self.waiting_removal_win = win
        win.title("Removal Mode Active")
        win.overrideredirect(True)
        bg_color, border_color = self._get_dynamic_colors()
        win.configure(bg=bg_color, highlightthickness=4, highlightbackground="#d9534f")
        win.attributes("-topmost", True)

        self.center_window(win, 420, 200)

        ctk.CTkLabel(win, text="Scanner is in Removal Mode", text_color="#d9534f", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(win, text="Scan a sample's QR code to delete it.", font=("Segoe UI", 12)).pack(pady=5)

        def cancel():
            if self.scanner_mgr:
                self.scanner_mgr.removal_mode = False
            win.destroy()
            self.spawn_notification("Removal mode cancelled.")

        ctk.CTkButton(win, text="Cancel", command=cancel, fg_color="#aaaaaa", hover_color="#888888", font=("Segoe UI", 12, "bold"), width=120).pack(pady=10)

    def open_removal_confirmation(self, sample_id, action_user, sample_name):
        win = tk.Toplevel(self.root)
        win.title("Confirm Removal")
        win.overrideredirect(True)
        bg_color, border_color = self._get_dynamic_colors()
        win.configure(bg=bg_color, highlightthickness=2, highlightbackground="#d9534f")
        win.attributes("-topmost", True)

        self.center_window(win, 440, 280)

        ctk.CTkLabel(win, text="⚠️ Warning", text_color="#d9534f", font=("Segoe UI", 18, "bold")).pack(pady=(15, 2))
        ctk.CTkLabel(win, text="Permanently remove:", font=("Segoe UI", 13)).pack()
        ctk.CTkLabel(win, text=f"{sample_name}", font=("Segoe UI", 14, "bold"), wraplength=380).pack(pady=2)
        ctk.CTkLabel(win, text=f"({sample_id})", text_color=["#666666", "#aaaaaa"], font=("Segoe UI", 11)).pack()
        
        req_frame = ctk.CTkFrame(win, fg_color=["#f9e6e6", "#4a1c1c"], border_width=1, border_color="#d9534f", corner_radius=4)
        req_frame.pack(pady=10, ipady=3, ipadx=10)
        ctk.CTkLabel(req_frame, text=f"Requested by: {action_user}", text_color=["#d9534f", "#ff6b6b"], font=("Segoe UI", 12, "bold")).pack()

        timeout_id = win.after(20000, lambda: cancel())

        def confirm():
            win.after_cancel(timeout_id)
            if self.storage:
                self.storage.remove_data_async(sample_id, action_user, self.message_queue)
            win.destroy()

        def cancel():
            if win.winfo_exists():
                win.after_cancel(timeout_id)
                win.destroy()
            self.spawn_notification("Removal cancelled due to inactivity.")

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=5)
        ctk.CTkButton(btn_frame, text="Confirm", command=confirm, fg_color="#d9534f", hover_color="#c9302c", font=("Segoe UI", 12, "bold"), width=120).pack(side=tk.LEFT, padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", command=cancel, fg_color="#aaaaaa", hover_color="#888888", font=("Segoe UI", 12, "bold"), width=120).pack(side=tk.LEFT, padx=10)

    def open_new_sample_form(self):
        active_users = []
        if self.scanner_mgr:
            for node in list(self.scanner_mgr.active_scanners.values()):
                if node.user and node.user not in active_users:
                    active_users.append(node.user)

        if not active_users and self.scanner_mgr and self.scanner_mgr.ad_fallback_name:
            active_users.append(self.scanner_mgr.ad_fallback_name)

        if not active_users:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
            self.spawn_notification("Access Denied:\nPlease log in to a scanner first.")
            return

        form = tk.Toplevel(self.root)
        form.title("Manual Sample Entry")
        form.overrideredirect(True)
        bg_color, border_color = self._get_dynamic_colors()
        form.configure(bg=bg_color, highlightthickness=2, highlightbackground=border_color) 
        form.attributes("-topmost", True)

        self.center_window(form, 480, 560)

        close_btn = ctk.CTkButton(form, text="✕", width=30, height=30, fg_color="transparent", text_color=["#999999", "#888888"], hover_color=["#ffcccc", "#662222"], command=form.destroy)
        close_btn.place(relx=1.0, x=-5, y=5, anchor="ne")

        ctk.CTkLabel(form, text="Sample ID (6-Digit Number)", font=("Segoe UI", 12, "bold")).pack(pady=(15, 2))
        entry_id = ctk.CTkEntry(form, width=280, justify="center", font=("Segoe UI", 14))
        entry_id.pack(pady=5)
        
        def limit_length(event):
            content = entry_id.get()
            if len(content) > 6:
                entry_id.delete(6, tk.END)
            elif not content.isdigit() and content != "":
                entry_id.delete(0, tk.END)
                entry_id.insert(0, ''.join(filter(str.isdigit, content)))
        entry_id.bind("<KeyRelease>", limit_length)

        ctk.CTkLabel(form, text="Requestor Name", font=("Segoe UI", 12, "bold")).pack(pady=(5, 2))
        entry_req = ctk.CTkEntry(form, width=280, justify="center", font=("Segoe UI", 14))
        entry_req.pack(pady=5)
        
        ctk.CTkLabel(form, text="Functional Department", font=("Segoe UI", 12, "bold")).pack(pady=(5, 2))
        dept_var = tk.StringVar()
        combo_dept = ctk.CTkComboBox(form, variable=dept_var, state="readonly", font=("Segoe UI", 14), width=280, justify="center")
        combo_dept.configure(values=("Customer Teams", "Engineering", "Global Materials Development", "Laboratories", "Quality", "Reman & Proto", "Technical Analysis"))
        combo_dept.pack(pady=5)

        ctk.CTkLabel(form, text="Project Number", font=("Segoe UI", 12, "bold")).pack(pady=(5, 2))
        entry_proj = ctk.CTkEntry(form, width=280, justify="center", font=("Segoe UI", 14))
        entry_proj.pack(pady=5)

        ctk.CTkLabel(form, text="Active Session", font=("Segoe UI", 12, "bold")).pack(pady=(10, 2))
        
        selected_user = tk.StringVar()
        accent_color = "#09ce66" if ctk.get_appearance_mode() == "Dark" else "#217346"
        
        if len(active_users) == 1:
            selected_user.set(active_users[0])
            user_frame = ctk.CTkFrame(form, fg_color=["#e8f4ea", "#1e3b2e"], border_width=1, border_color=accent_color, corner_radius=4)
            user_frame.pack(pady=5, ipady=3, ipadx=10)
            ctk.CTkLabel(user_frame, text=active_users[0], text_color=["#217346", "#09ce66"], font=("Segoe UI", 13, "bold"), width=240).pack()
        else:
            selected_user.set(active_users[0])
            combo_user = ctk.CTkComboBox(form, variable=selected_user, values=active_users, state="readonly", font=("Segoe UI", 13, "bold"), width=280, justify="center")
            combo_user.pack(pady=5)

        def reset_bg(event):
            err_color = ["#FFFFFF", "#081E33"]
            entry_id.configure(fg_color=err_color)
            entry_req.configure(fg_color=err_color)
            entry_proj.configure(fg_color=err_color)
            
        entry_id.bind("<Key>", reset_bg)
        entry_req.bind("<Key>", reset_bg)
        entry_proj.bind("<Key>", reset_bg)

        def save_manual_entry():
            id_raw = entry_id.get().strip()
            req_val = entry_req.get().strip().replace('\n', ' ').replace('\r', '')
            dept_val = dept_var.get().strip()
            proj_val = entry_proj.get().strip().replace('\n', ' ').replace('\r', '')
            user_val = selected_user.get() 
            
            if len(id_raw) == 6 and id_raw.isdigit() and req_val and dept_val and proj_val and user_val: 
                if self.storage:
                    self.storage.save_data_async(
                        location_id="LOC: Verification Queue", 
                        sample_id=id_raw,
                        requestor=req_val, 
                        dept=dept_val, 
                        project=proj_val,
                        user=user_val, 
                        message_queue=self.message_queue,
                        force_create=True 
                    )
                form.destroy()
            else:
                err_color = ["#ffcccc", "#662222"]
                if not id_raw or not id_raw.isdigit() or len(id_raw) != 6: entry_id.configure(fg_color=err_color)
                if not req_val: entry_req.configure(fg_color=err_color)
                if not proj_val: entry_proj.configure(fg_color=err_color)

        ctk.CTkButton(form, text="Initialize Item", command=save_manual_entry, font=("Segoe UI", 13, "bold"), width=180).pack(pady=(20, 20))

    def spawn_notification(self, text):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        transparent_color = "#FF00FF"
        window.configure(bg=transparent_color)
        window.wm_attributes("-transparentcolor", transparent_color)
        window.attributes("-topmost", True)
        
        canvas = tk.Canvas(window, bg=transparent_color, highlightthickness=0, width=400, height=100)
        canvas.pack()
        self.draw_rounded_rect(canvas, 5, 5, 395, 95, radius=15, color="#011528")
        
        lines = text.split('\n')
        if len(lines) == 3:
            tk.Label(window, text=lines[0], fg="#9db2c6", bg="#011528", font=("Segoe UI", 9, "bold")).place(relx=0.5, rely=0.20, anchor="center")
            tk.Label(window, text=lines[1], fg="#ffffff", bg="#011528", font=("Segoe UI", 12, "bold"), wraplength=380, justify="center").place(relx=0.5, rely=0.50, anchor="center")
            tk.Label(window, text=lines[2], fg="#cccccc", bg="#011528", font=("Segoe UI", 9)).place(relx=0.5, rely=0.80, anchor="center")
        elif len(lines) == 2:
            tk.Label(window, text=lines[0], fg="#9db2c6", bg="#011528", font=("Segoe UI", 9, "bold")).place(relx=0.5, rely=0.30, anchor="center")
            tk.Label(window, text=lines[1], fg="#ffffff", bg="#011528", font=("Segoe UI", 13, "bold"), wraplength=380, justify="center").place(relx=0.5, rely=0.65, anchor="center")
        else:
            tk.Label(window, text=text, fg="#ffffff", bg="#011528", font=("Segoe UI", 12, "bold"), wraplength=380, justify="center").place(relx=0.5, rely=0.5, anchor="center")
        
        self.position_and_show(window)
        window.after(6500, lambda: self.destroy_notification(window))

    def draw_rounded_rect(self, canvas, x1, y1, x2, y2, radius, color):
        points = [
            x1+radius, y1,  x2-radius, y1,  x2, y1,  x2, y1+radius,
            x2, y2-radius,  x2, y2,  x2-radius, y2,  x1+radius, y2,
            x1, y2,  x1, y2-radius,  x1, y1+radius,  x1, y1
        ]
        canvas.create_polygon(points, smooth=True, fill=color)

    def position_and_show(self, window):
        window.update_idletasks()
        window_width = 400
        window_height = 100
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x_pos = screen_width - window_width - 50
        y_pos = (screen_height - window_height - 60) - (len(self.active_notifications) * (window_height + 10))
        
        window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
        self.active_notifications.append(window)

    def destroy_notification(self, window):
        if window in self.active_notifications:
            self.active_notifications.remove(window)
            window.destroy()
            self.recalculate_positions()

    def recalculate_positions(self):
        window_width = 400
        window_height = 100
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x_pos = screen_width - window_width - 50
        base_y = screen_height - window_height - 60
        
        for index, window in enumerate(self.active_notifications):
            if window.winfo_exists():
                y_pos = base_y - (index * (window_height + 10))
                window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")

    def run(self):
        self.root.mainloop()