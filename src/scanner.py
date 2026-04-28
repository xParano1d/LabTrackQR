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
        # Start a background thread that constantly checks for unplugs/replugs
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        while self.is_monitoring:
            self.find_and_connect()
            self._cleanup_disconnected()
            time.sleep(2) # Check every 2 seconds

    def find_and_connect(self):
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if port.vid in self.allowed_vids and port.pid in self.allowed_pids:
                if port.device not in self.active_scanners:
                    print(f"[Scanner] Found Scanner on {port.device}")
                    scanner_node = ScannerNode(port.device, self.message_queue, self.storage)
                    self.active_scanners[port.device] = scanner_node
                    scanner_node.start_listening()

    def _cleanup_disconnected(self):
        # Find scanners that crashed/unplugged and remove them from memory
        dead_ports = [port for port, node in self.active_scanners.items() if not node.is_running]
        for port in dead_ports:
            del self.active_scanners[port]
            print(f"[Scanner] Cleared dead connection on {port}")

class ScannerNode:
    def __init__(self, port, message_queue, storage):
        self.port = port
        self.message_queue = message_queue
        self.storage = storage
        self.is_running = True

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
                            if not scanned_text: 
                                continue

                            # --- TESTING MODE: INSTANT POPUP & SAVE ---
                            print(f"[{self.port}] Raw Data: {scanned_text}")
                            self.message_queue.put(f"Scanned:\n{scanned_text}")
                            
                            if self.storage:
                                self.storage.save_data_async("Testing-Mode", scanned_text)

                        except UnicodeDecodeError:
                            pass
        except serial.SerialException as e:
            # When unplugged, this triggers instantly
            print(f"[{self.port}] Hardware unplugged.")
            self.message_queue.put(f"Scanner unplugged!\nWaiting for reconnect...")
        finally:
            # Mark the thread as dead so the Manager can clean it up
            self.is_running = False