# logviewer.py
import customtkinter as ctk
ctk.ScalingTracker.deactivate_automatic_dpi_awareness = True # THE MASTER FIX

import tkinter as tk
from tkinter import ttk
import os
import sys
import time
import ctypes
import threading
import requests
import re
import winreg
import hashlib
from PIL import Image
from datetime import datetime

def resource_path(file_name):
    try:
        base_path = sys._MEIPASS
        return os.path.join(base_path, file_name)
    except Exception:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "..", "..", "img", file_name)

def get_theme_icon():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        return "icon_white.ico" if value == 0 else "icon_black.ico"
    except Exception:
        return "iconApp.ico"

class LogViewerWindow:
    def __init__(self, parent_root, storage, notify_callback, is_server=False, current_user="", initial_search="", initial_filters=None):
        self.storage = storage
        self.notify = notify_callback
        self.is_server = is_server
        self.current_user = current_user
        
        self.tab_memory = None 
        
        theme_path = resource_path("BW_theme.json")
        if os.path.exists(theme_path):
            ctk.set_default_color_theme(theme_path)
            
        self.viewer = ctk.CTkToplevel(parent_root)
        self.viewer.title("System Logs & Inventory")
        
        width, height = 1100, 600
        self.viewer.update_idletasks()
        
        screen_w = self.viewer.winfo_screenwidth()
        screen_h = self.viewer.winfo_screenheight()
        
        x = int((screen_w / 2) - (width / 2))
        y = int((screen_h / 2) - (height / 2))
        
        self.viewer.geometry(f"{width}x{height}+{x}+{y}")
        
        try:
            icon_path = resource_path(get_theme_icon())
            self.viewer.iconbitmap(icon_path)
            self.viewer.after(200, lambda: self.viewer.iconbitmap(icon_path))
        except: pass
            
        self.current_app_theme = ctk.get_appearance_mode()
        self._update_window_theme_elements()
        self.viewer.after(200, self._update_window_theme_elements)
        
        self.current_tab = ['inventory'] 
        self.current_history_target = [None, None] 
        self.last_data_hash = [""] 
        self.current_sort_col = "Date"
        self.current_sort_reverse = True
        
        self.active_filters = set()
        self._pending_initial_filters = initial_filters or []
        
        self._build_ui()
            
        self.execute_search()
        self.auto_refresh()

    def switch_view(self, source, year=None, month=None):
        if hasattr(self, 'force_close_menu'): self.force_close_menu()

        self.tab_memory = None 
        
        self.search_var.set("")
        if hasattr(self, 'active_filters'):
            self.active_filters.clear()
        if hasattr(self, 'tag_widgets'):
            for lbl in self.tag_widgets.values():
                lbl.configure(fg_color="transparent", text_color=["#051728", "#FFFFFF"])
                
        self.current_tab[0] = source
        self.current_history_target[0] = year
        self.current_history_target[1] = month
        
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", tk.END, values=("", "", "↻ LOADING DATA...", "Please wait...", "Fetching from server", "", ""))
        self.viewer.update_idletasks()
        
        self.load_data(source, "", year=year, month=month)

    def _update_window_theme_elements(self):
        try:
            # 1. Set BOTH icons (Taskbar & Titlebar) to the OS Theme first
            os_icon_path = resource_path(get_theme_icon())
            self.viewer.iconbitmap(os_icon_path)
            
            # 2. Use Windows API to specifically override ONLY the Title Bar icon (ICON_SMALL) with the App Theme
            is_light_app = ctk.get_appearance_mode() == "Light"
            app_icon_path = resource_path("icon_black.ico" if is_light_app else "icon_white.ico")
            
            hwnd = ctypes.windll.user32.GetParent(self.viewer.winfo_id())
            
            # LoadImageW arguments: 0=hInst, path, 1=IMAGE_ICON, 16=width, 16=height, 0x0010=LR_LOADFROMFILE
            hIconSmall = ctypes.windll.user32.LoadImageW(0, app_icon_path, 1, 16, 16, 0x0010)
            
            if hIconSmall:
                # SendMessageW arguments: 0x0080=WM_SETICON, 0=ICON_SMALL
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hIconSmall)
                
        except Exception: pass
        
        self._apply_dark_title_bar(self.viewer)

    def _apply_dark_title_bar(self, window):
        try:
            window.update() 
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
            
            # Switch Immersive Mode (1 = Light Mode, 2 = Dark Mode)
            rendering_policy = ctypes.c_int(2 if mode_idx == 1 else 1)
            set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))

            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36
            
            bg_hex = ctk.ThemeManager.theme["CTk"]["fg_color"][mode_idx]
            text_hex = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode_idx]

            # Windows DWM requires BGR integer formats!
            def hex_to_bgr(hex_str):
                c = int(hex_str.replace("#", ""), 16)
                return (c & 0xFF) << 16 | (c & 0xFF00) | (c >> 16)

            bg_color = ctypes.c_int(hex_to_bgr(bg_hex))
            text_color = ctypes.c_int(hex_to_bgr(text_hex))
                
            set_window_attribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(bg_color), ctypes.sizeof(bg_color))
            set_window_attribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text_color), ctypes.sizeof(text_color))
        except Exception:
            pass

    def fetch_archive_months(self):
        try:
            target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")
            url = f"{target_url}/api/get_archive_months"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("months", [])
        except Exception:
            pass
        return []

    def fetch_view_data(self, source, year=None, month=None, sort_col="Date", reverse=True):
        if getattr(self.storage, 'is_offline_mode', False):
            if source == 'inventory':
                return self.storage.get_inventory_data()
            return [] 

        try:
            target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")
            url = f"{target_url}/api/view_data"
            params = {
                "source": source, "year": year or "", "month": month or "",
                "sort_col": sort_col, "reverse": str(reverse).lower()
            }
            resp = requests.get(url, params=params, timeout=3)
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception:
            pass
            
        if source == 'inventory' and getattr(self, 'storage', None):
            return self.storage.get_inventory_data()
            
        return []

    def _build_ui(self):
        self.viewer.minsize(700, 450)
        self.is_collapsed = False
        self.menu_is_open = False
        self.full_nav_width = 600 
        
        self.top_frame = ctk.CTkFrame(self.viewer, fg_color="transparent")
        self.top_frame.pack(fill=tk.X, pady=10, padx=10)
        
        try:
            m_img = Image.open(resource_path("menu.png"))
            self.icon_menu = ctk.CTkImage(m_img, size=(24, 24))
            mc_img = Image.open(resource_path("menuClose.png"))
            self.icon_menu_close = ctk.CTkImage(mc_img, size=(24, 24))
            
            s_img = Image.open(resource_path("search.png"))
            self.icon_search = ctk.CTkImage(s_img, size=(20, 20))
            c_img = Image.open(resource_path("delete.png"))
            self.icon_clear = ctk.CTkImage(c_img, size=(20, 20))
        except Exception:
            self.icon_menu = None
            self.icon_menu_close = None
            self.icon_search = None
            self.icon_clear = None

        self.hamburger_btn = ctk.CTkButton(
            self.top_frame, image=self.icon_menu, text="", width=40,
            command=self.toggle_hamburger_menu, fg_color=["#00386C", "#0E8187"]
        )
        
        self.collapsed_title = ctk.CTkLabel(self.top_frame, text="System Logs & Inventory", font=("Segoe UI", 16, "bold"))
        self.btn_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.btn_frame.pack(side=tk.LEFT)

        self.search_container = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.search_container.pack(side=tk.RIGHT)
        search_frame = ctk.CTkFrame(self.search_container, fg_color="transparent")
        search_frame.pack(side=tk.TOP, anchor="e", padx=(0,3))

        self.search_var = tk.StringVar()
        ctk.CTkLabel(search_frame, text="Search:", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT, padx=5)

        self.search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, border_width=3, width=200)
        self.search_entry.pack(side=tk.LEFT)
        self.search_entry.bind("<Return>", self.trigger_manual_search)

        def clear_search():
            self.search_var.set("")
            self.trigger_manual_search()

        search_btn = ctk.CTkButton(search_frame, image=self.icon_search, text="" if self.icon_search else "GO", command=self.trigger_manual_search, width=35)
        clear_btn = ctk.CTkButton(search_frame, image=self.icon_clear, text="" if self.icon_clear else "X", command=clear_search, width=35, fg_color="#d9534f", hover_color="#c9302c")
        search_btn.pack(side=tk.LEFT, padx=(5, 2))
        clear_btn.pack(side=tk.LEFT, padx=(0, 0))

        tags_frame = ctk.CTkFrame(self.search_container, fg_color="transparent")
        tags_frame.pack(side=tk.TOP, anchor="e", pady=(5, 0))

        self.tag_widgets = {}
        quick_tags = []
        
        if not self.is_server: 
            quick_tags.append(("My Samples", "ME"))
        else:
            quick_tags.append(("System", "system"))
            
        quick_tags.extend([("Verification", "verification queue"), ("Old", "old"), ("Today", "today"), ("Closed", "request closed")])

        def toggle_tag(keyword, btn_widget):
            if keyword == "ME": target = "MAGIC_ME_FILTER"
            elif keyword == "today": target = "MAGIC_TODAY_FILTER"
            else: target = keyword
                
            if not target: return

            conflict_map = {
                "MAGIC_TODAY_FILTER": ["old"],
                "old": ["MAGIC_TODAY_FILTER"],
                "request closed": ["system", "verification queue"],
                "system": ["request closed", "verification queue"],
                "verification queue": ["request closed", "system"]
            }
            conflicts = conflict_map.get(target, [])

            was_active = target in self.active_filters

            if was_active:
                self.active_filters.remove(target)
                btn_widget.configure(fg_color="transparent", text_color=["#051728", "#FFFFFF"])
                
                forcing_filters = {"old", "verification queue", "system", "request closed"}
                active_forcing = [f for f in self.active_filters if f in forcing_filters]
                
                if len(active_forcing) == 0 and self.tab_memory:
                    self.current_tab[0], self.current_history_target[0], self.current_history_target[1] = self.tab_memory
                    self.tab_memory = None
            else:
                for conflict in conflicts:
                    if conflict in self.active_filters:
                        self.active_filters.remove(conflict)
                        conflict_kw = "today" if conflict == "MAGIC_TODAY_FILTER" else conflict
                        if conflict_kw in self.tag_widgets:
                            self.tag_widgets[conflict_kw].configure(fg_color="transparent", text_color=["#051728", "#FFFFFF"])

                forces_inventory = keyword in ["old", "verification queue"]
                forces_history = keyword in ["system", "request closed"]
                
                if forces_inventory or forces_history:
                    if not self.tab_memory:
                        self.tab_memory = (self.current_tab[0], self.current_history_target[0], self.current_history_target[1])
                        
                    if forces_inventory and self.current_tab[0] != 'inventory':
                        self.current_tab[0] = 'inventory'
                    elif forces_history and self.current_tab[0] != 'history_specific':
                        now = datetime.now()
                        self.current_tab[0] = 'history_specific'
                        self.current_history_target[0] = now.strftime("%Y")
                        self.current_history_target[1] = now.strftime("%m")
                
                self.active_filters.add(target)
                btn_widget.configure(fg_color=["#00386C", "#0E8187"], text_color="#FFFFFF")
                
            self.execute_search()

        for display_text, actual_keyword in quick_tags:
            btn = ctk.CTkButton(tags_frame, text=display_text, height=24, width=16, border_width=2, fg_color="transparent", text_color=["#051728", "#FFFFFF"])
            btn.pack(side=tk.LEFT, padx=3)
            btn.configure(command=lambda k=actual_keyword, b=btn: toggle_tag(k, b))
            self.tag_widgets[actual_keyword] = btn
            
        if hasattr(self, '_pending_initial_filters'):
            for kw in self._pending_initial_filters:
                if kw in self.tag_widgets:
                    toggle_tag(kw, self.tag_widgets[kw])
            self._pending_initial_filters = []

        now = datetime.now()
        
        self.b1 = ctk.CTkButton(self.btn_frame, text="View Active Inventory", command=lambda: self.switch_view('inventory'), width=160)
        unsel_bg = ctk.ThemeManager.theme["CTkSegmentedButton"]["unselected_color"]
        unsel_hover = ctk.ThemeManager.theme["CTkSegmentedButton"]["unselected_hover_color"]
        
        self.b2 = ctk.CTkButton(self.btn_frame, text="Current Month Logs", command=lambda y=now.strftime("%Y"), m=now.strftime("%m"): self.switch_view('history_specific', year=y, month=m), width=150, fg_color=["#33424F", "#33424F"], hover_color=["#4A5C6A", "#4A5C6A"])
        
        self.history_btn = ctk.CTkButton(self.btn_frame, text="Archive", width=100, fg_color=["#555555", "#555555"], hover_color=["#777777", "#777777"])
        
        self.main_menu = tk.Menu(self.history_btn, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
        self.main_menu.add_command(label="Loading archives...", state="disabled") 
        threading.Thread(target=self._build_archive_menu_async, daemon=True).start()

        def popup_archive_menu(event):
            self.main_menu.post(event.widget.winfo_rootx(), event.widget.winfo_rooty() + event.widget.winfo_height())
        self.history_btn.bind("<ButtonRelease-1>", popup_archive_menu)

        self.b4 = ctk.CTkButton(self.btn_frame, text="Open in External Editor", command=self.open_external_file, width=170, fg_color="#217346", hover_color="#2a8f57")
        
        self.b1.pack(side=tk.LEFT, padx=5)
        self.b2.pack(side=tk.LEFT, padx=5)
        self.history_btn.pack(side=tk.LEFT, padx=5)
        self.b4.pack(side=tk.LEFT, padx=5)
        
        self.dropdown_frame = ctk.CTkFrame(self.viewer, border_width=2, border_color=["#00386C", "#0E8187"], width=180, height=160)
        self.dropdown_frame.pack_propagate(False)
        
        self.d1 = ctk.CTkButton(self.dropdown_frame, text="View Active Inventory", command=lambda: self.switch_view('inventory'))
        self.d2 = ctk.CTkButton(self.dropdown_frame, text="Current Month Logs", command=lambda y=now.strftime("%Y"), m=now.strftime("%m"): self.switch_view('history_specific', year=y, month=m), fg_color=["#33424F", "#33424F"], hover_color=["#4A5C6A", "#4A5C6A"])
        self.drop_history_btn = ctk.CTkButton(self.dropdown_frame, text="Archive", fg_color=["#555555", "#555555"], hover_color=["#777777", "#777777"])
        self.drop_history_btn.bind("<ButtonRelease-1>", popup_archive_menu)
        self.d4 = ctk.CTkButton(self.dropdown_frame, text="Open in External Editor", command=lambda: [self.force_close_menu(), self.open_external_file()], fg_color="#217346", hover_color="#2a8f57")

        self.d1.pack(fill=tk.X, padx=10, pady=(10, 5))
        self.d2.pack(fill=tk.X, padx=10, pady=5)
        self.drop_history_btn.pack(fill=tk.X, padx=10, pady=5)
        self.d4.pack(fill=tk.X, padx=10, pady=(5, 10))

        style = ttk.Style(self.viewer)
        style.theme_use("default")
        
        bg_color = self.viewer._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        text_color = self.viewer._apply_appearance_mode(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
        selected_color = self.viewer._apply_appearance_mode(ctk.ThemeManager.theme["CTkButton"]["fg_color"])
        head_bg = self.viewer._apply_appearance_mode(ctk.ThemeManager.theme["CTk"]["fg_color"])
        head_hover = self.viewer._apply_appearance_mode(ctk.ThemeManager.theme["CTkButton"]["hover_color"])

        style.configure("Treeview", background=bg_color, foreground=text_color, rowheight=28, fieldbackground=bg_color, borderwidth=1, bordercolor=selected_color, lightcolor=selected_color, darkcolor=selected_color)
        style.map('Treeview', background=[('selected', selected_color)])
        style.configure("Treeview.Heading", background=head_bg, foreground=text_color, relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Treeview.Heading", background=[('active', head_hover)])

        columns = ("Date", "Time", "Location", "Sample ID", "Requestor", "Department", "Project Number", "User")
        self.tree = ttk.Treeview(self.viewer, columns=columns, show="headings", height=15)
        for col in columns: self.tree.heading(col, text=col)
        
        self.tree.column("Date", width=95, anchor=tk.CENTER)
        self.tree.column("Time", width=75, anchor=tk.CENTER)
        self.tree.column("Location", width=220, anchor=tk.CENTER)
        self.tree.column("Sample ID", width=85, anchor=tk.CENTER)
        self.tree.column("Requestor", width=140, anchor=tk.CENTER)
        self.tree.column("Department", width=190, anchor=tk.CENTER) 
        self.tree.column("Project Number", width=120, anchor=tk.CENTER) 
        self.tree.column("User", width=110, anchor=tk.CENTER)

        scrollbar = ctk.CTkScrollbar(self.viewer, orientation="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 10))
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # --- TAG PRIORITY HIERARCHY ---
        # The lowest in the code wins conflicts!
        self.tree.tag_configure('system', foreground=self.viewer._apply_appearance_mode(["#10B981", "#09ce66"]))  
        self.tree.tag_configure('pending', foreground=self.viewer._apply_appearance_mode(['#06B6D4', '#2EFAD9'])) 
        self.tree.tag_configure('overdue', foreground=self.viewer._apply_appearance_mode(['#8B5CF6', '#a78bfa'])) # Purple overrides Cyan!
        self.tree.tag_configure('removed', foreground=self.viewer._apply_appearance_mode(['#EF4444', '#ff6b6b'])) # Red overrides Everything!

        self.last_refresh_time = 0

        def focus_search_bar(event):
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END) 
            return "break" 

        def handle_escape(event):
            self.search_var.set("")
            self.trigger_manual_search()
            self.viewer.focus_set() 
            return "break"

        def handle_f5(event):
            current_time = time.time()
            if current_time - self.last_refresh_time > 1.0: 
                self.last_refresh_time = current_time
                self.execute_search()
            return "break"

        def handle_new_window(event):
            if self.notify:
                self.notify("OPEN_NEW_VIEWER") 
            return "break"

        self.viewer.bind("<Control-f>", focus_search_bar)
        self.viewer.bind("<Control-F>", focus_search_bar)
        self.viewer.bind("<Escape>", handle_escape)
        self.viewer.bind("<F5>", handle_f5)
        self.viewer.bind("<Control-n>", handle_new_window)
        self.viewer.bind("<Control-N>", handle_new_window)
        self.viewer.bind("<Control-c>", self.copy_selection)
        self.viewer.bind("<Control-C>", self.copy_selection)

        ctk.CTkLabel(self.viewer, text="Select a row and press [Ctrl+C] to copy data  |  [Ctrl+F] for Searching  |  [Esc] Clears your Search Bar  |  [Ctrl+N] for New Window  |  F5 for Manual Refresh", text_color=["#666666", "#a0a0a0"], font=("Segoe UI", 11, "italic")).pack(side=tk.LEFT, padx=10, pady=(0, 5))
        self.viewer.bind("<Configure>", self.handle_window_resize)

    def handle_window_resize(self, event):
        if event.widget == self.viewer:
            search_width = self.search_container.winfo_reqwidth()
            
            if not self.is_collapsed:
                self.full_nav_width = self.btn_frame.winfo_reqwidth()
                
                if event.width < (self.full_nav_width + search_width + 30):
                    self.is_collapsed = True
                    self.btn_frame.pack_forget() 
                    self.hamburger_btn.pack(side=tk.LEFT, padx=5) 
                    self.collapsed_title.pack(side=tk.LEFT, padx=15) 
            else:
                if event.width > (self.full_nav_width + search_width + 30):
                    self.is_collapsed = False
                    self.hamburger_btn.pack_forget() 
                    self.collapsed_title.pack_forget()
                    
                    if self.menu_is_open:
                        self.toggle_hamburger_menu() 
                        
                    self.btn_frame.pack(side=tk.LEFT) 

    def toggle_hamburger_menu(self):
        if self.menu_is_open:
            self.dropdown_frame.place_forget()
            if self.icon_menu: self.hamburger_btn.configure(image=self.icon_menu, text="")
            else: self.hamburger_btn.configure(text="☰")
            self.menu_is_open = False
        else:
            x_pos = 15
            y_pos = self.top_frame.winfo_y() + self.top_frame.winfo_height()
            
            self.dropdown_frame.place(x=x_pos, y=y_pos)
            self.dropdown_frame.lift() 
            
            if self.icon_menu_close: self.hamburger_btn.configure(image=self.icon_menu_close, text="")
            else: self.hamburger_btn.configure(text="✕")
            self.menu_is_open = True

    def force_close_menu(self):
        if self.menu_is_open:
            self.toggle_hamburger_menu()

    def _build_archive_menu_async(self):
        available_history = self.fetch_archive_months() 
        self.viewer.after(0, lambda: self._render_archive_menu(available_history))
        
    def _render_archive_menu(self, available_history):
        self.main_menu.delete(0, tk.END)
        history_tree = {}
        for ym in available_history:
            y, m = ym.split('-')
            if y not in history_tree: history_tree[y] = []
            history_tree[y].append(m)

        if not history_tree:
            self.main_menu.add_command(label="No Archives Found", state="disabled")
        else:
            month_names = {"01": "January", "02": "February", "03": "March", "04": "April", "05": "May", "06": "June", 
                           "07": "July", "08": "August", "09": "September", "10": "October", "11": "November", "12": "December"}
            for year in sorted(history_tree.keys(), reverse=True):
                year_menu = tk.Menu(self.main_menu, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
                self.main_menu.add_cascade(label=f"Year: {year}", menu=year_menu)
                for month in sorted(history_tree[year], reverse=True):
                    year_menu.add_command(label=f"{month_names.get(month, month)} ({month})", command=lambda y=year, m=month: self.switch_view('history_specific', year=y, month=m))

    def _update_sort_headers(self, active_col, is_reverse):
        for c in self.tree["columns"]:
            if c == active_col:
                arrow = " ▼" if is_reverse else " ▲"
                self.tree.heading(c, text=c + arrow, command=lambda _col=c, _rev=not is_reverse: self.treeview_sort_column(_col, _rev))
            else:
                self.tree.heading(c, text=c, command=lambda _col=c: self.treeview_sort_column(_col, False))

    def treeview_sort_column(self, col, reverse):
        self.current_sort_col = col
        self.current_sort_reverse = reverse
        self._update_sort_headers(col, reverse)

        data_list = []
        for child in self.tree.get_children(''):
            date_val = self.tree.set(child, 'Date')
            time_val = self.tree.set(child, 'Time')
            absolute_time = f"{date_val} {time_val}"
            
            if col in ("Date", "Time"):
                primary_val = absolute_time
            else:
                primary_val = self.tree.set(child, col)
            
            data_list.append((primary_val, absolute_time, child))

        def smart_sort_key(item):
            primary = str(item[0]).strip().lower()
            tie_breaker = str(item[1])
            
            # --- THE FIX: Teach the sorter to read Polish dates ---
            if re.match(r"^\d{2}-\d{2}-\d{4}", primary):
                primary = f"{primary[6:10]}-{primary[3:5]}-{primary[0:2]}" + primary[10:]
                
            if primary.isdigit():
                return (0, int(primary), tie_breaker)
            return (1, primary, tie_breaker)

        data_list.sort(key=smart_sort_key, reverse=reverse)

        for index, (*_, child) in enumerate(data_list):
            self.tree.move(child, '', index)

    def trigger_manual_search(self, event=None):
        if hasattr(self, 'active_filters'):
            self.active_filters.clear()
        if hasattr(self, 'tag_widgets'):
            for lbl in self.tag_widgets.values():
                lbl.configure(fg_color="transparent", text_color=["#051728", "#FFFFFF"])
        
        if self.search_var.get().strip() == "" and self.tab_memory:
            self.current_tab[0], self.current_history_target[0], self.current_history_target[1] = self.tab_memory
            self.tab_memory = None
                
        self.execute_search()

    def execute_search(self, event=None):
        typed_query = self.search_var.get().strip()
        hidden_query = " ".join(self.active_filters)
        full_query = f"{typed_query} {hidden_query}".strip()
        
        if not full_query:
            if self.tab_memory:
                self.current_tab[0], self.current_history_target[0], self.current_history_target[1] = self.tab_memory
                self.tab_memory = None
            
            self.load_data(self.current_tab[0], "", year=self.current_history_target[0], month=self.current_history_target[1])
            return
        
        if self.current_tab[0] in ['inventory', 'history_specific']:
            self.load_data(self.current_tab[0], full_query, year=self.current_history_target[0], month=self.current_history_target[1])
        else:
            self.tree.delete(*self.tree.get_children())
            self.tree.insert("", tk.END, values=("", "", "↻ SEARCHING SERVER...", full_query, "Awaiting API response...", "", ""))
            self.viewer.update_idletasks()
            threading.Thread(target=lambda: self.run_api_deep_search(full_query), daemon=True).start()

    def run_api_deep_search(self, query):
        try:
            target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")
            response = requests.get(f"{target_url}/api/search", params={"q": query}, timeout=150)
            if response.status_code == 200:
                data = response.json()
                self.viewer.after(0, lambda: self.render_deep_search(data.get("results", []), data.get("warning", "")))
            else:
                self.viewer.after(0, lambda: self.notify(f"Search failed: HTTP {response.status_code}"))
        except Exception:
            self.viewer.after(0, lambda: self.notify(f"Network Error:\nCould not reach server API."))

    def render_deep_search(self, data, warning_msg=""):
        self.current_tab[0] = 'deep_search'
        self.tree.delete(*self.tree.get_children())
        
        for row in data:
            display_row = list(row) 
            clean_loc = str(display_row[2]).replace('LOC:', '').replace('LOC-', '').strip()
            display_row[2] = clean_loc
            item_id = str(display_row[3]) if len(display_row) > 3 else ""
            
            loc_lower = clean_loc.lower()
            row_tags = ()
            
            if 'closed' in loc_lower or 'removed' in loc_lower: row_tags = ('removed',)
            elif 'verification' in loc_lower or 'pending' in loc_lower: row_tags = ('pending',)
            elif 'system' in loc_lower: row_tags = ('system',)
                
            self.tree.insert("", tk.END, text=item_id, values=display_row, tags=row_tags)
            
        if warning_msg: self.notify(warning_msg)
        self.treeview_sort_column(self.current_sort_col, self.current_sort_reverse)

    def load_data(self, source_type, search_query="", is_auto_refresh=False, year=None, month=None):
        if source_type == 'deep_search': return 

        threading.Thread(
            target=self._threaded_load_data, 
            args=(source_type, search_query, is_auto_refresh, year, month), 
            daemon=True
        ).start()

    def _threaded_load_data(self, source_type, search_query, is_auto_refresh, year, month):
        data = self.fetch_view_data(source=source_type, year=year, month=month, sort_col=self.current_sort_col, reverse=self.current_sort_reverse)
        
        if self.viewer.winfo_exists():
            self.viewer.after(0, lambda: self._render_loaded_data(data, source_type, search_query, is_auto_refresh, year, month))

    def _render_loaded_data(self, data, source_type, search_query, is_auto_refresh, year, month):
        unique_data = []
        seen_rows = set()
        for row in data:
            row_str = str(row) 
            if row_str not in seen_rows:
                seen_rows.add(row_str)
                unique_data.append(row)
        data = unique_data

        # This converts the entire dataset into a secure MD5 hash string. 
        # If even a single letter changes anywhere in the file, this hash will change, forcing a refresh!
        content_hash = hashlib.md5(str(data).encode('utf-8', 'ignore')).hexdigest()
        current_hash = f"{content_hash}_{source_type}_{year}_{month}_{self.current_sort_col}_{self.current_sort_reverse}_{search_query}"
        
        if is_auto_refresh and current_hash == self.last_data_hash[0]: return 
        self.last_data_hash[0] = current_hash

        self.current_tab[0] = source_type
        if year and month:
            self.current_history_target[0] = year
            self.current_history_target[1] = month

        selected_ids = [self.tree.item(item, "text") for item in self.tree.selection()] if is_auto_refresh else []
        self.tree.delete(*self.tree.get_children())
        
        search_terms = [word.lower() for word in search_query.strip().split()]
        
        filter_old = "old" in search_terms
        if filter_old: search_terms.remove("old")
        
        filter_today = "magic_today_filter" in search_terms
        if filter_today: search_terms.remove("magic_today_filter")
        
        filter_me = "magic_me_filter" in search_terms
        if filter_me: search_terms.remove("magic_me_filter")
        
        now = datetime.now()
        is_active_inventory = (source_type == 'inventory')
        
        for row in data:
            loc_lower = str(row[2]).replace('LOC:', '').replace('LOC-', '').strip().lower()
            
            # 1. Parse the date whether it is ISO (YYYY-MM-DD) or DD.MM.YYYY or DD-MM-YYYY
            raw_date_str = str(row[0]).strip()[:10]
            row_date = None
            
            try:
                if "." in raw_date_str:
                    row_date = datetime.strptime(raw_date_str, "%d.%m.%Y")
                elif "-" in raw_date_str and len(raw_date_str) > 2 and raw_date_str[2] == "-":
                    row_date = datetime.strptime(raw_date_str, "%d-%m-%Y")
                else:
                    row_date = datetime.strptime(raw_date_str, "%Y-%m-%d")
            except Exception: pass
            
            display_date = row_date.strftime("%d-%m-%Y") if row_date else raw_date_str
            
            # 2. Format it beautifully for the UI
            display_date = row_date.strftime("%d-%m-%Y") if row_date else raw_date_str
            
            is_old = False
            is_today = False
            is_closed = 'closed' in loc_lower or 'removed' in loc_lower
            
            # Instead of looking for "14-day-old logs", the Old filter looks strictly at 
            # the Active Inventory to find 14-day-old samples. Since closed items 
            # are deleted from inventory, this is bulletproof!
            if is_active_inventory and row_date:
                if (now - row_date).days >= 14:
                    is_old = True
                    
            if row_date and row_date.date() == now.date():
                is_today = True
            
            if filter_old and not is_old: continue
            if filter_today and not is_today: continue
            
            if filter_me:
                if 'system' in loc_lower:
                    continue 
                row_str_lower = " ".join(str(cell).lower() for cell in row)
                if self.current_user and self.current_user.lower() not in row_str_lower:
                    continue
            
            row_str = " ".join(str(cell).lower() for cell in row)
            if search_terms and not all(term in row_str for term in search_terms): continue
            
            display_row = list(row)
            display_row[0] = display_date
            display_row[2] = str(display_row[2]).replace('LOC:', '').replace('LOC-', '').strip()
            item_id = str(display_row[3]) if len(display_row) > 3 else ""
            
            row_tags = ()
            if is_closed: row_tags = ('removed',)
            elif 'system' in loc_lower: row_tags = ('system',)
            elif is_old: row_tags = ('overdue',)
            elif 'verification' in loc_lower or 'pending' in loc_lower: row_tags = ('pending',)
            
            inserted = self.tree.insert("", tk.END, text=item_id, values=display_row, tags=row_tags)
            if item_id and item_id in selected_ids:
                try: self.tree.selection_add(inserted)
                except Exception: pass

        self.treeview_sort_column(self.current_sort_col, self.current_sort_reverse)

    def auto_refresh(self):
        if self.viewer.winfo_exists():

            if getattr(self, 'current_app_theme', None) != ctk.get_appearance_mode():
                self.current_app_theme = ctk.get_appearance_mode()
                self._update_window_theme_elements()

            if self.current_tab[0] in ['inventory', 'history_specific']:
                typed_query = self.search_var.get().strip()
                hidden_query = " ".join(getattr(self, 'active_filters', set()))
                full_query = f"{typed_query} {hidden_query}".strip()
                
                # Pass the year and month so the engine knows which file to check!
                self.load_data(self.current_tab[0], full_query, is_auto_refresh=True, year=self.current_history_target[0], month=self.current_history_target[1])

            self.viewer.after(1000, self.auto_refresh)

    def copy_selection(self, event=None):
        selected = self.tree.selection()
        if not selected: 
            return "break"
            
        current_time = time.time()
        if getattr(self, 'last_copy_time', 0) > 0 and (current_time - self.last_copy_time) < 0.3:
            return "break" # Ignore if it's been less 0.3s
        self.last_copy_time = current_time
        
        copied_lines = []
        for item in selected:
            values = self.tree.item(item, "values")
            copied_lines.append("\t".join(str(v) for v in values))
        
        self.viewer.clipboard_clear()
        self.viewer.clipboard_append("\n".join(copied_lines))
        self.notify(f"Copied {len(selected)} rows to clipboard" if len(selected) > 1 else "Copied 1 row to clipboard")
        return "break"

    def open_external_file(self):
        file_to_open = self.storage.get_active_file_path(
            self.current_tab[0], 
            year=self.current_history_target[0], 
            month=self.current_history_target[1]
        )
        try:
            if not file_to_open:
                self.notify("Editor Disabled.\nView master files directly on the Server.")
                return
            os.startfile(file_to_open)
        except Exception as e:
            self.notify(f"Could not open file:\n{e}")