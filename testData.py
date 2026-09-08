import os
import csv
import random
from datetime import datetime, timedelta

# --- CONFIGURE YOUR SERVER PATH HERE ---
BASE_PATH = r"Z:\Sample Tracking Tool\history_logs"

LOCATIONS = [
    "LOC: Optical Profilometry", "LOC: Stereoscopic Microscopy", 
    "LOC: Residual Stress Measurement", "LOC: Technicians Office", 
    "LOC: Sample Preparation Room", "LOC: Engineers Office", 
    "LOC: Pending-Storage", "LOC: Metallographic Microscope",
    "LOC: Cabinet 4", "LOC: Storage Rack B"
]

USERS = ["Filip Pelczarski", "Andrzej Nowak", "Jan Kowalski", "Anna Adamek", "Kamil Kamyk", "Dawid Lesiak", "Maciej nieMusiał", "SYSTEM"]
NOTES = ["Routine check", "Urgent analysis needed", "Needs re-calibration", "Customer sample", 
         "Awaiting polishing", "Surface scratch detected", "Test completed", "Data sent to client", 
         "Pending approval", "", "", "", ""] # Extra empty strings for realism
MATERIALS = ["Titanium", "Carbon_Fiber", "Steel_Alloy", "Polymer", "Aluminum", "Ceramic", "Composite"]

def generate_realistic_data():
    start_date = datetime(2022, 1, 1)
    end_date = datetime(2026, 9, 7) # Current date limit
    
    print(f"Starting Realistic Lab Simulation: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m')}")
    print("Simulating sample lifecycles... (This will take ~10-20 seconds)")
    
    # We will hold the generated rows in a dictionary grouped by 'YYYY-MM'
    records_by_month = {}
    
    current_date = start_date
    sample_counter = 100000
    total_records = 0
    
    # Move through time day by day
    while current_date < end_date:
        # Introduce ~100 new samples to the lab today
        num_new_samples = random.randint(80, 120)
        
        for _ in range(num_new_samples):
            sample_id = f"SMP:{sample_counter}"
            sample_counter += 1
            sample_name = f"{random.choice(MATERIALS)}_Batch_{random.randint(10,999)}"
            
            # This sample will have between 5 and 15 scans in its life
            num_steps = random.randint(5, 15)
            
            # Start the sample's life sometime during today's shift
            sample_time = current_date + timedelta(hours=random.randint(7, 15), minutes=random.randint(0, 59))
            
            for step in range(num_steps):
                year_month = sample_time.strftime("%Y-%m")
                if year_month not in records_by_month:
                    records_by_month[year_month] = []
                    
                date_str = sample_time.strftime("%Y-%m-%d")
                time_str = sample_time.strftime("%H:%M:%S")
                
                # --- LIFECYCLE LOGIC ---
                if step == 0:
                    loc = "LOC: Pending-Storage"
                    note = "Sample registered in system"
                elif step == num_steps - 1:
                    # If this is the final step, remove it! 
                    # UNLESS it is within the last 30 days of our simulation, then leave it active in the lab.
                    if sample_time > (end_date - timedelta(days=30)):
                        loc = random.choice(LOCATIONS)
                        note = random.choice(NOTES)
                    else:
                        loc = "LOC: Action: Removed"
                        note = "Sample disposed / Archived"
                else:
                    # Normal mid-life scan
                    loc = random.choice(LOCATIONS)
                    loc = loc.replace('LOC:', '').replace('LOC-', '').strip()
                    note = random.choice(NOTES)
                    
                user = random.choice(USERS)
                
                # Add to memory
                records_by_month[year_month].append([date_str, time_str, loc, sample_id, sample_name, note, user])
                total_records += 1
                
                # Time jump to the NEXT scan for this sample (anywhere from 1 hour to 4 days later)
                sample_time += timedelta(minutes=random.randint(60, 5760))
                
                # If the sample's lifecycle stretches into the future (past our end date), stop scanning it
                if sample_time > end_date:
                    break 

        current_date += timedelta(days=1)

    print(f"Simulation complete. {total_records:,} total records generated.")
    print("Writing chronological logs to disk...")

    # Now we write our beautifully simulated data to the actual CSV files
    for ym, rows in records_by_month.items():
        year, month = ym.split('-')
        dir_path = os.path.join(BASE_PATH, year)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, f"log_{month}.csv")
        
        # Sort the month's rows chronologically so the CSV looks perfectly natural
        rows.sort(key=lambda x: (x[0], x[1]))
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Date", "Time", "Location", "Sample ID", "Name", "Notes", "User"])
            writer.writerows(rows)
            
        print(f"Saved {year}-{month} -> {len(rows):,} records")

    print("\nSUCCESS! Realistic Database Generation Complete.")
    print("Try this test in your Client Search Bar:  '2024-05 pending Filip'")

if __name__ == "__main__":
    generate_realistic_data()