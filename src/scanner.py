import serial
import serial.tools.list_ports
import threading
import time

class ScannerManager:
    def __init__(self, vids, pids, message_queue, storage):
        self.allowed_vids = vids
        self.allowed_pids = pids
        self.message_queue = message_queue
        self.storage = storage  
        self.active_scanners = {}
        self.is_monitoring = True
        self.removal_mode = False

    def start_monitoring(self):
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        while self.is_monitoring:
            self.find_and_connect()
            self._cleanup_disconnected()
            time.sleep(2)

    def find_and_connect(self):
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if port.vid in self.allowed_vids and port.pid in self.allowed_pids:
                if port.device not in self.active_scanners:
                    scanner_node = ScannerNode(port.device, port.hwid, self.message_queue, self.storage, manager=self)
                    self.active_scanners[port.device] = scanner_node
                    scanner_node.start_listening()

    def _cleanup_disconnected(self):
        dead_ports = [port for port, node in self.active_scanners.items() if not node.is_running]
        for port in dead_ports:
            del self.active_scanners[port]

class ScannerNode:
    def __init__(self, port, hwid, message_queue, storage, manager=None):
        self.port = port
        self.hwid = hwid 
        self.message_queue = message_queue
        self.storage = storage
        self.manager = manager 
        self.is_running = True
        self.user = "Unknown" 
        
        self.current_location = None
        self.pending_samples = []
        self.timeout_timer = None
        self.TIMEOUT_SECONDS = 10.0

    def _reset_state(self):
        """Called automatically if no scans occur within the timeout window."""
        # Only show the warning popup if the user actually had unsaved samples!
        if self.pending_samples:
            self.pending_samples.clear()
            self.current_location = None
            self.message_queue.put("Scan Timeout:\nUnsaved samples cleared.")
        elif self.current_location:
            # If they only had a location saved, just clear it silently in the background
            # so we don't annoy them with popups after a successful scan session.
            self.current_location = None 

    def _start_or_refresh_timer(self):
        if self.timeout_timer:
            self.timeout_timer.cancel()
        self.timeout_timer = threading.Timer(self.TIMEOUT_SECONDS, self._reset_state)
        self.timeout_timer.start()

    def _clear_timer(self):
        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None

    def start_listening(self):
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        try:
            with serial.Serial(self.port, baudrate=9600, timeout=1) as ser:
                
                db_user = self.storage.get_user(self.hwid)
                if db_user:
                    self.user = db_user
                    self.message_queue.put(f"Welcome {self.user}!\nReady to scan.")
                else:
                    self.message_queue.put(f"COMMAND:REGISTER_SCANNER:{self.hwid}")
                
                while self.is_running:
                    if ser.in_waiting > 0:
                        raw_data = ser.readline()
                        try:
                            scanned_text = raw_data.decode('utf-8').strip()
                            if not scanned_text: continue

                            self._start_or_refresh_timer()

                            if self.manager and self.manager.removal_mode and scanned_text.startswith("SMP:"):
                                self.message_queue.put(f"COMMAND:CONFIRM_REMOVE:{scanned_text}")
                                self.manager.removal_mode = False 
                                continue
                            elif self.manager and self.manager.removal_mode:
                                self.message_queue.put("Removal Error:\nPlease scan an SMP code.")
                                self.manager.removal_mode = False
                                continue

                            if scanned_text.startswith("LOC:"):
                                self.current_location = scanned_text
                                self.message_queue.put(f"Location Set:\n{self.current_location.replace('LOC:', '').strip()}")
                                
                                for smp in self.pending_samples:
                                    self.storage.save_data_async(location_id=self.current_location, sample_id=smp, user=self.user, message_queue=self.message_queue)
                                self.pending_samples.clear()

                            elif scanned_text.startswith("SMP:"):
                                if self.current_location:
                                    self.storage.save_data_async(location_id=self.current_location, sample_id=scanned_text, user=self.user, message_queue=self.message_queue)
                                else:
                                    self.pending_samples.append(scanned_text)
                                    self.message_queue.put(f"Sample Queued:\n{scanned_text}\n(Scan Location to save)")
                            else:
                                self.message_queue.put(f"Unknown Code:\n{scanned_text}")

                        except UnicodeDecodeError:
                            pass
        except serial.SerialException:
            self.message_queue.put(f"Scanner unplugged!\nWaiting for reconnect...")
        finally:
            self.is_running = False
            self._clear_timer()