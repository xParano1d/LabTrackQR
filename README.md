# LabTrackQR

LabTrackQR is a background desktop application designed to intercept, process, and log barcode and QR code scans from physical scanning hardware. It establishes a direct Serial (Virtual COM) connection to prevent standard HID keyboard emulation, allowing users to scan tags without interfering with active system windows. 

The application features a self-healing hardware watchdog, local data logging, and a stacking UI notification overlay.

## Hardware Configuration

For the application to capture data correctly, the physical scanner must be configured using the control barcodes provided in the manufacturer's manual. 

Scan the configuration codes in this exact order (reference `scanner settings to change for using the app.txt`):
1. **Default** (Resets the scanner to factory baseline)
2. **Serial Port / USB Virtual Serial Port** (Disables HID Keyboard mode and routes data to COM ports)
3. **Manual Mode** (If applicable to your scanning workflow)
4. **Speed: 1 second** (Hardware-level buffer delay to ensure rapid-fire scans are processed cleanly)

*Note: Ensure the scanner is configured and work as Virtual COM USB Device, scanners often force HID keyboard emulation as default.*

## Installation

### Prerequisites
* Python 3.x
* Git

*Note: if you are using VS Code or Visual Studio, I highly recommend installing the [To Do Tasks](https://marketplace.visualstudio.com/items?itemName=sandy081.todotasks) extension for keeping upcoming and done tasks clean and organized.*

### Setup Process
Clone the repository and install the required dependencies:

```bash
git clone [https://github.com/YOUR_USERNAME/LabTrackQR.git](https://github.com/YOUR_USERNAME/LabTrackQR.git)
cd LabTrackQR
pip install -r requirements.txt
```

## Compiling to an Executable (.exe)

To distribute LabTrackQR without requiring a local Python environment, you can compile the application into a standalone Windows executable (`.exe`) using **PyInstaller** (which is automatically installed during the Setup Process).

### 1. Build the Executable
Open your terminal in the root project folder (the folder containing `icon.png` and the `src` directory) and run the following command:
```bash
pyinstaller --onefile --noconsole --icon=icon.png --add-data "icon.png;." --paths src src\main.py
```
**Command Breakdown:**
* `--onefile`: Compresses everything into a single `.exe` file.
* `--noconsole`: Hides the black background terminal window when the app is running.
* `--icon=icon.png`: Uses the custom logo for the desktop icon.
* `--add-data "icon.png;."`: Bundles the image inside the `.exe` so the System Tray icon doesn't break.
* `--paths src`: Tells the compiler where to find the rest of the Python modules (`config.py`, `overlay.py`, etc.).

### 2. Locate your File
Once the build process is complete, your packaged `main.exe` will be located inside the newly generated `dist/` folder. You can rename it to `LabTrackQR.exe` and move it anywhere on your PC!