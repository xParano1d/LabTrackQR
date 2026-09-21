# overlay.py (SERVER VERSION)
import customtkinter as ctk
ctk.ScalingTracker.deactivate_automatic_dpi_awareness = True # THE MASTER FIX

import sys
import os
import ctypes
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import ttk, messagebox
from logviewer import LogViewerWindow

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
        self.active_log_windows = []
        
        theme_path = resource_path("BW_theme.json")
        if os.path.exists(theme_path):
            ctk.set_default_color_theme(theme_path)

        self.root = ctk.CTk()
        try:
            self.root.iconbitmap(default=resource_path(get_theme_icon()))
        except Exception:
            pass
            
        self.root.withdraw() 
        self.show_splash_screen() 
        self.root.after(4500, self.check_queue)

    def _get_dynamic_colors(self):
        mode = 1 if ctk.get_appearance_mode() == "Dark" else 0
        bg_color = ctk.ThemeManager.theme["CTk"]["fg_color"][mode]
        border_color = ctk.ThemeManager.theme["CTkFrame"]["border_color"][mode]
        return bg_color, border_color

    def center_window(self, window, width, height):
        window.update_idletasks()
        
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        
        x = int((screen_w / 2) - (width / 2))
        y = int((screen_h / 2) - (height / 2))
        
        window.geometry(f"{width}x{height}+{x}+{y}")

    def show_splash_screen(self):
        # --- DYNAMIC THEME COLORS ---
        mode = 1 if ctk.get_appearance_mode() == "Dark" else 0
        bg_color = ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"][mode]
        border_color = ctk.ThemeManager.theme["CTkFrame"]["border_color"][mode]
        text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode]
        sub_text_color = ctk.ThemeManager.theme["CTkButton"]["text_color_disabled"][mode]

        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.configure(bg=bg_color, highlightthickness=4, highlightbackground=border_color)
        splash.attributes("-topmost", True)
        
        self.center_window(splash, 400, 240)
        
        try:
            # Dynamically loads icon_white.ico or icon_black.ico!
            original_img = Image.open(resource_path(get_theme_icon()))
            resized_img = original_img.resize((80, 80), Image.Resampling.LANCZOS)
            self.splash_logo = ImageTk.PhotoImage(resized_img)
            tk.Label(splash, image=self.splash_logo, bg=bg_color).pack(pady=(35, 0))
        except Exception:
            pass

        tk.Label(splash, text="LabTrackQR", bg=bg_color, fg=text_color, font=("Segoe UI", 26, "bold")).pack(pady=(5,0))
        tk.Label(splash, text="SERVER", bg=bg_color, fg=sub_text_color, font=("Segoe UI", 16, "italic bold")).pack(pady=(0,2))
        splash.after(2500, splash.destroy)

    def check_queue(self):
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            
            if msg == "COMMAND:OPEN_LOG_VIEWER": self.open_log_viewer(); continue
            if msg == "COMMAND:OPEN_USER_MANAGER": self.open_user_manager(); continue
            if isinstance(msg, str) and msg.startswith("COMMAND:"): continue

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

            latest_viewer = self.active_log_windows[-1].viewer
            latest_viewer.deiconify()
            latest_viewer.lift()
            latest_viewer.attributes('-topmost', True)
            latest_viewer.after(100, lambda: latest_viewer.attributes('-topmost', False))
            latest_viewer.focus_force()
            return

        viewer_instance = LogViewerWindow(self.root, self.storage, self.spawn_notification, is_server=True)
        self.active_log_windows.append(viewer_instance)

    def open_user_manager(self):
        if hasattr(self, 'user_mgr_win') and self.user_mgr_win and self.user_mgr_win.winfo_exists():
            self.user_mgr_win.deiconify()               
            self.user_mgr_win.lift()                    
            self.user_mgr_win.attributes('-topmost', True) 
            self.user_mgr_win.after(100, lambda: self.user_mgr_win.attributes('-topmost', False)) 
            self.user_mgr_win.focus_force()             
            return

        win = ctk.CTkToplevel(self.root)
        self.user_mgr_win = win
        win.title("User Management Dashboard")
        win.current_editing_badge = None 
        try:
            win.after(200, lambda: win.iconbitmap(resource_path(get_theme_icon())))
        except Exception: pass 
        
        self.center_window(win, 780, 520)
        
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(2)), 4)
            
            mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
            bg_hex = ctk.ThemeManager.theme["CTk"]["fg_color"][mode_idx]
            text_hex = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode_idx]

            def hex_to_bgr(hex_str):
                c = int(hex_str.replace("#", ""), 16)
                return (c & 0xFF) << 16 | (c & 0xFF00) | (c >> 16)

            bg_color = ctypes.c_int(hex_to_bgr(bg_hex))
            text_color = ctypes.c_int(hex_to_bgr(text_hex))
            
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(bg_color), 4)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), 4)
        except Exception: pass

        left_frame = ctk.CTkFrame(win, fg_color="transparent")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        right_frame = ctk.CTkFrame(win, width=320)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        right_frame.pack_propagate(False)

        ctk.CTkLabel(left_frame, text="Registered Employees", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold")).pack(anchor="w", pady=(0,5))

        style = ttk.Style(win)
        style.theme_use("default")
        bg_color = win._apply_appearance_mode(["#FFFFFF", "#081E33"])
        text_color = win._apply_appearance_mode(["#051728", "#FFFFFF"])
        selected_color = win._apply_appearance_mode(["#00386C", "#0E8187"])
        head_bg = win._apply_appearance_mode(["#F2F0EB", "#051728"])
        head_hover = win._apply_appearance_mode(["#E2ECF5", "#0B2238"])

        style.configure("Treeview", background=bg_color, foreground=text_color, rowheight=28, fieldbackground=bg_color, borderwidth=0)
        style.map('Treeview', background=[('selected', selected_color)])
        style.configure("Treeview.Heading", background=head_bg, foreground=text_color, relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Treeview.Heading", background=[('active', head_hover)])

        columns = ("Badge ID", "Full Name", "AD Login")
        tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        
        def sort_column(col, reverse):
            data_list = [(tree.set(child, col), child) for child in tree.get_children('')]
            data_list.sort(reverse=reverse, key=lambda x: x[0].lower())
            for index, (val, child) in enumerate(data_list):
                tree.move(child, '', index)
            tree.heading(col, command=lambda: sort_column(col, not reverse))

        for col in columns: 
            tree.heading(col, text=col, command=lambda c=col: sort_column(c, False))

        tree.column("Badge ID", width=90, anchor=tk.CENTER)
        tree.column("Full Name", width=180, anchor=tk.W)
        tree.column("AD Login", width=120, anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True)

        ctk.CTkLabel(right_frame, text="Employee Details", font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold")).pack(pady=(15, 0))
        
        accent_color = "#09ce66" if ctk.get_appearance_mode() == "Dark" else "#217346"
        mode_label = ctk.CTkLabel(right_frame, text="Creating New User", text_color=accent_color, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold", slant="italic"))
        mode_label.pack(pady=(0, 15))

        ctk.CTkLabel(right_frame, text="First Name:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=25)
        entry_first = ctk.CTkEntry(right_frame, font=("Segoe UI", 13))
        entry_first.pack(fill=tk.X, padx=25, pady=(2, 10))

        ctk.CTkLabel(right_frame, text="Last Name:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=25)
        entry_last = ctk.CTkEntry(right_frame, font=("Segoe UI", 13))
        entry_last.pack(fill=tk.X, padx=25, pady=(2, 10))

        ctk.CTkLabel(right_frame, text="Badge ID (8 Digits):", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=25)
        entry_badge = ctk.CTkEntry(right_frame, font=("Segoe UI", 13))
        entry_badge.pack(fill=tk.X, padx=25, pady=(2, 10))

        ctk.CTkLabel(right_frame, text="Windows AD Login:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=25)
        entry_ad = ctk.CTkEntry(right_frame, font=("Segoe UI", 13))
        entry_ad.pack(fill=tk.X, padx=25, pady=(2, 20))

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
                
                win.current_editing_badge = b_id 
                mode_label.configure(text="Editing Existing User", text_color="#f39c12")
                
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
            mode_label.configure(text="Creating New User", text_color=accent_color)
            
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
                old_b_id = win.current_editing_badge
                if old_b_id and old_b_id != b_id:
                    self.storage.delete_employee(old_b_id)
                
                self.storage.add_employee(b_id, f_name, l_name, ad_user)
                self.spawn_notification(f"Saved Successfully:\n{f_name} {l_name}")
                load_data()
                prepare_new_user()

        def delete_user():
            b_id = win.current_editing_badge or entry_badge.get().strip()
            if not b_id: return
            
            emps = self.storage.get_employees() if self.storage else {}
            full_name = emps.get(b_id, {}).get("full_name", "Unknown User")
            
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete {full_name} (ID:{b_id})?", parent=win):
                if self.storage:
                    self.storage.delete_employee(b_id)
                    self.spawn_notification(f"User Deleted:\n{full_name}")
                    load_data()
                    prepare_new_user()

        btn_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_frame.pack(fill=tk.X, padx=25, pady=5)

        ctk.CTkButton(btn_frame, text="Save / Update", command=save_user, fg_color=["#217346", "#09ce66"], hover_color=["#2a8f57", "#2EFAD9"], font=("Segoe UI", 12, "bold")).pack(fill=tk.X, pady=3)
        ctk.CTkButton(btn_frame, text="New User", command=prepare_new_user, fg_color=ctk.ThemeManager.theme["CTkSegmentedButton"]["unselected_color"], hover_color=ctk.ThemeManager.theme["CTkSegmentedButton"]["unselected_hover_color"], font=("Segoe UI", 12, "bold")).pack(fill=tk.X, pady=3)
        ctk.CTkButton(btn_frame, text="Delete User", command=delete_user, fg_color="#d9534f", hover_color="#c9302c", font=("Segoe UI", 12, "bold")).pack(fill=tk.X, pady=(25, 0))

        load_data()

    def spawn_notification(self, text):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        
        transparent_color = "#000001" 
        window.configure(bg=transparent_color)
        window.wm_attributes("-transparentcolor", transparent_color)
        window.attributes("-topmost", True)
        
        # --- PULL COLORS DIRECTLY FROM BW_THEME.JSON ---
        bg_color = ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]
        text_primary = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        text_secondary = ctk.ThemeManager.theme["CTkButton"]["text_color_disabled"]
        theme_accent = ctk.ThemeManager.theme["CTkButton"]["fg_color"]

        # 1. Semantic Analysis for Colors and Icons
        text_lower = text.lower()
        if "temp login active" in text_lower:
            theme_color = ["#f39c12", "#f39c12"] 
            icon_name = "user-clock"
        elif "automatically signed in" in text_lower or "login successful" in text_lower:
            theme_color = ["#09ce66", "#09ce66"] 
            icon_name = "user"
        elif "unsaved samples cleared" in text_lower:
            theme_color = ["#09ce66", "#09ce66"] 
            icon_name = "broom"
        elif "copied" in text_lower:
            theme_color = theme_accent 
            icon_name = "copy"
        elif "removal mode cancelled" in text_lower:
            theme_color = ["#f39c12", "#f39c12"] 
            icon_name = "warning"
        elif any(w in text_lower for w in ["remove", "removed", "removal"]):
            theme_color = ["#d9534f", "#d9534f"] 
            icon_name = "trash-can"
        elif any(w in text_lower for w in ["denied", "failed", "lost", "error"]):
            theme_color = ["#d9534f", "#d9534f"] 
            icon_name = "warning"
        elif any(w in text_lower for w in ["temp", "action", "attention", "limit", "offline"]):
            theme_color = ["#f39c12", "#f39c12"] 
            icon_name = "bell"
        elif any(w in text_lower for w in ["successful", "success", "saved", "registered"]):
            theme_color = ["#09ce66", "#09ce66"] 
            icon_name = "floppy-disk"
        else:
            theme_color = theme_accent 
            icon_name = "info-circle"

        # 2. Clean Corner Frame
        main_frame = ctk.CTkFrame(window, fg_color=bg_color, corner_radius=10, border_width=4, border_color=theme_color)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 3. Lifespan Progress Bar
        prog_bar = ctk.CTkProgressBar(main_frame, height=4, fg_color=bg_color, progress_color=theme_color, corner_radius=0, border_width=0)
        prog_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=(5, 7), pady=(0, 4))
        prog_bar.set(1.0)
        
        # 4. Text Layout Frame
        top_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # 5. Dynamic Iconography
        try:
            from ctkfontawesome import icon_to_ctkimage
            mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
            icon_img = icon_to_ctkimage(icon_name, fill=theme_color[mode_idx], scale_to_width=34)
            icon_lbl = ctk.CTkLabel(top_frame, text="", image=icon_img, width=40)
            icon_lbl.pack(side=tk.LEFT, padx=(5, 10))
        except Exception:
            icon_lbl = ctk.CTkLabel(top_frame, text="🔔", text_color=theme_color, font=("Segoe UI", 26), width=40)
            icon_lbl.pack(side=tk.LEFT, padx=(5, 10))
            
        # 6. Text Labels (Mathematically Centered!)
        text_container = ctk.CTkFrame(top_frame, fg_color="transparent")
        text_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        inner_text = ctk.CTkFrame(text_container, fg_color="transparent")
        inner_text.place(relx=0, rely=0.5, anchor="w", relwidth=1.0) # PERFECT VERTICAL CENTERING

        lines = text.split('\n')
        ctk.CTkLabel(inner_text, text=lines[0], text_color=theme_color, font=("Segoe UI", 14, "bold"), anchor="w", justify="left").pack(fill=tk.X)
        
        if len(lines) >= 2:
            ctk.CTkLabel(inner_text, text=lines[1], text_color=text_primary, font=("Segoe UI", 16, "bold"), anchor="w", justify="left").pack(fill=tk.X)
        if len(lines) == 3:
            ctk.CTkLabel(inner_text, text=lines[2], text_color=text_secondary, font=("Segoe UI", 12, "italic"), anchor="w", justify="left").pack(fill=tk.X)

        self.position_and_show(window)
        
        # 7. Smooth Drain Animation Loop
        duration_ms = 6500
        step_ms = 50
        steps = duration_ms // step_ms
        window.current_step = 0

        def update_progress():
            if not window.winfo_exists(): return
            window.current_step += 1
            remaining = 1.0 - (window.current_step / steps)
            if remaining <= 0:
                self.destroy_notification(window)
            else:
                prog_bar.set(remaining)
                window.after(step_ms, update_progress)

        window.after(step_ms, update_progress)


    def position_and_show(self, window):
            window.update_idletasks()
            window_width = 360
            window_height = 100
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            x_pos = screen_width - window_width - 20
            y_pos = (screen_height - window_height - 60) - (len(self.active_notifications) * (window_height + 10))
            
            window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
            self.active_notifications.append(window)
    
    def destroy_notification(self, window):
        if window in self.active_notifications:
            self.active_notifications.remove(window)
            window.destroy()
            self.recalculate_positions()

    def recalculate_positions(self):
        window_width = 360
        window_height = 100
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x_pos = screen_width - window_width - 20
        base_y = screen_height - window_height - 60
        
        for index, window in enumerate(self.active_notifications):
            if window.winfo_exists():
                y_pos = base_y - (index * (window_height + 10))
                window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")

    def run(self):
        self.root.mainloop()