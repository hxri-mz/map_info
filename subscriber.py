import sys
import time
import ecal.core.core as ecal_core
from ecal.core.subscriber import ProtoSubscriber
from mz_schemas_protobuf.Pose_pb2 import Pose
import json

# feed = []

# Callback for receiving messages
def callback(topic_name, Pose, time):
    print("Message {} from {}: {}".format(Pose.lat_lon_ht.latitude_deg, 
                                        Pose.lat_lon_ht.longitude_deg,
                                        time))
    data = {
    'timestamp': time,
    'latitude': Pose.lat_lon_ht.latitude_deg,
    'longitude': Pose.lat_lon_ht.longitude_deg,
    }
    # feed.append(data)
    # with open('logs/log_002.json', mode='w', encoding='utf-8') as f:
    #     json.dump(feed, f)
    with open("logs/log_003.ndjson", "a") as f:
        f.write(json.dumps(data) + "\n")

if __name__ == "__main__":
  # initialize eCAL API. The name of our Process will be
  ecal_core.initialize(sys.argv, "Python Protobuf Subscriber")
  
  # Create a Protobuf Publisher that publishes on the topic
  sub = ProtoSubscriber("rec_gnss", Pose)

  # Set the Callback
  sub.set_callback(callback) 
  
  # Just don't exit
  while ecal_core.ok():
    pass
  
  # finalize eCAL API
  ecal_core.finalize()