# overlay.py
import tkinter as tk
from tkinter import PhotoImage
import sys
import os
import ctypes

# Force Windows to show the custom icon on the taskbar instead of the Python default
try:
    myappid = 'labtrack.qr.desktop.app.1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

# Bulletproof path resolver for both uncompiled Python and compiled .exe
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
    def __init__(self, message_queue, storage=None):
        self.message_queue = message_queue
        self.storage = storage
        self.active_notifications = []
        
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
                
            if isinstance(msg, str) and msg.startswith("COMMAND:SHOW_CODE:"):
                code_text = msg.replace("COMMAND:SHOW_CODE:", "")
                self.show_persistent_code_window(code_text)
                continue
                
            if isinstance(msg, str):
                clean_msg = msg.strip()
                if clean_msg:
                    self.spawn_notification(clean_msg)

        self.root.after(50, self.check_queue)

    def show_persistent_code_window(self, code_text):
        win = tk.Toplevel(self.root)
        win.title("Print Barcode")
        win.geometry("380x180")
        win.configure(bg="#ffffff")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (380 // 2)
        y = (win.winfo_screenheight() // 2) - (180 // 2)
        win.geometry(f'+{x}+{y}')

        tk.Label(win, text="Type this into the printer:", bg="#ffffff", fg="#555555", font=("Segoe UI", 11)).pack(pady=(20, 5))
        
        tk.Label(win, text=code_text, bg="#ffffff", fg="#011528", font=("Segoe UI", 32, "bold")).pack(pady=5)
        
        tk.Button(win, text="Done", command=win.destroy, bg="#011528", fg="white", font=("Segoe UI", 11, "bold"), 
                  relief="flat", activebackground="#022a52", activeforeground="white", width=20, cursor="hand2").pack(pady=15)

    def open_new_sample_form(self):
        form = tk.Toplevel(self.root)
        form.title("Manual Sample Entry")
        form.geometry("420x340")
        form.configure(bg="#ffffff") 
        form.attributes("-topmost", True) 
        form.resizable(False, False) 

        form.update_idletasks()
        width = form.winfo_width()
        height = form.winfo_height()
        x = (form.winfo_screenwidth() // 2) - (width // 2)
        y = (form.winfo_screenheight() // 2) - (height // 2)
        form.geometry(f'{width}x{height}+{x}+{y}')

        tk.Label(form, text="Sample Name", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(20, 2))
        entry_name = tk.Entry(form, width=38, justify="center", font=("Segoe UI", 11), relief="solid", bd=1)
        entry_name.pack(pady=5, ipady=4)
        
        tk.Label(form, text="Description / Notes", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        entry_notes = tk.Entry(form, width=38, justify="center", font=("Segoe UI", 11), relief="solid", bd=1)
        entry_notes.pack(pady=5, ipady=4)
        
        tk.Label(form, text="User", bg="#ffffff", fg="#333333", font=("Segoe UI", 10, "bold")).pack(pady=(10, 2))
        entry_user = tk.Entry(form, width=38, justify="center", font=("Segoe UI", 11), relief="solid", bd=1)
        entry_user.pack(pady=5, ipady=4)

        def save_manual_entry():
            name_val = entry_name.get().strip()
            notes_val = entry_notes.get().strip()
            user_val = entry_user.get().strip()
            
            if name_val: 
                if self.storage:
                    self.storage.save_data_async(
                        location_id="LOC: Manual-Entry", 
                        sample_name=name_val, 
                        desc_notes=notes_val, 
                        user=user_val if user_val else "Unknown",
                        message_queue=self.message_queue
                    )
                form.destroy()
            else:
                entry_name.config(bg="#ffcccc")

        tk.Button(form, text="Add Item", command=save_manual_entry, bg="#011528", fg="white", font=("Segoe UI", 11, "bold"), 
                  relief="flat", activebackground="#022a52", activeforeground="white", width=20, cursor="hand2").pack(pady=20)

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
        
        # Split the text to create a visual hierarchy (Subtitle + Main Value)
        lines = text.split('\n')
        
        if len(lines) == 2:
            # First line: Smaller, lighter text (Subtitle)
            tk.Label(window, text=lines[0], fg="#9db2c6", bg="#011528", font=("Segoe UI", 9, "bold")).place(relx=0.5, rely=0.32, anchor="center")
            # Second line: Larger, pure white text (Main Highlight)
            tk.Label(window, text=lines[1], fg="#ffffff", bg="#011528", font=("Segoe UI", 13, "bold")).place(relx=0.5, rely=0.65, anchor="center")
        else:
            # Fallback for single lines or 3+ lines
            tk.Label(window, text=text, fg="#ffffff", bg="#011528", font=("Segoe UI", 12, "bold"), justify="center").place(relx=0.5, rely=0.5, anchor="center")
        
        self.position_and_show(window)
        window.after(4000, lambda: self.destroy_notification(window))

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