import tkinter as tk
import time

class NotificationManager:
    def __init__(self, message_queue):
        self.message_queue = message_queue
        self.active_notifications = []
        
        # We need a hidden root window just to run the Tkinter mainloop
        self.root = tk.Tk()
        self.root.withdraw() 
        self.check_queue()

    def check_queue(self):
        # Look for new scans in the bucket
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            # Split the giant string into individual lines if it caught multiple scans
            lines = msg.split('\n')
            for line in lines:
                clean_line = line.strip()
                if clean_line and clean_line != "Scanned:": # Ignore our old prefix
                    self.spawn_notification(clean_line)

        # Re-check the bucket every 50 milliseconds
        self.root.after(50, self.check_queue)

    def spawn_notification(self, text):
        # 1. Create a new, independent floating window
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        
        # 2. Transparent background hack
        transparent_color = "#FF00FF"
        window.configure(bg=transparent_color)
        window.wm_attributes("-transparentcolor", transparent_color)
        window.attributes("-topmost", True)
        
        # 3. Canvas for the rounded pill
        canvas = tk.Canvas(window, bg=transparent_color, highlightthickness=0, width=400, height=60)
        canvas.pack()
        
        # Draw the pill shape
        self.draw_rounded_rect(canvas, 5, 5, 395, 55, radius=15, color="#011528")
        
        # 4. Add the text
        label = tk.Label(window, text=text, fg="#fbfcf7", bg="#011528", font=("Arial", 12, "bold"))
        label.place(relx=0.5, rely=0.5, anchor="center")
        
        # 5. Position Logic (Calculate where to put it based on existing popups)
        self.position_and_show(window)
        
        # 6. Set it to auto-destroy after 4 seconds
        window.after(4000, lambda: self.destroy_notification(window))

    def draw_rounded_rect(self, canvas, x1, y1, x2, y2, radius, color):
        points = [
            x1+radius, y1,  x2-radius, y1,  x2, y1,  x2, y1+radius,
            x2, y2-radius,  x2, y2,  x2-radius, y2,  x1+radius, y2,
            x1, y2,  x1, y2-radius,  x1, y1+radius,  x1, y1
        ]
        canvas.create_polygon(points, smooth=True, fill=color)

    def position_and_show(self, window):
        # Standard screen width/height check
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x_pos = screen_width - 450 # Right side of screen
        
        # Calculate Y position. Base is near the bottom.
        # Each active notification pushes the new one up by 70 pixels
        base_y = screen_height - 150
        y_pos = base_y - (len(self.active_notifications) * 70)
        
        window.geometry(f"400x60+{x_pos}+{y_pos}")
        self.active_notifications.append(window)

    def destroy_notification(self, window):
        # Remove it from the list and destroy the widget
        if window in self.active_notifications:
            self.active_notifications.remove(window)
            window.destroy()
            self.recalculate_positions()

    def recalculate_positions(self):
        # When one dies, slide all the remaining ones down
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