import sys
import time
import os
import ecal.core.core as ecal_core
from ecal.core.subscriber import ProtoSubscriber
from mz_schemas_protobuf.Pose_pb2 import Pose
import json

# --- Get name from command-line argument ---
if len(sys.argv) < 2:
    print("Usage: python subscriber_script.py <ecal_session_name>")
    sys.exit(1)

session_name = sys.argv[1]  # e.g., "2025-07-11_13-18-35.710"

# Define log and output paths
log_dir = f"logs/{session_name}"
output_dir = f"outputs/{session_name}"

# Create directories
os.makedirs(log_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# Redirect stdout to log file
log_file_path = os.path.join(log_dir, "subscriber_log.txt")
sys.stdout = open(log_file_path, "w")

# Callback for receiving messages
def callback(topic_name, pose, timestamp):
    print("Timestamp: {} | Latitude: {} | Longitude: {}".format(timestamp,
                                                              pose.lat_lon_ht.latitude_deg, 
                                                              pose.lat_lon_ht.longitude_deg))
    data = {
        'timestamp': timestamp,
        'latitude': pose.lat_lon_ht.latitude_deg,
        'longitude': pose.lat_lon_ht.longitude_deg,
    }
    ndjson_path = os.path.join(output_dir, "data_log.ndjson")
    with open(ndjson_path, "a") as f:
        f.write(json.dumps(data) + "\n")

if __name__ == "__main__":
    ecal_core.initialize(sys.argv, "Python Protobuf Subscriber")
    
    sub = ProtoSubscriber("rec_gnss", Pose)
    sub.set_callback(callback)

    try:
        while ecal_core.ok():
            pass
    finally:
        sys.stdout.close()
        sys.stdout = sys.__stdout__
        ecal_core.finalize()
