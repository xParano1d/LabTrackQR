# server_api.py
import threading
from flask import Flask, request, jsonify
import logging

# Disable Flask's default console spam
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

class LabTrackAPI:
    def __init__(self, storage_manager):
        self.storage = storage_manager
        self.app = Flask(__name__)
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/api/ping', methods=['GET'])
        def ping():
            """Clients use this to check if the server is online."""
            return jsonify({"status": "online", "version": "1.0"}), 200

        @self.app.route('/api/get_inventory', methods=['GET'])
        def get_inventory():
            """Clients call this to cache the active inventory for offline validation."""
            data = self.storage.get_inventory_data()
            return jsonify({"inventory": data}), 200

        @self.app.route('/api/get_employees', methods=['GET'])
        def get_employees():
            """Syncs the employee AD dictionary to the client."""
            emps = self.storage.get_employees()
            return jsonify({"employees": emps}), 200

        @self.app.route('/api/log_sample', methods=['POST'])
        def log_sample():
            """Receives a scanned sample from a Client."""
            data = request.json
            if not data:
                return jsonify({"error": "No payload"}), 400
                
            # The payload expected from the Client
            loc_id = data.get("location_id")
            smp_id = data.get("sample_id")
            smp_name = data.get("sample_name", "N/A")
            notes = data.get("desc_notes", "N/A")
            user = data.get("user", "Unknown")
            is_force_create = data.get("force_create", False)
            timestamp = data.get("client_timestamp") # Used for deduplication later

            # Send it to the master CSV storage
            self.storage.save_data_async(
                location_id=loc_id, 
                sample_id=smp_id, 
                user=user, 
                message_queue=None, # Server doesn't show popups for client scans
                sample_name=smp_name, 
                desc_notes=notes, 
                force_create=is_force_create
            )
            return jsonify({"status": "success", "message": "Saved to master"}), 200

        @self.app.route('/api/remove_sample', methods=['POST'])
        def remove_sample():
            """Receives a removal request from a Client."""
            data = request.json
            smp_id = data.get("sample_id")
            user = data.get("user")
            
            self.storage.remove_data_async(smp_id, user, message_queue=None)
            return jsonify({"status": "success", "message": "Removed from master"}), 200

    def start_server(self, host='0.0.0.0', port=5000):
        """Runs the Flask API in a silent background thread."""
        server_thread = threading.Thread(target=self.app.run, kwargs={'host': host, 'port': port, 'debug': False, 'use_reloader': False})
        server_thread.daemon = True
        server_thread.start()
        print(f"[*] LabTrack Server API running on {host}:{port}")