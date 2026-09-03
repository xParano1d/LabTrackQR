# config file for static variables and settings

# Hardware IDs from Device Manager (Zenwire W213)
ALLOWED_VIDS = [0x0483]
ALLOWED_PIDS = [0x0115]

# Comunication rate for COM scanner
BAUDRATE = 9600


# --- File Save Paths ---
PARENT_FOLDER = "Z:\\Sample Tracking Tool"

HISTORY_DIR = PARENT_FOLDER+"\\history_logs" 
SAVE_PATH = PARENT_FOLDER+"\\inventory.csv"
EMPLOYEES_PATH = PARENT_FOLDER+"\\employees.json"


# --- Network Synchronization ---
# Change this to your NAS or Network Drive path (e.g., r"Z:\LabTrack_Backups")
# Set to None to disable network sync
NETWORK_SYNC_PATH = PARENT_FOLDER
SYNC_INTERVAL_SECONDS = 60 # Syncs every minute