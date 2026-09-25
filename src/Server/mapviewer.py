import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import os
import sys
import json
import shutil
import ctypes
import winreg
from datetime import datetime
from PIL import Image, ImageTk

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
        self.viewer.title("LabTrackQR - Digital Twin Map")
        
        width, height = 1400, 850
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
        
        self.viewer.after(200, self._update_window_theme_elements)
        
        self.local_map_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR', 'MapData')
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
        self.sheet_target_y = height
        self.sheet_current_y = height
        self.sheet_is_open = False
        self.active_zone_name = None
        
        self._sync_network_map()
        self._build_ui()
        self._bind_events()
        self._build_data_bridge()
        
        self.viewer.after(100, self._load_local_map)

    def _sync_network_map(self):
        r"""Safely copies map.png and map.json from the Server Z:\ drive to LocalAppData."""
        try:
            sys.path.append(os.path.join(os.path.dirname(__file__)))
            from config import BASE_PATH
            network_dir = os.path.join(BASE_PATH, "laboratory_map")
        except Exception:
            network_dir = r"Z:\Sample Tracking Tool\laboratory_map"
            
        try:
            if not os.path.exists(network_dir): 
                self.notify("Cannot fetch map from server.\nNetwork drive unreachable.")
                return
            
            for file_name in ["map.json", "map.png"]:
                net_file = os.path.join(network_dir, file_name)
                loc_file = os.path.join(self.local_map_dir, file_name)
                
                if os.path.exists(net_file):
                    if not os.path.exists(loc_file) or os.path.getmtime(net_file) > os.path.getmtime(loc_file):
                        shutil.copy2(net_file, loc_file)
        except Exception:
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
        unmapped_count = sum(len(items) for loc, items in self.inventory_map.items() if loc not in drawn_zone_names and "verification" not in loc)
        self.btn_other_locs.configure(text=f"Other Locations ({unmapped_count})")

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
        
        self.canvas_frame = ctk.CTkFrame(self.viewer, corner_radius=0)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew")
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # --- RADAR & HEATMAP (Rebuilt to match LogViewer exact styling) ---
        self.top_hud = ctk.CTkFrame(self.canvas_frame, fg_color=ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"], corner_radius=8, border_width=2, border_color=["#d0d0d0", "#1A3A5A"])
        self.top_hud.place(relx=0.5, y=20, anchor="n")
        
        try:
            s_img = Image.open(resource_path("search.png"))
            self.icon_search = ctk.CTkImage(s_img, size=(20, 20))
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
        ctk.CTkSwitch(self.top_hud, text="Density Heatmap", variable=self.heatmap_var, command=self.render_canvas, font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=(5, 15))

        # --- STATIC ZONES (Fixed ghost background artifacts) ---
        self.static_hud = ctk.CTkFrame(self.canvas_frame, fg_color="transparent", bg_color="transparent")
        self.static_hud.place(x=20, rely=1.0, y=-20, anchor="sw")
        
        self.btn_pending = ctk.CTkButton(self.static_hud, text="Verification Queue", bg_color="transparent", fg_color="#06B6D4", hover_color="#2EFAD9", text_color="#051728", font=("Segoe UI", 13, "bold"), height=40, command=lambda: self.open_bottom_sheet("verification queue"))
        self.btn_pending.pack(pady=(0, 10), fill=tk.X)
        
        self.btn_other_locs = ctk.CTkButton(self.static_hud, text="Other Locations", bg_color="transparent", fg_color="#33424F", font=("Segoe UI", 13, "bold"), height=40, command=lambda: self.open_bottom_sheet("OTHER"))
        self.btn_other_locs.pack(fill=tk.X)

        # --- BOTTOM SHEET ---
        mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
        sheet_bg = ctk.ThemeManager.theme["CTk"]["fg_color"][mode_idx]
        header_bg = ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"][mode_idx]

        self.bottom_sheet = ctk.CTkFrame(self.viewer, height=self.sheet_height, corner_radius=0, fg_color=sheet_bg, border_width=2, border_color=["#d0d0d0", "#1A3A5A"])
        self.bottom_sheet.pack_propagate(False)
        self.bottom_sheet.place(relx=0, y=self.viewer.winfo_height(), relwidth=1.0)
        
        self.drag_handle = ctk.CTkFrame(self.bottom_sheet, height=12, fg_color=["#d0d0d0", "#1A3A5A"], corner_radius=0, cursor="sb_v_double_arrow")
        self.drag_handle.pack(fill=tk.X)
        self.drag_handle.bind("<ButtonPress-1>", self.start_sheet_resize)
        self.drag_handle.bind("<B1-Motion>", self.do_sheet_resize)
        
        sheet_header = ctk.CTkFrame(self.bottom_sheet, fg_color=header_bg, corner_radius=0)
        sheet_header.pack(fill=tk.X)
        
        self.sheet_title = ctk.CTkLabel(sheet_header, text="Zone Details", font=("Segoe UI", 20, "bold"))
        self.sheet_title.pack(side=tk.LEFT, padx=20, pady=10)
        
        ctk.CTkButton(sheet_header, text="X", width=30, height=30, fg_color="#d9534f", hover_color="#ff474c", text_color="white", font=("Segoe UI", 14, "bold"), command=self.close_bottom_sheet).pack(side=tk.RIGHT, padx=10)

        # Data Table
        style = ttk.Style(self.viewer)
        style.theme_use("default")
        
        text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode_idx]
        selected_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"][mode_idx]

        style.configure("Map.Treeview", background=sheet_bg, foreground=text_color, rowheight=28, fieldbackground=sheet_bg, borderwidth=0, font=("Segoe UI", 10))
        style.map('Map.Treeview', background=[('selected', selected_color)], foreground=[('selected', '#FFFFFF')])
        style.configure("Map.Treeview.Heading", background=header_bg, foreground=text_color, relief="flat", font=("Segoe UI", 11, "bold"))

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
                self.sheet_target_y = self.viewer.winfo_height()
            self.bottom_sheet.place(y=self.sheet_target_y)
            self.sheet_current_y = self.sheet_target_y

    def start_sheet_resize(self, event):
        self._resize_start_y = event.y_root
        self._resize_start_height = self.sheet_height

    def do_sheet_resize(self, event):
        dy = event.y_root - self._resize_start_y
        new_height = self._resize_start_height - dy
        new_height = max(200, min(new_height, self.viewer.winfo_height() - 100))
        
        self.sheet_height = new_height
        self.sheet_target_y = self.viewer.winfo_height() - self.sheet_height
        self.sheet_current_y = self.sheet_target_y
        self.bottom_sheet.configure(height=self.sheet_height)
        self.bottom_sheet.place(y=self.sheet_target_y)

    # --- THE FIX: Cleaned up Popups and Safety Checks ---
    def radar_ping(self):
        target = self.search_var.get().strip().lower()
        if not target: return
        
        # Rigorously clear any stuck pings before starting a new search
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
            # 1. Is it drawn on the map?
            for i, z in enumerate(self.zones):
                if z['name'].lower() == found_loc:
                    self.jump_to_zone(i)
                    self._flash_zone(i, 7) # Start on 7 to guarantee it ends on False
                    self.search_var.set("") 
                    return
            
            # 2. Is it in Verification Queue?
            if "verification" in found_loc or "pending" in found_loc:
                self.open_bottom_sheet("verification queue")
                self.notify(f"Item '{target.upper()}' found\nin Verification Queue.")
                self.search_var.set("")
                return
            
            # 3. Otherwise, it is an Unmapped Location
            self.open_bottom_sheet("OTHER")
            self.notify(f"Item '{target.upper()}' found\nin Unmapped Locations.")
            self.search_var.set("")
        else:
            self.notify(f"Search term '{target}'\nnot found in active inventory.")
            
    def _flash_zone(self, index, flashes):
        if flashes <= 0:
            self.zones[index]['pinged'] = False
            self.render_canvas()
            return
            
        self.zones[index]['pinged'] = (flashes % 2 != 0)
        self.render_canvas()
        self.viewer.after(250, lambda: self._flash_zone(index, flashes - 1))

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
            
            self._refresh_image_cache()
        except Exception as e:
            self.notify(f"Map Load Error:\n{e}")

    def jump_to_zone(self, index):
        if not self.original_image: return
        zone = self.zones[index]
        
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
            self._animate_sheet()

    def close_bottom_sheet(self):
        self.sheet_target_y = self.viewer.winfo_height()
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

    def _refresh_image_cache(self):
        if not self.original_image: return
        self.viewer.update_idletasks()
        c_width = self.canvas.winfo_width()
        c_height = self.canvas.winfo_height()
        if c_width <= 10 or c_height <= 10: return

        left = max(0, int(-self.pan_x / self.zoom_level))
        top = max(0, int(-self.pan_y / self.zoom_level))
        right = min(self.original_image.width, int((c_width - self.pan_x) / self.zoom_level))
        bottom = min(self.original_image.height, int((c_height - self.pan_y) / self.zoom_level))

        if right > left and bottom > top:
            cropped = self.original_image.crop((left, top, right, bottom))
            new_width = int((right - left) * self.zoom_level)
            new_height = int((bottom - top) * self.zoom_level)

            if new_width > 0 and new_height > 0:
                self.display_image = cropped.resize((new_width, new_height), Image.Resampling.NEAREST)
                self.photo_image = ImageTk.PhotoImage(self.display_image)
                
                self.render_x = self.pan_x + (left * self.zoom_level)
                self.render_y = self.pan_y + (top * self.zoom_level)
        else:
            self.photo_image = None
            
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

    # --- THE FIX: Pole of Inaccessibility (Grid Scanner) for precise L-Shape centering ---
    def _get_visual_center(self, vertices):
        if not vertices: return 0, 0
        
        min_x = min(x for x, y in vertices)
        max_x = max(x for x, y in vertices)
        min_y = min(y for x, y in vertices)
        max_y = max(y for x, y in vertices)
        
        def is_inside(x, y):
            inside = False
            j = len(vertices) - 1
            for i in range(len(vertices)):
                if ((vertices[i][1] > y) != (vertices[j][1] > y)) and \
                   (x < (vertices[j][0] - vertices[i][0]) * (y - vertices[i][1]) / (vertices[j][1] - vertices[i][1]) + vertices[i][0]):
                    inside = not inside
                j = i
            return inside

        # 1. Try mathematical centroid first
        ax = sum(x for x, y in vertices) / len(vertices)
        ay = sum(y for x, y in vertices) / len(vertices)
        
        if is_inside(ax, ay):
            return ax, ay
            
        # 2. If it falls outside (concave L-Shape), scan a grid to find the deepest internal point
        best_pt = (ax, ay)
        max_score = -1
        
        for i in range(5, 100, 10):
            for j in range(5, 100, 10):
                tx = min_x + (max_x - min_x) * (i / 100.0)
                ty = min_y + (max_y - min_y) * (j / 100.0)
                
                if is_inside(tx, ty):
                    # Favor points closer to the mathematical center to keep text naturally aligned
                    score = -abs(tx - (min_x+max_x)/2) - abs(ty - (min_y+max_y)/2)
                    if score > max_score or max_score == -1:
                        max_score = score
                        best_pt = (tx, ty)
                        
        return best_pt

    def render_canvas(self):
        if not self.original_image: return
        self.canvas.delete("all")
        
        if self.photo_image:
            self.canvas.create_image(self.render_x, self.render_y, anchor=tk.NW, image=self.photo_image)
            
        if self._is_zooming: return 
        
        max_items = max([len(items) for items in self.inventory_map.values()] + [1])
        is_heatmap = self.heatmap_var.get()
        
        # --- THE FIX: Less aggressive text scaling ---
        font_size = max(8, min(14, int(11 * self.zoom_level)))
        
        for zone in reversed(self.zones):
            screen_coords = []
            for ix, iy in zone['vertices']:
                sx, sy = self.image_to_screen(ix, iy)
                screen_coords.extend([sx, sy])
                
            if len(screen_coords) >= 6: 
                is_hovered = zone.get('hovered', False)
                is_pinged = zone.get('pinged', False)
                item_count = len(self.inventory_map.get(zone['name'].lower(), []))
                
                fill_color = "#1ae6c5" if is_hovered else "#0E8187"
                outline_color = "#f39c12" if is_hovered else "#2EFAD9"
                outline_width = 3 if is_hovered else 2
                
                if is_heatmap:
                    density = item_count / max_items
                    if item_count == 0:
                        fill_color, outline_color, outline_width = "", "#33424F", 1
                    elif density < 0.33:
                        fill_color, outline_color = "#217346", "#09ce66" 
                    elif density < 0.66:
                        fill_color, outline_color = "#d68910", "#f39c12" 
                    else:
                        fill_color, outline_color = "#a82824", "#d9534f" 
                
                if is_pinged:
                    fill_color, outline_color, outline_width = "#09ce66", "#ffffff", 4
                
                self.canvas.create_polygon(screen_coords, fill=fill_color, outline=outline_color, width=outline_width, stipple="gray50")
                
                if not is_heatmap:
                    cx, cy = self._get_visual_center(zone['vertices'])
                    center_scr_x, center_scr_y = self.image_to_screen(cx, cy)
                    
                    display_text = f"{zone['name']}\n({item_count} items)"
                    
                    self.canvas.create_text(center_scr_x+1, center_scr_y+1, text=display_text, fill="#000000", font=("Segoe UI", font_size, "bold"), justify="center")
                    self.canvas.create_text(center_scr_x, center_scr_y, text=display_text, fill="#FFFFFF", font=("Segoe UI", font_size, "bold"), justify="center")