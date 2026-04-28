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

*Note: Ensure the scanner is connected via the physical USB cable, as wireless 2.4G dongles often force HID keyboard emulation regardless of configuration.*

## Installation

### Prerequisites
* Python 3.x
* Git

### Setup Process
Clone the repository and install the required dependencies:

```bash
git clone [https://github.com/YOUR_USERNAME/LabTrackQR.git](https://github.com/YOUR_USERNAME/LabTrackQR.git)
cd LabTrackQR
pip install -r requirements.txt