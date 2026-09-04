import os
import csv
import json
import shutil
import time
from datetime import datetime
import threading

class CsvStorage:
    def __init__(self, inventory_file, employees_file, history_dir, sync_path=None, sync_interval=300):
        self.inventory_file = inventory_file
        self.employees_file = employees_file
        self.history_dir = history_dir
        self.sync_path = sync_path
        self.sync_interval = sync_interval

        self.recent_scans = {} # Tracks recent hashes to block duplicates
        self.lock = threading.Lock()
        self._ensure_files_exist()
        
        if self.sync_path:
            threading.Thread(target=self._network_sync_loop, daemon=True).start()

    def _ensure_files_exist(self):
        if not os.path.exists(self.inventory_file):
            with open(self.inventory_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Date", "Time", "Location", "Sample ID", "Name", "Notes", "User"])
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)

    # --- NETWORK SYNC LOGIC (Same as before) ---
    def is_server_available(self):
        if not self.sync_path: return False
        return os.path.exists(self.sync_path)

    def get_active_file_path(self, file_type):
        server_up = self.is_server_available()
        if file_type == 'inventory':
            return os.path.join(self.sync_path, "inventory.csv") if server_up else self.inventory_file
        else:
            now = datetime.now()
            year_str, month_str = now.strftime("%Y"), now.strftime("%m")
            if server_up: return os.path.join(self.sync_path, "history_logs", year_str, f"log_{month_str}.csv")
            else: return os.path.join(self.history_dir, year_str, f"log_{month_str}.csv")

    def _trigger_immediate_sync(self):
        if self.sync_path: threading.Thread(target=self._perform_sync, daemon=True).start()

    def _perform_sync(self):
        if self.is_server_available():
            try:
                os.makedirs(self.sync_path, exist_ok=True)
                shutil.copy(self.inventory_file, os.path.join(self.sync_path, "inventory.csv"))
                if os.path.exists(self.employees_file): shutil.copy(self.employees_file, os.path.join(self.sync_path, "employees.json"))
                shutil.copytree(self.history_dir, os.path.join(self.sync_path, "history_logs"), dirs_exist_ok=True)
            except Exception: pass 

    def _network_sync_loop(self):
        while True:
            time.sleep(self.sync_interval)
            self._perform_sync()

    def _log_to_history(self, location, sample_id, name, notes, user):
        now = datetime.now()
        date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
        year_str, month_str = now.strftime("%Y"), now.strftime("%m")
        
        year_dir = os.path.join(self.history_dir, year_str)
        if not os.path.exists(year_dir): os.makedirs(year_dir)
            
        history_file = os.path.join(year_dir, f"log_{month_str}.csv")
        row = [date_str, time_str, location, sample_id, name, notes, user]
        
        if not os.path.exists(history_file):
            with open(history_file, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f, delimiter=';').writerow(["Date", "Time", "Location", "Sample ID", "Name", "Notes", "User"])
        with open(history_file, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f, delimiter=';').writerow(row)

    # --- UPGRADED EMPLOYEE JSON MANAGEMENT ---
    def get_employees(self):
        with self.lock:
            try:
                if os.path.exists(self.employees_file):
                    with open(self.employees_file, 'r', encoding='utf-8') as f: return json.load(f)
            except Exception: pass
            return {}

    def get_employee_name(self, badge_id):
        emps = self.get_employees()
        if badge_id in emps:
            return emps[badge_id].get("full_name")
        return None
        
    def get_employee_by_ad(self, ad_username):
        """Looks up an employee by their Windows AD Login"""
        emps = self.get_employees()
        for b_id, data in emps.items():
            if data.get("ad_username", "").lower() == ad_username.lower():
                return data
        return None

    def add_employee(self, badge_id, first_name, last_name, ad_username=""):
        with self.lock:
            try:
                if os.path.exists(self.employees_file):
                    with open(self.employees_file, 'r', encoding='utf-8') as f: emps = json.load(f)
                else: emps = {}
            except Exception: emps = {}
                
            full_name = f"{first_name} {last_name}"
            emps[badge_id] = {
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "ad_username": ad_username
            }
            
            with open(self.employees_file, 'w', encoding='utf-8') as f:
                json.dump(emps, f, indent=4)
                
            self._log_to_history("SYSTEM: REGISTRATION", f"ID:{badge_id}", full_name, f"AD: {ad_username}", "SYSTEM")
        self._trigger_immediate_sync()

    # --- INVENTORY CSV MANAGEMENT (Same as before) ---
    def sample_exists(self, sample_id):
        with self.lock:
            try:
                with open(self.inventory_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter=';')
                    next(reader, None) 
                    for row in reader:
                        if len(row) > 3 and row[3] == sample_id: return True
            except Exception: pass
        return False

    def get_sample_name(self, sample_id):
        with self.lock:
            try:
                with open(self.inventory_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter=';')
                    next(reader, None)
                    for row in reader:
                        if len(row) >= 5 and row[3] == sample_id: return row[4]
            except Exception: pass
        return "Unknown Sample"

    def save_data_async(self, location_id, sample_id, user, message_queue, sample_name="N/A", desc_notes="N/A", force_create=False):
        threading.Thread(target=self._save_data, args=(location_id, sample_id, user, message_queue, sample_name, desc_notes, force_create), daemon=True).start()

    def _save_data(self, location_id, sample_id, user, message_queue, sample_name, desc_notes, force_create):
        sample_name = sample_name.replace('\n', ' | ').replace('\r', '')
        desc_notes = desc_notes.replace('\n', ' | ').replace('\r', '')
        
        with self.lock:
            # --- DEDUPLICATION FILTER ---
            if not hasattr(self, 'recent_scans'):
                self.recent_scans = {}
            
            scan_signature = f"{sample_id}_{user}_{location_id}"
            current_time = time.time()
            if scan_signature in self.recent_scans:
                if current_time - self.recent_scans[scan_signature] < 3.0:
                    return  # Silently discard duplicate packet received within 3 seconds
            self.recent_scans[scan_signature] = current_time
            # ----------------------------

            now = datetime.now()
            date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
            rows_to_keep = []
            found_existing = False

            try:
                with open(self.inventory_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter=';')
                    header = next(reader, None)
                    if header: rows_to_keep.append(header)
                    for r in reader:
                        if len(r) >= 6 and r[3] == sample_id:
                            found_existing = True
                            if not force_create:
                                if r[4] != "N/A": sample_name = r[4]
                                if r[5] != "N/A": desc_notes = r[5]
                            rows_to_keep.append([date_str, time_str, location_id, sample_id, sample_name, desc_notes, user])
                        else: rows_to_keep.append(r)
            except Exception: pass

            if not found_existing: rows_to_keep.append([date_str, time_str, location_id, sample_id, sample_name, desc_notes, user])

            with open(self.inventory_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerows(rows_to_keep)
                
            self._log_to_history(location_id, sample_id, sample_name, desc_notes, user)
            
            # Server might not have a message queue (API calls), so check first
            if message_queue:
                clean_loc = location_id.replace('LOC:', '').strip()
                message_queue.put(f"Saved: {sample_id}\nLocation: {clean_loc}")
            
        self._trigger_immediate_sync()

    def remove_data_async(self, sample_id, user, message_queue):
        threading.Thread(target=self._remove_data, args=(sample_id, user, message_queue), daemon=True).start()

    def _remove_data(self, sample_id, user, message_queue):
        with self.lock:
            sample_name = "Unknown Sample"
            rows_to_keep = []
            try:
                with open(self.inventory_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter=';')
                    header = next(reader, None)
                    if header: rows_to_keep.append(header)
                    for row in reader:
                        if len(row) > 3 and row[3] == sample_id: sample_name = row[4] if len(row) > 4 else "Unknown Sample"
                        else: rows_to_keep.append(row)
                            
                with open(self.inventory_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerows(rows_to_keep)
                self._log_to_history("ACTION: REMOVED", sample_id, sample_name, "Sample permanently removed", user)
            except Exception: pass
        if message_queue: message_queue.put(f"Removed: {sample_id}\nBy: {user}")
        self._trigger_immediate_sync()

    def get_inventory_data(self):
        with self.lock:
            try:
                with open(self.inventory_file, 'r', encoding='utf-8') as f: return list(csv.reader(f, delimiter=';'))[1:] 
            except: return []

    def get_available_history_months(self):
        months = []
        if os.path.exists(self.history_dir):
            for year in sorted(os.listdir(self.history_dir), reverse=True):
                year_path = os.path.join(self.history_dir, year)
                if os.path.isdir(year_path):
                    for log in sorted(os.listdir(year_path), reverse=True):
                        if log.startswith("log_") and log.endswith(".csv"):
                            months.append(f"{year}-{log.replace('log_', '').replace('.csv', '')}")
        return months

    def get_specific_history(self, year, month):
        with self.lock:
            try:
                with open(os.path.join(self.history_dir, year, f"log_{month}.csv"), 'r', encoding='utf-8') as f: return list(csv.reader(f, delimiter=';'))[1:]
            except: return []
                
    def get_all_time_history(self):
        all_data = []
        for ym in self.get_available_history_months():
            y, m = ym.split('-')
            all_data.extend(self.get_specific_history(y, m))
        return all_data