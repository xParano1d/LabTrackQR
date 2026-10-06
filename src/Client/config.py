# src\client\config.py

# ==========================================
# 1. NETWORK & API SETTINGS
# ==========================================
# Server API Address (Change this to your Server's static IP)
# Default: "http://10.217.159.9:5000"
SERVER_URL = "http://10.217.159.9:5000"

# Base fallback path for external network drives (used for external CSV viewing)
# Default: r"Z:\Sample Tracking Tool"
BASE_PATH = r"Z:\Sample Tracking Tool" 

# How long (in seconds) the client waits for the server before assuming it is offline
# Default: 3 (Short) / 5 (Long) / 150 (Deep Search)
API_TIMEOUT_SHORT = 3  
API_TIMEOUT_LONG = 5   
API_TIMEOUT_SEARCH = 150

# ==========================================
# 2. HARDWARE & SCANNER SETTINGS
# ==========================================
# Hardware IDs from Device Manager (Format as an array to allow multiple scanners)
# Example for multiple: ALLOWED_VIDS = [0x0483, 0x1234, 0xABCD]
# Default: [0x0483]
ALLOWED_VIDS = [0x0483]
# Default: [0x0115]
ALLOWED_PIDS = [0x0115]

# Communication rate for the COM scanner
# Default: 9600
BAUDRATE = 9600

# Scanner Engine Timers (in seconds)
# Default: 10.0 (Idle) / 300.0 (Temp Revert) / 1.5 (Debounce) / 5.0 (Spam Silence)
SCANNER_IDLE_TIMEOUT = 10.0      # Clears unsaved scans if left idle
SCANNER_TEMP_USER_REVERT = 300.0 # Time (5 min) before reverting to Windows AD user
SCANNER_DEBOUNCE_DELAY = 1.5     # Prevents double-scanning the exact same barcode
SCANNER_SPAM_SILENCE = 5.0       # Prevents repeating the "Already logged in" popup

# ==========================================
# 3. BACKGROUND ENGINE SETTINGS
# ==========================================
# How often (in seconds) the background thread pushes offline scans to the server
# Default: 2
QUEUE_PROCESS_INTERVAL = 2

# How often (in seconds) the background thread downloads the inventory for offline use
# Default: 30
CACHE_UPDATE_INTERVAL = 30

# UI Auto-Refresh Rate (in milliseconds) for the Map and Log Viewer
# Default: 1000
UI_AUTO_REFRESH_MS = 1000

# ==========================================
# 4. BUSINESS LOGIC & SECURITY
# ==========================================
# The number of days before a sample is flagged as "Action Required" or "Old"
# Default: 14
STALE_SAMPLE_DAYS = 14

# Security prompt timeouts (in milliseconds)
# Default: 15000 (Relog) / 30000 (Removal)
RELOG_TIMEOUT_MS = 15000         # 15 seconds to confirm a user switch
REMOVAL_TIMEOUT_MS = 30000       # 30 seconds to confirm a sample deletion

# How long standard notifications stay on screen (in milliseconds)
# Default: 6500
NOTIFICATION_DURATION_MS = 6500

# ==========================================
# 5. UI COLOR PALETTE
# ==========================================
BTN_SUCCESS = ["#217346", "#09ce66"]
BTN_SUCCESS_HOVER = ["#2a8f57", "#2EFAD9"]
BTN_DANGER = "#d9534f"
BTN_DANGER_HOVER = "#c9302c"
BTN_WARNING = "#f39c12"
BTN_WARNING_HOVER = "#d68910"
BTN_SECONDARY = "#555555"
BTN_SECONDARY_HOVER = "#777777"
BTN_PRIMARY = "#2980b9"