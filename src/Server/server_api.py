# server_api.py
import os
import json
import csv
import threading
import concurrent.futures
from flask import Flask, request, jsonify
import logging

# Disable Flask's default console spam
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

class LabTrackAPI:
    def __init__(self, storage_manager):
        self.storage = storage_manager
        self.app = Flask(__name__)
        
        # --- ULTRA-FAST RAM CACHE ---
        self.view_cache = {} 
        self.cache_lock = threading.Lock()
        
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/api/ping', methods=['GET'])
        def ping():
            return jsonify({"status": "online", "version": "1.0"}), 200

        @self.app.route('/api/get_inventory', methods=['GET'])
        def get_inventory():
            data = self.storage.get_inventory_data()
            return jsonify({"inventory": data}), 200

        @self.app.route('/api/get_employees', methods=['GET'])
        def get_employees():
            emps = self.storage.get_employees()
            return jsonify({"employees": emps}), 200

        @self.app.route('/api/add_employee', methods=['POST'])
        def add_employee():
            data = request.json
            self.storage.add_employee(
                data.get('badge_id'), 
                data.get('first_name'), 
                data.get('last_name'), 
                data.get('ad_username', '')
            )
            return jsonify({"status": "success"}), 200

        @self.app.route('/api/log_sample', methods=['POST'])
        def log_sample():
            data = request.json
            if not data:
                return jsonify({"error": "No payload"}), 400
                
            loc_id = data.get("location_id")
            smp_id = data.get("sample_id")
            smp_name = data.get("sample_name", "N/A")
            notes = data.get("desc_notes", "N/A")
            user = data.get("user", "Unknown")
            is_force_create = data.get("force_create", False)

            self.storage.save_data_async(
                location_id=loc_id, sample_id=smp_id, user=user, 
                message_queue=None, sample_name=smp_name, 
                desc_notes=notes, force_create=is_force_create
            )
            return jsonify({"status": "success"}), 200

        @self.app.route('/api/remove_sample', methods=['POST'])
        def remove_sample():
            data = request.json
            self.storage.remove_data_async(data.get("sample_id"), data.get("user"), message_queue=None)
            return jsonify({"status": "success"}), 200

        @self.app.route('/api/get_archive_months', methods=['GET'])
        def get_archive_months():
            """Returns the list of available history months to populate the Client's dropdown."""
            settings_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR', 'server_settings.json')
            try:
                with open(settings_path, 'r') as f:
                    base_path = json.load(f).get("PARENT_FOLDER")
            except Exception:
                base_path = r"D:\LAB_Share\Sample Tracking Tool" 

            history_dir = os.path.join(base_path, "history_logs")
            months = []
            if os.path.exists(history_dir):
                for year in sorted(os.listdir(history_dir), reverse=True):
                    year_path = os.path.join(history_dir, year)
                    if os.path.isdir(year_path):
                        for log in sorted(os.listdir(year_path), reverse=True):
                            if log.startswith("log_") and log.endswith(".csv"):
                                months.append(f"{year}-{log.replace('log_', '').replace('.csv', '')}")
            return jsonify({"months": months})

        @self.app.route('/api/view_data', methods=['GET'])
        def api_view_data():
            """Natively sorts massive files, uses RAM caching to prevent DDoS, and returns top 1500."""
            source = request.args.get('source', 'inventory')
            year = request.args.get('year', '')
            month = request.args.get('month', '')
            sort_col = request.args.get('sort_col', 'Date/Day')
            is_reverse = request.args.get('reverse', 'true').lower() == 'true'

            settings_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR', 'server_settings.json')
            try:
                with open(settings_path, 'r') as f:
                    base_path = json.load(f).get("PARENT_FOLDER")
            except Exception:
                base_path = r"D:\LAB_Share\Sample Tracking Tool"

            if source == 'inventory':
                filepath = os.path.join(base_path, "inventory.csv")
            else:
                filepath = os.path.join(base_path, "history_logs", year, f"log_{month}.csv")

            # --- CACHE CHECK ---
            try:
                current_mtime = os.path.getmtime(filepath)
            except Exception:
                return jsonify({"results": []}) 

            cache_key = f"{filepath}_{sort_col}_{is_reverse}"
            with self.cache_lock:
                if cache_key in self.view_cache:
                    if self.view_cache[cache_key]['mtime'] == current_mtime:
                        return jsonify({"results": self.view_cache[cache_key]['data']})

            # --- HARD DRIVE READ ---
            results = []
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = list(csv.reader(f, delimiter=';'))[1:]
                    results = reader
            except Exception:
                return jsonify({"results": []})

            # Native Sort
            cols = ["Date/Day", "Time", "Location", "Sample ID", "Name", "Notes", "User"]
            col_idx = cols.index(sort_col) if sort_col in cols else 0

            if sort_col in ("Date/Day", "Time"):
                results.sort(key=lambda x: (x[0] + " " + x[1]) if len(x)>1 else "", reverse=is_reverse)
            else:
                results.sort(key=lambda x: x[col_idx].lower() if len(x)>col_idx else "", reverse=is_reverse)

            final_results = results[:1500]

            # Save to RAM
            with self.cache_lock:
                self.view_cache[cache_key] = {"mtime": current_mtime, "data": final_results}

            return jsonify({"results": final_results})

        @self.app.route('/api/search', methods=['GET'])
        def api_deep_search():
            """High-speed threaded search engine for massive CSV archives."""
            query = request.args.get('q', '').strip()
            if not query:
                return jsonify({"results": [], "warning": ""})

            search_terms = [word.lower() for word in query.split()]
            max_results = 1000
            results = []
            
            settings_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LabTrackQR', 'server_settings.json')
            try:
                with open(settings_path, 'r') as f:
                    base_path = json.load(f).get("PARENT_FOLDER")
            except Exception:
                base_path = r"D:\LAB_Share\Sample Tracking Tool" 
            
            files_to_search = [os.path.join(base_path, "inventory.csv")]
            
            history_dir = os.path.join(base_path, "history_logs")
            if os.path.exists(history_dir):
                for year in sorted(os.listdir(history_dir), reverse=True):
                    year_path = os.path.join(history_dir, year)
                    if os.path.isdir(year_path):
                        for log in sorted(os.listdir(year_path), reverse=True):
                            if log.startswith("log_") and log.endswith(".csv"):
                                files_to_search.append(os.path.join(year_path, log))

            def search_file(filepath):
                local_results = []
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        next(f, None) 
                        for line in f:
                            line_lower = line.lower()
                            if all(term in line_lower for term in search_terms):
                                row = line.strip().split(';')
                                local_results.append(row)
                                if len(local_results) > max_results:
                                    break
                except Exception:
                    pass 
                return local_results

            warning_msg = ""
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                for file_results in executor.map(search_file, files_to_search):
                    results.extend(file_results)
                    if len(results) >= max_results:
                        results = results[:max_results]
                        warning_msg = "⚠️ Displaying first 1,000 results.\nPlease use more specific search terms."
                        executor.shutdown(wait=False, cancel_futures=True) 
                        break

            return jsonify({"results": results, "warning": warning_msg})

    def start_server(self, host='0.0.0.0', port=5000):
        """Runs the Flask API in a silent background thread."""
        server_thread = threading.Thread(target=self.app.run, kwargs={'host': host, 'port': port, 'debug': False, 'use_reloader': False})
        server_thread.daemon = True
        server_thread.start()
        print(f"[*] LabTrack Server API running on {host}:{port}")