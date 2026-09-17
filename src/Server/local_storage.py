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

        self.recent_scans = {} 
        self.lock = threading.Lock()
        self._ensure_files_exist()
        
        if self.sync_path:
            threading.Thread(target=self._network_sync_loop, daemon=True).start()

    # --- DATA SCRUBBING ENGINE ---
    def _normalize_date(self, date_str):
        """Forces Excel-corrupted dates back into YYYY-MM-DD format."""
        date_str = str(date_str).strip()[:10]
        if not date_str: return date_str
        
        # If it's already perfect, skip parsing
        if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
            return date_str
            
        # If Excel mangled it, fix it!
        for fmt in ("%d.%m.%Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return date_str 

    def _scrub_file_dates(self, filepath):
        """Silently opens a CSV and corrects all corrupted dates."""
        try:
            needs_rewrite = False
            rows = []
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                header = next(reader, None)
                if header: rows.append(header)
                for r in reader:
                    if len(r) > 0:
                        original = r[0]
                        fixed = self._normalize_date(original)
                        if original != fixed:
                            needs_rewrite = True
                            r[0] = fixed
                    rows.append(r)
            if needs_rewrite:
                with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerows(rows)
        except Exception: pass
    # -----------------------------

    def _ensure_files_exist(self):
        if not os.path.exists(self.inventory_file):
            with open(self.inventory_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Date", "Time", "Location", "Sample ID", "Requestor", "Functional Dept", "Project Number", "User"])
        else:
            # Self-Heal on Startup!
            self._scrub_file_dates(self.inventory_file)
            
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)

    def is_server_available(self):
        if not self.sync_path: return False
        return os.path.exists(self.sync_path)

    def get_active_file_path(self, file_type, year=None, month=None):
        if file_type == 'inventory':
            return self.inventory_file # THE FIX: Corrected variable name!
        else:
            if year and month:
                target_year = year
                target_month = month
            else:
                now = datetime.now()
                target_year = now.strftime("%Y")
                target_month = now.strftime("%m")
                
            return os.path.join(self.history_dir, target_year, f"log_{target_month}.csv")

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

    def _log_to_history(self, location, sample_id, requestor, dept, project, user):
        now = datetime.now()
        date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
        year_str, month_str = now.strftime("%Y"), now.strftime("%m")
        
        year_dir = os.path.join(self.history_dir, year_str)
        if not os.path.exists(year_dir): os.makedirs(year_dir)
            
        history_file = os.path.join(year_dir, f"log_{month_str}.csv")
        location = location.replace('LOC:', '').replace('LOC-', '').strip()
        
        row = [date_str, time_str, location, sample_id, requestor, dept, project, user]
        
        if not os.path.exists(history_file):
            with open(history_file, 'w', newline='', encoding='utf-8-sig') as f:
                csv.writer(f, delimiter=';').writerow(["Date", "Time", "Location", "Sample ID", "Requestor", "Functional Dept", "Project Number", "User"])
        with open(history_file, 'a', newline='', encoding='utf-8-sig') as f:
            csv.writer(f, delimiter=';').writerow(row)

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
                
            self._log_to_history("SYSTEM: REGISTRATION", f"ID:{badge_id}", full_name, f"AD: {ad_username}", "SYSTEM LOG", "SYSTEM")
        self._trigger_immediate_sync()

    def delete_employee(self, badge_id):
        with self.lock:
            try:
                if os.path.exists(self.employees_file):
                    with open(self.employees_file, 'r', encoding='utf-8') as f: 
                        emps = json.load(f)
                    
                    if badge_id in emps:
                        deleted_name = emps[badge_id].get("full_name", "Unknown")
                        del emps[badge_id]
                        
                        with open(self.employees_file, 'w', encoding='utf-8') as f: 
                            json.dump(emps, f, indent=4)
                            
                        self._log_to_history("SYSTEM: DELETION", f"ID:{badge_id}", deleted_name, "Manually Deleted", "SYSTEM LOG", "SERVER ADMIN")
                        self._trigger_immediate_sync()
                        return True
            except Exception: 
                pass
            return False

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
                        if len(row) >= 7 and row[3] == sample_id: 
                            return f"Req: {row[4]} | Proj: {row[6]}"
            except Exception: pass
        return "Unknown Sample"

    def save_data_async(self, location_id, sample_id, user, message_queue, requestor="N/A", dept="N/A", project="N/A", force_create=False):
        threading.Thread(target=self._save_data, args=(location_id, sample_id, user, message_queue, requestor, dept, project, force_create), daemon=True).start()

    def _save_data(self, location_id, sample_id, user, message_queue, requestor, dept, project, force_create):
        requestor = requestor.replace('\n', ' ').replace('\r', '')
        dept = dept.replace('\n', ' ').replace('\r', '')
        project = project.replace('\n', ' ').replace('\r', '')
        
        with self.lock:
            if not hasattr(self, 'recent_scans'):
                self.recent_scans = {}
            
            scan_signature = f"{sample_id}_{user}_{location_id}"
            current_time = time.time()
            if scan_signature in self.recent_scans:
                if current_time - self.recent_scans[scan_signature] < 3.0:
                    return  
            self.recent_scans[scan_signature] = current_time

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
                        if len(r) > 0:
                            # Self-Heal row on read
                            r[0] = self._normalize_date(r[0])
                            
                        if len(r) >= 7 and r[3] == sample_id:
                            found_existing = True
                            if not force_create:
                                if r[4] != "N/A": requestor = r[4]
                                if r[5] != "N/A": dept = r[5]
                                if r[6] != "N/A": project = r[6]
                            rows_to_keep.append([date_str, time_str, location_id, sample_id, requestor, dept, project, user])
                        else: rows_to_keep.append(r)
            except Exception: pass

            if not found_existing: rows_to_keep.append([date_str, time_str, location_id, sample_id, requestor, dept, project, user])

            with open(self.inventory_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerows(rows_to_keep)
                
            self._log_to_history(location_id, sample_id, requestor, dept, project, user)
            
            if message_queue:
                clean_loc = location_id.replace('LOC:', '').strip()
                message_queue.put(f"Saved: {sample_id}\nLocation: {clean_loc}")
            
        self._trigger_immediate_sync()

    def remove_data_async(self, sample_id, user, message_queue):
        threading.Thread(target=self._remove_data, args=(sample_id, user, message_queue), daemon=True).start()

    def _remove_data(self, sample_id, user, message_queue):
        with self.lock:
            req, dept, proj = "Unknown", "Unknown", "Unknown"
            rows_to_keep = []
            try:
                with open(self.inventory_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter=';')
                    header = next(reader, None)
                    if header: rows_to_keep.append(header)
                    for row in reader:
                        if len(row) > 0:
                            # Self-Heal row on read
                            row[0] = self._normalize_date(row[0])
                            
                        if len(row) > 6 and row[3] == sample_id: 
                            req, dept, proj = row[4], row[5], row[6]
                        else: 
                            rows_to_keep.append(row)
                            
                with open(self.inventory_file, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerows(rows_to_keep)
                    
                self._log_to_history("REQUEST CLOSED", sample_id, req, dept, proj, user)
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