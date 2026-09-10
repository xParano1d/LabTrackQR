# overlay.py (SERVER VERSION)
import tkinter as tk
import sys
import os
import ctypes
from PIL import Image, ImageTk
from tkinter import ttk, messagebox
from logviewer import LogViewerWindow # Uses the shared engine!

try:
    myappid = 'labtrack.qr.desktop.app.server.1' 
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
        self.active_log_windows = []
        
        self.root = tk.Tk()
        try:
            self.root.iconbitmap(default=resource_path(get_theme_icon()))
        except Exception:
            pass
            
        self.root.withdraw() 
        self.show_splash_screen() 
        self.root.after(4500, self.check_queue)

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
        tk.Label(splash, text="SERVER", bg="#011528", fg="#9db2c6", font=("Segoe UI", 16, "italic bold")).pack(pady=(0,2))
        splash.after(2500, splash.destroy)

    def check_queue(self):
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            
            if msg == "COMMAND:OPEN_LOG_VIEWER":
                self.open_log_viewer()
                continue
                
            if msg == "COMMAND:OPEN_USER_MANAGER":
                self.open_user_manager()
                continue
                
            if isinstance(msg, str) and msg.startswith("COMMAND:"):
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

        # Summons the shared LogViewerWindow and passes True for is_server
        viewer_instance = LogViewerWindow(self.root, self.storage, self.spawn_notification, is_server=True)
        self.active_log_windows.append(viewer_instance)

    def open_user_manager(self):
        if hasattr(self, 'user_mgr_win') and self.user_mgr_win and self.user_mgr_win.winfo_exists():
            self.user_mgr_win.lift()
            return

        win = tk.Toplevel(self.root)
        self.user_mgr_win = win
        win.title("User Management Dashboard")
        win.geometry("780x520")
        win.configure(bg="#f4f4f4")
        
        # Background memory to track if we are fixing a typo in an existing ID
        win.current_editing_badge = None 
        
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(2)), 4)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(0x00281501)), 4)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(ctypes.c_int(0x00FFFFFF)), 4)
        except Exception: pass

        left_frame = tk.Frame(win, bg="#f4f4f4")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        right_frame = tk.Frame(win, bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        tk.Label(left_frame, text="Registered Employees", bg="#f4f4f4", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0,5))

        # 1. The Dynamic Employee List
        columns = ("Badge ID", "Full Name", "AD Login")
        tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        
        # --- THE FIX: Clickable Sorting Headers! ---
        def sort_column(col, reverse):
            data_list = [(tree.set(child, col), child) for child in tree.get_children('')]
            data_list.sort(reverse=reverse, key=lambda x: x[0].lower())
            for index, (val, child) in enumerate(data_list):
                tree.move(child, '', index)
            # Switch the arrow direction for the next click
            tree.heading(col, command=lambda: sort_column(col, not reverse))

        for col in columns: 
            tree.heading(col, text=col, command=lambda c=col: sort_column(c, False))
        # -------------------------------------------

        tree.column("Badge ID", width=90, anchor=tk.CENTER)
        tree.column("Full Name", width=180, anchor=tk.W)
        tree.column("AD Login", width=120, anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True)

        # 2. The Form Fields
        tk.Label(right_frame, text="Employee Details", bg="#ffffff", font=("Segoe UI", 14, "bold"), fg="#011528").pack(pady=(15, 0))
        
        # --- NEW: Dynamic Mode Indicator ---
        mode_label = tk.Label(right_frame, text="Creating New User", bg="#ffffff", fg="#217346", font=("Segoe UI", 9, "bold italic"))
        mode_label.pack(pady=(0, 15))

        tk.Label(right_frame, text="Badge ID (8 Digits):", bg="#ffffff", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15)
        entry_badge = tk.Entry(right_frame, font=("Segoe UI", 11), relief="solid", bd=1)
        entry_badge.pack(fill=tk.X, padx=15, pady=(2, 10), ipady=3)

        tk.Label(right_frame, text="First Name:", bg="#ffffff", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15)
        entry_first = tk.Entry(right_frame, font=("Segoe UI", 11), relief="solid", bd=1)
        entry_first.pack(fill=tk.X, padx=15, pady=(2, 10), ipady=3)

        tk.Label(right_frame, text="Last Name:", bg="#ffffff", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15)
        entry_last = tk.Entry(right_frame, font=("Segoe UI", 11), relief="solid", bd=1)
        entry_last.pack(fill=tk.X, padx=15, pady=(2, 10), ipady=3)

        tk.Label(right_frame, text="Windows AD Login:", bg="#ffffff", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15)
        entry_ad = tk.Entry(right_frame, font=("Segoe UI", 11), relief="solid", bd=1)
        entry_ad.pack(fill=tk.X, padx=15, pady=(2, 20), ipady=3)

        # --- LOGIC & EVENTS ---
        def load_data():
            tree.delete(*tree.get_children())
            emps = self.storage.get_employees() if self.storage else {}
            for b_id, data in emps.items():
                if isinstance(data, dict):
                    tree.insert("", tk.END, text=str(b_id), values=(str(b_id), data.get("full_name", ""), data.get("ad_username", "")))

        def on_select(event):
            selected = tree.selection()
            if not selected: return
            
            b_id = str(tree.item(selected[0], "text"))
            emps = self.storage.get_employees()
            if b_id in emps:
                data = emps[b_id]
                
                # Remember who we are editing!
                win.current_editing_badge = b_id 
                mode_label.config(text="Editing Existing User", fg="#f39c12")
                
                # Now the badge ID is fully editable to fix typos!
                entry_badge.delete(0, tk.END)
                entry_badge.insert(0, b_id)

                entry_first.delete(0, tk.END)
                entry_first.insert(0, data.get("first_name", ""))
                entry_last.delete(0, tk.END)
                entry_last.insert(0, data.get("last_name", ""))
                entry_ad.delete(0, tk.END)
                entry_ad.insert(0, data.get("ad_username", ""))

        tree.bind("<<TreeviewSelect>>", on_select)

        def prepare_new_user():
            win.current_editing_badge = None
            mode_label.config(text="Creating New User", fg="#217346")
            
            entry_badge.delete(0, tk.END)
            entry_first.delete(0, tk.END)
            entry_last.delete(0, tk.END)
            entry_ad.delete(0, tk.END)
            for sel in tree.selection(): tree.selection_remove(sel)

        def save_user():
            b_id = entry_badge.get().strip()
            f_name = entry_first.get().strip()
            l_name = entry_last.get().strip()
            ad_user = entry_ad.get().strip()

            if len(b_id) != 8 or not b_id.isdigit():
                messagebox.showerror("Error", "Badge ID must be exactly 8 numbers.", parent=win)
                return
            if not f_name or not l_name:
                messagebox.showerror("Error", "First and Last name are required.", parent=win)
                return

            if self.storage:
                # --- THE FIX: Delete the old profile if they fixed a typo in the Badge ID ---
                old_b_id = win.current_editing_badge
                if old_b_id and old_b_id != b_id:
                    self.storage.delete_employee(old_b_id)
                # ----------------------------------------------------------------------------
                
                self.storage.add_employee(b_id, f_name, l_name, ad_user)
                self.spawn_notification(f"Saved Successfully:\n{f_name} {l_name}")
                load_data()
                prepare_new_user()

        def delete_user():
            # Protect against empty deletions
            b_id = win.current_editing_badge or entry_badge.get().strip()
            if not b_id: return
            
            # Safely fetch the user's real name directly from the database
            emps = self.storage.get_employees() if self.storage else {}
            full_name = emps.get(b_id, {}).get("full_name", "Unknown User")
            
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete {full_name} (ID:{b_id})?", parent=win):
                if self.storage:
                    self.storage.delete_employee(b_id)
                    self.spawn_notification(f"User Deleted:\n{full_name}")
                    load_data()
                    prepare_new_user()

        # 3. Action Buttons
        btn_frame = tk.Frame(right_frame, bg="#ffffff")
        btn_frame.pack(fill=tk.X, padx=15, pady=5)

        tk.Button(btn_frame, text="Save / Update", command=save_user, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2").pack(fill=tk.X, pady=3)
        tk.Button(btn_frame, text="New User", command=prepare_new_user, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2").pack(fill=tk.X, pady=3)
        tk.Button(btn_frame, text="Delete User", command=delete_user, bg="#d9534f", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2").pack(fill=tk.X, pady=(25, 0))

        load_data()

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