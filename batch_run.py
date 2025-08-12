import subprocess
import time
import os
from config import *

ecal_file_list = ECAL_FILES_LIST
subscriber_script = SUBSCRIBER_SCRIPT
vis_script = VIZ_SCRIPT

# Read all ecal paths from file
with open(ecal_file_list, "r") as f:
    ecal_paths = [line.strip() for line in f if line.strip()]


# Process each path
for path in ecal_paths:
    print(f"\n=== Processing: {path} ===")

    if not os.path.exists(path):
        print(f"Skipping: {path} (not found)")
        continue

    # Start ecal_play as a subprocess
    if ECAL_UNLIMITED_SPEED:
        ecal_play_proc = subprocess.Popen(["ecal_play", "-m", path, "-u"])
    else:
        ecal_play_proc = subprocess.Popen(["ecal_play", "-m", path])
    print("Started ecal_play...")

    # Small delay to ensure ecal_play is running before subscriber starts
    time.sleep(2)

    # Start subscriber script
    subscriber_proc = subprocess.Popen(["python3", subscriber_script, os.path.basename(path)])

    # Wait for ecal_play to finish
    ecal_play_proc.wait()
    print("ecal_play finished.")

    # Give subscriber a few seconds to finish receiving last messages
    time.sleep(2)

    # Terminate subscriber process
    subscriber_proc.terminate()
    print("Terminated subscriber.\n")

    # Run post-processing
    print("Running OSRM + map generation...")
    subprocess.run(["python3", vis_script, os.path.basename(path)])

print("✅ All files processed.")
