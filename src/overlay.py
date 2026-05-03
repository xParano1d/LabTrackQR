# overlay.py
import tkinter as tk
import time

class NotificationManager:
    # Parametr storage przekazywany z main.py
    def __init__(self, message_queue, storage=None):
        self.message_queue = message_queue
        self.storage = storage
        self.active_notifications = []
        
        # Ukryty root window
        self.root = tk.Tk()
        self.root.withdraw() 
        self.check_queue()

    def check_queue(self):
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            
            # Przechwytywanie komendy otwarcia formularza
            if msg == "COMMAND:OPEN_FORM":
                self.open_new_sample_form()
                continue
                
            lines = msg.split('\n')
            for line in lines:
                clean_line = line.strip()
                if clean_line and clean_line != "Scanned:": 
                    self.spawn_notification(clean_line)

        self.root.after(50, self.check_queue)

    def open_new_sample_form(self):
        form = tk.Toplevel(self.root)
        form.title("Ręczne wprowadzanie próbki")
        form.geometry("350x250")
        form.configure(bg="#f0f0f0")
        form.attributes("-topmost", True) # Zawsze na wierzchu
        
        # --- ZMIANA: Usuwanie domyślnej ikonki pióra ---
        # Ustawienie pustej ikonki bitmapowej usuwa domyślne pióro na Windows
        form.iconbitmap('') 
        # Alternatywa, jeśli powyższe nie działa na specyficznej konfiguracji:
        # form.wm_attributes('-toolwindow', 'True') # Zmienia styl okna na narzędziowe (bez ikony)

        # Wyśrodkowanie okna na ekranie
        form.update_idletasks()
        width = form.winfo_width()
        height = form.winfo_height()
        x = (form.winfo_screenwidth() // 2) - (width // 2)
        y = (form.winfo_screenheight() // 2) - (height // 2)
        form.geometry(f'{width}x{height}+{x}+{y}')

        # --- ZMIANY W ETYKIETACH (Labels) ---
        
        # 1. Zmieniono na: ID Próbki
        tk.Label(form, text="Sample ID", bg="#f0f0f0").pack(pady=(15, 0))
        entry_sample = tk.Entry(form, width=30)
        entry_sample.pack(pady=5)
        
        # 2. Zmieniono na: ID Lokalizacji
        tk.Label(form, text="Location ID", bg="#f0f0f0").pack(pady=(5, 0))
        entry_loc = tk.Entry(form, width=30)
        entry_loc.pack(pady=5)
        
        # 3. Zmieniono na: Notatki/Opcjonalne
        tk.Label(form, text="Notes", bg="#f0f0f0").pack(pady=(5, 0))
        entry_notes = tk.Entry(form, width=30)
        entry_notes.pack(pady=5)

        def save_manual_entry():
            sample_val = entry_sample.get().strip()
            loc_val = entry_loc.get().strip()
            notes_val = entry_notes.get().strip()
            
            if sample_val: 
                # Jeśli nie podano lokacji, używamy domyślnej
                loc_val = loc_val if loc_val else "Manual-Entry"
                
                # Zapis do CSV
                if self.storage:
                    self.storage.save_data_async(location_id=loc_val, sample_id=sample_val, notes=notes_val)
                
                # Powiadomienie o sukcesie
                self.spawn_notification(f"Dodano ręcznie:\n{sample_val}")
                form.destroy()
            else:
                # Prosta walidacja
                entry_sample.config(bg="#ffcccc")

        tk.Button(form, text="Add Item", command=save_manual_entry, bg="#011528", fg="white", width=15).pack(pady=15)

    # --- Reszta kodu bez zmian ---

    def spawn_notification(self, text):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        
        transparent_color = "#FF00FF"
        window.configure(bg=transparent_color)
        window.wm_attributes("-transparentcolor", transparent_color)
        window.attributes("-topmost", True)
        
        canvas = tk.Canvas(window, bg=transparent_color, highlightthickness=0, width=400, height=60)
        canvas.pack()
        
        self.draw_rounded_rect(canvas, 5, 5, 395, 55, radius=15, color="#011528")
        
        label = tk.Label(window, text=text, fg="#fbfcf7", bg="#011528", font=("Arial", 12, "bold"))
        label.place(relx=0.5, rely=0.5, anchor="center")
        
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
        y_pos = base_y - (len(self.active_notifications) * 70)
        
        window.geometry(f"400x60+{x_pos}+{y_pos}")
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
                y_pos = base_y - (index * 70)
                window.geometry(f"400x60+{x_pos}+{y_pos}")

    def run(self):
        self.root.mainloop()