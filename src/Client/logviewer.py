# logviewer.py
import tkinter as tk
from tkinter import ttk
import os
import sys
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
        
        self._build_ui()
        
        if initial_filters:
            for f in initial_filters:
                if f in self.tag_widgets:
                    self.active_filters.add(f)
                    self.tag_widgets[f].config(bg="#011528", fg="white")
                    
        if initial_search:
            self.search_var.set(initial_search)
            
        self.execute_search()
        self.auto_refresh()

    def switch_view(self, source, year=None, month=None):
        """Cleans up the UI (wipes search and buttons) before changing tabs."""
        self.search_var.set("")
        if hasattr(self, 'active_filters'):
            self.active_filters.clear()
        if hasattr(self, 'tag_widgets'):
            for lbl in self.tag_widgets.values():
                lbl.config(bg="#e8e8e8", fg="#333333") # Reset to grey
                
        # --- THE FIX: Instantly change state so auto-refresh backs off ---
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
        top_frame = tk.Frame(self.viewer, bg="#f4f4f4")
        top_frame.pack(fill=tk.X, pady=10, padx=10)
        btn_frame = tk.Frame(top_frame, bg="#f4f4f4")
        btn_frame.pack(side=tk.LEFT)
        search_container = tk.Frame(top_frame, bg="#f4f4f4")
        search_container.pack(side=tk.RIGHT)
        search_frame = tk.Frame(search_container, bg="#f4f4f4")
        search_frame.pack(side=tk.TOP, anchor="e", padx=(0,3))

        # --- UI: ENTER-TO-SEARCH BAR ---
        self.search_var = tk.StringVar()
        tk.Label(search_frame, text="Search:", bg="#f4f4f4", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        search_entry = tk.Entry(search_frame, textvariable=self.search_var, font=("Segoe UI", 10), width=24, relief="solid", bd=1)
        search_entry.pack(side=tk.LEFT, ipady=3)
        search_entry.bind("<Return>", self.trigger_manual_search)

        def clear_search():
            self.search_var.set("")
            self.trigger_manual_search()

        # Load PNG Icons and attach them to 'self' to prevent memory deletion
        try:
            s_img = Image.open(resource_path("search.png")).resize((22, 22), Image.Resampling.LANCZOS)
            self.icon_search = ImageTk.PhotoImage(s_img)
            
            c_img = Image.open(resource_path("delete.png")).resize((22, 22), Image.Resampling.LANCZOS)
            self.icon_clear = ImageTk.PhotoImage(c_img)
            
            # Create buttons using the images instead of text
            search_btn = tk.Button(search_frame, image=self.icon_search, command=self.trigger_manual_search, bg="#011528", activebackground="#022a52", relief="flat", cursor="hand2", bd=0, padx=6, pady=2)
            clear_btn = tk.Button(search_frame, image=self.icon_clear, command=clear_search, bg="#d9534f", activebackground="#c9302c", relief="flat", cursor="hand2", bd=0, padx=6, pady=2)
            
        except Exception:
            # Safe Fallback to text if the image files are missing
            search_btn = tk.Button(search_frame, text="🔍", command=self.execute_search, bg="#011528", fg="white", font=("Segoe UI", 9), relief="flat", cursor="hand2", width=4 )
            clear_btn = tk.Button(search_frame, text="⌫", command=clear_search, bg="#d9534f", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2", width=3, round=2)

        search_btn.pack(side=tk.LEFT, padx=(2, 2), ipady=2)
        clear_btn.pack(side=tk.LEFT, padx=(0, 0), ipady=2)

        # --- UI: QUICK TAGS ---
        tags_frame = tk.Frame(search_container, bg="#f4f4f4")
        tags_frame.pack(side=tk.TOP, anchor="e", pady=(2, 0))

        self.active_filters = set() # Stores the hidden search terms
        self.tag_widgets = {}       # Stores the buttons to change their colors    

        # Hide "My Samples" on the Server
        quick_tags = []
        if not self.is_server:
            quick_tags.append(("My Samples", "ME"))
            
        quick_tags.extend([
            ("Today", "today"),
            ("Old", "old"),
            ("Pending", "pending-storage"), 
            ("Removed", "removed")
        ])

        def toggle_tag(keyword, lbl_widget):
            # 1. Resolve dynamic targets
            if keyword == "ME":
                target = self.current_user if self.current_user else ""
            elif keyword == "today":
                target = datetime.now().strftime("%Y-%m-%d")
            else:
                target = keyword
                
            if not target: return

            # 2. Force inventory view for operational tags
            if keyword in ["ME", "old", "pending-storage", "today"]:
                self.current_tab[0] = 'inventory'

            # 3. Toggle the hidden state and update the button color!
            if target in self.active_filters:
                self.active_filters.remove(target)
                lbl_widget.config(bg="#e8e8e8", fg="#333333") # Inactive state (Grey)
            else:
                self.active_filters.add(target)
                lbl_widget.config(bg="#011528", fg="white") # Active state (Dark Blue)

            self.execute_search()

        for display_text, actual_keyword in quick_tags:
            lbl = tk.Label(tags_frame, text=display_text, bg="#e8e8e8", fg="#333333", font=("Segoe UI", 8, "bold"), padx=5, pady=2, cursor="hand2")
            lbl.pack(side=tk.LEFT, padx=3)
            
            # Bind the click event, passing the label widget itself so we can color it
            lbl.bind("<Button-1>", lambda e, k=actual_keyword, w=lbl: toggle_tag(k, w))
            
            # Smart hover effects (only change color if it isn't currently active)
            def on_enter(e, w=lbl):
                if w.cget("bg") == "#e8e8e8": w.config(bg="#d0d0d0")
            def on_leave(e, w=lbl):
                if w.cget("bg") == "#d0d0d0": w.config(bg="#e8e8e8")
                
            lbl.bind("<Enter>", on_enter)
            lbl.bind("<Leave>", on_leave)
            
            self.tag_widgets[actual_keyword] = lbl

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
        self.tree.bind("<Control-c>", self.copy_selection)

        self.tree.tag_configure('removed', foreground='#EF4444') 
        self.tree.tag_configure('pending', foreground='#06B6D4') 
        self.tree.tag_configure('system', foreground="#10B981")  
        self.tree.tag_configure('overdue', foreground='#8B5CF6')

        tk.Label(self.viewer, text="Tip: Select a row and press Ctrl+C to copy data", bg="#f4f4f4", fg="#666666", font=("Segoe UI", 9, "italic")).pack(side=tk.LEFT, padx=10, pady=(0, 5))

        now = datetime.now()

        tk.Button(btn_frame, text="View Active Inventory", command=lambda: self.switch_view('inventory'), bg="#011528", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Current Month Logs", command=lambda y=now.strftime("%Y"), m=now.strftime("%m"): self.switch_view('history_specific', year=y, month=m), bg="#445566", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=20).pack(side=tk.LEFT, padx=5)

        self.history_btn = tk.Menubutton(btn_frame, text="Archive", bg="#555555", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12, activebackground="#777777", activeforeground="white", cursor="hand2")
        self.history_btn.pack(side=tk.LEFT, padx=5)
        
        self.main_menu = tk.Menu(self.history_btn, tearoff=0, bg="#ffffff", fg="#333333", font=("Segoe UI", 10))
        self.history_btn.config(menu=self.main_menu)
        self.main_menu.add_command(label="Loading archives...", state="disabled") 
        
        threading.Thread(target=self._build_archive_menu_async, daemon=True).start()

        tk.Button(btn_frame, text="Open in External Editor", command=self.open_external_file, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=22).pack(side=tk.LEFT, padx=5)

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
            
            if 'removed' in loc_lower: row_tags = ('removed',)
            elif 'pending' in loc_lower: row_tags = ('pending',)
            elif 'system' in loc_lower: row_tags = ('system',)
                
            self.tree.insert("", tk.END, text=item_id, values=display_row, tags=row_tags)
            
        if warning_msg: self.notify(warning_msg)
        # --- THE FIX: Force the UI to physically sort the new data ---
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
            
            if 'removed' in loc_lower: row_tags = ('removed',)
            elif is_old: row_tags = ('overdue',)
            elif 'pending' in loc_lower: row_tags = ('pending',)
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
        if not selected: return
        copied_lines = []
        for item in selected:
            values = self.tree.item(item, "values")
            copied_lines.append("\t".join(str(v) for v in values))
        
        self.viewer.clipboard_clear()
        self.viewer.clipboard_append("\n".join(copied_lines))
        self.notify(f"Copied {len(selected)} rows to clipboard" if len(selected) > 1 else "Copied 1 row to clipboard")

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