# saving scanned data locally (for now)
import threading
from datetime import datetime

class TxtStorage:
    def __init__(self, file_path):
        self.file_path = file_path

    def save_data_async(self, zone, data):
        # Run in a background thread so it never freezes the scanner
        threading.Thread(target=self._append_to_txt, args=(zone, data), daemon=True).start()

    def _append_to_txt(self, zone, data):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] Zone: {zone} | Scanned: {data}\n")
            print(f"[Storage] Saved to TXT: {data}")
        except Exception as e:
            print(f"[Storage Error] Could not write to file: {e}")