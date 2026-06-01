# overlay.py
import tkinter as tk
from tkinter import PhotoImage
from tkinter import ttk
import sys
import os
import ctypes

import qrcode
from PIL import Image, ImageTk

try:
    myappid = 'labtrack.qr.desktop.app.1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
        return os.path.join(base_path, relative_path)
    except Exception:
        if os.path.exists(relative_path):
            return os.path.abspath(relative_path)
        elif os.path.exists(os.path.join("..", relative_path)):
            return os.path.abspath(os.path.join("..", relative_path))
        return os.path.abspath(relative_path)

class NotificationManager:
    def __init__(self, message_queue, storage=None, scanner_mgr=None):
        self.message_queue = message_queue
        self.storage = storage
        self.scanner_mgr = scanner_mgr
        self.active_notifications = []
        self.waiting_removal_win = None
        
        self.root = tk.Tk()
        
        try:
            icon_img = PhotoImage(file=resource_path("icon.png"))
            self.root.iconphoto(True, icon_img)
        except Exception as e:
            print(f"[UI Warning] Could not load icon.png: {e}")
            
        self.root.withdraw() 
        self.check_queue()

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
                self.open_user_manager()
                continue
                
            if isinstance(msg, str) and msg.startswith("COMMAND:CONFIRM_REMOVE:"):
                if self.waiting_removal_win and self.waiting_removal_win.winfo_exists():
                    self.waiting_removal_win.destroy()
                
                raw_payload = msg.replace("COMMAND:CONFIRM_REMOVE:", "")
                if "|" in raw_payload:
                    sample_id, action_user = raw_payload.split("|")
                else:
                    sample_id = raw_payload
                    action_user = "Unknown"
                    
                self.open_removal_confirmation(sample_id, action_user)
                continue
                
            if isinstance(msg, str):
                clean_msg = msg.strip()
                if clean_msg:
                    self.spawn_notification(clean_msg)

        self.root.after(50, self.check_queue)


    def open_user_manager(self):
        manager = tk.Toplevel(self.root)
        manager.title("Employee Management")
        manager.geometry("500x530")
        manager.configure(bg="#f4f4f4")
        manager.resizable(False, False)

        manager.update_idletasks()
        x = (manager.winfo_screenwidth() // 2) - (500 // 2)
        y = (manager.winfo_screenheight() // 2) - (530 // 2)
        manager.geometry(f'+{x}+{y}')

        tk.Label(manager, text="Employee Database (Login Codes)", bg="#f4f4f4", font=("Segoe UI", 16, "bold"), fg="#011528").pack(pady=(15, 10))
        
        sel_frame = tk.Frame(manager, bg="#f4f4f4")
        sel_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(sel_frame, text="Select Employee:", bg="#f4f4f4", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        
        users_list = self.storage.get_employees() if self.storage else []
        selected_user = tk.StringVar()
        
        combo = ttk.Combobox(sel_frame, textvariable=selected_user, values=users_list, state="readonly", font=("Segoe UI", 11), width=20)
        combo.pack(side=tk.LEFT, padx=10)
        if users_list:
            combo.current(0)
            
        qr_frame = tk.Frame(manager, bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc", width=250, height=250)
        qr_frame.pack(pady=15)
        qr_frame.pack_propagate(False)
        
        qr_label = tk.Label(qr_frame, bg="#ffffff")
        qr_label.pack(expand=True)
        
        qr_text = tk.Label(manager, text="Select an employee and click Generate", bg="#f4f4f4", font=("Segoe UI", 10, "italic"), fg="#555")
        qr_text.pack(pady=5)
        
        def generate_qr():
            user = selected_user.get()
            if not user: return
            
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(f"USR:{user}")
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            img = img.resize((230, 230), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            
            qr_label.config(image=tk_img)
            qr_label.image = tk_img 
            
            qr_text.config(text=f"QR Code for: {user}", font=("Segoe UI", 11, "bold"), fg="#011528")

        tk.Button(sel_frame, text="Show QR", command=generate_qr, bg="#011528", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10).pack(side=tk.LEFT, padx=5)

        ttk.Separator(manager, orient='horizontal').pack(fill='x', padx=20, pady=15)
        
        add_frame = tk.Frame(manager, bg="#f4f4f4")
        add_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(add_frame, text="Add New Employee:", bg="#f4f4f4", font=("Segoe UI", 11, "bold"), fg="#333").pack(anchor="w")
        
        input_frame = tk.Frame(add_frame, bg="#f4f4f4")
        input_frame.pack(fill=tk.X, pady=5)
        
        new_name_entry = tk.Entry(input_frame, font=("Segoe UI", 11), width=23, relief="solid", bd=1)
        new_name_entry.pack(side=tk.LEFT, ipady=3)
        
        def save_new_user():
            raw_name = new_name_entry.get().strip().upper()
            if raw_name:
                formatted_name = raw_name.replace(" ", "_")
                if self.storage:
                    self.storage.add_employee(formatted_name)
                    updated_users = self.storage.get_employees()
                    combo['values'] = updated_users
                    selected_user.set(formatted_name)
                    
                    new_name_entry.delete(0, tk.END)
                    generate_qr() 
                    self.spawn_notification(f"Employee Added:\n{formatted_name}")

        tk.Button(input_frame, text="Save & Show QR", command=save_new_user, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat").pack(side=tk.LEFT, padx=10)


    def open_waiting_for_removal(self):
        if self.waiting_removal_win and self.waiting_removal_win.winfo_exists():
            return
            
        win = tk.Toplevel(self.root)
        self.waiting_removal_win = win
        win.title("Removal Mode Active")
        win.geometry("400x160")
        
        win.overrideredirect(True)
        win.configure(bg="#ffffff", highlightthickness=4, highlightbackground="#d9534f")
        win.attributes("-topmost", True)
        win.resizable(False, False)

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

    def open_removal_confirmation(self, sample_id, action_user):
        win = tk.Toplevel(self.root)
        win.title("Confirm Removal")
        win.geometry("400x180")
        
        win.overrideredirect(True)
        win.configure(bg="#ffffff", highlightthickness=2, highlightbackground="#d9534f")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (400 // 2)
        y = (win.winfo_screenheight() // 2) - (180 // 2)
        win.geometry(f'+{x}+{y}')

        tk.Label(win, text="⚠️ Warning", bg="#ffffff", fg="#d9534f", font=("Segoe UI", 14, "bold")).pack(pady=(15, 5))
        tk.Label(win, text=f"Permanently remove {sample_id} from the system?", bg="#ffffff", fg="#333333", font=("Segoe UI", 11)).pack(pady=5)

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
        btn_frame.pack(pady=15)
        
        tk.Button(btn_frame, text="Confirm", command=confirm, bg="#d9534f", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=cancel, bg="#aaaaaa", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=12).pack(side=tk.LEFT, padx=10)

    def open_new_sample_form(self):
        form = tk.Toplevel(self.root)
        form.title("Manual Sample Entry")
        # Powiększono okno żeby zmieścił się wybór usera
        form.geometry("420x400")
        
        form.overrideredirect(True)
        form.configure(bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc") 
        form.resizable(False, False) 

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
        entry_notes = tk.Entry(form, width=38, justify="center", font=("Segoe UI", 11), relief="solid", bd=1)
        entry_notes.pack(pady=5, ipady=4)

        # WYBÓR PRACOWNIKA
        tk.Label(form, text="Employee / User", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        users_list = self.storage.get_employees() if self.storage else ["Admin"]
        if not users_list:
            users_list = ["Admin"]
        selected_user = tk.StringVar(value=users_list[0])
        combo_user = ttk.Combobox(form, textvariable=selected_user, values=users_list, state="readonly", font=("Segoe UI", 11), width=36)
        combo_user.pack(pady=5)

        def reset_bg(event):
            event.widget.config(bg="#ffffff")
            
        entry_id.bind("<Key>", reset_bg)
        entry_name.bind("<Key>", reset_bg)

        def save_manual_entry():
            id_raw = entry_id.get().strip()
            name_val = entry_name.get().strip()
            notes_val = entry_notes.get().strip()
            user_val = selected_user.get()
            
            if id_raw.isdigit() and name_val and user_val: 
                formatted_id = f"SMP:{id_raw}"
                if self.storage:
                    self.storage.save_data_async(
                        location_id="LOC: Manual-Entry", 
                        sample_id=formatted_id,
                        sample_name=name_val, 
                        desc_notes=notes_val, 
                        user=user_val, # Terraz bierze usera z listy!
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
        elif 'action: removed' in lower_str:
            icon = "❌"
        else:
            icon = "📍"
            
        return f"{icon} {clean_str}"

    def open_log_viewer(self):
        viewer = tk.Toplevel(self.root)
        viewer.title("System Logs & Inventory")
        viewer.geometry("900x500")
        viewer.configure(bg="#f4f4f4")

        top_frame = tk.Frame(viewer, bg="#f4f4f4")
        top_frame.pack(fill=tk.X, pady=10, padx=10)

        btn_frame = tk.Frame(top_frame, bg="#f4f4f4")
        btn_frame.pack(side=tk.LEFT)

        search_frame = tk.Frame(top_frame, bg="#f4f4f4")
        search_frame.pack(side=tk.RIGHT)

        search_var = tk.StringVar()
        tk.Label(search_frame, text="Search:", bg="#f4f4f4", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        entry_border = tk.Frame(search_frame, bg="#ffffff", highlightthickness=1, highlightbackground="#cccccc")
        entry_border.pack(side=tk.LEFT)
        search_entry = tk.Entry(entry_border, textvariable=search_var, font=("Segoe UI", 10), width=25, relief="flat", bd=0)
        search_entry.pack(side=tk.LEFT, ipady=4, padx=8)

        columns = ("Date/Day", "Time", "Location", "Sample ID", "Name", "Notes", "User")
        tree = ttk.Treeview(viewer, columns=columns, show="headings", height=15)
        
        for col in columns:
            tree.heading(col, text=col)
        tree.column("Date/Day", width=90, anchor=tk.CENTER)
        tree.column("Time", width=80, anchor=tk.CENTER)
        tree.column("Location", width=180, anchor=tk.W)
        tree.column("Sample ID", width=90, anchor=tk.CENTER)
        tree.column("Name", width=150, anchor=tk.W)
        tree.column("Notes", width=200, anchor=tk.W)
        tree.column("User", width=100, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(viewer, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        current_tab = ['inventory'] 

        def open_external_file():
            import datetime 
            if current_tab[0] == 'inventory':
                file_to_open = self.storage.inventory_file
            else:
                month_str = datetime.datetime.now().strftime("%Y_%m")
                file_to_open = f"history_log_{month_str}.csv"
            
            try:
                os.startfile(file_to_open)
            except Exception as e:
                self.spawn_notification(f"Could not open file:\n{e}")

        def load_data(source_type, search_query=""):
            current_tab[0] = source_type
            tree.delete(*tree.get_children())
            data = self.storage.get_inventory_data() if source_type == 'inventory' else self.storage.get_history_data()
            
            query = search_query.lower()
            for row in reversed(data):
                if query and not any(query in str(cell).lower() for cell in row):
                    continue
                row[2] = self._clean_and_iconify_location(str(row[2]))
                tree.insert("", tk.END, values=row)

        search_entry.bind("<KeyRelease>", lambda e: load_data(current_tab[0], search_var.get()))

        tk.Button(btn_frame, text="View Active Inventory", command=lambda: load_data('inventory', search_var.get()), bg="#011528", fg="white", font=("Segoe UI", 10), relief="flat", width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="View Current Month History", command=lambda: load_data('history', search_var.get()), bg="#555555", fg="white", font=("Segoe UI", 10), relief="flat", width=25).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Open in External Editor", command=open_external_file, bg="#217346", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", width=22).pack(side=tk.LEFT, padx=5)

        load_data('inventory')

    def spawn_notification(self, text):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        
        transparent_color = "#FF00FF"
        window.configure(bg=transparent_color)
        window.wm_attributes("-transparentcolor", transparent_color)
        window.attributes("-topmost", True)
        
        canvas = tk.Canvas(window, bg=transparent_color, highlightthickness=0, width=400, height=80)
        canvas.pack()
        
        self.draw_rounded_rect(canvas, 5, 5, 395, 75, radius=15, color="#011528")
        
        lines = text.split('\n')
        
        if len(lines) == 2:
            tk.Label(window, text=lines[0], fg="#9db2c6", bg="#011528", font=("Segoe UI", 9, "bold")).place(relx=0.5, rely=0.32, anchor="center")
            tk.Label(window, text=lines[1], fg="#ffffff", bg="#011528", font=("Segoe UI", 13, "bold")).place(relx=0.5, rely=0.65, anchor="center")
        else:
            tk.Label(window, text=text, fg="#ffffff", bg="#011528", font=("Segoe UI", 12, "bold"), justify="center").place(relx=0.5, rely=0.5, anchor="center")
        
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
        base_y = screen_height - 150
        y_pos = base_y - (len(self.active_notifications) * 90)
        
        window.geometry(f"400x80+{x_pos}+{y_pos}")
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
        base_y = screen_height - 150
        
        for index, window in enumerate(self.active_notifications):
            if window.winfo_exists():
                y_pos = base_y - (index * 90)
                window.geometry(f"400x80+{x_pos}+{y_pos}")

    def run(self):
        self.root.mainloop()