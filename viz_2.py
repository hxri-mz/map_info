import json
import folium
import requests
import osmnx as ox
import math
from shapely.geometry import Point

def haversine(lat1, lon1, lat2, lon2):
    # Radius of Earth (km)
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

# === Load GPS data ===
with open('logs/log_003.ndjson', 'r') as f:
    gps_data = [json.loads(line) for line in f]


coords = [{"longitude": pt["longitude"], "latitude": pt["latitude"]} for pt in gps_data]

# # Extract first and last point
start = gps_data[0]
end = gps_data[-1]

all_steps = []
all_coords = []

for i, chunk in enumerate(chunk_gps_data(gps_data, chunk_size=100, overlap=0)):
    print(f"Matching chunk {i+1}")
    result = osrm_match_trace(chunk)
    if not result or 'matchings' not in result:
        continue
    
    matching = result['matchings'][0]
    all_coords.extend(matching['geometry']['coordinates'])
    
    for leg in matching['legs']:
        all_steps.extend(leg['steps'])

# steps = data['matchings'][0]['legs'][0]['steps']
# route_geometry = data['matchings'][0]['geometry']['coordinates']

steps = all_steps
route_geometry = all_coords

mymap = folium.Map(location=[start['latitude'], start['longitude']], zoom_start=18)

# Plot the route (convert to lat, lon for folium)
route_latlon = [(lat, lon) for lon, lat in route_geometry]
folium.PolyLine(route_latlon, color='blue', weight=4).add_to(mymap)

folium.Marker(
    [start['latitude'], start['longitude']], popup="Start", icon=folium.Icon(color="green")
).add_to(mymap)
folium.Marker(
    [end['latitude'], end['longitude']], popup="End", icon=folium.Icon(color="red")
).add_to(mymap)

with open("turns_log_003.txt", "w") as log_file:
    prev_latlon = 0
    for i, step in enumerate(steps):
        maneuver = step['maneuver']
        type_ = maneuver.get('type')
        modifier = maneuver.get('modifier')
        location = maneuver.get('location')
        latlon = (location[1], location[0])

        # Calculate distance from start
        if prev_latlon == 0:
            dist_km = haversine(start['latitude'], start['longitude'], latlon[0], latlon[1])
        else:
            dist_km = haversine(prev_latlon[0], prev_latlon[1], latlon[0], latlon[1])

        # Only log real turns
        if type_ == "turn":
            G = ox.graph_from_point(latlon, dist=50, network_type='drive')
            edges = ox.graph_to_gdfs(G, nodes=False)
            point = Point(latlon)
            nearest_edge = edges.geometry.distance(point).sort_values().index[0]
            road_info = edges.loc[nearest_edge]

            label = f"{modifier} turn"

            log_file.write(f"Turn: {label} at {latlon} \n")
            log_file.write(f"Road Name: {road_info.get('name')} | Highway Type: {road_info.get('highway')} | Lanes: {road_info.get('lanes')} | Max Speed: {road_info.get('maxspeed')} | Oneway: {road_info.get('oneway')} \n")
            log_file.write(f"---------------------------------------------------------\n")

            prev_latlon = latlon

            # Add marker
            folium.Marker(
                latlon,
                popup=f"{label} ({dist_km:.2f} km)",
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(mymap)
        
        elif type_ == "arrive":
            pass
        
        elif type_ == "depart":
            pass
        
        else:
            G = ox.graph_from_point(latlon, dist=50, network_type='drive')
            edges = ox.graph_to_gdfs(G, nodes=False)
            point = Point(latlon)
            nearest_edge = edges.geometry.distance(point).sort_values().index[0]
            road_info = edges.loc[nearest_edge]

            log_file.write(f"{modifier} at {latlon} \n")
            log_file.write(f"Road Name: {road_info.get('name')} | Highway Type: {road_info.get('highway')} | Lanes: {road_info.get('lanes')} | Max Speed: {road_info.get('maxspeed')} | Oneway: {road_info.get('oneway')} \n")
            log_file.write(f"---------------------------------------------------------\n")

            prev_latlon = latlon

            folium.Marker(
                latlon,
                popup=type_,
                icon=folium.Icon(color="yellow", icon="info-sign")
            ).add_to(mymap)

mymap.save("osrm_turns_map_003.html")
print("Map saved as 'osrm_turns_map.html'. Open it in your browser.")
