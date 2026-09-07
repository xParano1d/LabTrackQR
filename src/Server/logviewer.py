# logviewer.py
import tkinter as tk
from tkinter import ttk
import os
import sys
import ctypes
import threading
import requests
from datetime import datetime

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

class LogViewerWindow:
    def __init__(self, parent_root, storage, notify_callback, is_server=False):
        self.storage = storage
        self.notify = notify_callback
        self.is_server = is_server
        
        self.viewer = tk.Toplevel(parent_root)
        title = "System Logs & Inventory"
        self.viewer.title(title)
        self.viewer.geometry("1050x550")
        self.viewer.configure(bg="#f4f4f4")
        
        try:
            self.viewer.iconbitmap(default=get_theme_icon())
        except:
            pass
            
        self._apply_dark_title_bar(self.viewer)
        
        self.current_tab = ['inventory'] 
        self.current_history_target = [None, None] 
        self.last_data_hash = [""] 
        
        # Default Sorting States
        self.current_sort_col = "Date/Day"
        self.current_sort_reverse = True
        
        self._build_ui()
        self.load_data('inventory')
        self.auto_refresh()

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

    # --- THE UNIFIED API FETCHERS ---
    # By putting these here, BOTH the Server and Client use the exact same network logic!
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
        try:
            target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")
            url = f"{target_url}/api/view_data"
            params = {
                "source": source, "year": year or "", "month": month or "",
                "sort_col": sort_col, "reverse": str(reverse).lower()
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception:
            pass
        return []
    # ---------------------------------

    def _build_ui(self):
        top_frame = tk.Frame(self.viewer, bg="#f4f4f4")
        top_frame.pack(fill=tk.X, pady=10, padx=10)

        btn_frame = tk.Frame(top_frame, bg="#f4f4f4")
        btn_frame.pack(side=tk.LEFT)

        search_container = tk.Frame(top_frame, bg="#f4f4f4")
        search_container.pack(side=tk.RIGHT)

        search_frame = tk.Frame(search_container, bg="#f4f4f4")
        search_frame.pack(side=tk.TOP, anchor="e")

        # --- UI: ENTER-TO-SEARCH BAR ---
        self.search_var = tk.StringVar()
        tk.Label(search_frame, text="Search:", bg="#f4f4f4", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        entry_border = tk.Frame(search_frame, bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc")
        entry_border.pack(side=tk.LEFT)
        
        search_entry = tk.Entry(entry_border, textvariable=self.search_var, font=("Segoe UI", 10), width=28, relief="flat", bd=0)
        search_entry.pack(side=tk.LEFT, ipady=4, padx=(8, 0))
        search_entry.bind("<Return>", self.execute_search)

        search_btn = tk.Label(entry_border, text="🔍", bg="#ffffff", fg="#555555", font=("Segoe UI", 11), cursor="hand2")
        search_btn.pack(side=tk.RIGHT, padx=5)
        search_btn.bind("<Button-1>", self.execute_search)

        # --- UI: QUICK TAGS ---
        tags_frame = tk.Frame(search_container, bg="#f4f4f4")
        tags_frame.pack(side=tk.TOP, anchor="e", pady=(5, 0))

        quick_tags = [
            ("📅 Today", "today"), 
            ("⏳ Pending", "pending"), 
            ("❌ Removed", "removed"),
            ("🧹 Clear", "CLEAR")
        ]

        def toggle_tag(keyword):
            if keyword == "CLEAR":
                self.search_var.set("")
                self.execute_search()
                return

            if keyword == "today":
                keyword = datetime.now().strftime("%Y-%m-%d")

            current_query = self.search_var.get().strip()
            words = [w.lower() for w in current_query.split()]

            if keyword in words:
                words.remove(keyword)
            else:
                words.append(keyword)

            self.search_var.set(" ".join(words))
            self.execute_search()

        for display_text, actual_keyword in quick_tags:
            is_clear_btn = (actual_keyword == "CLEAR")
            bg_color = "#e8e8e8" if not is_clear_btn else "#ffdddd"
            hover_color = "#d0d0d0" if not is_clear_btn else "#ffbbbb"
            text_color = "#333333" if not is_clear_btn else "#d9534f"

            lbl = tk.Label(tags_frame, text=display_text, bg=bg_color, fg=text_color, font=("Segoe UI", 8, "bold"), padx=8, pady=2, cursor="hand2")
            lbl.pack(side=tk.LEFT, padx=3)
            
            lbl.bind("<Button-1>", lambda e, k=actual_keyword: toggle_tag(k))
            lbl.bind("<Enter>", lambda e, c=hover_color: e.widget.config(bg=c))
            lbl.bind("<Leave>", lambda e, c=bg_color: e.widget.config(bg=c))

        # --- TREEVIEW SETUP ---
        columns = ("Date/Day", "Time", "Location", "Sample ID", "Name", "Notes", "User")
        self.tree = ttk.Treeview(self.viewer, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.tree.heading(col, text=col)
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
        self.tree.bind("<Control-c>", self.copy_selection)

        tk.Label(self.viewer, text="Tip: Select a row and press Ctrl+C to copy data", bg="#f4f4f4", fg="#666666", font=("Segoe UI", 9, "italic")).pack(side=tk.LEFT, padx=10, pady=(0, 5))

        now = datetime.now()
        curr_year = now.strftime("%Y")
        curr_month = now.strftime("%m")
        tk.Button(btn_frame, text="View Active Inventory", command=lambda: self.load_data('inventory', ""), bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Current Month Logs", command=lambda y=curr_year, m=curr_month: self.load_data('history_specific', "", year=y, month=m), bg="#445566", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20).pack(side=tk.LEFT, padx=5)

        # --- DYNAMIC CASCADE MENU ---
        month_names = {"01": "January", "02": "February", "03": "March", "04": "April", "05": "May", "06": "June", 
                       "07": "July", "08": "August", "09": "September", "10": "October", "11": "November", "12": "December"}
        
        # Calling the unified API fetcher instead of storage!
        available_history = self.fetch_archive_months() 
        history_tree = {}
        for ym in available_history:
            y, m = ym.split('-')
            if y not in history_tree: history_tree[y] = []
            history_tree[y].append(m)

        history_btn = tk.Menubutton(btn_frame, text="Archive", bg="#555555", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12, activebackground="#777777", activeforeground="white", cursor="hand2")
        history_btn.pack(side=tk.LEFT, padx=5)

        main_menu = tk.Menu(history_btn, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
        history_btn.config(menu=main_menu)

        if not history_tree:
            main_menu.add_command(label="No Archives Found", state="disabled")
        else:
            for year in sorted(history_tree.keys(), reverse=True):
                year_menu = tk.Menu(main_menu, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
                main_menu.add_cascade(label=f"Year: {year}", menu=year_menu)
                
                for month in sorted(history_tree[year], reverse=True):
                    pretty_month = f"{month_names.get(month, month)} ({month})"
                    year_menu.add_command(label=pretty_month, command=lambda y=year, m=month: self.load_data('history_specific', "", year=y, month=m))

        tk.Button(btn_frame, text="Open in External Editor", command=self.open_external_file, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=22).pack(side=tk.LEFT, padx=5)

    # --- SORTING FIX ---
    def _update_sort_headers(self, active_col, is_reverse):
        """Purely visual update of headers, prevents infinite loading loops."""
        for c in self.tree["columns"]:
            if c == active_col:
                arrow = " ▼" if is_reverse else " ▲"
                # Passes the OPPOSITE of the current direction to the command
                self.tree.heading(c, text=c + arrow, command=lambda _col=c, _rev=not is_reverse: self.treeview_sort_column(_col, _rev))
            else:
                # Other columns reset to default text and prepare for a clean reverse=False click
                self.tree.heading(c, text=c, command=lambda _col=c: self.treeview_sort_column(_col, False))

    def treeview_sort_column(self, col, reverse):
        self.current_sort_col = col
        self.current_sort_reverse = reverse
        
        self._update_sort_headers(col, reverse)

        if self.current_tab[0] == 'deep_search':
            if col in ("Date/Day", "Time"):
                data_list = [(f"{self.tree.set(child, 'Date/Day')} {self.tree.set(child, 'Time')}", child) for child in self.tree.get_children('')]
            else:
                data_list = [(self.tree.set(child, col).lower(), child) for child in self.tree.get_children('')]
            data_list.sort(reverse=reverse)
            for index, (val, child) in enumerate(data_list):
                self.tree.move(child, '', index)
        else:
            # Trigger API reload for massive files to avoid freezing the UI!
            self.load_data(self.current_tab[0], self.search_var.get(), year=self.current_history_target[0], month=self.current_history_target[1])
    # -------------------

    def execute_search(self, event=None):
        query = self.search_var.get().strip()
        if not query:
            if self.current_tab[0] == 'deep_search': self.current_tab[0] = 'inventory'
            self.load_data(self.current_tab[0], "", year=self.current_history_target[0], month=self.current_history_target[1])
            return
        
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", tk.END, values=("", "", "⏳ SEARCHING SERVER...", query, "Awaiting API response...", "", ""))
        self.viewer.update_idletasks()
        
        threading.Thread(target=lambda: self.run_api_deep_search(query), daemon=True).start()

    def run_api_deep_search(self, query):
        try:
            target_url = getattr(self.storage, 'server_url', "http://127.0.0.1:5000")
            url = f"{target_url}/api/search" 
            response = requests.get(url, params={"q": query}, timeout=150)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                warning = data.get("warning", "")
                self.viewer.after(0, lambda: self.render_deep_search(results, warning))
            else:
                self.viewer.after(0, lambda: self.notify(f"Search failed: HTTP {response.status_code}"))
        except Exception:
            self.viewer.after(0, lambda: self.notify(f"Network Error:\nCould not reach server API."))

    def render_deep_search(self, data, warning_msg=""):
        self.current_tab[0] = 'deep_search'
        self.tree.delete(*self.tree.get_children())
        
        for row in data:
            display_row = list(row) 
            display_row[2] = self._clean_and_iconify_location(str(display_row[2]))
            item_id = str(display_row[3]) if len(display_row) > 3 else ""
            self.tree.insert("", tk.END, text=item_id, values=display_row)
            
        if warning_msg:
            self.notify(warning_msg)
            
        self._update_sort_headers(self.current_sort_col, self.current_sort_reverse)

    def load_data(self, source_type, search_query="", is_auto_refresh=False, year=None, month=None):
        if source_type == 'deep_search': return 

        # Let the server do all the heavy reading and sorting via our unified fetcher!
        data = self.fetch_view_data(
            source=source_type, year=year, month=month, 
            sort_col=self.current_sort_col, reverse=self.current_sort_reverse
        )
        
        unique_data = []
        seen_rows = set()
        for row in data:
            row_str = str(row) 
            if row_str not in seen_rows:
                seen_rows.add(row_str)
                unique_data.append(row)
        data = unique_data

        current_hash = f"{len(data)}_{source_type}_{year}_{month}_{(str(data[-1]) if data else '')}_{self.current_sort_col}_{self.current_sort_reverse}"
        if is_auto_refresh and current_hash == self.last_data_hash[0]:
            return 
        self.last_data_hash[0] = current_hash

        self.current_tab[0] = source_type
        if year and month:
            self.current_history_target[0] = year
            self.current_history_target[1] = month

        selected_ids = [self.tree.item(item, "text") for item in self.tree.selection()] if is_auto_refresh else []

        self.tree.delete(*self.tree.get_children())
        
        search_terms = [word.lower() for word in search_query.strip().split()]
        
        for row in data:
            row_str = " ".join(str(cell).lower() for cell in row)
            if search_terms and not all(term in row_str for term in search_terms):
                continue
            
            display_row = list(row)
            display_row[2] = self._clean_and_iconify_location(str(display_row[2]))
            item_id = str(display_row[3]) if len(display_row) > 3 else ""
            
            inserted = self.tree.insert("", tk.END, text=item_id, values=display_row)
            if item_id and item_id in selected_ids:
                try: self.tree.selection_add(inserted)
                except Exception: pass

        self._update_sort_headers(self.current_sort_col, self.current_sort_reverse)

    def auto_refresh(self):
        if self.viewer.winfo_exists():
            if len(self.search_var.get().strip()) < 2:
                if self.current_tab[0] == 'deep_search':
                    self.current_tab[0] = 'inventory'
                self.load_data(self.current_tab[0], "", is_auto_refresh=True, year=self.current_history_target[0], month=self.current_history_target[1])
            self.viewer.after(2000, self.auto_refresh) 

    def copy_selection(self, event=None):
        selected = self.tree.selection()
        if not selected: return
        copied_lines = []
        for item in selected:
            values = self.tree.item(item, "values")
            copied_lines.append("\t".join(str(v) for v in values))
        
        self.viewer.clipboard_clear()
        self.viewer.clipboard_append("\n".join(copied_lines))
        
        copiedItemsCount = len(selected)
        if copiedItemsCount > 1:
            self.notify(f"Copied {copiedItemsCount} rows to clipboard")
        else:
            self.notify("Copied 1 row to clipboard")

    def open_external_file(self):
        file_to_open = self.storage.get_active_file_path(self.current_tab[0])
        try:
            if not file_to_open:
                self.notify("Editor Disabled.\nView master files directly on the Server.")
                return
            os.startfile(file_to_open)
        except Exception as e:
            self.notify(f"Could not open file:\n{e}")