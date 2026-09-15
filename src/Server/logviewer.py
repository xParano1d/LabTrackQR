# logviewer.py
import tkinter as tk
from tkinter import ttk
import os
import sys
import time
import ctypes
import threading
import requests
import re
from PIL import Image, ImageTk
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
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        return "icon_white.ico" if value == 0 else "icon_black.ico"
    except Exception:
        return "icon_white.ico"

class LogViewerWindow:
    def __init__(self, parent_root, storage, notify_callback, is_server=False, current_user="", initial_search="", initial_filters=None):
        self.storage = storage
        self.notify = notify_callback
        self.is_server = is_server
        self.current_user = current_user
        
        self.viewer = tk.Toplevel(parent_root)
        self.viewer.title("System Logs & Inventory")
        self.viewer.geometry("1000x550")
        self.viewer.configure(bg="#f4f4f4")
        
        try:
            self.viewer.iconbitmap(default=resource_path(get_theme_icon()))
        except: pass
            
        self._apply_dark_title_bar(self.viewer)
        
        self.current_tab = ['inventory'] 
        self.current_history_target = [None, None] 
        self.last_data_hash = [""] 
        self.current_sort_col = "Date/Day"
        self.current_sort_reverse = True
        
        self.active_filters = set()
        self._pending_initial_filters = initial_filters or []
        
        
        self._build_ui()
            
        self.execute_search()
        self.auto_refresh()

    def switch_view(self, source, year=None, month=None):
        """Cleans up the UI (wipes search and buttons) before changing tabs."""
        if hasattr(self, 'force_close_menu'): self.force_close_menu()

        self.search_var.set("")
        if hasattr(self, 'active_filters'):
            self.active_filters.clear()
        if hasattr(self, 'tag_widgets'):
            for lbl in self.tag_widgets.values():
                lbl.config(bg="#e8e8e8", fg="#333333") # Reset to grey
                
        self.current_tab[0] = source
        self.current_history_target[0] = year
        self.current_history_target[1] = month
        
        # Instantly wipe the screen and show a loading indicator 
        # so you know the button click actually registered!
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", tk.END, values=("", "", "⏳ LOADING DATA...", "Please wait...", "Fetching from server", "", ""))
        self.viewer.update_idletasks()
        
        # Now safely fetch the data in the background
        self.load_data(source, "", year=year, month=month)

    def _apply_dark_title_bar(self, window):
        try:
            window.update() 
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            rendering_policy = ctypes.c_int(2)
            set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))

            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36
            bg_color = ctypes.c_int(0x00281501)
            text_color = ctypes.c_int(0x00FFFFFF) 
            
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

    def fetch_view_data(self, source, year=None, month=None, sort_col="Date/Day", reverse=True):
        if getattr(self.storage, 'is_offline_mode', False):
            if source == 'inventory':
                return self.storage.get_inventory_data()
            return [] # Cannot view history archives while offline

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
        
        # --- THE HOVER ENGINE ---
        def apply_hover(widget, default_bg, hover_bg):
            widget.bind("<Enter>", lambda e, w=widget, c=hover_bg: w.config(bg=c))
            widget.bind("<Leave>", lambda e, w=widget, c=default_bg: w.config(bg=c))

        self.top_frame = tk.Frame(self.viewer, bg="#f4f4f4")
        self.top_frame.pack(fill=tk.X, pady=10, padx=10)
        
        try:
            m_img = Image.open(resource_path("menu.png")).resize((24, 24), Image.Resampling.LANCZOS)
            self.icon_menu = ImageTk.PhotoImage(m_img)
            mc_img = Image.open(resource_path("menuClose.png")).resize((24, 24), Image.Resampling.LANCZOS)
            self.icon_menu_close = ImageTk.PhotoImage(mc_img)
        except Exception:
            self.icon_menu = None
            self.icon_menu_close = None

        self.hamburger_btn = tk.Button(
            self.top_frame, image=self.icon_menu, text="☰" if not self.icon_menu else "",
            command=self.toggle_hamburger_menu, bg="#011528", fg="white", 
            font=("Segoe UI", 14), relief="flat", cursor="hand2", padx=10
        )
        apply_hover(self.hamburger_btn, "#011528", "#022a52") # Hover for Hamburger
        
        self.collapsed_title = tk.Label(self.top_frame, text="System Logs & Inventory", bg="#f4f4f4", fg="#011528", font=("Segoe UI", 14, "bold"))
        self.btn_frame = tk.Frame(self.top_frame, bg="#f4f4f4")
        self.btn_frame.pack(side=tk.LEFT)

        self.search_container = tk.Frame(self.top_frame, bg="#f4f4f4")
        self.search_container.pack(side=tk.RIGHT)
        search_frame = tk.Frame(self.search_container, bg="#f4f4f4")
        search_frame.pack(side=tk.TOP, anchor="e", padx=(0,3))

        self.search_var = tk.StringVar()
        tk.Label(search_frame, text="Search:", bg="#f4f4f4", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)

        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var, font=("Segoe UI", 10), width=24, relief="solid", bd=1)
        self.search_entry.pack(side=tk.LEFT, ipady=3)
        self.search_entry.bind("<Return>", self.trigger_manual_search)

        def clear_search():
            self.search_var.set("")
            self.trigger_manual_search()

        try:
            s_img = Image.open(resource_path("search.png")).resize((22, 22), Image.Resampling.LANCZOS)
            self.icon_search = ImageTk.PhotoImage(s_img)
            c_img = Image.open(resource_path("delete.png")).resize((22, 22), Image.Resampling.LANCZOS)
            self.icon_clear = ImageTk.PhotoImage(c_img)
            search_btn = tk.Button(search_frame, image=self.icon_search, command=self.trigger_manual_search, bg="#011528", activebackground="#022a52", relief="flat", cursor="hand2", bd=0, padx=6, pady=2)
            clear_btn = tk.Button(search_frame, image=self.icon_clear, command=clear_search, bg="#d9534f", activebackground="#c9302c", relief="flat", cursor="hand2", bd=0, padx=6, pady=2)
        except Exception:
            search_btn = tk.Button(search_frame, text="🔍", command=self.execute_search, bg="#011528", fg="white", font=("Segoe UI", 9), relief="flat", cursor="hand2", width=4 )
            clear_btn = tk.Button(search_frame, text="⌫", command=clear_search, bg="#d9534f", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2", width=3, round=2)

        search_btn.pack(side=tk.LEFT, padx=(2, 2), ipady=2)
        clear_btn.pack(side=tk.LEFT, padx=(0, 0), ipady=2)
        
        apply_hover(search_btn, "#011528", "#022a52") # Hover for Search
        apply_hover(clear_btn, "#d9534f", "#c9302c")  # Hover for Clear

        tags_frame = tk.Frame(self.search_container, bg="#f4f4f4")
        tags_frame.pack(side=tk.TOP, anchor="e", pady=(2, 0))

        self.tag_widgets = {}
        quick_tags = []
        if not self.is_server: quick_tags.append(("My Samples", "ME"))
        quick_tags.extend([("Today", "today"), ("Old", "old"), ("Verification", "verification queue"), ("Closed", "request closed")])

        def toggle_tag(keyword, lbl_widget):
            if keyword == "ME": target = self.current_user if self.current_user else ""
            elif keyword == "today": target = datetime.now().strftime("%Y-%m-%d")
            else: target = keyword
                
            if not target: return
            if keyword in ["ME", "old", "verification queue", "today"]: self.current_tab[0] = 'inventory'

            was_active = False
            if target in self.active_filters:
                self.active_filters.remove(target)
                was_active = True
            if keyword in self.active_filters:
                self.active_filters.remove(keyword)
                was_active = True

            if was_active:
                lbl_widget.config(bg="#e8e8e8", fg="#333333") 
            else:
                self.active_filters.add(target)
                lbl_widget.config(bg="#011528", fg="white") 
            self.execute_search()

        for display_text, actual_keyword in quick_tags:
            lbl = tk.Label(tags_frame, text=display_text, bg="#e8e8e8", fg="#333333", font=("Segoe UI", 8, "bold"), padx=5, pady=2, cursor="hand2")
            lbl.pack(side=tk.LEFT, padx=3)
            lbl.bind("<Button-1>", lambda e, k=actual_keyword, w=lbl: toggle_tag(k, w))
            def on_enter(e, w=lbl):
                if w.cget("bg") == "#e8e8e8": w.config(bg="#d0d0d0")
            def on_leave(e, w=lbl):
                if w.cget("bg") == "#d0d0d0": w.config(bg="#e8e8e8")
            lbl.bind("<Enter>", on_enter)
            lbl.bind("<Leave>", on_leave)
            self.tag_widgets[actual_keyword] = lbl
            
        if hasattr(self, '_pending_initial_filters'):
            for kw in self._pending_initial_filters:
                if kw in self.tag_widgets:
                    toggle_tag(kw, self.tag_widgets[kw])
            self._pending_initial_filters = []

        # --- DUAL BUTTON STRATEGY ---
        now = datetime.now()
        
        # Group 1: Standard Horizontal Buttons
        self.b1 = tk.Button(self.btn_frame, text="View Active Inventory", command=lambda: self.switch_view('inventory'), bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20)
        self.b2 = tk.Button(self.btn_frame, text="Current Month Logs", command=lambda y=now.strftime("%Y"), m=now.strftime("%m"): self.switch_view('history_specific', year=y, month=m), bg="#445566", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20)
        
        self.history_btn = tk.Menubutton(self.btn_frame, text="Archive", bg="#555555", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12, activebackground="#777777", activeforeground="white", cursor="hand2")
        self.main_menu = tk.Menu(self.history_btn, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
        self.history_btn.config(menu=self.main_menu)
        self.main_menu.add_command(label="Loading archives...", state="disabled") 
        threading.Thread(target=self._build_archive_menu_async, daemon=True).start()

        self.b4 = tk.Button(self.btn_frame, text="Open in External Editor", command=self.open_external_file, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=22)
        
        apply_hover(self.b1, "#011528", "#022a52")
        apply_hover(self.b2, "#445566", "#5d6d7e")
        apply_hover(self.history_btn, "#555555", "#777777")
        apply_hover(self.b4, "#217346", "#2a8f57")

        self.b1.pack(side=tk.LEFT, padx=5)
        self.b2.pack(side=tk.LEFT, padx=5)
        self.history_btn.pack(side=tk.LEFT, padx=5)
        self.b4.pack(side=tk.LEFT, padx=5)
        
        # Group 2: The Vertical Dropdown Frame
        self.dropdown_frame = tk.Frame(self.viewer, bg="#ffffff", highlightthickness=2, highlightbackground="#cccccc")
        
        self.d1 = tk.Button(self.dropdown_frame, text="View Active Inventory", command=lambda: self.switch_view('inventory'), bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat")
        self.d2 = tk.Button(self.dropdown_frame, text="Current Month Logs", command=lambda y=now.strftime("%Y"), m=now.strftime("%m"): self.switch_view('history_specific', year=y, month=m), bg="#445566", fg="white", font=("Segoe UI", 10, "bold"), relief="flat")
        
        self.drop_history_btn = tk.Button(self.dropdown_frame, text="Archive", bg="#555555", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", activebackground="#777777", activeforeground="white", cursor="hand2")
        
        def popup_archive_menu(event):
            self.main_menu.post(event.widget.winfo_rootx() + 150, event.widget.winfo_rooty())
            
        self.drop_history_btn.bind("<ButtonRelease-1>", popup_archive_menu)
        
        self.d4 = tk.Button(self.dropdown_frame, text="Open in External Editor", command=lambda: [self.force_close_menu(), self.open_external_file()], bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat")

        apply_hover(self.d1, "#011528", "#022a52")
        apply_hover(self.d2, "#445566", "#5d6d7e")
        apply_hover(self.drop_history_btn, "#555555", "#777777")
        apply_hover(self.d4, "#217346", "#2a8f57")

        self.d1.pack(fill=tk.X, padx=10, pady=(10, 5), ipady=3)
        self.d2.pack(fill=tk.X, padx=10, pady=5, ipady=3)
        self.drop_history_btn.pack(fill=tk.X, padx=10, pady=5, ipady=3)
        self.d4.pack(fill=tk.X, padx=10, pady=(5, 10), ipady=3)

        # --- DATA TABLE ---
        columns = ("Date/Day", "Time", "Location", "Sample ID", "Name", "Notes", "User")
        self.tree = ttk.Treeview(self.viewer, columns=columns, show="headings", height=15)
        for col in columns: self.tree.heading(col, text=col)
        self.tree.column("Date/Day", width=90, anchor=tk.CENTER)
        self.tree.column("Time", width=80, anchor=tk.CENTER)
        self.tree.column("Location", width=180, anchor=tk.W)
        self.tree.column("Sample ID", width=90, anchor=tk.CENTER)
        self.tree.column("Name", width=150, anchor=tk.W)
        self.tree.column("Notes", width=250, anchor=tk.W) 
        self.tree.column("User", width=120, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(self.viewer, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.tree.tag_configure('removed', foreground='#EF4444') 
        self.tree.tag_configure('pending', foreground='#06B6D4') 
        self.tree.tag_configure('system', foreground="#10B981")  
        self.tree.tag_configure('overdue', foreground='#8B5CF6')

        # --- GLOBAL KEYBINDS ---
        self.last_refresh_time = 0

        def focus_search_bar(event):
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, tk.END) # Highlights existing text for quick typing
            return "break" # Stops the OS from doing a default Ctrl+F action

        def handle_escape(event):
            self.search_var.set("")
            self.trigger_manual_search()
            self.viewer.focus_set() # Removes the blinking cursor from the search box
            return "break"

        def handle_f5(event):
            current_time = time.time()
            if current_time - self.last_refresh_time > 1.0: # 1-second cooldown
                self.last_refresh_time = current_time
                self.execute_search()
            return "break"

        def handle_new_window(event):
            # Asks the main tray application to safely spawn a new viewer
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

        tk.Label(self.viewer, text="Select a row and press [Ctrl+C] to copy data  |  [Ctrl+F] for Searching  |  [Esc] Clears your Search Bar  |  [Ctrl+N] for New Window  |  F5 for Manual Refresh", bg="#f4f4f4", fg="#666666", font=("Segoe UI", 9, "italic")).pack(side=tk.LEFT, padx=10, pady=(0, 5))
        self.viewer.bind("<Configure>", self.handle_window_resize)

    def handle_window_resize(self, event):
        """Monitors the window width and hides/shows the horizontal buttons."""
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
        """Places the pre-built dropdown container safely over the data table."""
        if self.menu_is_open:
            self.dropdown_frame.place_forget()
            if self.icon_menu: self.hamburger_btn.config(image=self.icon_menu, text="")
            else: self.hamburger_btn.config(text="☰")
            self.menu_is_open = False
        else:
            x_pos = 15
            y_pos = self.top_frame.winfo_y() + self.top_frame.winfo_height()
            
            self.dropdown_frame.place(x=x_pos, y=y_pos, width=260)
            self.dropdown_frame.lift() 
            
            if self.icon_menu_close: self.hamburger_btn.config(image=self.icon_menu_close, text="")
            else: self.hamburger_btn.config(text="✕")
            self.menu_is_open = True

    def force_close_menu(self):
        """Helper to ensure the menu auto-closes when an option is clicked."""
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
            date_val = self.tree.set(child, 'Date/Day')
            time_val = self.tree.set(child, 'Time')
            absolute_time = f"{date_val} {time_val}"
            
            if col in ("Date/Day", "Time"):
                primary_val = absolute_time
            else:
                primary_val = self.tree.set(child, col)
            
            data_list.append((primary_val, absolute_time, child))

        def smart_sort_key(item):
            primary = str(item[0]).strip().lower()
            tie_breaker = str(item[1])
            
            if primary.startswith("smp:"):
                try:
                    return (0, int(primary.replace("smp:", "")), tie_breaker)
                except ValueError:
                    pass
                    
            return (1, primary, tie_breaker)

        data_list.sort(key=smart_sort_key, reverse=reverse)

        for index, (*_, child) in enumerate(data_list):
            self.tree.move(child, '', index)

    def trigger_manual_search(self, event=None):
        """Clears all active Quick Tags when the user performs a manual text search."""
        if hasattr(self, 'active_filters'):
            self.active_filters.clear()
        if hasattr(self, 'tag_widgets'):
            for lbl in self.tag_widgets.values():
                lbl.config(bg="#e8e8e8", fg="#333333") # Reset to grey
                
        self.execute_search()

    def execute_search(self, event=None):
        typed_query = self.search_var.get().strip()
        hidden_query = " ".join(self.active_filters)
        
        # Combine the visual search box with the hidden button filters
        full_query = f"{typed_query} {hidden_query}".strip()
        
        if not full_query:
            if self.current_tab[0] == 'deep_search': 
                self.current_tab[0] = 'inventory'
            self.load_data(self.current_tab[0], "", year=self.current_history_target[0], month=self.current_history_target[1])
            return
        
        # --- CONTEXT-AWARE ROUTING ---
        if self.current_tab[0] == 'inventory':
            self.load_data('inventory', full_query)
        else:
            self.tree.delete(*self.tree.get_children())
            self.tree.insert("", tk.END, values=("", "", "⏳ SEARCHING SERVER...", full_query, "Awaiting API response...", "", ""))
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

        # Offload the slow network request to a background thread!
        threading.Thread(
            target=self._threaded_load_data, 
            args=(source_type, search_query, is_auto_refresh, year, month), 
            daemon=True
        ).start()

    def _threaded_load_data(self, source_type, search_query, is_auto_refresh, year, month):
        data = self.fetch_view_data(source=source_type, year=year, month=month, sort_col=self.current_sort_col, reverse=self.current_sort_reverse)
        
        # Once the server replies, safely push the data back to the UI thread
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

        current_hash = f"{len(data)}_{source_type}_{year}_{month}_{(str(data[-1]) if data else '')}_{self.current_sort_col}_{self.current_sort_reverse}_{search_query}"
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
        
        now = datetime.now()
        is_active_inventory = (source_type == 'inventory')
        
        for row in data:
            is_old = False
            if is_active_inventory:
                try:
                    if (now - datetime.strptime(str(row[0]), "%Y-%m-%d")).days >= 14:
                        is_old = True
                except Exception: pass
            
            if filter_old and not is_old: continue
            
            row_str = " ".join(str(cell).lower() for cell in row)
            if search_terms and not all(term in row_str for term in search_terms): continue
            
            display_row = list(row)
            clean_loc = str(display_row[2]).replace('LOC:', '').replace('LOC-', '').strip()
            display_row[2] = clean_loc
            item_id = str(display_row[3]) if len(display_row) > 3 else ""
            
            loc_lower = clean_loc.lower()
            row_tags = ()
            
            if 'closed' in loc_lower or 'removed' in loc_lower: row_tags = ('removed',)
            elif is_old: row_tags = ('overdue',)
            elif 'verification' in loc_lower or 'pending' in loc_lower: row_tags = ('pending',)
            elif 'system' in loc_lower: row_tags = ('system',)
            
            inserted = self.tree.insert("", tk.END, text=item_id, values=display_row, tags=row_tags)
            if item_id and item_id in selected_ids:
                try: self.tree.selection_add(inserted)
                except Exception: pass

        self.treeview_sort_column(self.current_sort_col, self.current_sort_reverse)

    def auto_refresh(self):
        if self.viewer.winfo_exists():
            
            if self.current_tab[0] == 'inventory':
                typed_query = self.search_var.get().strip()
                hidden_query = " ".join(getattr(self, 'active_filters', set()))
                full_query = f"{typed_query} {hidden_query}".strip()
                self.load_data('inventory', full_query, is_auto_refresh=True)
                    
            self.viewer.after(2000, self.auto_refresh)

    def copy_selection(self, event=None):
        selected = self.tree.selection()
        if not selected: 
            return "break"
        copied_lines = []
        for item in selected:
            values = self.tree.item(item, "values")
            copied_lines.append("\t".join(str(v) for v in values))
        
        self.viewer.clipboard_clear()
        self.viewer.clipboard_append("\n".join(copied_lines))
        self.notify(f"Copied {len(selected)} rows to clipboard" if len(selected) > 1 else "Copied 1 row to clipboard")
        return "break"  # Stops event propagation and prevents duplicate firing

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