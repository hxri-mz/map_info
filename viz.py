import json
import folium
import requests
import osmnx as ox
import math
import os
import sys
from shapely.geometry import Point
import csv

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def chunk_gps_data(data, chunk_size=100, overlap=5):
    chunks = []
    for i in range(0, len(data), chunk_size - overlap):
        chunk = data[i:i + chunk_size]
        if len(chunk) >= 2:
            chunks.append(chunk)
    return chunks

def osrm_match_trace(chunk):
    coords = ";".join([f"{p['longitude']},{p['latitude']}" for p in chunk])
    url = f"http://router.project-osrm.org/match/v1/driving/{coords}"
    params = {
        'steps': 'true',
        'geometries': 'geojson',
        'overview': 'full'
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"OSRM error {response.status_code}: {response.text}")
        return None
    try:
        return response.json()
    except json.JSONDecodeError:
        print("Failed to parse response.")
        return None

# --- Entry point ---
if len(sys.argv) < 2:
    print("Usage: python process_route.py <session_name>")
    sys.exit(1)

session_name = sys.argv[1]
output_dir = f"outputs/{session_name}"
ndjson_path = os.path.join(output_dir, "data_log.ndjson")

if not os.path.exists(ndjson_path):
    print(f"NDJSON file not found: {ndjson_path}")
    sys.exit(1)

with open(ndjson_path, 'r') as f:
    gps_data = [json.loads(line) for line in f]

if len(gps_data) < 2:
    print("Not enough data to process.")
    sys.exit(1)

start = gps_data[0]
end = gps_data[-1]

steps = []
route_geometry = []

for i, chunk in enumerate(chunk_gps_data(gps_data, chunk_size=100, overlap=0)):
    print(f"Matching chunk {i+1}")
    result = osrm_match_trace(chunk)
    if not result or 'matchings' not in result:
        continue

    matching = result['matchings'][0]
    route_geometry.extend(matching['geometry']['coordinates'])

    # Get list of original timestamps for this chunk
    gps_timestamps = [pt['timestamp'] for pt in chunk]

    step_index = 0
    for leg in matching['legs']:
        for step in leg['steps']:
            # Assign closest GPS timestamp to the step
            if step_index < len(gps_timestamps):
                step['timestamp'] = gps_timestamps[step_index]
            else:
                step['timestamp'] = gps_timestamps[-1]  # fallback to last if more steps than points
            steps.append(step)
            step_index += 1


mymap = folium.Map(location=[start['latitude'], start['longitude']], zoom_start=18)
route_latlon = [(lat, lon) for lon, lat in route_geometry]
folium.PolyLine(route_latlon, color='blue', weight=4).add_to(mymap)

folium.Marker(
    [start['latitude'], start['longitude']], popup="Start", icon=folium.Icon(color="green")
).add_to(mymap)
folium.Marker(
    [end['latitude'], end['longitude']], popup="End", icon=folium.Icon(color="red")
).add_to(mymap)

write_csv_header = True

prev_latlon = 0
incident = 0
dir_changes = {}
for step in steps:
    maneuver = step['maneuver']
    type_ = maneuver.get('type')
    modifier = maneuver.get('modifier')
    location = maneuver.get('location')
    latlon = (location[1], location[0])

    if prev_latlon == 0:
        dist_km = haversine(start['latitude'], start['longitude'], latlon[0], latlon[1])
    else:
        dist_km = haversine(prev_latlon[0], prev_latlon[1], latlon[0], latlon[1])

    if type_ == "turn":
        label = f"{modifier} turn"
        prev_latlon = latlon
        folium.Marker(
            latlon,
            popup=f"{label}",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(mymap)

        # Convert modifier to NAV_* label
        nav_label = f"NAV_{modifier.upper()}" if modifier else "NAV_UNKNOWN"

        ways = step['intersections'][0].get('bearings', []).copy()
        normalized = [angle - 180 if angle > 180 else angle for angle in ways]
        filtered = [angle for angle in normalized if abs(angle - normalized[0]) <= 120]
        dir = f"DIR_{len(filtered)}WAY"

        if os.path.exists("processed_data.csv"):
            write_csv_header = False

        # Append to shared CSV
        with open("processed_data.csv", "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            if write_csv_header:
                writer.writerow(["ECAL ID", "Timestamp", "Label", "Direction"])
                write_csv_header = False
            timest = round((step['timestamp'] - start['timestamp']) / 1e+6, 2)
            writer.writerow([session_name, timest, nav_label, dir])
        
        incident = 1
    
    elif type_ == "arrive":
        pass
    
    elif type_ == "depart":
        pass
    
    else:
        pass
    
    if len(step['intersections'][0]['bearings']) > 1:
        dir_changes.update({'dirs': len(step['intersections'][0]['bearings']),
                            'timestamp': round((step['timestamp'] - start['timestamp']) / 1e+6, 3)})
        

if incident == 0:
    print("processing for straight road")
    url = (f"http://router.project-osrm.org/route/v1/driving/"
           f"{start['longitude']},{start['latitude']};{end['longitude']},{end['latitude']}?steps=true&overview=full")
    resp = requests.get(url)
    data = resp.json()

    if not data.get("routes"):
        print("No route found.")
        sys.exit(1)

    route_steps = data["routes"][0]["legs"][0]["steps"]

    for step in route_steps:
        intersections = step.get("intersections", [])[1:]  # exclude first

        for inter in intersections:
            inter_lat, inter_lon = inter['location'][1], inter['location'][0]

            # Find closest GPS point
            closest_point = min(
                gps_data,
                key=lambda pt: haversine(inter_lat, inter_lon, pt['latitude'], pt['longitude'])
            )
            timestamp = closest_point['timestamp']
            inter['timestamp'] = timestamp

            nav_label = "NAV_STRAIGHT"
            ways = inter.get('bearings', []).copy()
            normalized = [angle - 180 if angle > 180 else angle for angle in ways]
            filtered = [angle for angle in normalized if abs(angle - normalized[0]) <= 120]
            dir = f"DIR_{len(filtered)}WAY"

            if os.path.exists("processed_data.csv"):
                write_csv_header = False

            with open("processed_data.csv", "a", newline="") as csvfile:
                writer = csv.writer(csvfile)
                if write_csv_header:
                    writer.writerow(["ECAL ID", "Timestamp", "Label", "Direction"])
                    write_csv_header = False
                timest = round((timestamp - start['timestamp']) / 1e+6, 3)
                writer.writerow([session_name, timest, nav_label, dir])

            folium.Marker(
                (inter_lat, inter_lon),
                popup=nav_label,
                icon=folium.Icon(color="orange", icon="star")
            ).add_to(mymap)



map_path = os.path.join(output_dir, "osrm_turns_map.html")
mymap.save(map_path)
print(f"✅ Map saved to {map_path}")
