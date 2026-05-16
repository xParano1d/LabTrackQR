# local_storage.py
import threading
import csv
import os
import json
from datetime import datetime
from filelock import FileLock, Timeout
from config import USERS_DB_PATH

class CsvStorage:
    def __init__(self, base_path="inventory.csv"):
        self.inventory_file = base_path
        self.lock_path = "database.lock"
        self.users_file = USERS_DB_PATH
        self.current_user = "System"
        
        # --- NEW 7-COLUMN HEADERS ---
        self.headers = ["date_or_day", "time", "location_id", "sample_id", "sample_name", "desc/notes", "user"]
        self._ensure_users_db()

    def _ensure_users_db(self):
        """Creates the users.json file if it doesn't exist yet on the server/drive."""
        if not os.path.exists(self.users_file):
            try:
                with open(self.users_file, "w") as f:
                    json.dump({}, f)
            except Exception as e:
                print(f"[Storage Error] Could not create users DB: {e}")

    def get_user(self, hwid):
        """Looks up the scanner's hardware ID to find the owner."""
        try:
            with open(self.users_file, "r") as f:
                users = json.load(f)
                user = users.get(hwid)
                if user:
                    self.current_user = user 
                return user
        except Exception:
            return None

    def register_user(self, hwid, username):
        """Binds a scanner's hardware ID to a specific employee."""
        try:
            with open(self.users_file, "r") as f:
                users = json.load(f)
        except Exception:
            users = {}
            
        users[hwid] = username
        with open(self.users_file, "w") as f:
            json.dump(users, f, indent=4)
            
        self.current_user = username

    def _migrate_row(self, row):
        """Automatically upgrades old 6-column CSV data to the new 7-column format."""
        if len(row) == 6:
            parts = str(row[0]).split(" ")
            if len(parts) == 2:
                # Splits old "YYYY-MM-DD HH:MM:SS" into two separate columns
                return [parts[0], parts[1], row[1], row[2], row[3], row[4], row[5]]
            return [row[0], "00:00:00", row[1], row[2], row[3], row[4], row[5]]
        return row

    def save_data_async(self, location_id, sample_name="", desc_notes="", user="System", sample_id=None, message_queue=None, force_create=False):
        threading.Thread(target=self._update_databases, args=(location_id, sample_id, sample_name, desc_notes, user, message_queue, force_create), daemon=True).start()

    def _update_databases(self, location_id, sample_id, sample_name, desc_notes, user, message_queue, force_create):
        lock = FileLock(self.lock_path, timeout=5.0)
        
        try:
            with lock:
                # --- NEW TIME VARIABLES ---
                full_date = datetime.now().strftime("%Y-%m-%d")
                day_only = datetime.now().strftime("%d")
                current_time = datetime.now().strftime("%H:%M:%S")
                
                month_str = datetime.now().strftime("%Y_%m")
                history_file = f"history_log_{month_str}.csv"
                
                inventory_data = []
                target_sample_id = str(sample_id)
                
                if os.path.exists(self.inventory_file):
                    with open(self.inventory_file, mode='r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        next(reader, None)
                        for row in reader:
                            if len(row) >= 6:
                                inventory_data.append(self._migrate_row(row))
                                
                updated_inventory = []
                found_existing = False
                final_sample_name = sample_name
                final_desc_notes = desc_notes
                final_user = user
                
                for row in inventory_data:
                    if row[3] == target_sample_id: # ID is now index 3
                        final_sample_name = row[4] if not sample_name else sample_name
                        final_desc_notes = row[5] if not desc_notes else desc_notes
                        final_user = user if user != "System" else row[6]
                        
                        # Inventory keeps the full date since it has no year_month in its filename
                        updated_inventory.append([full_date, current_time, location_id, row[3], final_sample_name, final_desc_notes, final_user])
                        found_existing = True
                    else:
                        updated_inventory.append(row)
                        
                if not found_existing:
                    if not force_create:
                        if message_queue:
                            message_queue.put(f"Unknown Sample Error:\n{target_sample_id} not initialized!")
                        return 
                        
                    updated_inventory.append([full_date, current_time, location_id, target_sample_id, final_sample_name, final_desc_notes, final_user])
                    
                # History file uses ONLY the Day
                final_log_row = [day_only, current_time, location_id, target_sample_id, final_sample_name, final_desc_notes, final_user]
                
                with open(self.inventory_file, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.headers)
                    writer.writerows(updated_inventory)
                    
                history_exists = os.path.exists(history_file)
                with open(history_file, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    if not history_exists:
                        writer.writerow(self.headers)
                    writer.writerow(final_log_row)

                if message_queue:
                    display_name = final_sample_name if final_sample_name else target_sample_id
                    loc_clean = location_id.replace('LOC:', '').strip()
                    if "Manual-Entry" in loc_clean:
                        message_queue.put(f"Initialized in System:\n{display_name}")
                    else:
                        message_queue.put(f"Moved to {loc_clean}:\n{display_name}")

        except Timeout:
            if message_queue: message_queue.put("Storage Error:\nDatabase is busy!")
        except Exception as e:
            if message_queue: message_queue.put(f"System Error:\n{str(e)}")

    def remove_data_async(self, sample_id, message_queue=None):
        threading.Thread(target=self._remove_from_databases, args=(sample_id, message_queue), daemon=True).start()

    def _remove_from_databases(self, sample_id, message_queue):
        lock = FileLock(self.lock_path, timeout=5.0)
        try:
            with lock:
                day_only = datetime.now().strftime("%d")
                current_time = datetime.now().strftime("%H:%M:%S")
                month_str = datetime.now().strftime("%Y_%m")
                history_file = f"history_log_{month_str}.csv"
                
                inventory_data = []
                removed_row = None
                
                if os.path.exists(self.inventory_file):
                    with open(self.inventory_file, mode='r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        next(reader, None)
                        for row in reader:
                            if len(row) >= 6:
                                row = self._migrate_row(row)
                                if row[3] == str(sample_id): # ID is now index 3
                                    removed_row = row
                                else:
                                    inventory_data.append(row)
                                    
                if not removed_row:
                    if message_queue: message_queue.put(f"Error:\n{sample_id} not found in system!")
                    return
                    
                with open(self.inventory_file, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.headers)
                    writer.writerows(inventory_data)
                    
                # Log removal using only the Day
                final_log_row = [day_only, current_time, "ACTION: REMOVED", sample_id, removed_row[4], removed_row[5], removed_row[6]]
                history_exists = os.path.exists(history_file)
                with open(history_file, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    if not history_exists:
                        writer.writerow(self.headers)
                    writer.writerow(final_log_row)

                if message_queue:
                    message_queue.put(f"Sample Removed:\n{sample_id} deleted.")

        except Timeout:
            if message_queue: message_queue.put("Storage Error:\nDatabase is busy!")
        except Exception as e:
            if message_queue: message_queue.put(f"System Error:\n{str(e)}")

    def get_inventory_data(self):
        data = []
        if os.path.exists(self.inventory_file):
            with open(self.inventory_file, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                data = [self._migrate_row(row) for row in reader if len(row) >= 6]
        return data

    def get_history_data(self):
        month_str = datetime.now().strftime("%Y_%m")
        history_file = f"history_log_{month_str}.csv"
        data = []
        if os.path.exists(history_file):
            with open(history_file, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                data = [self._migrate_row(row) for row in reader if len(row) >= 6]
        return data