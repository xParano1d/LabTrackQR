# overlay.py
import tkinter as tk
from tkinter import PhotoImage
from tkinter import ttk
import sys
import os
import ctypes

import qrcode
from PIL import Image, ImageTk

try:
    myappid = 'labtrack.qr.desktop.app.1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
        return os.path.join(base_path, relative_path)
    except Exception:
        if os.path.exists(relative_path):
            return os.path.abspath(relative_path)
        elif os.path.exists(os.path.join("..", relative_path)):
            return os.path.abspath(os.path.join("..", relative_path))
        return os.path.abspath(relative_path)

class NotificationManager:
    def __init__(self, message_queue, storage=None, scanner_mgr=None):
        self.message_queue = message_queue
        self.storage = storage
        self.scanner_mgr = scanner_mgr
        self.active_notifications = []
        self.waiting_removal_win = None
        
        self.root = tk.Tk()
        
        try:
            self.root.iconbitmap(default=resource_path("icon.ico"))
        except Exception as e:
            print(f"Icon failed to load: {e}")
            
        self.root.withdraw() 
        self.show_splash_screen() # Call the splash screen
        self.check_queue()

    def _apply_dark_title_bar(self, window):
        """Forces the Windows title bar into Dark Mode and applies custom brand colors."""
        try:
            window.update() # Ensure window is fully drawn first
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute

            # 1. Base Dark Mode (Serves as a fallback for Windows 10 users)
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            rendering_policy = ctypes.c_int(2)
            set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))

            # 2. Custom Title Bar Color (Windows 11+)
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36
            
            # #011528 translated to Windows COLORREF format (0x00BBGGRR)
            bg_color = ctypes.c_int(0x00281501)
            # Pure white text for contrast (0x00FFFFFF)
            text_color = ctypes.c_int(0x00FFFFFF) 
            
            set_window_attribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(bg_color), ctypes.sizeof(bg_color))
            set_window_attribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text_color), ctypes.sizeof(text_color))

        except Exception as e:
            pass # Fail silently on older versions of Windows

    def show_splash_screen(self):
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.configure(bg="#011528", highlightthickness=2, highlightbackground="#ffffff")
        splash.attributes("-topmost", True)
        
        # Increased height to 240 to perfectly fit the new logo
        width, height = 400, 240
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        splash.geometry(f"{width}x{height}+{x}+{y}")
        
        # --- THE LOGO INTEGRATION ---
        try:
            # 1. Open your universal icon.ico
            original_img = Image.open(resource_path("icon.ico"))
            # 2. Resize it to a crisp 80x80 for the center of the screen
            resized_img = original_img.resize((80, 80), Image.Resampling.LANCZOS)
            # 3. Save as 'self.splash_logo' so Tkinter doesn't delete it from memory!
            self.splash_logo = ImageTk.PhotoImage(resized_img)
            # 4. Display it at the top
            tk.Label(splash, image=self.splash_logo, bg="#011528").pack(pady=(25, 0))
        except Exception as e:
            print(f"Could not load logo: {e}")

        # The rest of your text, slightly adjusted padding
        tk.Label(splash, text="LabTrackQR", bg="#011528", fg="white", font=("Segoe UI", 26, "bold")).pack(pady=(5, 5))
        tk.Label(splash, text="Connecting to hardware & network...", bg="#011528", fg="#9db2c6", font=("Segoe UI", 11, "italic")).pack()
        
        # Destroys itself after 2500 milliseconds (2.5 seconds)
        splash.after(3000, splash.destroy)

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
                badge_id = msg.replace("COMMAND:UNKNOWN_BADGE:", "")
                self.open_register_badge(badge_id)
                continue
                
            if isinstance(msg, str) and msg.startswith("COMMAND:CONFIRM_REMOVE:"):
                if self.waiting_removal_win and self.waiting_removal_win.winfo_exists():
                    self.waiting_removal_win.destroy()
                
                raw_payload = msg.replace("COMMAND:CONFIRM_REMOVE:", "")
                parts = raw_payload.split("|")
                sample_id = parts[0]
                action_user = parts[1] if len(parts) > 1 else "Unknown"
                sample_name = parts[2] if len(parts) > 2 else "Unknown Sample"
                    
                self.open_removal_confirmation(sample_id, action_user, sample_name)
                continue
                
            if isinstance(msg, str):
                clean_msg = msg.strip()
                if clean_msg:
                    self.spawn_notification(clean_msg)

        self.root.after(50, self.check_queue)

    def open_lock_screen(self):
        if hasattr(self, 'lock_screen_win') and self.lock_screen_win and self.lock_screen_win.winfo_exists():
            self.lock_screen_win.lift()
            return

        win = tk.Toplevel(self.root)
        self.lock_screen_win = win
        win.title("Scanner Locked")
        win.geometry("450x180")
        
        win.overrideredirect(True)
        win.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#011528")
        win.attributes("-topmost", True)

        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (450 // 2)
        y = (win.winfo_screenheight() // 2) - (180 // 2)
        win.geometry(f'+{x}+{y}')

        tk.Label(win, text="Scanner Locked", bg="#ffffff", fg="#011528", font=("Segoe UI", 16, "bold")).pack(pady=(20, 10))
        tk.Label(win, text="Please scan your physical ID badge to log in.", bg="#ffffff", fg="#333333", font=("Segoe UI", 12)).pack(pady=5)

        btn_frame = tk.Frame(win, bg="#ffffff")
        btn_frame.pack(pady=15)

        def on_close():
            win.destroy()

        def on_open_directory():
            win.destroy()
            self.open_employee_directory()

        tk.Button(btn_frame, text="I have a badge (Close)", command=on_close, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=22).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Generate Login QR", command=on_open_directory, bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=18).pack(side=tk.LEFT, padx=10)

    def open_register_badge(self, badge_id):
        reg_win = tk.Toplevel(self.root)
        reg_win.title("Register New Employee")
        reg_win.geometry("400x300")
        
        reg_win.overrideredirect(True)
        reg_win.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#217346")
        reg_win.attributes("-topmost", True)

        reg_win.update_idletasks()
        x = (reg_win.winfo_screenwidth() // 2) - (400 // 2)
        y = (reg_win.winfo_screenheight() // 2) - (300 // 2)
        reg_win.geometry(f'+{x}+{y}')
        
        tk.Label(reg_win, text="New ID Card Detected", bg="#ffffff", fg="#217346", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
        tk.Label(reg_win, text=f"Badge ID: {badge_id}", bg="#ffffff", fg="#555555", font=("Segoe UI", 11)).pack()
        
        tk.Label(reg_win, text="First Name:", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(pady=(15, 2))
        entry_first = tk.Entry(reg_win, font=("Segoe UI", 12), justify="center", width=25, relief="solid", bd=1)
        entry_first.pack(ipady=3)
        
        tk.Label(reg_win, text="Last Name:", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        entry_last = tk.Entry(reg_win, font=("Segoe UI", 12), justify="center", width=25, relief="solid", bd=1)
        entry_last.pack(ipady=3)
        
        def save_badge():
            f_name = entry_first.get().strip()
            l_name = entry_last.get().strip()
            if f_name and l_name:
                full_name = f"{f_name} {l_name}"
                if self.storage:
                    self.storage.add_employee(badge_id, full_name)
                    
                # --- AUTO-LOGIN LOGIC ---
                # Log the newly registered user into any currently locked scanners
                if self.scanner_mgr:
                    for node in self.scanner_mgr.active_scanners.values():
                        if node.user is None:
                            node.user = full_name
                            self.message_queue.put(f"Login Successful:\nWelcome {full_name}!")
                            
                self.spawn_notification(f"Registered Successfully:\n{full_name}")
                reg_win.destroy()
            else:
                entry_first.config(bg="#ffcccc")
                entry_last.config(bg="#ffcccc")
                
        def cancel():
            reg_win.destroy()
            
        btn_frame = tk.Frame(reg_win, bg="#ffffff")
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Cancel", command=cancel, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Assign & Save", command=save_badge, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=15).pack(side=tk.LEFT, padx=10)

    def open_employee_directory(self):
        manager = tk.Toplevel(self.root)
        manager.title("Manage Employee Badges")
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

        tk.Label(manager, text="Manage Employee Badges", bg="#ffffff", fg="#011528", font=("Segoe UI", 18, "bold")).pack(pady=(20, 10))
        
        sel_frame = tk.Frame(manager, bg="#ffffff")
        sel_frame.pack(fill=tk.X, padx=30, pady=10)
        
        tk.Label(sel_frame, text="Select Employee:", bg="#ffffff", fg="#333333", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        
        emp_dict = self.storage.get_employees() if self.storage else {}
        display_list = [f"{name} ({b_id})" for b_id, name in emp_dict.items()]
        display_list.sort()
            
        selected_user = tk.StringVar()
        combo = ttk.Combobox(sel_frame, textvariable=selected_user, values=display_list, state="readonly", font=("Segoe UI", 12), width=40)
        combo.pack(pady=5, ipady=3)
        if display_list:
            combo.current(0)
            
        qr_frame = tk.Frame(manager, bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc", width=250, height=250)
        qr_frame.pack(pady=10)
        qr_frame.pack_propagate(False)
        
        qr_label = tk.Label(qr_frame, bg="#ffffff")
        qr_label.pack(expand=True)
        
        qr_text = tk.Label(manager, text="Select an employee and click Generate", bg="#ffffff", font=("Segoe UI", 10, "italic"), fg="#555")
        qr_text.pack(pady=5)
        
        def generate_qr():
            selection = selected_user.get()
            if not selection: return
            
            badge_id = selection.split("(")[-1].replace(")", "").strip()
            
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(f"ID: {badge_id}")
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            img = img.resize((230, 230), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            
            qr_label.config(image=tk_img)
            qr_label.image = tk_img 
            
            qr_text.config(text=f"Scan to login as: {selection.split('(')[0].strip()}", font=("Segoe UI", 12, "bold"), fg="#217346")

        tk.Button(sel_frame, text="Generate Login QR", command=generate_qr, bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2").pack(pady=10)

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
        # Made taller to fit wrapped text
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
        
        # FIX: ADDED WRAPLENGTH SO LONG NAMES DON'T OVERFLOW
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
        
        # FIX: ADDED WRAP=TK.WORD TO PREVENT WORDS FROM SPLITTING IN HALF
        entry_notes = tk.Text(form, width=38, height=3, font=("Segoe UI", 11), relief="solid", bd=1, wrap=tk.WORD)
        entry_notes.pack(pady=5)

        tk.Label(form, text="Active Session", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        
        selected_user = tk.StringVar()
        
        if len(active_users) == 1:
            selected_user.set(active_users[0])
            tk.Label(form, text=active_users[0], bg="#e8f4ea", fg="#217346", font=("Segoe UI", 11, "bold"), width=34, relief="solid", bd=1).pack(pady=5, ipady=4)
        else:
            selected_user.set(active_users[0])
            combo_user = ttk.Combobox(form, textvariable=selected_user, values=active_users, state="readonly", font=("Segoe UI", 11, "bold"), width=34)
            combo_user.pack(pady=5)

        def reset_bg(event):
            event.widget.config(bg="#ffffff")
            
        entry_id.bind("<Key>", reset_bg)
        entry_name.bind("<Key>", reset_bg)

        def save_manual_entry():
            id_raw = entry_id.get().strip()
            name_val = entry_name.get().strip().replace('\n', ' ').replace('\r', '')
            
            # --- SANITIZE NEWLINES OUT OF THE TEXT BOX ---
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
                if not id_raw or not id_raw.isdigit(): 
                    entry_id.config(bg="#ffcccc")
                if not name_val: 
                    entry_name.config(bg="#ffcccc")

        tk.Button(form, text="Initialize Item", command=save_manual_entry, bg="#011528", fg="white", font=("Segoe UI", 11, "bold"), relief="flat", width=20, cursor="hand2").pack(pady=(15, 20))

    def _clean_and_iconify_location(self, loc_str):
        clean_str = loc_str.replace('LOC:', '').replace('LOC-', '').strip()
        lower_str = clean_str.lower()
        
        if any(k in lower_str for k in ['microscop', 'mikroskop', 'profilometry', 'photography', 'fotografia']):
            icon = "🔬"
        elif any(k in lower_str for k in ['cabinet', 'rack', 'storage', 'warehouse', 'szafa', 'regał', 'magazyn']):
            icon = "🗄️"
        elif any(k in lower_str for k in ['office', 'biuro']):
            icon = "🧑‍💼"
        elif any(k in lower_str for k in ['preparation', 'polishing', 'printers', 'przygotowanie', 'drukarki']):
            icon = "⚙️"
        elif any(k in lower_str for k in ['testing', 'analysis', 'test', 'analiza']):
            icon = "📊"
        elif any(k in lower_str for k in ['pending', 'manual', 'unassigned']):
            icon = "⏳"
        elif 'action: removed' in lower_str:
            icon = "❌"
        elif 'system: ' in lower_str:
            icon = "🔧"
        else:
            icon = "📍"
            
        return f"{icon} {clean_str}"

    def open_log_viewer(self):
        viewer = tk.Toplevel(self.root)
        viewer.title("System Logs & Inventory")
        viewer.geometry("1000x550")
        viewer.configure(bg="#f4f4f4")
        
        # --- APPLY DARK MODE TO TITLE BAR ---
        self._apply_dark_title_bar(viewer)

        top_frame = tk.Frame(viewer, bg="#f4f4f4")
        top_frame.pack(fill=tk.X, pady=10, padx=10)

        btn_frame = tk.Frame(top_frame, bg="#f4f4f4")
        btn_frame.pack(side=tk.LEFT)

        search_frame = tk.Frame(top_frame, bg="#f4f4f4")
        search_frame.pack(side=tk.RIGHT)

        search_var = tk.StringVar()
        tk.Label(search_frame, text="Search:", bg="#f4f4f4", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        entry_border = tk.Frame(search_frame, bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc")
        entry_border.pack(side=tk.LEFT)
        search_entry = tk.Entry(entry_border, textvariable=search_var, font=("Segoe UI", 10), width=25, relief="flat", bd=0)
        search_entry.pack(side=tk.LEFT, ipady=4, padx=8)

        columns = ("Date/Day", "Time", "Location", "Sample ID", "Name", "Notes", "User")
        tree = ttk.Treeview(viewer, columns=columns, show="headings", height=15)
        
        for col in columns:
            tree.heading(col, text=col)
        tree.column("Date/Day", width=90, anchor=tk.CENTER)
        tree.column("Time", width=80, anchor=tk.CENTER)
        tree.column("Location", width=180, anchor=tk.W)
        tree.column("Sample ID", width=90, anchor=tk.CENTER)
        tree.column("Name", width=150, anchor=tk.W)
        tree.column("Notes", width=250, anchor=tk.W) 
        tree.column("User", width=120, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(viewer, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        tk.Label(viewer, text="Tip: Select a row and press Ctrl+C to copy data", bg="#f4f4f4", fg="#666666", font=("Segoe UI", 9, "italic")).pack(side=tk.LEFT, padx=10, pady=(0, 5))

        current_tab = ['inventory'] 
        last_data_hash = [""] 

        def open_external_file():
            # Dynamically grabs NAS file if online, or Local file if offline
            file_to_open = self.storage.get_active_file_path(current_tab[0])
            try:
                os.startfile(file_to_open)
            except Exception as e:
                self.spawn_notification(f"Could not open file:\n{e}")

        def load_data(source_type, search_query="", is_auto_refresh=False):
            if source_type == 'inventory':
                data = self.storage.get_inventory_data()
            else:
                data = self.storage.get_all_time_history() # Seamlessly loads all history
            
            current_hash = str(len(data)) + source_type + (str(data[-1]) if data else "")
            if is_auto_refresh and current_hash == last_data_hash[0]:
                return 
            last_data_hash[0] = current_hash

            current_tab[0] = source_type
            
            selected = tree.selection()
            selected_ids = [tree.item(item, "text") for item in selected]

            tree.delete(*tree.get_children())
            
            query = search_query.lower()
            for row in reversed(data):
                if query and not any(query in str(cell).lower() for cell in row):
                    continue
                row[2] = self._clean_and_iconify_location(str(row[2]))
                
                item_id = str(row[3]) if len(row) > 3 else ""
                try:
                    inserted = tree.insert("", tk.END, text=item_id, values=row)
                    if item_id in selected_ids:
                        tree.selection_add(inserted)
                except:
                    tree.insert("", tk.END, values=row)

        search_timer = [None]
        def on_search_change(e):
            if search_timer[0] is not None:
                viewer.after_cancel(search_timer[0])
            search_timer[0] = viewer.after(400, lambda: load_data(current_tab[0], search_var.get()))

        search_entry.bind("<KeyRelease>", on_search_change)

        def auto_refresh():
            if viewer.winfo_exists():
                load_data(current_tab[0], search_var.get(), is_auto_refresh=True)
                viewer.after(2000, auto_refresh) 

        viewer.after(2000, auto_refresh)

        def copy_selection(event):
            selected = tree.selection()
            if selected:
                values = tree.item(selected[0], 'values')
                clipboard_text = "\t".join(str(v) for v in values)
                viewer.clipboard_clear()
                viewer.clipboard_append(clipboard_text)
                self.spawn_notification("Row copied to clipboard!")
        tree.bind("<Control-c>", copy_selection)

        # YOUR BEAUTIFUL BUTTONS ARE BACK
        tk.Button(btn_frame, text="View Active Inventory", command=lambda: load_data('inventory', search_var.get()), bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="View History Archive", command=lambda: load_data('history', search_var.get()), bg="#555555", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=25).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Open in External Editor", command=open_external_file, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=22).pack(side=tk.LEFT, padx=5)

        load_data('inventory')

    def spawn_notification(self, text):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        
        transparent_color = "#FF00FF"
        window.configure(bg=transparent_color)
        window.wm_attributes("-transparentcolor", transparent_color)
        window.attributes("-topmost", True)
        
        # MADE SLIGHTLY TALLER TO ACCOMMODATE WRAPPING
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
            # FIX: ADDED WRAPLENGTH TO PREVENT OVERFLOW
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
        # ADJUSTED Y OFFSET FOR THE TALLER 100px NOTIFICATIONS
        base_y = screen_height - 160
        y_pos = base_y - (len(self.active_notifications) * 110)
        
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