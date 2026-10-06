import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import os
import sys
import json
import shutil
import ctypes
import winreg
import textwrap
from PIL import ImageChops
from datetime import datetime
from PIL import Image, ImageTk, ImageFont, ImageDraw, ImageFilter

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

class MapViewerWindow:
    def __init__(self, parent_root, storage, notify_callback):
        self.storage = storage
        self.notify = notify_callback
        
        theme_path = resource_path("BW_theme.json")
        if os.path.exists(theme_path):
            ctk.set_default_color_theme(theme_path)
            
        self.viewer = ctk.CTkToplevel(parent_root)
        self.viewer.title("Laboratory Storage Map")
        
        self.viewer.update_idletasks()
        screen_w = self.viewer.winfo_screenwidth()
        screen_h = self.viewer.winfo_screenheight()
        
        # --- ADAPTIVE SIZING ---
        # Takes up 85% of the screen, but caps at a maximum of 1400x850 for massive monitors
        width = min(1400, int(screen_w * 0.85))
        height = min(850, int(screen_h * 0.85))
        
        x = int((screen_w / 2) - (width / 2))
        y = int((screen_h / 2) - (height / 2) - 50)
        self.viewer.geometry(f"{width}x{height}+{x}+{y}")
        
        try:
            icon_path = resource_path(get_theme_icon())
            self.viewer.iconbitmap(icon_path)
            self.viewer.after(200, lambda: self.viewer.iconbitmap(icon_path))
        except: pass
        
        self.viewer.after(200, self._update_window_theme_elements)
        
        self.local_map_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR')
        os.makedirs(self.local_map_dir, exist_ok=True)
        
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.photo_image = None
        self.render_x = 0
        self.render_y = 0
        
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._pan_start_x = 0
        self._pan_start_y = 0
        
        self.zones = [] 
        self.inventory_map = {} 
        
        self._zoom_timer = None 
        self._is_zooming = False
        
        self.sheet_height = 350
        self.sheet_target_y = 5000 
        self.sheet_current_y = 5000
        self.sheet_is_open = False
        self.active_zone_name = None
        
        self.text_image_cache = {}
        
        self._sync_network_map()
        self._build_ui()
        self._bind_events()
        self._build_data_bridge()
        
        self.viewer.after(100, self._load_local_map)

    def _sync_network_map(self):
        r"""Safely copies map.png and map.json from the Master Directory to LocalAppData, with silent offline fallback."""
        network_dir = r"Z:\Sample Tracking Tool\laboratory_map"
        try:
            settings_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR', 'server_settings.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    data = json.load(f)
                    saved_path = data.get("PARENT_FOLDER")
                    if saved_path and os.path.exists(saved_path):
                        network_dir = os.path.join(saved_path, "laboratory_map")
        except Exception:
            pass
            
        # 1. Check if we already have a working offline cache on the hard drive
        has_cache = (os.path.exists(os.path.join(self.local_map_dir, "map.json")) and 
                     os.path.exists(os.path.join(self.local_map_dir, "map.png")))

        try:
            if not os.path.exists(network_dir): 
                # If server is down and we HAVE NO cache, warn the user.
                if not has_cache:
                    self.notify("Cannot fetch map from server.\nNo local offline cache available.")
                # If server is down but we HAVE a cache, stay completely silent and load the cache!
                return
            
            # 2. Server is online! Check for updates and re-cache if the Admin changed something
            for file_name in ["map.json", "map.png"]:
                net_file = os.path.join(network_dir, file_name)
                loc_file = os.path.join(self.local_map_dir, file_name)
                
                if os.path.exists(net_file):
                    # If local file is missing, OR server file is modified more recently -> overwrite cache
                    if not os.path.exists(loc_file) or os.path.getmtime(net_file) > os.path.getmtime(loc_file):
                        shutil.copy2(net_file, loc_file)
                        
        except Exception:
            if not has_cache:
                self.notify("Cannot fetch map from server.\nTry again later.")

    def _build_data_bridge(self):
        self.inventory_map.clear()
        raw_inventory = self.storage.get_inventory_data()
        
        for row in raw_inventory:
            if len(row) < 7: continue
            raw_loc = str(row[2]).replace('LOC:', '').replace('LOC-', '').strip().lower()
            if raw_loc not in self.inventory_map:
                self.inventory_map[raw_loc] = []
            self.inventory_map[raw_loc].append(row)
            
        drawn_zone_names = {z['name'].lower() for z in self.zones}
        self.unmapped_count = sum(len(items) for loc, items in self.inventory_map.items() if loc not in drawn_zone_names and "verification" not in loc)
        
        if hasattr(self, 'btn_other_locs'):
            self.btn_other_locs.configure(text=f"Other Locations ({self.unmapped_count})")

    def _update_window_theme_elements(self):
        try:
            os_icon_path = resource_path(get_theme_icon())
            self.viewer.iconbitmap(os_icon_path)
            
            is_light_app = ctk.get_appearance_mode() == "Light"
            app_icon_path = resource_path("icon_black.ico" if is_light_app else "icon_white.ico")
            
            hwnd = ctypes.windll.user32.GetParent(self.viewer.winfo_id())
            hIconSmall = ctypes.windll.user32.LoadImageW(0, app_icon_path, 1, 16, 16, 0x0010)
            if hIconSmall: ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hIconSmall)
                
            mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
            rendering_policy = ctypes.c_int(2 if mode_idx == 1 else 1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(rendering_policy), 4)

            bg_hex = ctk.ThemeManager.theme["CTk"]["fg_color"][mode_idx]
            text_hex = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode_idx]

            def hex_to_bgr(hex_str):
                c = int(hex_str.replace("#", ""), 16)
                return (c & 0xFF) << 16 | (c & 0xFF00) | (c >> 16)

            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(hex_to_bgr(bg_hex))), 4)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(ctypes.c_int(hex_to_bgr(text_hex))), 4)
        except Exception: pass

    def _build_ui(self):
        self.viewer.grid_rowconfigure(0, weight=1)
        self.viewer.grid_columnconfigure(0, weight=1) 
        
        mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
        canvas_bg = ctk.ThemeManager.theme["CTk"]["fg_color"][mode_idx]
        panel_bg = ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"][mode_idx]
        text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode_idx]
        
        self.canvas_frame = ctk.CTkFrame(self.viewer, corner_radius=0)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew")
        
        self.canvas = tk.Canvas(self.canvas_frame, bg=canvas_bg, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.top_hud = ctk.CTkFrame(self.viewer, fg_color=panel_bg, bg_color=canvas_bg, corner_radius=8, border_width=2, border_color=["#d0d0d0", "#1A3A5A"])
        self.top_hud.place(relx=0.5, y=20, anchor="n")
        
        try:
            s_img = Image.open(resource_path("search.png"))
            self.icon_search = ctk.CTkImage(s_img, size=(16, 16))
        except Exception:
            self.icon_search = None

        search_frame = ctk.CTkFrame(self.top_hud, fg_color="transparent")
        search_frame.pack(side=tk.LEFT, padx=10, pady=5)
        
        ctk.CTkLabel(search_frame, text="Search:", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT, padx=(5, 5))
        
        self.search_var = tk.StringVar()
        self.search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, placeholder_text="Enter Sample ID or Keyword...", border_width=3, width=220)
        self.search_entry.pack(side=tk.LEFT)
        self.search_entry.bind("<Return>", lambda e: self.radar_ping())
        
        btn_text = "" if self.icon_search else "GO"
        ctk.CTkButton(search_frame, text=btn_text, image=self.icon_search, width=35, command=self.radar_ping).pack(side=tk.LEFT, padx=(5, 0))
        
        ctk.CTkFrame(self.top_hud, width=2, height=24, fg_color=["#d0d0d0", "#33424F"]).pack(side=tk.LEFT, padx=10)
        
        self.heatmap_var = ctk.BooleanVar(value=False)
        # Lock active state color to prevent default gray rendering
        self.btn_heatmap = ctk.CTkSwitch(
            self.top_hud, text="Density Heatmap", variable=self.heatmap_var, 
            command=self.toggle_heatmap, font=("Segoe UI", 12, "bold"),
            progress_color="#1ae6c5", button_color="#0E8187", button_hover_color="#2EFAD9"
        )
        self.btn_heatmap.pack(side=tk.LEFT, padx=(5, 15))

       # --- HEATMAP LEGEND ---
        self.legend_frame = ctk.CTkFrame(self.canvas_frame, fg_color=panel_bg, corner_radius=8, border_width=2, border_color=["#d0d0d0", "#1A3A5A"])
        ctk.CTkLabel(self.legend_frame, text="Sample Density", font=("Segoe UI", 12, "bold")).pack(pady=(5, 0))
        
        self.gradient_canvas = tk.Canvas(self.legend_frame, width=200, height=35, bg=panel_bg, highlightthickness=0)
        self.gradient_canvas.pack(padx=10, pady=(0, 5))
        
        # Draw 7-Stop Meteorological Gradient (Ending in Pure Bright Red)
        def interpolate(color1, color2, t):
            return tuple(int(c1 + (c2 - c1) * t) for c1, c2 in zip(color1, color2))
            
        stops = [(20, 20, 80), (30, 100, 200), (0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 128, 0), (255, 0, 0)]
        for i in range(200):
            t = i / 199.0
            idx = min(5, int(t * 6))
            t_local = (t - (idx / 6.0)) * 6.0
            r, g, b = interpolate(stops[idx], stops[idx+1], t_local)
            self.gradient_canvas.create_line(i, 0, i, 15, fill=f"#{r:02x}{g:02x}{b:02x}")
            
        self.legend_min = self.gradient_canvas.create_text(5, 25, text="0", fill=text_color, font=("Segoe UI", 10, "bold"), anchor="w")
        self.legend_mid = self.gradient_canvas.create_text(100, 25, text="5", fill=text_color, font=("Segoe UI", 10, "bold"), anchor="center")
        self.legend_max = self.gradient_canvas.create_text(195, 25, text="10", fill=text_color, font=("Segoe UI", 10, "bold"), anchor="e")

        self.static_hud = ctk.CTkFrame(self.viewer, fg_color=canvas_bg, bg_color=canvas_bg, corner_radius=8)
        self.static_hud.place(x=20, rely=1.0, y=-20, anchor="sw")
        
        self.btn_pending = ctk.CTkButton(self.static_hud, text="Verification Queue", fg_color="#06B6D4", hover_color="#2EFAD9", text_color="#051728", font=("Segoe UI", 13, "bold"), height=40, corner_radius=6, command=lambda: self.open_bottom_sheet("verification queue"))
        self.btn_pending.pack(pady=(0, 10), fill=tk.X)
        
        self.btn_other_locs = ctk.CTkButton(self.static_hud, text="Other Locations", fg_color="#33424F", font=("Segoe UI", 13, "bold"), height=40, corner_radius=6, command=lambda: self.open_bottom_sheet("OTHER"))
        self.btn_other_locs.pack(fill=tk.X)

        self.bottom_sheet = ctk.CTkFrame(self.viewer, height=2000, corner_radius=0, fg_color=canvas_bg, border_width=2, border_color=["#d0d0d0", "#1A3A5A"])
        self.bottom_sheet.pack_propagate(False)
        self.bottom_sheet.place(relx=0, y=self.sheet_target_y, relwidth=1.0)
        
        self.drag_handle = ctk.CTkFrame(self.bottom_sheet, height=12, fg_color=["#d0d0d0", "#1A3A5A"], corner_radius=0, cursor="sb_v_double_arrow")
        self.drag_handle.pack(fill=tk.X)
        self.drag_handle.bind("<ButtonPress-1>", self.start_sheet_resize)
        self.drag_handle.bind("<B1-Motion>", self.do_sheet_resize)
        
        sheet_header = ctk.CTkFrame(self.bottom_sheet, fg_color=panel_bg, corner_radius=0)
        sheet_header.pack(fill=tk.X)
        
        self.sheet_title = ctk.CTkLabel(sheet_header, text="Zone Details", font=("Segoe UI", 20, "bold"))
        self.sheet_title.pack(side=tk.LEFT, padx=20, pady=10)
        
        ctk.CTkButton(sheet_header, text="X", width=30, height=30, fg_color="#d9534f", hover_color="#ff474c", text_color="white", font=("Segoe UI", 14, "bold"), command=self.close_bottom_sheet).pack(side=tk.RIGHT, padx=10)

        style = ttk.Style(self.viewer)
        style.theme_use("default")
        
        selected_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"][mode_idx]

        style.configure("Map.Treeview", background=canvas_bg, foreground=text_color, rowheight=28, fieldbackground=canvas_bg, borderwidth=0, font=("Segoe UI", 10))
        style.map('Map.Treeview', background=[('selected', selected_color)], foreground=[('selected', '#FFFFFF')])
        style.configure("Map.Treeview.Heading", background=panel_bg, foreground=text_color, relief="flat", font=("Segoe UI", 11, "bold"))

        columns = ("Date", "Time", "Location", "Sample ID", "Requestor", "Project Number", "User")
        self.tree = ttk.Treeview(self.bottom_sheet, columns=columns, show="headings", style="Map.Treeview")
        for col in columns: self.tree.heading(col, text=col)
        
        self.tree.column("Date", width=95, anchor=tk.CENTER)
        self.tree.column("Time", width=75, anchor=tk.CENTER)
        self.tree.column("Location", width=220, anchor=tk.CENTER)
        self.tree.column("Sample ID", width=120, anchor=tk.CENTER)
        self.tree.column("Requestor", width=140, anchor=tk.CENTER)
        self.tree.column("Project Number", width=120, anchor=tk.CENTER) 
        self.tree.column("User", width=110, anchor=tk.CENTER)

        scrollbar = ctk.CTkScrollbar(self.bottom_sheet, orientation="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 20), padx=(0, 10))
        self.tree.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))
        
        self.tree.tag_configure('system', foreground=["#10B981", "#09ce66"][mode_idx])  
        self.tree.tag_configure('pending', foreground=['#06B6D4', '#2EFAD9'][mode_idx]) 
        self.tree.tag_configure('overdue', foreground=['#8B5CF6', '#a78bfa'][mode_idx]) 
        self.tree.tag_configure('removed', foreground=['#EF4444', '#ff6b6b'][mode_idx]) 

    def _bind_events(self):
        self.canvas.bind("<Control-MouseWheel>", self.handle_zoom)
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.do_pan)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.do_pan)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.viewer.bind("<Configure>", self._handle_resize)

    def _handle_resize(self, event):
        if event.widget == self.viewer:
            self._refresh_image_cache()
            if self.sheet_is_open:
                self.sheet_target_y = self.viewer.winfo_height() - self.sheet_height
            else:
                self.sheet_target_y = 5000
            self.bottom_sheet.place(y=self.sheet_target_y)
            self.sheet_current_y = self.sheet_target_y

    def start_sheet_resize(self, event):
        self._resize_start_y = event.y_root
        self._resize_start_sheet_y = self.sheet_target_y

    def do_sheet_resize(self, event):
        dy = event.y_root - self._resize_start_y
        new_y = self._resize_start_sheet_y + dy
        
        min_y = self.viewer.winfo_height() * 0.15 
        max_y = self.viewer.winfo_height() - 100  
        new_y = max(min_y, min(new_y, max_y))
        
        self.sheet_height = self.viewer.winfo_height() - new_y
        self.sheet_target_y = new_y
        self.sheet_current_y = new_y
        self.bottom_sheet.place(y=new_y)

    def radar_ping(self):
        target = self.search_var.get().strip().lower()
        if not target: return
        
        for z in self.zones: z['pinged'] = False
        
        found_loc = None
        for loc, items in self.inventory_map.items():
            for row in items:
                if len(row) > 3 and target in str(row[3]).lower():
                    found_loc = loc
                    break
                elif any(target in str(cell).lower() for cell in row):
                    found_loc = loc
            if found_loc: break
            
        if found_loc:
            for i, z in enumerate(self.zones):
                if z['name'].lower() == found_loc:
                    self.jump_to_zone(i)
                    self._flash_zone(i, 7) 
                    self.search_var.set("") 
                    return
            
            if "verification" in found_loc or "pending" in found_loc:
                self.open_bottom_sheet("verification queue")
                self.notify(f"Found in Verification Queue:\n{target.upper()}")
                self.search_var.set("")
                return
            
            self.open_bottom_sheet("OTHER")
            self.notify(f"Found in Unmapped Locations:\n{target.upper()}")
            self.search_var.set("")
        else:
            self.notify(f"Not found in active inventory:\n{target}")
            
    def _flash_zone(self, index, flashes):
        if flashes <= 0:
            self.zones[index]['pinged'] = False
            self.render_canvas()
            return
            
        self.zones[index]['pinged'] = (flashes % 2 != 0)
        self.render_canvas()
        self.viewer.after(250, lambda: self._flash_zone(index, flashes - 1))

    def _get_visual_center(self, vertices):
        """Fallback for older maps missing custom label configuration"""
        if not vertices: return 0, 0
        min_x = min(x for x, y in vertices)
        max_x = max(x for x, y in vertices)
        min_y = min(y for x, y in vertices)
        max_y = max(y for x, y in vertices)
        
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        return cx, cy

    def _load_local_map(self):
        self.viewer.update_idletasks()
        c_width = self.canvas.winfo_width()
        c_height = self.canvas.winfo_height()
        
        if c_width <= 10 or c_height <= 10:
            self.viewer.after(100, self._load_local_map)
            return
            
        json_path = os.path.join(self.local_map_dir, "map.json")
        img_path = os.path.join(self.local_map_dir, "map.png")
        
        if not os.path.exists(json_path) or not os.path.exists(img_path):
            self.canvas.create_text(
                c_width/2, c_height/2, 
                text="No Map Configuration Found.\nPlease use the Server's Map Creator to generate the map.", 
                fill="#666666", font=("Segoe UI", 16, "italic")
            )
            return
            
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.image_path = img_path
            self.original_image = Image.open(img_path).convert("RGBA")
            self.zones = data.get("zones", [])
            for z in self.zones: z['hovered'] = False
            self._build_data_bridge()
            
            scale_w = c_width / self.original_image.width
            scale_h = c_height / self.original_image.height
            self.zoom_level = min(scale_w, scale_h) * 0.95
            
            self.pan_x = (c_width - (self.original_image.width * self.zoom_level)) / 2
            self.pan_y = (c_height - (self.original_image.height * self.zoom_level)) / 2
            
            self.text_image_cache.clear()
            self._refresh_image_cache()
        except Exception as e:
            self.notify(f"Map Load Error:\n{e}")

    def jump_to_zone(self, index):
        if not self.original_image: return
        zone = self.zones[index]
        
        if 'label' in zone:
            cx, cy = zone['label']['x'], zone['label']['y']
        else:
            cx, cy = self._get_visual_center(zone['vertices'])
            
        c_width = self.canvas.winfo_width()
        c_height = self.canvas.winfo_height()
        
        self.pan_x = (c_width / 2) - (cx * self.zoom_level)
        self.pan_y = (c_height / 2) - (cy * self.zoom_level)
        
        self.open_bottom_sheet(zone['name'])
        self._refresh_image_cache()

    def open_bottom_sheet(self, zone_name):
        self.active_zone_name = zone_name
        
        if zone_name == "OTHER":
            self.sheet_title.configure(text=f"Samples in Unmapped Locations")
        elif zone_name.lower() == "verification queue":
            self.sheet_title.configure(text=f"Verification Queue")
        else:
            self.sheet_title.configure(text=f"Inventory: {zone_name}")
            
        self._populate_treeview(zone_name)
        
        if not self.sheet_is_open:
            self.sheet_target_y = self.viewer.winfo_height() - self.sheet_height
            self.sheet_is_open = True
            
            if self.sheet_current_y > self.viewer.winfo_height():
                self.sheet_current_y = self.viewer.winfo_height()
                
            self._animate_sheet()

    def close_bottom_sheet(self):
        self.sheet_target_y = self.viewer.winfo_height() + 50
        if self.sheet_is_open:
            self.sheet_is_open = False
            self._animate_sheet()

    def _animate_sheet(self):
        if not self.viewer.winfo_exists(): return
        
        self.sheet_current_y += (self.sheet_target_y - self.sheet_current_y) * 0.15
        self.bottom_sheet.place(y=int(self.sheet_current_y))
        
        if abs(self.sheet_current_y - self.sheet_target_y) > 1.0:
            self.viewer.after(8, self._animate_sheet)
        else:
            self.bottom_sheet.place(y=self.sheet_target_y) 

    def _populate_treeview(self, zone_name):
        self.tree.delete(*self.tree.get_children())
        
        zone_lower = zone_name.lower()
        rows_to_show = []
        
        if zone_name == "OTHER":
            drawn_zone_names = {z['name'].lower() for z in self.zones}
            for loc, items in self.inventory_map.items():
                if loc not in drawn_zone_names and "verification" not in loc:
                    rows_to_show.extend(items)
        elif zone_lower in self.inventory_map:
            rows_to_show = self.inventory_map[zone_lower]
            
        now = datetime.now()
            
        for row in rows_to_show:
            loc_lower = str(row[2]).lower()
            
            is_old = False
            raw_date_str = str(row[0]).strip()[:10]
            try:
                if "." in raw_date_str: row_date = datetime.strptime(raw_date_str, "%d.%m.%Y")
                elif "-" in raw_date_str and len(raw_date_str) > 2 and raw_date_str[2] == "-": row_date = datetime.strptime(raw_date_str, "%d-%m-%Y")
                else: row_date = datetime.strptime(raw_date_str, "%Y-%m-%d")
                
                if (now - row_date).days >= 14:
                    is_old = True
            except Exception: pass
            
            row_tags = ()
            if 'closed' in loc_lower or 'removed' in loc_lower: row_tags = ('removed',)
            elif 'system' in loc_lower: row_tags = ('system',)
            elif is_old: row_tags = ('overdue',)
            elif 'verification' in loc_lower or 'pending' in loc_lower: row_tags = ('pending',)
            
            display_row = [row[0], row[1], row[2], row[3], row[4], row[6], row[7]] if len(row) >= 8 else row
            self.tree.insert("", tk.END, values=display_row, tags=row_tags)

    def on_mouse_move(self, event):
        if not self.original_image: return
        img_x, img_y = self.screen_to_image(event.x, event.y)
        
        hover_changed = False
        for zone in self.zones:
            inside = False
            pts = zone['vertices']
            j = len(pts) - 1
            for i in range(len(pts)):
                if ((pts[i][1] > img_y) != (pts[j][1] > img_y)) and \
                   (img_x < (pts[j][0] - pts[i][0]) * (img_y - pts[i][1]) / (pts[j][1] - pts[i][1]) + pts[i][0]):
                    inside = not inside
                j = i
            
            if zone.get('hovered', False) != inside:
                zone['hovered'] = inside
                hover_changed = True
                
        if hover_changed:
            self.render_canvas()
            if any(z.get('hovered') for z in self.zones):
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.config(cursor="")

    def on_canvas_click(self, event):
        self.start_pan(event)
        
        clicked_zone = None
        for zone in self.zones:
            if zone.get('hovered', False):
                clicked_zone = zone['name']
                break
                
        if clicked_zone:
            self.open_bottom_sheet(clicked_zone)
        elif self.sheet_is_open:
            self.close_bottom_sheet()

    def toggle_heatmap(self):
        if self.heatmap_var.get():
            self.legend_frame.place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")
            self._build_heatmap_image()
        else:
            self.legend_frame.place_forget()
        self._refresh_image_cache()

    def _build_heatmap_image(self):
        if not self.original_image: return

        # --- density from mapped locations ---
        counts = {z['name']: len(self.inventory_map.get(z['name'].lower(), [])) for z in self.zones}
        max_items = max(list(counts.values()) + [1])

        GAMMA = 0.4  # sqrt scaling, like your reference image (makes low counts visible)

        if hasattr(self, 'gradient_canvas'):
            # with sqrt scaling, the middle of the colour bar corresponds to max * 0.5^2
            mid_val = max(1, round(max_items * (0.5 ** (1 / GAMMA))))
            self.gradient_canvas.itemconfig(self.legend_min, text="0")
            self.gradient_canvas.itemconfig(self.legend_mid, text=str(mid_val))
            self.gradient_canvas.itemconfig(self.legend_max, text=str(max_items))

        scale = 0.5
        w, h = int(self.original_image.width * scale), int(self.original_image.height * scale)

        # --- two intensity layers: soft halo + tighter core ---
        halo = Image.new('L', (w, h), 0)
        core = Image.new('L', (w, h), 0)
        d_halo, d_core = ImageDraw.Draw(halo), ImageDraw.Draw(core)

        def shrunk(zone, cx, cy, f):
            return [((cx + (x - cx) * f) * scale, (cy + (y - cy) * f) * scale)
                    for x, y in zone['vertices']]

        # draw cold zones first so hot zones are never overwritten by them
        for zone in sorted(self.zones, key=lambda z: counts[z['name']]):
            n = counts[zone['name']]
            if n == 0:
                continue
            inten = int(((n / max_items) ** GAMMA) * 255)

            xs = [x for x, _ in zone['vertices']]; ys = [y for _, y in zone['vertices']]
            if 'label' in zone:
                cx, cy = zone['label']['x'], zone['label']['y']
            else:
                cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

            d_halo.polygon(shrunk(zone, cx, cy, 1.10), fill=int(inten * 0.55))
            d_core.polygon(shrunk(zone, cx, cy, 0.92), fill=inten)

        halo = halo.filter(ImageFilter.GaussianBlur(radius=18))
        core = core.filter(ImageFilter.GaussianBlur(radius=6.6))

        # 'lighter' = per-pixel max, so neighbouring zones don't add up into fake hot spots
        heat = ImageChops.lighter(halo, core)

        # blur lowers the peak; stretch so the hottest spot is really "max" (red)
        peak = heat.getextrema()[1]
        if peak == 0:
            self.heatmap_image = self.original_image.copy()
            return
        heat = heat.point(lambda v: min(255, int(v * 255 / peak)))

        # --- colour lookup from your 7-stop legend ---
        stops = [(20, 20, 80), (30, 100, 200), (0, 255, 255), (0, 255, 0),
                (255, 255, 0), (255, 128, 0), (255, 0, 0)]
        lut_r, lut_g, lut_b = [], [], []
        for i in range(256):
            t = i / 255.0
            idx = min(len(stops) - 2, int(t * (len(stops) - 1)))
            tl = t * (len(stops) - 1) - idx
            a, b = stops[idx], stops[idx + 1]
            lut_r.append(int(a[0] + (b[0] - a[0]) * tl))
            lut_g.append(int(a[1] + (b[1] - a[1]) * tl))
            lut_b.append(int(a[2] + (b[2] - a[2]) * tl))

        rgb = Image.merge('RGB', (heat.point(lut_r), heat.point(lut_g), heat.point(lut_b)))

        # --- alpha follows intensity: empty = fully transparent, hot = strong ---
        alpha = heat.point(lambda v: min(215, int(v * 5)))  # fades in quickly, caps at ~85%
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=2))
        overlay = rgb.convert('RGBA')
        overlay.putalpha(alpha)

        overlay_full = overlay.resize(self.original_image.size, Image.Resampling.BICUBIC)
        self.heatmap_image = Image.alpha_composite(self.original_image.copy(), overlay_full)

    def _refresh_image_cache(self):
        if not self.original_image: return
        self.viewer.update_idletasks()
        c_width = self.canvas.winfo_width()
        c_height = self.canvas.winfo_height()
        if c_width <= 10 or c_height <= 10: return

        # Determine whether to cut from the normal map or the glowing heatmap
        source_image = self.heatmap_image if self.heatmap_var.get() and hasattr(self, 'heatmap_image') else self.original_image

        left = max(0, int(-self.pan_x / self.zoom_level))
        top = max(0, int(-self.pan_y / self.zoom_level))
        right = min(source_image.width, int((c_width - self.pan_x) / self.zoom_level))
        bottom = min(source_image.height, int((c_height - self.pan_y) / self.zoom_level))

        if right > left and bottom > top:
            cropped = source_image.crop((left, top, right, bottom))
            new_width = int((right - left) * self.zoom_level)
            new_height = int((bottom - top) * self.zoom_level)

            if new_width > 0 and new_height > 0:
                self.display_image = cropped.resize((new_width, new_height), Image.Resampling.NEAREST)
                self.photo_image = ImageTk.PhotoImage(self.display_image)
                
                self.render_x = self.pan_x + (left * self.zoom_level)
                self.render_y = self.pan_y + (top * self.zoom_level)
        else:
            self.photo_image = None
            
        self.text_image_cache.clear()
        self.render_canvas()

    def handle_zoom(self, event):
        if not self.original_image: return
        self._is_zooming = True
        
        zoom_factor = 1.1 if event.delta > 0 else 0.9
        mouse_x, mouse_y = event.x, event.y
        img_x, img_y = self.screen_to_image(mouse_x, mouse_y)
        self.zoom_level *= zoom_factor
        
        if self.zoom_level < 0.05: self.zoom_level = 0.05
        
        self.pan_x = mouse_x - (img_x * self.zoom_level)
        self.pan_y = mouse_y - (img_y * self.zoom_level)
        
        if self._zoom_timer is not None:
            self.viewer.after_cancel(self._zoom_timer)
        self._zoom_timer = self.viewer.after(100, self._finalize_zoom)
        self._refresh_image_cache()

    def _finalize_zoom(self):
        self._is_zooming = False
        self._refresh_image_cache()

    def screen_to_image(self, screen_x, screen_y):
        if not self.original_image: return 0, 0
        return (screen_x - self.pan_x) / self.zoom_level, (screen_y - self.pan_y) / self.zoom_level

    def image_to_screen(self, img_x, img_y):
        if not self.original_image: return 0, 0
        return (img_x * self.zoom_level) + self.pan_x, (img_y * self.zoom_level) + self.pan_y

    def start_pan(self, event):
        self._pan_start_x = event.x
        self._pan_start_y = event.y

    def do_pan(self, event):
        self.pan_x += event.x - self._pan_start_x
        self.pan_y += event.y - self._pan_start_y
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._refresh_image_cache() 

    # Generate rotated text images for map zones
    def _get_rotated_text_image(self, index, zone_name, item_count, font_size, rotation, is_selected=False):
        cache_key = f"{index}_{item_count}_{font_size}_{rotation}_{is_selected}"
        if index in self.text_image_cache and self.text_image_cache[index].get("key") == cache_key:
            return self.text_image_cache[index]["img"]

        try:
            font = ImageFont.truetype("segoeuib.ttf", int(font_size))
        except Exception:
            font = ImageFont.load_default()

        # Wrap text logically and append item count
        wrapped_name = "\n".join(textwrap.wrap(zone_name, width=14))
        full_text = f"{wrapped_name}\n({item_count})"
        lines = full_text.split('\n')
        
        max_w = 0
        total_h = 0
        for line in lines:
            try:
                bbox = font.getbbox(line)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                max_w = max(max_w, w)
                total_h += h + 4 
            except Exception:
                max_w, total_h = 100, 50 

        pad = int(font_size * 2)
        img = Image.new('RGBA', (max_w + pad*2, total_h + pad*2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        current_y = pad
        for line in lines:
            try:
                bbox = font.getbbox(line)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                x = pad + (max_w - w) / 2
                
                # Draw stroke/outline
                shadow_col = "#f39c12" if is_selected else "#000000"
                for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1), (0, 1), (0, -1), (1, 0), (-1, 0)]:
                    draw.text((x + dx, current_y + dy), line, font=font, fill=shadow_col)
                # Main Text
                draw.text((x, current_y), line, font=font, fill="#FFFFFF")
                        
                current_y += h + 4
            except Exception: pass

        rotated = img.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
        photo = ImageTk.PhotoImage(rotated)
        
        self.text_image_cache[index] = {"key": cache_key, "img": photo}
        return photo

    def render_canvas(self):
        if not self.original_image: return
        self.canvas.delete("all")
        
        if self.photo_image:
            self.canvas.create_image(self.render_x, self.render_y, anchor=tk.NW, image=self.photo_image)
            
        if self._is_zooming: return 
        
        max_items = max([len(items) for items in self.inventory_map.values()] + [1])
        is_heatmap = self.heatmap_var.get()
        
        for i, zone in enumerate(reversed(self.zones)):
            actual_idx = len(self.zones) - 1 - i 
            
            screen_coords = []
            for ix, iy in zone['vertices']:
                sx, sy = self.image_to_screen(ix, iy)
                screen_coords.extend([sx, sy])
                
            if len(screen_coords) >= 6: 
                item_count = len(self.inventory_map.get(zone['name'].lower(), []))
                is_hovered = zone.get('hovered', False)
                is_pinged = zone.get('pinged', False)
                
                base_color = zone.get('color', "#0E8187")
                fill_color = "#1ae6c5" if is_hovered else base_color
                outline_color = "#f39c12" if is_hovered else "#2EFAD9"
                outline_width = 3 if is_hovered else 2
                
                if is_pinged:
                    fill_color, outline_color, outline_width = "#09ce66", "#ffffff", 4
                elif is_heatmap and is_hovered:
                    fill_color, outline_color, outline_width = "", "#f39c12", 3
                
                # Hide geometric polygons if Heatmap is ON (unless pinged by Radar Search or Hovered)
                if not is_heatmap or is_pinged or is_hovered:
                    self.canvas.create_polygon(screen_coords, fill=fill_color if not is_heatmap else (fill_color if is_pinged else ""), outline=outline_color, width=outline_width, stipple="gray50")
                
                # Show text normally, but in heatmap mode ONLY show on hover/ping to keep the map visually clean
                show_text = (not is_heatmap) or is_hovered or is_pinged
                
                if show_text:
                    if 'label' in zone:
                        lx, ly = self.image_to_screen(zone['label']['x'], zone['label']['y'])
                        scaled_font = zone['label']['base_font_size'] * self.zoom_level
                        
                        # Only draw if the scaled font is visible enough
                        if scaled_font > 4: 
                            txt_img = self._get_rotated_text_image(
                                actual_idx, 
                                zone['name'],
                                item_count,
                                scaled_font, 
                                zone['label']['rotation'], 
                                is_selected=(is_hovered or is_pinged)
                            )
                            self.canvas.create_image(lx, ly, anchor=tk.CENTER, image=txt_img)
                    else:
                        # Fallback for old configs without 'label'
                        min_x = min(x for x, y in screen_coords[::2])
                        max_x = max(x for x, y in screen_coords[::2])
                        min_y = min(y for x, y in screen_coords[1::2])
                        max_y = max(y for x, y in screen_coords[1::2])
                        
                        room_screen_w = max_x - min_x
                        room_screen_h = max_y - min_y
                        
                        if room_screen_w > 70 and room_screen_h > 40:
                            cx, cy = self._get_visual_center(zone['vertices'])
                            center_scr_x, center_scr_y = self.image_to_screen(cx, cy)
                            
                            dynamic_font = max(8, min(14, int(room_screen_w / 12)))
                            wrap_chars = max(8, int(room_screen_w / (dynamic_font * 0.7)))
                            
                            wrapped_name = "\n".join(textwrap.wrap(zone['name'], width=wrap_chars))
                            display_text = f"{wrapped_name}\n({item_count})"
                            
                            self.canvas.create_text(center_scr_x+1, center_scr_y+1, text=display_text, fill="#000000", font=("Segoe UI", dynamic_font, "bold"), justify="center")
                            self.canvas.create_text(center_scr_x, center_scr_y, text=display_text, fill="#FFFFFF", font=("Segoe UI", dynamic_font, "bold"), justify="center")