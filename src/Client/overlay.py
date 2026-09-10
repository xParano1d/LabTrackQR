# overlay.py (CLIENT VERSION)
import sys
import os
import ctypes
import qrcode
import tkinter as tk
import threading
import requests
from tkinter import ttk
from PIL import Image, ImageTk
from logviewer import LogViewerWindow # Uses the shared engine!

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
    """Checks Windows Registry to see if the taskbar is in Light or Dark mode."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        # If SystemUsesLightTheme is 0, taskbar is DARK -> use white icon
        # If SystemUsesLightTheme is 1, taskbar is LIGHT -> use black icon
        return "icon_white.ico" if value == 0 else "icon_black.ico"
    except Exception:
        return "icon_white.ico" # Fallback just in case

class NotificationManager:
    def __init__(self, message_queue, storage=None, scanner_mgr=None):
        self.message_queue = message_queue
        self.storage = storage
        self.scanner_mgr = scanner_mgr
        self.active_notifications = []
        self.waiting_removal_win = None
        self.active_log_windows = []
        
        self.root = tk.Tk()
        try:
            self.root.iconbitmap(default=resource_path(get_theme_icon()))
        except Exception:
            pass
            
        self.root.withdraw() 
        self.show_splash_screen()
        self.root.after(4500, self.check_queue)
        
        # --- Start the background heartbeat! ---
        self.root.after(5000, self.send_heartbeat)

    def send_heartbeat(self):
        """Silently pings the server to prove this client is online and tracks connection state."""
        if self.storage:
            target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")

            def ping_server():
                try:
                    # A quick, 2-second timeout ping just to trigger the server interceptor
                    resp = requests.get(f"{target_url}/api/ping", timeout=2)
                    
                    if resp.status_code == 200:
                        # If we WERE offline, but now we succeeded: Reconnect!
                        if getattr(self.storage, 'is_offline_mode', False):
                            self.storage.is_offline_mode = False
                            import winsound
                            winsound.MessageBeep(winsound.MB_ICONASTERISK)
                            # The polished "We are back" popup
                            self.message_queue.put("SERVER CONNECTED \nOnline mode active.\nSyncing data in background...")
                
                except Exception:
                    # If we WERE online, but the ping failed: Disconnect!
                    if not getattr(self.storage, 'is_offline_mode', True):
                        self.storage.is_offline_mode = True
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONHAND)
                        # The "Server died" popup
                        self.message_queue.put("⚠️ CONNECTION LOST ⚠️\nSwitched to Offline Mode.\nData will be saved locally.")

            # Fire and forget in a background thread
            threading.Thread(target=ping_server, daemon=True).start()

        # Run exactly every 5 seconds
        self.root.after(5000, self.send_heartbeat)

    def show_splash_screen(self):
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.configure(bg="#011528", highlightthickness=2, highlightbackground="#ffffff")
        splash.attributes("-topmost", True)
        
        width, height = 400, 240
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        splash.geometry(f"{width}x{height}+{x}+{y}")
        
        try:
            original_img = Image.open(resource_path("icon_white.ico"))
            resized_img = original_img.resize((80, 80), Image.Resampling.LANCZOS)
            self.splash_logo = ImageTk.PhotoImage(resized_img)
            tk.Label(splash, image=self.splash_logo, bg="#011528").pack(pady=(35, 0))
        except Exception:
            pass

        tk.Label(splash, text="LabTrackQR", bg="#011528", fg="white", font=("Segoe UI", 26, "bold")).pack(pady=(5,0))
        tk.Label(splash, text="Connecting to hardware & network...", bg="#011528", fg="#9db2c6", font=("Segoe UI", 11, "italic")).pack()
        splash.after(2500, splash.destroy)

    def check_queue(self):
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            
            if msg == "COMMAND:OPEN_FORM":
                self.open_new_sample_form()
                continue
            if msg == "COMMAND:OPEN_LOG_VIEWER":
                self.open_log_viewer()
                continue
            if msg == "COMMAND:WAITING_FOR_REMOVAL_SCAN":
                self.open_waiting_for_removal()
                continue
            if msg == "COMMAND:OPEN_USER_MANAGER":
                self.open_employee_directory()
                continue
            if msg == "COMMAND:SHOW_LOCK_SCREEN":
                self.open_lock_screen()
                continue
                
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

    def open_log_viewer(self):
        self.active_log_windows = [w for w in self.active_log_windows if w.viewer.winfo_exists()]
        if len(self.active_log_windows) >= 2:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
            self.spawn_notification("Window Limit Reached:\nMaximum of 2 log windows allowed.")
            return

        # Summons the shared LogViewerWindow and passes False for is_server
        viewer_instance = LogViewerWindow(self.root, self.storage, self.spawn_notification, is_server=False)
        self.active_log_windows.append(viewer_instance)

    # --- ALL OTHER CLIENT FUNCTIONS REMAIN EXACTLY THE SAME ---
    def open_relog_confirmation(self, new_user):
        if hasattr(self, 'relog_win') and self.relog_win and self.relog_win.winfo_exists():
            self.relog_win.lift()
            return
            
        win = tk.Toplevel(self.root)
        self.relog_win = win
        win.title("Switch User")
        win.geometry("400x220") 
        win.overrideredirect(True)
        win.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#f39c12")
        win.attributes("-topmost", True)

        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (400 // 2)
        y = (win.winfo_screenheight() // 2) - (220 // 2)
        win.geometry(f'+{x}+{y}')

        tk.Label(win, text="Switch User?", bg="#ffffff", fg="#f39c12", font=("Segoe UI", 16, "bold")).pack(pady=(15, 2))
        tk.Label(win, text=f"Do you want to log out the current user\nand log in as {new_user}?", bg="#ffffff", fg="#333333", font=("Segoe UI", 11)).pack(pady=2)

        revert_var = tk.BooleanVar(value=True) 
        chk = tk.Checkbutton(win, text="Revert to original user after 5 min of inactivity", variable=revert_var, bg="#ffffff", fg="#555555", font=("Segoe UI", 9, "italic"), activebackground="#ffffff", selectcolor="#ffffff")
        chk.pack(pady=5)

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

            if is_temp_now:
                self.spawn_notification(f"Temp Login Active:\nWelcome {new_user}!\n(5m idle timer running)")
            else:
                self.spawn_notification(f"Login Successful:\nWelcome {new_user}!")
            win.destroy()

        def cancel():
            if win.winfo_exists():
                win.after_cancel(timeout_id)
                win.destroy()
            self.spawn_notification("User switch cancelled.")

        btn_frame = tk.Frame(win, bg="#ffffff")
        btn_frame.pack(pady=5)
        
        tk.Button(btn_frame, text="Yes, Switch", command=confirm, bg="#f39c12", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=15).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=cancel, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)

    def open_register_badge(self, badge_id=None, ad_username=""):
        reg_win = tk.Toplevel(self.root)
        reg_win.title("Register New Employee")
        reg_win.geometry("400x380")
        reg_win.overrideredirect(True)
        reg_win.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#217346")
        reg_win.attributes("-topmost", True)

        reg_win.update_idletasks()
        x = (reg_win.winfo_screenwidth() // 2) - (400 // 2)
        y = (reg_win.winfo_screenheight() // 2) - (380 // 2)
        reg_win.geometry(f'+{x}+{y}')
        
        title_text = "Windows AD Setup" if ad_username else "New ID Card Detected"
        tk.Label(reg_win, text=title_text, bg="#ffffff", fg="#217346", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
        
        if ad_username:
            tk.Label(reg_win, text=f"Linking to Windows account: {ad_username}", bg="#ffffff", fg="#555555", font=("Segoe UI", 10, "italic")).pack(pady=(0, 10))
            
        tk.Label(reg_win, text="8-Digit Badge ID:", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(pady=(5, 2))
        entry_badge = tk.Entry(reg_win, font=("Segoe UI", 12), justify="center", width=25, relief="solid", bd=1)
        entry_badge.pack(ipady=3)
        if badge_id:
            entry_badge.insert(0, badge_id)
            entry_badge.config(state="disabled")
            
        tk.Label(reg_win, text="First Name:", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(pady=(15, 2))
        entry_first = tk.Entry(reg_win, font=("Segoe UI", 12), justify="center", width=25, relief="solid", bd=1)
        entry_first.pack(ipady=3)
        
        tk.Label(reg_win, text="Last Name:", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        entry_last = tk.Entry(reg_win, font=("Segoe UI", 12), justify="center", width=25, relief="solid", bd=1)
        entry_last.pack(ipady=3)
        
        def save_badge():
            b_id = entry_badge.get().strip()
            f_name = entry_first.get().strip()
            l_name = entry_last.get().strip()

            if len(b_id) == 8 and b_id.isdigit() and f_name and l_name:
                full_name = f"{f_name} {l_name}"
                
                # --- THE FIX ---
                if self.storage:
                    success = self.storage.add_employee(b_id, f_name, l_name, ad_username)
                    if not success:
                        self.spawn_notification("Registration Failed:\nCould not reach server.")
                        return  # Stops the function and keeps the window open!
                # ---------------

                if self.scanner_mgr:
                    for node in self.scanner_mgr.active_scanners.values():
                        if node.user is None or ad_username:
                            node.user = full_name
                            if ad_username: node.ad_fallback_name = full_name
                            self.message_queue.put(f"Login Successful:\nWelcome {full_name}!")

                self.spawn_notification(f"Registered Successfully:\n{full_name}")
                reg_win.destroy()
            else:
                if len(b_id) != 8: entry_badge.config(bg="#ffcccc")
                if not f_name: entry_first.config(bg="#ffcccc")
                if not l_name: entry_last.config(bg="#ffcccc")
                
        def cancel(): reg_win.destroy()
            
        btn_frame = tk.Frame(reg_win, bg="#ffffff")
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Cancel", command=cancel, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Assign & Save", command=save_badge, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=15).pack(side=tk.LEFT, padx=10)

    def open_employee_directory(self):
        manager = tk.Toplevel(self.root)
        manager.title("Employee Login Badges")
        manager.geometry("500x530")
        manager.overrideredirect(True)
        manager.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#011528")
        manager.attributes("-topmost", True)

        manager.update_idletasks()
        x = (manager.winfo_screenwidth() // 2) - (500 // 2)
        y = (manager.winfo_screenheight() // 2) - (530 // 2)
        manager.geometry(f'+{x}+{y}')

        close_btn = tk.Button(manager, text="✕", command=manager.destroy, bg="#ffffff", fg="#999999", font=("Segoe UI", 12, "bold"), relief="flat", activebackground="#ffcccc", cursor="hand2")
        close_btn.place(relx=1.0, x=-5, y=5, anchor="ne")

        # Refined Header
        tk.Label(manager, text="Employee Login Badges", bg="#ffffff", fg="#011528", font=("Segoe UI", 18, "bold")).pack(pady=(25, 5))
        tk.Label(manager, text="Select a user to automatically generate their QR card", bg="#ffffff", fg="#666666", font=("Segoe UI", 10, "italic")).pack(pady=(0, 15))

        sel_frame = tk.Frame(manager, bg="#ffffff")
        sel_frame.pack(fill=tk.X, padx=40, pady=5)
        
        emp_dict = self.storage.get_employees() if self.storage else {}
        display_list = []
        for b_id, data in emp_dict.items():
            name_str = data.get("full_name", "Unknown") if isinstance(data, dict) else data
            display_list.append(f"{name_str} ({b_id})")
        display_list.sort()

        # --- THE COMBOBOX STYLING UPGRADE ---
        # 1. Style the Dropdown List (The part that pops out)
        manager.option_add('*TCombobox*Listbox.background', '#ffffff')
        manager.option_add('*TCombobox*Listbox.foreground', '#333333')
        manager.option_add('*TCombobox*Listbox.selectBackground', '#011528')
        manager.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        manager.option_add('*TCombobox*Listbox.font', ('Segoe UI', 11))
        
        # 2. Style the Main Box (Prevents the solid blue highlight)
        style = ttk.Style()
        style.map('Modern.TCombobox', 
                  fieldbackground=[('readonly', '#ffffff')],
                  selectbackground=[('readonly', '#ffffff')],
                  selectforeground=[('readonly', '#011528')])

        selected_user = tk.StringVar()
        combo = ttk.Combobox(sel_frame, textvariable=selected_user, values=display_list, state="readonly", font=("Segoe UI", 12), width=35, style='Modern.TCombobox')
        combo.pack(pady=5, ipady=4)
        # ------------------------------------

        # Soft, premium QR code container
        qr_frame = tk.Frame(manager, bg="#f9f9f9", highlightthickness=1, highlightbackground="#e0e0e0", width=280, height=280)
        qr_frame.pack(pady=(15, 10))
        qr_frame.pack_propagate(False)

        qr_label = tk.Label(qr_frame, bg="#f9f9f9")
        qr_label.pack(expand=True)

        qr_text = tk.Label(manager, text="", bg="#ffffff", font=("Segoe UI", 12, "bold"), fg="#217346")
        qr_text.pack(pady=5)

        def generate_qr(event=None):
            selection = selected_user.get()
            if not selection: return
            badge_id = selection.split("(")[-1].replace(")", "").strip()
            
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(f"ID: {badge_id}")
            qr.make(fit=True)
            
            # Match the QR code to your app's Dark Blue theme!
            img = qr.make_image(fill_color="#011528", back_color="#f9f9f9") 
            img = img.resize((260, 260), Image.Resampling.LANCZOS)
            
            tk_img = ImageTk.PhotoImage(img)
            qr_label.config(image=tk_img)
            qr_label.image = tk_img 
            qr_text.config(text=f"Scan to login as: {selection.split('(')[0].strip()}")
            
            # 3. Instantly drops focus to kill the dotted outline!
            manager.focus_set()

        # Bind the dropdown selection so it auto-generates on click
        combo.bind("<<ComboboxSelected>>", generate_qr)

        # Pre-load the first user so the box isn't empty when the window opens
        if display_list:
            combo.current(0)
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
        win.geometry("400x160")
        win.overrideredirect(True)
        win.configure(bg="#ffffff", highlightthickness=4, highlightbackground="#d9534f")
        win.attributes("-topmost", True)

        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (400 // 2)
        y = (win.winfo_screenheight() // 2) - (160 // 2)
        win.geometry(f'+{x}+{y}')

        tk.Label(win, text="Scanner is in Removal Mode", bg="#ffffff", fg="#d9534f", font=("Segoe UI", 13, "bold")).pack(pady=(20, 5))
        tk.Label(win, text="Scan a sample's QR code to delete it.", bg="#ffffff", fg="#333333", font=("Segoe UI", 10)).pack(pady=5)

        def cancel():
            if self.scanner_mgr:
                self.scanner_mgr.removal_mode = False
            win.destroy()
            self.spawn_notification("Removal mode cancelled.")

        tk.Button(win, text="Cancel", command=cancel, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=15).pack(pady=10)

    def open_removal_confirmation(self, sample_id, action_user, sample_name):
        win = tk.Toplevel(self.root)
        win.title("Confirm Removal")
        win.geometry("420x260") 
        win.overrideredirect(True)
        win.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#d9534f")
        win.attributes("-topmost", True)

        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (420 // 2)
        y = (win.winfo_screenheight() // 2) - (260 // 2)
        win.geometry(f'+{x}+{y}')

        tk.Label(win, text="⚠️ Warning", bg="#ffffff", fg="#d9534f", font=("Segoe UI", 16, "bold")).pack(pady=(15, 2))
        tk.Label(win, text="Permanently remove:", bg="#ffffff", fg="#333333", font=("Segoe UI", 11)).pack()
        tk.Label(win, text=f"{sample_name}", bg="#ffffff", fg="#000000", font=("Segoe UI", 12, "bold"), wraplength=380, justify="center").pack(pady=2)
        tk.Label(win, text=f"({sample_id})", bg="#ffffff", fg="#666666", font=("Segoe UI", 10)).pack()
        tk.Label(win, text=f"Requested by: {action_user}", bg="#f9e6e6", fg="#d9534f", font=("Segoe UI", 10, "bold"), width=34, relief="solid", bd=1).pack(pady=10, ipady=3)

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

        btn_frame = tk.Frame(win, bg="#ffffff")
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Confirm", command=confirm, bg="#d9534f", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=cancel, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)

    def open_new_sample_form(self):
        active_users = []
        if self.scanner_mgr:
            for node in list(self.scanner_mgr.active_scanners.values()):
                if node.user and node.user not in active_users:
                    active_users.append(node.user)
        
        if not active_users:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
            self.spawn_notification("Access Denied:\nPlease log in to a scanner first.")
            return

        form = tk.Toplevel(self.root)
        form.title("Manual Sample Entry")
        form.geometry("450x430") 
        form.overrideredirect(True)
        form.configure(bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc") 
        form.attributes("-topmost", True)

        form.update_idletasks()
        width = form.winfo_width()
        height = form.winfo_height()
        x = (form.winfo_screenwidth() // 2) - (width // 2)
        y = (form.winfo_screenheight() // 2) - (height // 2)
        form.geometry(f'{width}x{height}+{x}+{y}')

        close_btn = tk.Button(form, text="✕", command=form.destroy, bg="#ffffff", fg="#999999", font=("Segoe UI", 12, "bold"), relief="flat", activebackground="#ffcccc", cursor="hand2")
        close_btn.place(relx=1.0, x=-5, y=5, anchor="ne")

        def only_numbers(char):
            return char.isdigit() or char == ""
        val_numbers = (form.register(only_numbers), '%P')

        tk.Label(form, text="Sample ID (Numbers only, e.g. 123)", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(15, 2))
        entry_id = tk.Entry(form, width=38, justify="center", font=("Segoe UI", 11), relief="solid", bd=1, validate="key", validatecommand=val_numbers)
        entry_id.pack(pady=5, ipady=4)

        tk.Label(form, text="Sample Name", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        entry_name = tk.Entry(form, width=38, justify="center", font=("Segoe UI", 11), relief="solid", bd=1)
        entry_name.pack(pady=5, ipady=4)
        
        tk.Label(form, text="Description / Notes", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        entry_notes = tk.Text(form, width=38, height=3, font=("Segoe UI", 11), relief="solid", bd=1, wrap=tk.WORD)
        entry_notes.pack(pady=5)

        tk.Label(form, text="Active Session", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        
        selected_user = tk.StringVar()
        if len(active_users) == 1:
            selected_user.set(active_users[0])
            tk.Label(form, text=active_users[0], bg="#e8f4ea", fg="#217346", font=("Segoe UI", 11, "bold"), width=34, relief="solid", bd=1).pack(pady=5, ipady=4)
        else:
            selected_user.set(active_users[0])
            from tkinter import ttk
            combo_user = ttk.Combobox(form, textvariable=selected_user, values=active_users, state="readonly", font=("Segoe UI", 11, "bold"), width=34)
            combo_user.pack(pady=5)

        def reset_bg(event):
            event.widget.config(bg="#ffffff")
            
        entry_id.bind("<Key>", reset_bg)
        entry_name.bind("<Key>", reset_bg)

        def save_manual_entry():
            id_raw = entry_id.get().strip()
            name_val = entry_name.get().strip().replace('\n', ' ').replace('\r', '')
            notes_val = entry_notes.get("1.0", tk.END).strip().replace('\n', ' | ').replace('\r', '')
            user_val = selected_user.get() 
            
            if id_raw.isdigit() and name_val and user_val: 
                formatted_id = f"SMP:{id_raw}"
                if self.storage:
                    self.storage.save_data_async(
                        location_id="LOC: Pending-Storage", 
                        sample_id=formatted_id,
                        sample_name=name_val, 
                        desc_notes=notes_val, 
                        user=user_val, 
                        message_queue=self.message_queue,
                        force_create=True 
                    )
                form.destroy()
            else:
                if not id_raw or not id_raw.isdigit(): entry_id.config(bg="#ffcccc")
                if not name_val: entry_name.config(bg="#ffcccc")

        tk.Button(form, text="Initialize Item", command=save_manual_entry, bg="#011528", fg="white", font=("Segoe UI", 11, "bold"), relief="flat", width=20, cursor="hand2").pack(pady=(15, 20))

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
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = screen_width - 450
        y_pos = (screen_height - 160) - (len(self.active_notifications) * 110)
        window.geometry(f"400x100+{x_pos}+{y_pos}")
        self.active_notifications.append(window)

    def destroy_notification(self, window):
        if window in self.active_notifications:
            self.active_notifications.remove(window)
            window.destroy()
            self.recalculate_positions()

    def recalculate_positions(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = screen_width - 450
        base_y = screen_height - 160
        for index, window in enumerate(self.active_notifications):
            if window.winfo_exists():
                y_pos = base_y - (index * 110)
                window.geometry(f"400x100+{x_pos}+{y_pos}")

    def run(self):
        self.root.mainloop()