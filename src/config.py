# config file for static variables and settings

# Hardware IDs from Device Manager (Zenwire W213)
ALLOWED_VIDS = [0x0483]
ALLOWED_PIDS = [0x0115]

# Comunication rate for COM scanner
BAUDRATE = 9600

# --- File Save Paths ---
SAVE_PATH = "Z:\\Sample Tracking Tool\\inventory.csv"
EMPLOYEES_PATH = "Z:\\Sample Tracking Tool\\employees.json"
HISTORY_DIR = "Z:\\Sample Tracking Tool\\history_logs" 

# --- Network Synchronization ---
# Change this to your NAS or Network Drive path (e.g., r"Z:\LabTrack_Backups")
# Set to None to disable network sync
NETWORK_SYNC_PATH = None
SYNC_INTERVAL_SECONDS = 300 # Syncs every 5 minutes