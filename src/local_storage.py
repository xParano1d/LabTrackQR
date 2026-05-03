# local_storage.py
import threading
import csv
import os
from datetime import datetime

class CsvStorage:
    def __init__(self, file_path):
        self.file_path = file_path
        self._ensure_headers()

    def _ensure_headers(self):
        # Sprawdza, czy plik istnieje. Jeśli nie, tworzy go z nagłówkami.
        if not os.path.exists(self.file_path):
            try:
                with open(self.file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Timestamp", "Location_ID", "Sample_ID", "Notes"])
            except Exception as e:
                print(f"[Storage Error] Could not create CSV headers: {e}")

    def save_data_async(self, location_id, sample_id, notes=""):
        # Uruchamiamy zapis w tle, żeby nie zablokować UI i skanera
        threading.Thread(target=self._append_to_csv, args=(location_id, sample_id, notes), daemon=True).start()

    def _append_to_csv(self, location_id, sample_id, notes):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.file_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, location_id, sample_id, notes])
            print(f"[Storage] Saved to CSV -> Loc: {location_id} | Sample: {sample_id}")
        except Exception as e:
            print(f"[Storage Error] Could not write to CSV: {e}")