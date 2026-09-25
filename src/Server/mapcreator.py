import customtkinter as ctk
from customtkinter import filedialog
import tkinter as tk
import os
import json
import math
import time
import copy 
from PIL import Image, ImageTk
from ctkfontawesome import icon_to_ctkimage
import winreg

def get_app_theme():
    """Reads the LabTrackQR theme from the registry. Falls back to OS theme if standalone."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\LabTrackQR") as key:
            theme, _ = winreg.QueryValueEx(key, "Theme")
            if theme.lower() in ["light", "dark", "system"]:
                return theme.lower()
    except FileNotFoundError:
        pass
    return "system"

class MapConfigurator(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        theme_path = "BW_theme.json"
        if os.path.exists(theme_path):
            ctk.set_default_color_theme(theme_path)
        ctk.set_appearance_mode(get_app_theme())
        
        self.title("LabTrackQR - Map Config Creator")
        self.geometry("1500x900")
        self.minsize(1000, 500)
        
        icon_path = os.path.join(".", "img", "iconApp.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
        
        # --- STATE VARIABLES ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.photo_image = None
        self.render_x = 0
        self.render_y = 0
        
        self.zoom_level = 1.0
        self.scale_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._pan_start_x = 0
        self._pan_start_y = 0
        self.mm_bounds = None 
        
        self.zones = [] 
        self.active_vertices = []
        
        self.global_undo_stack = []
        self.global_redo_stack = []
        self.vertex_redo_stack = [] 
        
        self.current_mouse_x = 0
        self.current_mouse_y = 0

        self.editing_zone_index = None
        self.dragged_vertex_index = None
        self.backup_vertices = []
        
        self.draw_mode = "Polygon" 
        
        self.last_key_time = 0
        self.key_streak = 0
        self.snap_lines = (None, None)
        
        self._zoom_timer = None 
        self._is_zooming = False
        self.last_zoom_time = 0
        
        self.shift_held = False
        self.last_selected_index = None
        self.checkbox_vars = {}
        
        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1) 
        self.grid_columnconfigure(1, weight=0) 
        
        self.canvas_frame = ctk.CTkFrame(self, corner_radius=0)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew")
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.sidebar = ctk.CTkFrame(self, width=400, corner_radius=0, fg_color=["#f5f8fa", "#0B2238"])
        self.sidebar.grid(row=0, column=1, sticky="nsew")
        self.sidebar.grid_propagate(False)
        
        ctrl_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        ctrl_frame.pack(fill=tk.X, padx=15, pady=15)
        
        try:
            icon_load = icon_to_ctkimage("folder-open", fill="#FFFFFF", scale_to_width=20)
            icon_save = icon_to_ctkimage("save", fill="#FFFFFF", scale_to_width=20)
            icon_json = icon_to_ctkimage("arrow-right-to-file", fill="#FFFFFF", scale_to_width=16)
            
            icon_edit = icon_to_ctkimage("edit", fill="#FFFFFF", scale_to_width=16)
            icon_ren = icon_to_ctkimage("font", fill="#FFFFFF", scale_to_width=16)
            icon_cpy = icon_to_ctkimage("copy", fill="#FFFFFF", scale_to_width=16)
            icon_del = icon_to_ctkimage("trash", fill="#FFFFFF", scale_to_width=16)
            icon_up = icon_to_ctkimage("square-caret-up", fill="#FFFFFF", scale_to_width=16)
            icon_dn = icon_to_ctkimage("square-caret-down", fill="#FFFFFF", scale_to_width=16)
            icon_poly = icon_to_ctkimage("draw-polygon", fill="#FFFFFF", scale_to_width=16)
            icon_rect = icon_to_ctkimage("square", fill="#FFFFFF", scale_to_width=16)

            print(f"Icons Loaded!")
        except Exception as e:
            print(f"Icon Load Failed (Fallback to text only): {e}")
            icon_load = icon_save = icon_json = icon_edit = icon_ren = icon_cpy = icon_del = icon_up = icon_dn = None

        self.btn_load = ctk.CTkButton(ctrl_frame, text="Load Map PNG", image=icon_load, command=self.load_map, height=36)
        self.btn_load.pack(fill=tk.X, pady=(0, 5))
        
        self.btn_load_cfg = ctk.CTkButton(ctrl_frame, text="Import Config (.json)", image=icon_json, command=self.load_config, height=36, fg_color=["#4A5A6A", "#1F3B55"])
        self.btn_load_cfg.pack(fill=tk.X, pady=(0, 15))
        
        self.btn_save = ctk.CTkButton(ctrl_frame, text="Save Config", image=icon_save, command=self.save_config, height=36, fg_color=["#1e3b2e", "#217346"], hover_color=["#2a8f57", "#2a8f57"])
        self.btn_save.pack(fill=tk.X)
        
        # Custom Toggle Bar to support Icons
        self.mode_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        self.mode_frame.pack(fill=tk.X, pady=(15, 0))
        self.mode_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkFrame(self.sidebar, height=2, fg_color=["#d0d0d0", "#33424F"]).pack(fill=tk.X, padx=15, pady=10)

        self.btn_poly = ctk.CTkButton(self.mode_frame, text=" Polygon", image=icon_poly, fg_color="#2980b9", corner_radius=6, command=lambda: self.change_draw_mode("Polygon"))
        self.btn_poly.grid(row=0, column=0, sticky="nsew", padx=(0, 2))

        self.btn_rect = ctk.CTkButton(self.mode_frame, text=" Rectangle", image=icon_rect, fg_color="#33424F", corner_radius=6, command=lambda: self.change_draw_mode("Rectangle"))
        self.btn_rect.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        
        ctk.CTkFrame(self.sidebar, height=2, fg_color=["#d0d0d0", "#33424F"]).pack(fill=tk.X, padx=15, pady=10)
        
        action_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        action_container.pack(fill=tk.X, padx=15)
        ctk.CTkLabel(action_container, text="Zones & Actions", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        
        self.action_bar = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=40)
        self.action_bar.pack(fill=tk.X, padx=15, pady=5)
        self.action_bar.grid_propagate(False) 
        
        self.btn_act_edit = ctk.CTkButton(self.action_bar, text="Edit", image=icon_edit, width=70, fg_color="#2980b9", command=self.action_edit)
        self.btn_act_edit.pack(side=tk.LEFT, padx=2)
        
        self.btn_act_ren = ctk.CTkButton(self.action_bar, text="Rename", image=icon_ren, width=75, fg_color="#33424F", command=self.action_rename)
        self.btn_act_ren.pack(side=tk.LEFT, padx=2)
        
        self.btn_act_cpy = ctk.CTkButton(self.action_bar, text="Copy", image=icon_cpy, width=70, fg_color="#33424F", command=self.action_copy)
        self.btn_act_cpy.pack(side=tk.LEFT, padx=2)
        
        self.btn_act_del = ctk.CTkButton(self.action_bar, text="Del", image=icon_del, width=65, fg_color="#c9302c", hover_color="#a82824", command=self.delete_selected_zones)
        self.btn_act_del.pack(side=tk.LEFT, padx=2)

        layer_bar = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=36)
        layer_bar.pack(fill=tk.X, padx=15, pady=(0, 5))
        layer_bar.grid_propagate(False)
        
        self.btn_act_up = ctk.CTkButton(layer_bar, text="Layer Up", image=icon_up, width=130, fg_color="#33424F", command=lambda: self.action_move(-1))
        self.btn_act_up.pack(side=tk.LEFT, padx=2)
        self.btn_act_dn = ctk.CTkButton(layer_bar, text="Layer Down", image=icon_dn, width=130, fg_color="#33424F", command=lambda: self.action_move(1))
        self.btn_act_dn.pack(side=tk.LEFT, padx=2)

        self.zone_list = ctk.CTkScrollableFrame(self.sidebar, fg_color=["#ffffff", "#051728"])
        self.zone_list.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        inst_text = "Shift-Click or Ctrl+A to multi-select!\n\nLeft Click: Add Point / Middle Mouse: Pan\nCtrl+Scroll: Zoom / Ctrl+Z: Global Undo\n\nEdit Keybinds (Select Zones First):\nDelete: Remove | Backspace: Reset Size\nCtrl+R: Rotate | Arrows: Move | + / -: Scale"
        ctk.CTkLabel(self.sidebar, text=inst_text, font=("Segoe UI", 11, "italic"), justify="left", text_color=["#666666", "#aaaaaa"]).pack(padx=15, pady=(0, 15), anchor="w")

        self.edit_panel = ctk.CTkFrame(self.canvas_frame, fg_color=["#2980b9", "#1A5276"], corner_radius=6)
        ctk.CTkLabel(self.edit_panel, text="Editing Vertices", font=("Segoe UI", 14, "bold"), text_color="white").pack(pady=(5, 0))
        
        edit_btn_frame = ctk.CTkFrame(self.edit_panel, fg_color="transparent")
        edit_btn_frame.pack(pady=5, padx=10)
        ctk.CTkButton(edit_btn_frame, text="Save", command=self.save_edit, width=80, fg_color="#217346", hover_color="#2a8f57").pack(side="left", padx=5)
        ctk.CTkButton(edit_btn_frame, text="Cancel", command=self.cancel_edit, width=80, fg_color="#c9302c", hover_color="#a82824").pack(side="left", padx=5)

        self._update_action_bar() 

    def change_draw_mode(self, new_mode):
        self.draw_mode = new_mode
        
        # Update colors to show which is active
        if new_mode == "Polygon":
            self.btn_poly.configure(fg_color="#2980b9")
            self.btn_rect.configure(fg_color="#33424F")
        else:
            self.btn_poly.configure(fg_color="#33424F")
            self.btn_rect.configure(fg_color="#2980b9")
            
        self.cancel_edit()
        self.cancel_draw()

    def _bind_events(self):
        self.canvas.bind("<Control-MouseWheel>", self.handle_zoom)
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.do_pan)
        self.canvas.bind("<Configure>", lambda e: self._refresh_image_cache()) 

        self.canvas.bind("<ButtonRelease-1>", self.on_left_release)
        self.canvas.bind("<ButtonPress-1>", self.on_left_click)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click)
        
        self.bind("<Escape>", self.escape_action)
        self.bind("<Control-z>", self.perform_undo)
        self.bind("<Control-y>", self.perform_redo)
        
        self.bind("<Control-a>", self.select_all_zones)
        self.bind("<Control-A>", self.select_all_zones)
        self.bind_all("<KeyPress-Shift_L>", lambda e: setattr(self, 'shift_held', True))
        self.bind_all("<KeyRelease-Shift_L>", lambda e: setattr(self, 'shift_held', False))
        
        self.bind("<Delete>", self.delete_selected_zones)
        self.bind("<BackSpace>", lambda e: self.reset_zones())
        
        self.bind("<Control-r>", lambda e: self.rotate_zones("right"))
        self.bind("<Control-R>", lambda e: self.rotate_zones("left")) 
        self.bind("<Up>", lambda e: self.nudge_zones(0, -1))
        self.bind("<Down>", lambda e: self.nudge_zones(0, 1))
        self.bind("<Left>", lambda e: self.nudge_zones(-1, 0))
        self.bind("<Right>", lambda e: self.nudge_zones(1, 0))
        self.bind("<plus>", lambda e: self.scale_zones(1.01))
        self.bind("<equal>", lambda e: self.scale_zones(1.01)) 
        self.bind("<minus>", lambda e: self.scale_zones(0.99))

    def escape_action(self, event=None):
        if self.active_vertices:
            self.cancel_draw()
        else:
            self.deselect_all_zones()

    def deselect_all_zones(self):
        for i, zone in enumerate(self.zones):
            zone['selected'] = False
            if i in self.checkbox_vars:
                self.checkbox_vars[i].set(False)
        self._update_action_bar()
        self.render_canvas()

    def _update_action_bar(self):
        selected_indices = [i for i, z in enumerate(self.zones) if z.get('selected', False)]
        count = len(selected_indices)
        
        if count == 0:
            for btn in [self.btn_act_edit, self.btn_act_ren, self.btn_act_cpy, self.btn_act_del, self.btn_act_up, self.btn_act_dn]:
                btn.configure(state="disabled")
        elif count == 1:
            for btn in [self.btn_act_edit, self.btn_act_ren, self.btn_act_cpy, self.btn_act_del, self.btn_act_up, self.btn_act_dn]:
                btn.configure(state="normal")
            if len(self.zones) == 1:
                self.btn_act_up.configure(state="disabled")
                self.btn_act_dn.configure(state="disabled")
        else:
            self.btn_act_edit.configure(state="disabled")
            self.btn_act_ren.configure(state="disabled")
            self.btn_act_cpy.configure(state="normal") 
            self.btn_act_del.configure(state="normal") 
            if count == len(self.zones):
                self.btn_act_up.configure(state="disabled")
                self.btn_act_dn.configure(state="disabled")
            else:
                self.btn_act_up.configure(state="normal")
                self.btn_act_dn.configure(state="normal")

    def _get_single_selected_index(self):
        selected = [i for i, z in enumerate(self.zones) if z.get('selected', False)]
        return selected[0] if len(selected) == 1 else None

    def action_edit(self):
        idx = self._get_single_selected_index()
        if idx is not None: self.start_edit_zone(idx)

    def action_rename(self):
        idx = self._get_single_selected_index()
        if idx is not None:
            old_name = self.zones[idx]['name']
            dialog = ctk.CTkInputDialog(text=f"Rename '{old_name}' to:", title="Rename Zone")
            new_name = dialog.get_input()
            if new_name and new_name.strip():
                self.commit_state()
                self.zones[idx]['name'] = new_name.strip()
                self.update_sidebar()
                self.render_canvas()

    def action_copy(self):
        selected = [i for i, z in enumerate(self.zones) if z.get('selected', False)]
        if not selected: return
        
        self.commit_state()
        new_zones = []
        for idx in selected:
            original = self.zones[idx]
            new_zone = copy.deepcopy(original)
            new_zone['name'] = f"{original['name']} (Copy)"
            
            original['selected'] = False
            new_zone['selected'] = True
            
            offset = 20 / self.zoom_level
            new_zone['vertices'] = [(x + offset, y + offset) for x, y in new_zone['vertices']]
            new_zones.append(new_zone)
            
        self.zones.extend(new_zones)
        self.update_sidebar()
        self.render_canvas()

    def action_move(self, direction):
        selected = [i for i, z in enumerate(self.zones) if z.get('selected', False)]
        if not selected or len(selected) == len(self.zones): return
        
        self.commit_state()
        if direction == -1: 
            for idx in sorted(selected):
                if idx > 0 and not self.zones[idx-1].get('selected'):
                    self.zones[idx], self.zones[idx-1] = self.zones[idx-1], self.zones[idx]
        else: 
            for idx in sorted(selected, reverse=True):
                if idx < len(self.zones) - 1 and not self.zones[idx+1].get('selected'):
                    self.zones[idx], self.zones[idx+1] = self.zones[idx+1], self.zones[idx]
                    
        self.update_sidebar()
        self.render_canvas()

    def select_all_zones(self, event=None):
        for i, zone in enumerate(self.zones):
            zone['selected'] = True
            if i in self.checkbox_vars:
                self.checkbox_vars[i].set(True)
        self._update_action_bar()
        self.render_canvas()

    def toggle_selection(self, zone_idx, var):
        is_checked = var.get()
        if self.shift_held and self.last_selected_index is not None:
            start = min(zone_idx, self.last_selected_index)
            end = max(zone_idx, self.last_selected_index)
            
            for i in range(start, end + 1):
                self.zones[i]['selected'] = is_checked
                if i in self.checkbox_vars:
                    self.checkbox_vars[i].set(is_checked)
        else:
            self.zones[zone_idx]['selected'] = is_checked
            self.last_selected_index = zone_idx
            
        self._update_action_bar()
        self.render_canvas() 

    def commit_state(self):
        if len(self.global_undo_stack) > 50: self.global_undo_stack.pop(0) 
        self.global_undo_stack.append(copy.deepcopy(self.zones))
        self.global_redo_stack.clear()

    def perform_undo(self, event=None):
        if self.active_vertices:
            popped = self.active_vertices.pop()
            self.vertex_redo_stack.append(popped)
            self.render_canvas()
            return
            
        if self.global_undo_stack:
            self.global_redo_stack.append(copy.deepcopy(self.zones))
            self.zones = self.global_undo_stack.pop()
            self.update_sidebar()
            self.render_canvas()

    def perform_redo(self, event=None):
        if self.active_vertices and self.vertex_redo_stack:
            self.active_vertices.append(self.vertex_redo_stack.pop())
            self.render_canvas()
            return
            
        if self.global_redo_stack:
            self.global_undo_stack.append(copy.deepcopy(self.zones))
            self.zones = self.global_redo_stack.pop()
            self.update_sidebar()
            self.render_canvas()

    def _get_acceleration(self):
        now = time.time()
        if now - self.last_key_time < 0.15:
            self.key_streak += 1
        else:
            self.key_streak = 1
        self.last_key_time = now
        return min(self.key_streak, 15)

    def load_config(self):
        target_file = filedialog.askopenfilename(title="Select map.json", filetypes=[("JSON Files", "*.json")])
        if target_file and os.path.exists(target_file):
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "zones" in data:
                    self.commit_state()
                    for z in data["zones"]: 
                        z['selected'] = False
                        z['original_vertices'] = list(z['vertices']) 
                    self.zones = data["zones"]
                    self.update_sidebar()
                    self._refresh_image_cache() 

    def _get_target_zones(self):
        selected = [z for z in self.zones if z.get('selected', False)]
        return selected if selected else self.zones

    def delete_selected_zones(self, event=None):
        selected_zones = [z for z in self.zones if z.get('selected', False)]
        if not selected_zones: return
        self.commit_state()
        self.zones = [z for z in self.zones if not z.get('selected', False)]
        self.update_sidebar()
        self.render_canvas()

    def rotate_zones(self, direction):
        target_zones = self._get_target_zones()
        if not self.original_image or not target_zones: return
        
        if self.key_streak == 1: self.commit_state() 
        sum_x, sum_y, pt_count = 0, 0, 0
        for zone in target_zones:
            for x, y in zone['vertices']:
                sum_x += x
                sum_y += y
                pt_count += 1
                
        if pt_count == 0: return
        cx, cy = sum_x / pt_count, sum_y / pt_count
        
        for zone in target_zones:
            new_verts = []
            for x, y in zone['vertices']:
                tx, ty = x - cx, y - cy
                if direction == "right":
                    rx, ry = -ty, tx
                else:
                    rx, ry = ty, -tx
                new_verts.append((rx + cx, ry + cy))
            zone['vertices'] = new_verts
        self.render_canvas()

    def nudge_zones(self, dx, dy):
        target_zones = self._get_target_zones()
        if not target_zones: return
        
        multiplier = self._get_acceleration() * 0.25 
        if self.key_streak == 1: self.commit_state()
        
        dx *= multiplier
        dy *= multiplier
        for zone in target_zones:
            zone['vertices'] = [(x + dx, y + dy) for x, y in zone['vertices']]
        self.render_canvas()

    def scale_zones(self, scale_factor):
        target_zones = self._get_target_zones()
        if not self.original_image or not target_zones: return
        
        multiplier = self._get_acceleration()
        if self.key_streak == 1: self.commit_state()
        
        dynamic_factor = 1.0 + ((scale_factor - 1.0) * (multiplier * 0.25))
        sum_x, sum_y, pt_count = 0, 0, 0
        for zone in target_zones:
            for x, y in zone['vertices']:
                sum_x += x
                sum_y += y
                pt_count += 1
                
        if pt_count == 0: return
        cx, cy = sum_x / pt_count, sum_y / pt_count
        
        for zone in target_zones:
            zone['vertices'] = [(((x - cx) * dynamic_factor) + cx, ((y - cy) * dynamic_factor) + cy) for x, y in zone['vertices']]
        self.render_canvas()

    def _refresh_image_cache(self):
        if not self.original_image: return
        
        self.update_idletasks()
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

    def load_map(self):
        target_file = filedialog.askopenfilename(
            title="Select Laboratory Map",
            filetypes=[("PNG Images", "*.png"), ("JPEG Images", "*.jpg;*.jpeg"), ("All Files", "*.*")]
        )
        if target_file and os.path.exists(target_file):
            self.image_path = target_file
            self.original_image = Image.open(target_file).convert("RGBA")
            self.zoom_level = 1.0
            
            self.update_idletasks()
            c_width = self.canvas.winfo_width()
            c_height = self.canvas.winfo_height()
            
            scale_w = c_width / self.original_image.width
            scale_h = c_height / self.original_image.height
            self.zoom_level = min(scale_w, scale_h) * 0.95
            
            self.pan_x = (c_width - (self.original_image.width * self.zoom_level)) / 2
            self.pan_y = (c_height - (self.original_image.height * self.zoom_level)) / 2
            
            self._refresh_image_cache()

    def handle_zoom(self, event):
        if not self.original_image: return
        
        # --- THE FIX: Culling engine for 144 FPS Zero-Lag zooming ---
        self._is_zooming = True
        
        zoom_factor = 1.1 if event.delta > 0 else 0.9
        mouse_x, mouse_y = event.x, event.y
        img_x, img_y = self.screen_to_image(mouse_x, mouse_y)
        self.zoom_level *= zoom_factor
        
        if self.zoom_level < 0.05: self.zoom_level = 0.05
        
        self.pan_x = mouse_x - (img_x * self.zoom_level)
        self.pan_y = mouse_y - (img_y * self.zoom_level)
        
        if self._zoom_timer is not None:
            self.after_cancel(self._zoom_timer)
        self._zoom_timer = self.after(150, self._finalize_zoom)
        
        now = time.time()
        if now - self.last_zoom_time > 0.03: 
            self.last_zoom_time = now
            self._refresh_image_cache()
        else:
            self.render_canvas()

    def _finalize_zoom(self):
        self._is_zooming = False
        self._refresh_image_cache()

    def screen_to_image(self, screen_x, screen_y):
        if not self.original_image: return 0, 0
        img_x = (screen_x - self.pan_x) / self.zoom_level
        img_y = (screen_y - self.pan_y) / self.zoom_level
        return img_x, img_y

    def image_to_screen(self, img_x, img_y):
        if not self.original_image: return 0, 0
        screen_x = (img_x * self.zoom_level) + self.pan_x
        screen_y = (img_y * self.zoom_level) + self.pan_y
        return screen_x, screen_y

    def set_hover(self, zone, state):
        zone['hovered'] = state
        self.render_canvas()

    def start_edit_zone(self, index):
        self.cancel_draw() 
        self.editing_zone_index = index
        self.backup_vertices = list(self.zones[index]['vertices'])
        self.edit_panel.place(relx=0.5, rely=0.05, anchor="n") 
        self.render_canvas()

    def save_edit(self):
        if not self._is_valid_polygon(self.zones[self.editing_zone_index]['vertices']):
            self.canvas.create_text(self.canvas.winfo_width()/2, 50, text="Invalid Shape (Intersecting Lines)", fill="#ff6b6b", font=("Segoe UI", 14, "bold"))
            return
            
        self.commit_state()
        self.editing_zone_index = None
        self.edit_panel.place_forget()
        self.update_sidebar()
        self.render_canvas()

    def cancel_edit(self):
        if self.editing_zone_index is not None:
            self.zones[self.editing_zone_index]['vertices'] = self.backup_vertices
            self.editing_zone_index = None
            self.edit_panel.place_forget()
            self.render_canvas()

    def start_pan(self, event):
        self._pan_start_x = event.x
        self._pan_start_y = event.y

    def do_pan(self, event):
        dx = event.x - self._pan_start_x
        dy = event.y - self._pan_start_y
        self.pan_x += dx
        self.pan_y += dy
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._refresh_image_cache() 

    def render_canvas(self):
        if not self.original_image: return
        self.canvas.delete("all")
        
        if self.photo_image:
            self.canvas.create_image(self.render_x, self.render_y, anchor=tk.NW, image=self.photo_image)
            
        self._render_zones()
        self._render_active_drawing()
        self._render_minimap()

    def _ccw(self, A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    def _lines_intersect(self, A, B, C, D):
        return self._ccw(A, C, D) != self._ccw(B, C, D) and self._ccw(A, B, C) != self._ccw(A, B, D)

    def _is_valid_polygon(self, vertices):
        if len(vertices) < 3: return True
        pts = vertices + [vertices[0]]
        for i in range(len(pts) - 1):
            for j in range(i + 2, len(pts) - 1):
                if i == 0 and j == len(pts) - 2: continue 
                if self._lines_intersect(pts[i], pts[i+1], pts[j], pts[j+1]):
                    return False
        return True

    def reset_zones(self):
        self.commit_state()
        target_zones = self._get_target_zones()
        for zone in target_zones:
            if 'original_vertices' in zone:
                zone['vertices'] = list(zone['original_vertices'])
        self.render_canvas()
        
    def _apply_smart_snap(self, img_x, img_y):
        snap_threshold_img = 10 / self.zoom_level
        snapped_x, snapped_y = img_x, img_y
        snap_line_x, snap_line_y = None, None

        if self.active_vertices:
            for vx, vy in self.active_vertices:
                if abs(img_x - vx) < snap_threshold_img:
                    snapped_x = vx
                    snap_line_x = vx
                if abs(img_y - vy) < snap_threshold_img:
                    snapped_y = vy
                    snap_line_y = vy
                    
        return snapped_x, snapped_y, snap_line_x, snap_line_y

    def _render_active_drawing(self):
        if self.editing_zone_index is not None or self._is_zooming: return
        
        # --- THE FIX: High Visibility First-Vertex Crosshair ---
        if not self.active_vertices: 
            if self.current_mouse_x and self.current_mouse_y and self.original_image:
                cx, cy = self.current_mouse_x, self.current_mouse_y
                self.canvas.create_line(cx-15, cy, cx+15, cy, fill="#ff6b6b", width=2)
                self.canvas.create_line(cx, cy-15, cx, cy+15, fill="#ff6b6b", width=2)
                self.canvas.create_oval(cx-6, cy-6, cx+6, cy+6, outline="#2EFAD9", width=2)
            return
        
        draw_color = "#ff6b6b" if self.draw_mode == "Polygon" else "#f39c12"
        screen_coords = []
        
        for ix, iy in self.active_vertices:
            sx, sy = self.image_to_screen(ix, iy)
            screen_coords.extend([sx, sy])
            self.canvas.create_oval(sx-4, sy-4, sx+4, sy+4, fill=draw_color, outline="white", width=1)
            
        if self.draw_mode == "Polygon":
            if len(screen_coords) >= 4:
                self.canvas.create_line(screen_coords, fill=draw_color, width=3)
            if len(screen_coords) >= 2:
                last_x, last_y = screen_coords[-2], screen_coords[-1]
                self.canvas.create_line(last_x, last_y, self.current_mouse_x, self.current_mouse_y, fill=draw_color, width=2, dash=(4, 4))
                
            sx, sy = self.snap_lines
            if sx is not None:
                scr_x, _ = self.image_to_screen(sx, 0)
                self.canvas.create_line(scr_x, 0, scr_x, self.canvas.winfo_height(), fill="#2EFAD9", width=2)
            if sy is not None:
                _, scr_y = self.image_to_screen(0, sy)
                self.canvas.create_line(0, scr_y, self.canvas.winfo_width(), scr_y, fill="#2EFAD9", width=2)
                
            if sx is not None or sy is not None:
                target_x = sx if sx is not None else self.screen_to_image(self.current_mouse_x, 0)[0]
                target_y = sy if sy is not None else self.screen_to_image(0, self.current_mouse_y)[1]
                scr_tgt_x, scr_tgt_y = self.image_to_screen(target_x, target_y)
                self.canvas.create_oval(scr_tgt_x-10, scr_tgt_y-10, scr_tgt_x+10, scr_tgt_y+10, outline="#2EFAD9", width=3)
                
        elif self.draw_mode == "Rectangle":
            if len(screen_coords) >= 2:
                start_x, start_y = screen_coords[0], screen_coords[1]
                self.canvas.create_rectangle(start_x, start_y, self.current_mouse_x, self.current_mouse_y, outline=draw_color, width=2, dash=(4, 4))

    def _render_minimap(self):
        if not self.original_image: return
        
        c_width = self.canvas.winfo_width()
        c_height = self.canvas.winfo_height()
        img_w_scaled = self.original_image.width * self.zoom_level
        img_h_scaled = self.original_image.height * self.zoom_level
        
        if img_w_scaled <= c_width and img_h_scaled <= c_height:
            self.mm_bounds = None 
            return 
            
        mm_size = 200
        padding = 20
        ratio = mm_size / max(self.original_image.width, self.original_image.height)
        
        mm_w = self.original_image.width * ratio
        mm_h = self.original_image.height * ratio
        mm_x_start = c_width - mm_w - padding
        mm_y_start = c_height - mm_h - padding
        
        self.mm_bounds = (mm_x_start, mm_y_start, mm_x_start + mm_w, mm_y_start + mm_h)
        
        if not hasattr(self, 'mm_image') or self.mm_image is None:
            self.mm_image = self.original_image.resize((int(mm_w), int(mm_h)), Image.Resampling.NEAREST)
            self.mm_photo = ImageTk.PhotoImage(self.mm_image)
            
        self.canvas.create_image(mm_x_start, mm_y_start, anchor=tk.NW, image=self.mm_photo)
        self.canvas.create_rectangle(mm_x_start, mm_y_start, mm_x_start + mm_w, mm_y_start + mm_h, outline="#2EFAD9", width=2)
        
        vp_left = max(0, -self.pan_x / img_w_scaled)
        vp_top = max(0, -self.pan_y / img_h_scaled)
        vp_right = min(1.0, (c_width - self.pan_x) / img_w_scaled)
        vp_bottom = min(1.0, (c_height - self.pan_y) / img_h_scaled)
        
        box_x1 = mm_x_start + (vp_left * mm_w)
        box_y1 = mm_y_start + (vp_top * mm_h)
        box_x2 = mm_x_start + (vp_right * mm_w)
        box_y2 = mm_y_start + (vp_bottom * mm_h)
        
        self.canvas.create_rectangle(box_x1, box_y1, box_x2, box_y2, outline="#09ce66", fill="#09ce66", stipple="gray25", width=2)

    def on_mouse_move(self, event):
        self.current_mouse_x = event.x
        self.current_mouse_y = event.y
        self.snap_lines = (None, None)
        
        if self.editing_zone_index is not None and self.dragged_vertex_index is not None:
            img_x, img_y = self.screen_to_image(event.x, event.y)
            
            if event.state & 0x0001: 
                zone = self.zones[self.editing_zone_index]
                prev_idx = self.dragged_vertex_index - 1
                if prev_idx < 0: prev_idx = len(zone['vertices']) - 1 
                if prev_idx != self.dragged_vertex_index: 
                    last_x, last_y = zone['vertices'][prev_idx]
                    img_x, img_y = self._calculate_shift_lock(last_x, last_y, img_x, img_y)
            
            self.zones[self.editing_zone_index]['vertices'][self.dragged_vertex_index] = (img_x, img_y)
            self.render_canvas()
            return
            
        if event.state & 0x0100: 
            if self.mm_bounds:
                x1, y1, x2, y2 = self.mm_bounds
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.jump_to_minimap(event.x, event.y, x1, y1, x2, y2)
                    return

        img_x, img_y = self.screen_to_image(event.x, event.y)
        
        if event.state & 0x0001 and self.active_vertices and self.draw_mode == "Polygon":
            last_x, last_y = self.active_vertices[-1]
            img_x, img_y = self._calculate_shift_lock(last_x, last_y, img_x, img_y)
        elif self.active_vertices and self.draw_mode == "Polygon":
            img_x, img_y, sx, sy = self._apply_smart_snap(img_x, img_y)
            self.snap_lines = (sx, sy)
            
        self.current_mouse_x, self.current_mouse_y = self.image_to_screen(img_x, img_y)
            
        if self.active_vertices or (not self.active_vertices and self.original_image):
            self.render_canvas()

    def on_left_release(self, event):
        self.dragged_vertex_index = None 
        
    def on_right_click(self, event):
        if len(self.active_vertices) > 2:
            
            if self.draw_mode == "Polygon" and not self._is_valid_polygon(self.active_vertices):
                self.canvas.create_text(self.current_mouse_x, self.current_mouse_y - 20, text="Invalid Shape (Intersecting Lines)", fill="#ff6b6b", font=("Segoe UI", 12, "bold"))
                self.after(1500, self.cancel_draw)
                return
            
            dialog = ctk.CTkInputDialog(text="Enter the exact Location Name:", title="Seal Zone")
            zone_name = dialog.get_input()
            
            if zone_name:
                self.commit_state()
                self.zones.append({
                    "name": zone_name.strip(),
                    "selected": False,
                    "vertices": list(self.active_vertices),
                    "original_vertices": list(self.active_vertices) 
                })
                self.update_sidebar()
                
        self.active_vertices.clear()
        self.vertex_redo_stack.clear()
        self.render_canvas()

    def on_left_click(self, event):
        if not self.original_image: return
        
        if self.editing_zone_index is not None:
            zone = self.zones[self.editing_zone_index]
            for i, (vx, vy) in enumerate(zone['vertices']):
                sx, sy = self.image_to_screen(vx, vy)
                if math.hypot(event.x - sx, event.y - sy) < 12:
                    self.dragged_vertex_index = i
                    return
        
        if self.mm_bounds:
            x1, y1, x2, y2 = self.mm_bounds
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.jump_to_minimap(event.x, event.y, x1, y1, x2, y2)
                return

        img_x, img_y = self.screen_to_image(event.x, event.y)
        
        if self.draw_mode == "Polygon":
            if event.state & 0x0001 and self.active_vertices: 
                last_x, last_y = self.active_vertices[-1]
                img_x, img_y = self._calculate_shift_lock(last_x, last_y, img_x, img_y)
            else:
                img_x, img_y, _, _ = self._apply_smart_snap(img_x, img_y)
                
            self.active_vertices.append((img_x, img_y))
            
        elif self.draw_mode == "Rectangle":
            if len(self.active_vertices) == 0:
                self.active_vertices.append((img_x, img_y))
            elif len(self.active_vertices) == 1:
                start_x, start_y = self.active_vertices[0]
                self.active_vertices = [
                    (start_x, start_y),
                    (img_x, start_y),
                    (img_x, img_y),
                    (start_x, img_y)
                ]
                self.on_right_click(None) 
                return

        self.vertex_redo_stack.clear()
        self.render_canvas()

    def jump_to_minimap(self, mouse_x, mouse_y, x1, y1, x2, y2):
        pct_x = (mouse_x - x1) / (x2 - x1)
        pct_y = (mouse_y - y1) / (y2 - y1)
        
        target_img_x = pct_x * self.original_image.width
        target_img_y = pct_y * self.original_image.height
        
        c_width = self.canvas.winfo_width()
        c_height = self.canvas.winfo_height()
        
        self.pan_x = (c_width / 2) - (target_img_x * self.zoom_level)
        self.pan_y = (c_height / 2) - (target_img_y * self.zoom_level)
        self._refresh_image_cache() 
        
    def cancel_draw(self, event=None):
        self.active_vertices.clear()
        self.vertex_redo_stack.clear()
        self.render_canvas()

    # --- THE FIX: True Mathematical Centroid Math for L-Shapes ---
    def _get_polygon_centroid(self, vertices):
        """Calculates area-weighted center of polygon instead of bounding box"""
        if len(vertices) < 3: return vertices[0] if vertices else (0, 0)
        
        pts = vertices + [vertices[0]]
        area, cx, cy = 0.0, 0.0, 0.0
        
        for i in range(len(vertices)):
            cross = (pts[i][0] * pts[i+1][1]) - (pts[i+1][0] * pts[i][1])
            area += cross
            cx += (pts[i][0] + pts[i+1][0]) * cross
            cy += (pts[i][1] + pts[i+1][1]) * cross
            
        area *= 0.5
        if area == 0: return vertices[0] 
        
        return cx / (6 * area), cy / (6 * area)

    def _render_zones(self):
        if self._is_zooming: return # Hide Zones entirely during active scroll!
        
        for i, zone in enumerate(reversed(self.zones)):
            actual_idx = len(self.zones) - 1 - i 
            
            screen_coords = []
            
            for ix, iy in zone['vertices']:
                sx, sy = self.image_to_screen(ix, iy)
                screen_coords.extend([sx, sy])
                
            if len(screen_coords) >= 6: 
                is_selected = zone.get('selected', False)
                is_hovered = zone.get('hovered', False)
                
                fill_color = "#1ae6c5" if is_hovered else "#0E8187"
                outline_color = "#ffffff" if is_selected else ("#f39c12" if is_hovered else "#2EFAD9")
                outline_width = 3 if (is_selected or is_hovered) else 2
                
                if self.editing_zone_index == actual_idx:
                    fill_color = "#2980b9"
                    outline_color = "#ffffff"
                    outline_width = 3
                
                self.canvas.create_polygon(screen_coords, fill=fill_color, outline=outline_color, width=outline_width, stipple="gray50")
                
                if self.editing_zone_index == actual_idx:
                    for vx, vy in zone['vertices']:
                        px, py = self.image_to_screen(vx, vy)
                        self.canvas.create_oval(px-5, py-5, px+5, py+5, fill="#2980b9", outline="white", width=2)
                
                center_img_x, center_img_y = self._get_polygon_centroid(zone['vertices'])
                center_scr_x, center_scr_y = self.image_to_screen(center_img_x, center_img_y)
                self.canvas.create_text(center_scr_x, center_scr_y, text=zone['name'], fill="#FFFFFF", font=("Segoe UI", 10, "bold"), justify="center")

    def update_sidebar(self):
        self.checkbox_vars.clear()
        for widget in self.zone_list.winfo_children():
            widget.destroy()
            
        for i, zone in enumerate(self.zones):
            row_frame = ctk.CTkFrame(self.zone_list, fg_color="transparent")
            row_frame.pack(fill=tk.X, pady=2)
            
            var = tk.BooleanVar(value=zone.get('selected', False))
            self.checkbox_vars[i] = var 
            
            chk = ctk.CTkCheckBox(row_frame, text=zone['name'], font=("Segoe UI", 13, "bold"), variable=var, command=lambda idx=i, v=var: self.toggle_selection(idx, v))
            chk.pack(side=tk.LEFT, padx=5, pady=2, anchor="w")
            
            def bind_hover(w):
                w.bind("<Enter>", lambda e, z=zone: self.set_hover(z, True))
                w.bind("<Leave>", lambda e, z=zone: self.set_hover(z, False))
                
            bind_hover(row_frame)
            bind_hover(chk)
            
        self._update_action_bar()

    def _calculate_shift_lock(self, origin_x, origin_y, target_x, target_y):
        dx = target_x - origin_x
        dy = target_y - origin_y
        
        angle = math.atan2(dy, dx)
        snapped_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
        
        distance = math.hypot(dx, dy)
        new_x = origin_x + (math.cos(snapped_angle) * distance)
        new_y = origin_y + (math.sin(snapped_angle) * distance)
        
        return new_x, new_y

    def save_config(self):
        if not self.zones: return
        
        target_file = filedialog.asksaveasfilename(
            defaultextension=".json", 
            initialfile="map.json",
            title="Save Map Configuration",
            filetypes=[("JSON Files", "*.json")]
        )
        
        if target_file:
            clean_zones = []
            for z in self.zones:
                clean_zone = {k: v for k, v in z.items() if k not in ('selected', 'hovered')}
                clean_zones.append(clean_zone)
                
            payload = {
                "image_file": os.path.basename(self.image_path) if self.image_path else "",
                "zones": clean_zones
            }
            
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)
                
            self.btn_save.configure(text=" Saved Successfully!", fg_color="#09ce66")
            self.after(2000, lambda: self.btn_save.configure(text=" Save Config", fg_color=["#1e3b2e", "#217346"]))

if __name__ == "__main__":
    app = MapConfigurator()
    app.mainloop()