# overlay.py
import tkinter as tk
from tkinter import PhotoImage
from tkinter import ttk
import sys
import os
import ctypes
from datetime import datetime
import qrcode
from PIL import Image, ImageTk

try:
    myappid = 'labtrack.qr.desktop.app.1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def resource_path(file_name):
    try:
        # COMPILED .exe MODE: PyInstaller extracts everything to the root of _MEIPASS
        base_path = sys._MEIPASS
        return os.path.join(base_path, file_name)
    except Exception:
        # DEVELOPMENT MODE: Calculate path from this script (src/Client) up to the img folder
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "..", "..", "img", file_name)

class NotificationManager:
    def __init__(self, message_queue, storage=None, scanner_mgr=None):
        self.message_queue = message_queue
        self.storage = storage
        self.scanner_mgr = scanner_mgr
        self.active_notifications = []
        self.waiting_removal_win = None
        
        self.root = tk.Tk()
        
        try:
            self.root.iconbitmap(default=resource_path("icon_white.ico"))
        except Exception as e:
            print(f"Icon failed to load: {e}")
            
        self.root.withdraw() 
        self.show_splash_screen() # Call the splash screen
        
        # Delay the queue processor for 4.5 seconds so it starts exactly after the splash screen dies
        self.root.after(4500, self.check_queue)

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
                # 1. Open your universal icon
                original_img = Image.open(resource_path("icon_white.ico"))
                # 2. Resize it to a crisp 80x80 for the center of the screen
                resized_img = original_img.resize((80, 80), Image.Resampling.LANCZOS)
                # 3. Save as 'self.splash_logo' so Tkinter doesn't delete it from memory!
                self.splash_logo = ImageTk.PhotoImage(resized_img)
                # 4. Display it at the top
                tk.Label(splash, image=self.splash_logo, bg="#011528").pack(pady=(35, 0))
            except Exception as e:
                print(f"Could not load logo: {e}")
    
            # The rest of your text, slightly adjusted padding
            tk.Label(splash, text="LabTrackQR", bg="#011528", fg="white", font=("Montserrat", 26, "bold")).pack(pady=(5,0))
            # tk.Label(splash, text="CLIENT", bg="#011528", fg="#9db2c6", font=("Montserrat", 16, "italic bold")).pack(pady=(0,2))
            tk.Label(splash, text="Connecting to hardware & network...", bg="#011528", fg="#9db2c6", font=("Montserrat", 11, "italic")).pack()
            
            # Destroys itself after 2500 milliseconds (2.5 seconds)
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
                
            if isinstance(msg, str) and msg.startswith("COMMAND:REGISTER_AD_USER:"):
                ad_username = msg.replace("COMMAND:REGISTER_AD_USER:", "")
                self.open_register_badge(badge_id=None, ad_username=ad_username)
                continue

            if isinstance(msg, str) and msg.startswith("COMMAND:CONFIRM_RELOG:"):
                new_user = msg.replace("COMMAND:CONFIRM_RELOG:", "")
                self.open_relog_confirmation(new_user)
                continue

            if isinstance(msg, str):
                clean_msg = msg.strip()
                if clean_msg:
                    self.spawn_notification(clean_msg)


        self.root.after(50, self.check_queue)

    def open_relog_confirmation(self, new_user):
        if hasattr(self, 'relog_win') and self.relog_win and self.relog_win.winfo_exists():
            self.relog_win.lift()
            return
            
        win = tk.Toplevel(self.root)
        self.relog_win = win
        win.title("Switch User")
        # Made taller to fit the checkbox comfortably
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

        # --- THE NEW CHECKBOX ---
        revert_var = tk.BooleanVar(value=True) # Defaults to checked
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
                    
                    # IDIOT-PROOFING 1: Kill any running timer immediately
                    if node.revert_timer:
                        node.revert_timer.cancel()
                        node.revert_timer = None
                    
                    # IDIOT-PROOFING 2: If the AD User logs back in manually, they cannot be temporary.
                    if new_user == node.ad_fallback_name:
                        node.auto_revert = False
                    else:
                        node.auto_revert = is_temporary
                        
                    # IDIOT-PROOFING 3: Start the timer (which checks the flag internally)
                    node._start_ad_revert_timer()
            
            # Check the final state to show the correct notification
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
                if self.storage:
                    # Save with the AD username if provided
                    self.storage.add_employee(b_id, f_name, l_name, ad_username)
                    
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
        display_list = []
        for b_id, data in emp_dict.items():
            # Handle the new dictionary format, but fallback to string for backwards compatibility
            name_str = data.get("full_name", "Unknown") if isinstance(data, dict) else data
            display_list.append(f"{name_str} ({b_id})")
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
        # --- ENFORCE 2 WINDOW LIMIT ---
        if not hasattr(self, 'active_log_windows'):
            self.active_log_windows = []
        # Clean out closed windows
        self.active_log_windows = [w for w in self.active_log_windows if w.winfo_exists()]
        
        if len(self.active_log_windows) >= 2:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
            self.spawn_notification("Window Limit Reached:\nMaximum of 2 log windows allowed.")
            return

        viewer = tk.Toplevel(self.root)
        self.active_log_windows.append(viewer)
        viewer.title("System Logs & Inventory")
        viewer.geometry("1000x550")
        viewer.configure(bg="#f4f4f4")
        
        # --- FIX TASKBAR ICON ---
        try:
            viewer.iconbitmap(default=resource_path("iconApp.ico"))
        except:
            pass
        
        # --- APPLY DARK MODE TO TITLE BAR ---
        self._apply_dark_title_bar(viewer)

        top_frame = tk.Frame(viewer, bg="#f4f4f4")
        top_frame.pack(fill=tk.X, pady=10, padx=10)

        btn_frame = tk.Frame(top_frame, bg="#f4f4f4")
        btn_frame.pack(side=tk.LEFT)

        search_frame = tk.Frame(top_frame, bg="#f4f4f4")
        search_frame.pack(side=tk.RIGHT)

       # --- UI: ALWAYS-ON SMART SEARCH ---
        search_var = tk.StringVar()

        tk.Label(search_frame, text="Search:", bg="#f4f4f4", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        entry_border = tk.Frame(search_frame, bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc")
        entry_border.pack(side=tk.LEFT)
        search_entry = tk.Entry(entry_border, textvariable=search_var, font=("Segoe UI", 10), width=25, relief="flat", bd=0)
        search_entry.pack(side=tk.LEFT, ipady=4, padx=8)

        # --- TREEVIEW SETUP ---
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

        def open_external_file():
            file_to_open = self.storage.get_active_file_path(current_tab[0])
            try:
                os.startfile(file_to_open)
            except Exception as e:
                self.spawn_notification(f"Could not open file:\n{e}")

        current_tab = ['inventory'] 
        current_history_target = [None, None] 
        last_data_hash = [""] 

        # --- THE DEEP SEARCH ENGINE ---
        search_thread_id = [0] 

        def run_deep_search(query):
            search_thread_id[0] += 1
            current_id = search_thread_id[0]

            # --- NEW: VISUAL FEEDBACK ---
            tree.delete(*tree.get_children())
            tree.insert("", tk.END, values=("", "", "⏳ DEEP SEARCH ACTIVE", f"Scanning...", "Reading archives, please wait...", "", ""))
            viewer.update_idletasks() # Force UI to draw this immediately
            # ----------------------------
                
            def worker():
                results = []
                query_lower = query.lower()
                seen = set()
                
                def add_row(r):
                    r_str = str(r)
                    if r_str not in seen:
                        seen.add(r_str)
                        results.append(r)
                        
                if current_id != search_thread_id[0]: return 
                for row in self.storage.get_inventory_data():
                    if any(query_lower in str(c).lower() for c in row):
                        add_row(row)
                        
                months = self.storage.get_available_history_months()
                for ym in months:
                    if current_id != search_thread_id[0]: return 
                    y, m = ym.split('-')
                    
                    for row in self.storage.get_specific_history(y, m):
                        if current_id != search_thread_id[0]: return 
                        if any(query_lower in str(c).lower() for c in row):
                            add_row(row)
                            
                if current_id == search_thread_id[0]:
                    viewer.after(0, lambda: render_deep_search(results))
                    
            import threading
            threading.Thread(target=worker, daemon=True).start()
            
        def render_deep_search(data):
            current_tab[0] = 'deep_search'
            tree.delete(*tree.get_children())
            for row in reversed(data):
                display_row = list(row) 
                display_row[2] = self._clean_and_iconify_location(str(display_row[2]))
                item_id = str(display_row[3]) if len(display_row) > 3 else ""
                tree.insert("", tk.END, text=item_id, values=display_row)
        # ------------------------------

        def load_data(source_type, search_query="", is_auto_refresh=False, year=None, month=None):
            if source_type == 'inventory':
                data = self.storage.get_inventory_data()
            elif source_type == 'history_specific':
                data = self.storage.get_specific_history(year, month)
            else:
                data = self.storage.get_all_time_history() 
            
            unique_data = []
            seen_rows = set()
            for row in data:
                row_str = str(row) 
                if row_str not in seen_rows:
                    seen_rows.add(row_str)
                    unique_data.append(row)
            data = unique_data

            current_hash = f"{len(data)}_{source_type}_{year}_{month}_{(str(data[-1]) if data else '')}"
            if is_auto_refresh and current_hash == last_data_hash[0]:
                return 
            last_data_hash[0] = current_hash

            current_tab[0] = source_type
            if year and month:
                current_history_target[0] = year
                current_history_target[1] = month
            
            selected_ids = []
            if is_auto_refresh:
                selected = tree.selection()
                selected_ids = [tree.item(item, "text") for item in selected]

            tree.delete(*tree.get_children())
            
            query = search_query.lower()
            for row in reversed(data):
                if query and not any(query in str(cell).lower() for cell in row):
                    continue
                
                display_row = list(row)
                display_row[2] = self._clean_and_iconify_location(str(display_row[2]))
                item_id = str(display_row[3]) if len(display_row) > 3 else ""
                
                inserted = tree.insert("", tk.END, text=item_id, values=display_row)
                if item_id and item_id in selected_ids:
                    try:
                        tree.selection_add(inserted)
                    except Exception:
                        pass

        search_timer = [None]
        def on_search_change(e):
            if search_timer[0] is not None:
                viewer.after_cancel(search_timer[0])
            
            query = search_var.get().strip()
            
            # --- THE SMART ROUTER ---
            if len(query) >= 2:
                # If they type 2+ characters, rip through everything automatically
                search_timer[0] = viewer.after(400, lambda: run_deep_search(query))
            else:
                # If they clear the box, revert exactly to whatever tab they were looking at
                # We pass an empty string so it doesn't try to filter by a single letter
                if current_tab[0] == 'deep_search': current_tab[0] = 'inventory' # Fallback if clearing search
                search_timer[0] = viewer.after(400, lambda: load_data(current_tab[0], "", year=current_history_target[0], month=current_history_target[1]))

        search_entry.bind("<KeyRelease>", on_search_change)

        def auto_refresh():
            if viewer.winfo_exists():
                # Pause auto-refresh entirely if they have text in the search bar
                if len(search_var.get().strip()) < 2:
                    load_data(current_tab[0], "", is_auto_refresh=True, year=current_history_target[0], month=current_history_target[1])
                viewer.after(2000, auto_refresh) 

        viewer.after(2000, auto_refresh)

        def copy_selection(event=None):
            selected = tree.selection()
            if not selected: 
                return
            
            copied_lines = []
            for item in selected:
                # Get the values for each selected row
                values = tree.item(item, "values")
                # Join them with a Tab (\t) character for clean Excel pasting
                copied_lines.append("\t".join(str(v) for v in values))
            
            viewer.clipboard_clear()
            viewer.clipboard_append("\n".join(copied_lines))
            
            # Optional: Give the user feedback that multiple rows copied
            copiedItemsCount=len(selected);
            if(copiedItemsCount>1):
                self.spawn_notification(f"Copied {copiedItemsCount} rows to clipboard")
            else:
                self.spawn_notification(f"Copied 1 row to clipboard")
        tree.bind("<Control-c>", copy_selection)


        now = datetime.now()
        curr_year = now.strftime("%Y")
        curr_month = now.strftime("%m")
        tk.Button(btn_frame, text="View Active Inventory", command=lambda: load_data('inventory', search_var.get()), bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Current Month Logs", command=lambda y=curr_year, m=curr_month: load_data('history_specific', search_var.get(), year=y, month=m), bg="#445566", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20).pack(side=tk.LEFT, padx=5)


        # --- DYNAMIC CASCADE MENU FOR HISTORY ---
        month_names = {"01": "January", "02": "February", "03": "March", "04": "April", "05": "May", "06": "June", 
                       "07": "July", "08": "August", "09": "September", "10": "October", "11": "November", "12": "December"}
        
        available_history = self.storage.get_available_history_months() if self.storage else []
        
        # Organize flat list into a dictionary: {'2026': ['09', '08'], '2027': ['01']}
        history_tree = {}
        for ym in available_history:
            y, m = ym.split('-')
            if y not in history_tree: history_tree[y] = []
            history_tree[y].append(m)

        history_btn = tk.Menubutton(btn_frame, text="Archive \u25BC", bg="#555555", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=15, activebackground="#777777", activeforeground="white", cursor="hand2")
        history_btn.pack(side=tk.LEFT, padx=5)

        main_menu = tk.Menu(history_btn, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
        history_btn.config(menu=main_menu)

        if not history_tree:
            main_menu.add_command(label="No Archives Found", state="disabled")
        else:
            # Sort years descending (newest first)
            for year in sorted(history_tree.keys(), reverse=True):
                year_menu = tk.Menu(main_menu, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
                main_menu.add_cascade(label=f"Year: {year}", menu=year_menu)
                
                # Sort months descending
                for month in sorted(history_tree[year], reverse=True):
                    pretty_month = f"{month_names.get(month, month)} ({month})"
                    # Use a lambda default argument (y=year, m=month) to capture the exact iteration values
                    year_menu.add_command(
                        label=pretty_month, 
                        command=lambda y=year, m=month: load_data('history_specific', search_var.get(), year=y, month=m)
                    )

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