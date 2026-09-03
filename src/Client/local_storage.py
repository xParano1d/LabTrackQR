import os
import json
import time
from datetime import datetime
import threading
import requests

class ApiStorage:
    def __init__(self, server_url):
        self.server_url = server_url.rstrip('/')
        
        # Build the hidden offline vault in Windows %localappdata%
        self.local_appdata = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR')
        os.makedirs(self.local_appdata, exist_ok=True)
        
        self.queue_file = os.path.join(self.local_appdata, 'offline_queue.json')
        self.cache_file = os.path.join(self.local_appdata, 'inventory_cache.json')
        self.lock = threading.Lock()
        
        if not os.path.exists(self.queue_file):
            with open(self.queue_file, 'w') as f: json.dump([], f)
        if not os.path.exists(self.cache_file):
            with open(self.cache_file, 'w') as f: json.dump([], f)
            
        # Start the background engines
        threading.Thread(target=self._queue_processor, daemon=True).start()
        threading.Thread(target=self._cache_updater, daemon=True).start()

    def _queue_processor(self):
        """Silently fires queued scans to the Server. If server is down, they wait safely."""
        while True:
            time.sleep(2) # Check queue every 2 seconds
            with self.lock:
                try:
                    with open(self.queue_file, 'r') as f: queue = json.load(f)
                except: queue = []
            
            if not queue: continue
            
            successful_items = []
            for item in queue:
                try:
                    endpoint = f"{self.server_url}/api/remove_sample" if item.get('is_removal') else f"{self.server_url}/api/log_sample"
                    resp = requests.post(endpoint, json=item, timeout=3)
                    if resp.status_code == 200:
                        successful_items.append(item)
                except Exception:
                    break # Stop trying if server is unreachable
                    
            # Delete only the items the Server successfully confirmed
            if successful_items:
                with self.lock:
                    with open(self.queue_file, 'r') as f: current_queue = json.load(f)
                    new_queue = [x for x in current_queue if x not in successful_items]
                    with open(self.queue_file, 'w') as f: json.dump(new_queue, f)

    def _cache_updater(self):
        """Silently downloads a lightweight copy of the active inventory every 30 seconds for offline validation."""
        while True:
            try:
                resp = requests.get(f"{self.server_url}/api/get_inventory", timeout=5)
                if resp.status_code == 200:
                    with self.lock:
                        with open(self.cache_file, 'w') as f: json.dump(resp.json().get('inventory', []), f)
            except Exception: pass
            time.sleep(30)

    # --- API DATA FETCHING ---
    def get_employees(self):
        try:
            resp = requests.get(f"{self.server_url}/api/get_employees", timeout=2)
            if resp.status_code == 200: return resp.json().get('employees', {})
        except Exception: pass
        return {}

# --- API DATA FETCHING ---
    def get_employees(self):
        try:
            resp = requests.get(f"{self.server_url}/api/get_employees", timeout=2)
            if resp.status_code == 200: return resp.json().get('employees', {})
        except Exception: pass
        return {}

    def get_employee_name(self, badge_id):
        emp_data = self.get_employees().get(badge_id)
        if isinstance(emp_data, str): 
            return emp_data # Backwards compatibility for your old JSON format!
        if isinstance(emp_data, dict): 
            return emp_data.get("full_name")
        return None

    def get_employee_by_ad(self, ad_username):
        """Looks up an employee by their Windows AD Login"""
        emps = self.get_employees()
        for b_id, data in emps.items():
            if isinstance(data, dict) and data.get("ad_username", "").lower() == ad_username.lower():
                return data
        return None

    def add_employee(self, badge_id, first_name, last_name, ad_username=""):
        """Sends the new user registration to the Server API."""
        payload = {
            "badge_id": badge_id, "first_name": first_name, 
            "last_name": last_name, "ad_username": ad_username
        }
        try:
            resp = requests.post(f"{self.server_url}/api/add_employee", json=payload, timeout=3)
            print(f"API Response: {resp.status_code}") # <-- ADD THIS
        except Exception as e:
            print(f"NETWORK ERROR: Could not reach Server at {self.server_url} - {e}") # <-- ADD THIS

    # --- OFFLINE CACHE VALIDATION ---
    def sample_exists(self, sample_id):
        with self.lock:
            try:
                with open(self.cache_file, 'r') as f: cache = json.load(f)
                for row in cache:
                    if len(row) > 3 and row[3] == sample_id: return True
            except Exception: pass
        return False

    def get_sample_name(self, sample_id):
        with self.lock:
            try:
                with open(self.cache_file, 'r') as f: cache = json.load(f)
                for row in cache:
                    if len(row) > 4 and row[3] == sample_id: return row[4]
            except Exception: pass
        return "Unknown Sample"

    # --- QUEUE DATA WRITERS ---
    def save_data_async(self, location_id, sample_id, user, message_queue, sample_name="N/A", desc_notes="N/A", force_create=False):
        payload = {
            "location_id": location_id, "sample_id": sample_id, "user": user,
            "sample_name": sample_name, "desc_notes": desc_notes, "force_create": force_create,
            "client_timestamp": datetime.now().isoformat()
        }
        with self.lock:
            with open(self.queue_file, 'r') as f: queue = json.load(f)
            queue.append(payload)
            with open(self.queue_file, 'w') as f: json.dump(queue, f)
            
        if message_queue:
            clean_loc = location_id.replace('LOC:', '').strip()
            message_queue.put(f"Saved:\n{sample_id}\nLocation: {clean_loc}")

    def remove_data_async(self, sample_id, user, message_queue):
        payload = {"sample_id": sample_id, "user": user, "is_removal": True, "client_timestamp": datetime.now().isoformat()}
        with self.lock:
            with open(self.queue_file, 'r') as f: queue = json.load(f)
            queue.append(payload)
            with open(self.queue_file, 'w') as f: json.dump(queue, f)
            
        if message_queue: message_queue.put(f"Removal Queued:\n{sample_id}\nBy: {user}")

    # --- UI COMPATIBILITY ---
    def get_inventory_data(self):
        with self.lock:
            try:
                with open(self.cache_file, 'r') as f: return json.load(f)
            except Exception: return []
            
    def get_all_time_history(self):
        return [] # The Client UI no longer needs history access; use the Server for this.
        
    def get_active_file_path(self, file_type):
        return ""