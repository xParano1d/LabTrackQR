# local_storage.py
import threading
import csv
import os
from datetime import datetime
from filelock import FileLock, Timeout

class CsvStorage:
    def __init__(self, base_path="inventory.csv"):
        self.inventory_file = base_path
        self.lock_path = "database.lock"
        self.headers = ["timestamp", "location_id", "sample_id", "sample_name", "desc/notes", "user"]

    def save_data_async(self, location_id, sample_name="", desc_notes="", user="System", sample_id=None, message_queue=None):
        threading.Thread(target=self._update_databases, args=(location_id, sample_id, sample_name, desc_notes, user, message_queue), daemon=True).start()

    def _update_databases(self, location_id, sample_id, sample_name, desc_notes, user, message_queue):
        lock = FileLock(self.lock_path, timeout=5.0)
        
        try:
            with lock:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                month_str = datetime.now().strftime("%Y_%m")
                history_file = f"history_log_{month_str}.csv"
                
                inventory_data = []
                max_id = 0
                
                # 1. Read existing inventory to find max ID and map existing samples
                if os.path.exists(self.inventory_file):
                    with open(self.inventory_file, mode='r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        next(reader, None)
                        for row in reader:
                            if len(row) >= 6:
                                inventory_data.append(row)
                                try:
                                    clean_id = row[2].replace("SMP:", "").strip()
                                    current_id = int(clean_id)
                                    if current_id > max_id:
                                        max_id = current_id
                                except ValueError:
                                    pass
                                    
                # 2. Determine target sample_id
                is_new_generation = False
                if not sample_id:
                    # Generate infinite scaling ID (e.g., SMP:1, SMP:2)
                    target_sample_id = f"SMP:{max_id + 1}"
                    is_new_generation = True
                else:
                    target_sample_id = str(sample_id)
                
                updated_inventory = []
                found_existing = False
                final_sample_name = sample_name
                final_desc_notes = desc_notes
                final_user = user
                
                # 3. Update Logic
                for row in inventory_data:
                    if row[2] == target_sample_id:
                        final_sample_name = row[3]
                        final_desc_notes = row[4]
                        final_user = row[5]
                        updated_inventory.append([timestamp, location_id, row[2], final_sample_name, final_desc_notes, final_user])
                        found_existing = True
                    else:
                        updated_inventory.append(row)
                        
                # --- NEW STRICT VALIDATION BLOCK ---
                if not found_existing:
                    if not is_new_generation:
                        # ERROR: The scanner passed an ID that does not exist in the database!
                        if message_queue:
                            message_queue.put(f"Unknown Sample Error:\n{target_sample_id} not initialized!")
                        return  # Abort the save entirely and safely release the FileLock
                        
                    # If it IS a new generation from the UI button, safely append it
                    updated_inventory.append([timestamp, location_id, target_sample_id, final_sample_name, final_desc_notes, final_user])
                # -----------------------------------
                    
                final_log_row = [timestamp, location_id, target_sample_id, final_sample_name, final_desc_notes, final_user]
                
                # 4. Write back to files
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

                # 5. Send UI Notification
                if message_queue:
                    if is_new_generation:
                        message_queue.put(f"COMMAND:SHOW_CODE:{target_sample_id}")
                    else:
                        display_name = final_sample_name if final_sample_name else target_sample_id
                        loc_clean = location_id.replace('LOC:', '').strip()
                        message_queue.put(f"Moved to {loc_clean}:\n{display_name}")

        except Timeout:
            if message_queue: message_queue.put("Storage Error:\nDatabase is busy!")
        except Exception as e:
            if message_queue: message_queue.put(f"System Error:\n{str(e)}")