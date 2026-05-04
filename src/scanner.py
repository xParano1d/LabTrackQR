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
                    scanner_node = ScannerNode(port.device, self.message_queue, self.storage)
                    self.active_scanners[port.device] = scanner_node
                    scanner_node.start_listening()

    def _cleanup_disconnected(self):
        dead_ports = [port for port, node in self.active_scanners.items() if not node.is_running]
        for port in dead_ports:
            del self.active_scanners[port]

class ScannerNode:
    def __init__(self, port, message_queue, storage):
        self.port = port
        self.message_queue = message_queue
        self.storage = storage
        self.is_running = True
        
        # --- STATE MACHINE VARIABLES ---
        self.current_location = None
        self.pending_samples = []
        
        # --- INACTIVITY TIMER VARIABLES ---
        self.timeout_timer = None
        self.TIMEOUT_SECONDS = 10.0

    def _reset_state(self):
        """Called automatically if no scans occur within the timeout window."""
        # Only notify and clear if there is actually data sitting in memory
        if self.current_location or self.pending_samples:
            self.current_location = None
            self.pending_samples.clear()
            self.message_queue.put("Session Timeout:\nLocation or sample was not scanned.")

    def _start_or_refresh_timer(self):
        """Restarts the countdown clock on every successful scan."""
        if self.timeout_timer:
            self.timeout_timer.cancel()
            
        self.timeout_timer = threading.Timer(self.TIMEOUT_SECONDS, self._reset_state)
        self.timeout_timer.start()

    def _clear_timer(self):
        """Safely shuts down the timer if the hardware is unplugged."""
        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None

    def start_listening(self):
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        try:
            with serial.Serial(self.port, baudrate=9600, timeout=1) as ser:
                self.message_queue.put(f"Connected on {self.port}\nReady to scan!")
                
                while self.is_running:
                    if ser.in_waiting > 0:
                        raw_data = ser.readline()
                        try:
                            scanned_text = raw_data.decode('utf-8').strip()
                            if not scanned_text: continue

                            # --- RESTART THE 10-SECOND CLOCK ---
                            self._start_or_refresh_timer()

                            # --- PREFIX PARSING LOGIC ---
                            if scanned_text.startswith("LOC:"):
                                self.current_location = scanned_text
                                self.message_queue.put(f"Location Set:\n{self.current_location.replace('LOC:', '').strip()}")
                                
                                # If we scanned samples earlier, save them to this new location now
                                for smp in self.pending_samples:
                                    self.storage.save_data_async(location_id=self.current_location, sample_id=smp, user="Scanner Hardware", message_queue=self.message_queue)
                                self.pending_samples.clear()

                            elif scanned_text.startswith("SMP:"):
                                if self.current_location:
                                    # We have a location, save immediately
                                    self.storage.save_data_async(location_id=self.current_location, sample_id=scanned_text, user="Scanner Hardware", message_queue=self.message_queue)
                                else:
                                    # No location yet, hold it in memory
                                    self.pending_samples.append(scanned_text)
                                    self.message_queue.put(f"Scanned {scanned_text}\n Waiting for Location to save")
                            else:
                                self.message_queue.put(f"Unknown Code:\n{scanned_text}")

                        except UnicodeDecodeError:
                            pass
        except serial.SerialException:
            self.message_queue.put(f"Scanner unplugged!\nWaiting for reconnect...")
        finally:
            self.is_running = False
            self._clear_timer() # Clean up the background timer so it doesn't crash