import json
import folium
import requests
import math
import os
import sys
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
        print(f"OSRM match error {response.status_code}: {response.text}")
        return None
    return response.json()

def osrm_route_between(start, end):
    url = f"http://router.project-osrm.org/route/v1/driving/{start['longitude']},{start['latitude']};{end['longitude']},{end['latitude']}?steps=true&overview=full"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"OSRM route error {response.status_code}: {response.text}")
        return None
    return response.json()

def log_csv(session_name, timestamp, label, direction, write_header_flag):
    if os.path.exists("processed_data.csv"):
        write_header_flag = False
    with open("processed_data.csv", "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        if write_header_flag:
            writer.writerow(["ECAL ID", "Timestamp", "Label", "Direction"])
        writer.writerow([session_name, timestamp, label, direction])
    return False

def detect_missed_turns(chunk, mymap, session_name, start_time, write_csv_header):
    route_data = osrm_route_between(chunk[0], chunk[-1])
    if not route_data or not route_data.get("routes"):
        return write_csv_header

    for step in route_data["routes"][0]["legs"][0]["steps"]:
        for inter in step.get("intersections", []):
            bearings = inter.get("bearings", [])
            if len(bearings) <= 1:
                continue

            inter_lat, inter_lon = inter['location'][1], inter['location'][0]
            closest_point = min(chunk, key=lambda pt: haversine(inter_lat, inter_lon, pt['latitude'], pt['longitude']))
            timestamp = closest_point['timestamp']
            timest = round((timestamp - start_time) / 1e+6, 3)

            normalized = [angle - 180 if angle > 180 else angle for angle in bearings]
            normalized = list(set(normalized))
            normalized.sort()
            filtered = [angle for angle in normalized if abs(angle - normalized[0]) <= 120]
            dir = f"DIR_{len(filtered)}WAY"
            write_csv_header = log_csv(session_name, timest, "NAV_STRAIGHT", dir, write_csv_header)

            folium.Marker(
                (inter_lat, inter_lon),
                popup=dir,
                icon=folium.Icon(color="orange", icon="star")
            ).add_to(mymap)
    return write_csv_header

if len(sys.argv) < 2:
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

mymap = folium.Map(location=[start['latitude'], start['longitude']], zoom_start=18)
folium.Marker([start['latitude'], start['longitude']], popup="Start", icon=folium.Icon(color="green")).add_to(mymap)
folium.Marker([end['latitude'], end['longitude']], popup="End", icon=folium.Icon(color="red")).add_to(mymap)

route_geometry = []
write_csv_header = True

for i, chunk in enumerate(chunk_gps_data(gps_data, chunk_size=100, overlap=5)):
    print(f"Processing chunk {i+1}")
    match_result = osrm_match_trace(chunk)
    if not match_result or 'matchings' not in match_result:
        continue

    matching = match_result['matchings'][0]
    route_geometry.extend(matching['geometry']['coordinates'])

    gps_timestamps = [pt['timestamp'] for pt in chunk]
    turn_detected = False
    step_index = 0

    for leg in matching['legs']:
        for step in leg['steps']:
            step['timestamp'] = gps_timestamps[min(step_index, len(gps_timestamps) - 1)]
            step_index += 1

            maneuver = step['maneuver']
            type_ = maneuver.get('type')
            modifier = maneuver.get('modifier')
            location = maneuver.get('location')
            latlon = (location[1], location[0])

            if type_ == "turn":
                turn_detected = True
                nav_label = f"NAV_{modifier.upper()}" if modifier else "NAV_UNKNOWN"
                bearings = step['intersections'][0].get('bearings', [])
                dir = f"DIR_{len(bearings)}WAY"
                timest = round((step['timestamp'] - start['timestamp']) / 1e+6, 2)

                folium.Marker(
                    latlon,
                    popup=f"{nav_label}",
                    icon=folium.Icon(color="blue", icon="info-sign")
                ).add_to(mymap)

                write_csv_header = log_csv(session_name, timest, nav_label, dir, write_csv_header)

    if not turn_detected:
        write_csv_header = detect_missed_turns(chunk, mymap, session_name, start['timestamp'], write_csv_header)

route_latlon = [(lat, lon) for lon, lat in route_geometry]
folium.PolyLine(route_latlon, color='blue', weight=4).add_to(mymap)

map_path = os.path.join(output_dir, "osrm_turns_map.html")
mymap.save(map_path)
print(f"Map saved to {map_path}")
