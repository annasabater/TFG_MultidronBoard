'''

import json
import numpy as np
import cv2
import matplotlib.pyplot as plt

# Cargar la imagen sin el obstáculo (Asegúrate de que la imagen esté en la misma carpeta)
image_path_clean = "C:/Users/LENOVO/Desktop/EETAC/TFG/2. Codig/multidronBoard/competencia/image.png"
image_clean = cv2.imread(image_path_clean)
image_clean = cv2.cvtColor(image_clean, cv2.COLOR_BGR2RGB)

# Datos JSON actualizado con 3 jugadores: rojo, azul y verde
json_data = {
    "numPlayers": 3,
    "scenarios": [
        {
            "player": "red",
            "scenario": [
                {
                    "type": "polygon",
                    "waypoints": [
                        {"lat": 41.27643277540265, "lon": 1.9882405117504334},
                        {"lat": 41.27649123286352, "lon": 1.9884899571888184},
                        {"lat": 41.276250347472626, "lon": 1.9885945633403992},
                        {"lat": 41.27618886612167, "lon": 1.9883410945884918}
                    ]
                }
            ]
        },
        {
            "player": "blue",
            "scenario": [
                {
                    "type": "polygon",
                    "waypoints": [
                        {"lat": 41.27649425652386, "lon": 1.9885087326519226},
                        {"lat": 41.276549690272034, "lon": 1.9887756124489044},
                        {"lat": 41.276330978664795, "lon": 1.988873513077948},
                        {"lat": 41.276267481609295, "lon": 1.9886321142666077}
                    ]
                }
            ]
        },
        {
            "player": "green",
            "scenario": [
                {
                    "type": "polygon",
                    "waypoints": [
                        {"lat": 41.27655232263017, "lon": 1.9887950841099382},
                        {"lat": 41.27660775632902, "lon": 1.9890083197266222},
                        {"lat": 41.27639307646976, "lon": 1.989098173728621},
                        {"lat": 41.27634066625604, "lon": 1.9888956669479967}
                    ]
                }
            ]
        }
    ]
}


# Función para convertir coordenadas geográficas a píxeles
def geo_to_pixel(coords, img_shape):
    lat_min, lat_max = 41.27615, 41.27675  # Límites de latitud estimados
    lon_min, lon_max = 1.98815, 1.9892

    x = (coords[:, 0] - lon_min) / (lon_max - lon_min) * img_shape[1]
    y = (1 - (coords[:, 1] - lat_min) / (lat_max - lat_min)) * img_shape[0]
    return np.vstack((x, y)).T.astype(int)


# Función para extraer los puntos de los polígonos y círculos
def get_polygon_and_circle_points(player_data):
    polygon_points = []
    circle_points = []

    for scenario in player_data:
        if scenario["type"] == "polygon":
            polygon_points.extend([[point["lon"], point["lat"]] for point in scenario["waypoints"]])
        elif scenario["type"] == "circle":
            circle_points.append([scenario["lat"], scenario["lon"], scenario["radius"]])

    return np.array(polygon_points), circle_points


# Extraer los puntos de los polígonos y círculos para cada jugador
polygon_red_points, circle_red = get_polygon_and_circle_points(json_data["scenarios"][0]["scenario"])
polygon_blue_points, circle_blue = get_polygon_and_circle_points(json_data["scenarios"][1]["scenario"])
polygon_green_points, circle_green = get_polygon_and_circle_points(json_data["scenarios"][2]["scenario"])

# Convertir coordenadas geográficas a píxeles
polygon_red_pixels = geo_to_pixel(polygon_red_points, image_clean.shape)
polygon_blue_pixels = geo_to_pixel(polygon_blue_points, image_clean.shape)
polygon_green_pixels = geo_to_pixel(polygon_green_points, image_clean.shape)

# Dibujar la imagen con las zonas roja, azul y verde
fig, ax = plt.subplots(figsize=(8, 6))
ax.imshow(image_clean)

# Dibujar el área roja
polygon_red_patch = plt.Polygon(polygon_red_pixels, edgecolor='red', facecolor='red', alpha=0.4)
ax.add_patch(polygon_red_patch)

# Dibujar el área azul
polygon_blue_patch = plt.Polygon(polygon_blue_pixels, edgecolor='blue', facecolor='blue', alpha=0.4)
ax.add_patch(polygon_blue_patch)

# Dibujar el área verde
polygon_green_patch = plt.Polygon(polygon_green_pixels, edgecolor='green', facecolor='green', alpha=0.4)
ax.add_patch(polygon_green_patch)


# Dibujar los círculos de los jugadores (si hay)
def draw_circles(circles, color):
    for circle in circles:
        center = geo_to_pixel(np.array([[circle[1], circle[0]]]), image_clean.shape)[0]
        radius = int(circle[2] / (1 / (41.27675 - 41.27615)) * image_clean.shape[0])  # Estimación del radio en píxeles
        circle_patch = plt.Circle(center, radius, color=color, fill=True, alpha=0.3)
        ax.add_patch(circle_patch)


draw_circles(circle_red, "red")
draw_circles(circle_blue, "blue")
draw_circles(circle_green, "green")

ax.axis('off')

# Guardar la nueva imagen generada
output_path_clean = r"C:\Users\LENOVO\Desktop\EETAC\TFG\2. Codig\multidronBoard\competencia\3_escenario_sin_obstaculo.png"
plt.savefig(output_path_clean, bbox_inches='tight', pad_inches=0)
plt.show()

print(f"Imagen guardada en: {output_path_clean}")

'''

import json
import numpy as np
import cv2
import matplotlib.pyplot as plt

# Cargar la imagen sin el obstáculo (Asegúrate de que la imagen esté en la misma carpeta)
image_path_clean = "C:/Users/LENOVO/Desktop/EETAC/TFG/2. Codig/multidronBoard/competencia/image.png"
image_clean = cv2.imread(image_path_clean)
image_clean = cv2.cvtColor(image_clean, cv2.COLOR_BGR2RGB)

# Datos JSON actualizado con 4 jugadores: rojo, azul, verde y amarillo
json_data = {
        "numPlayers": 4,
        "scenarios": [
            {
                "player": "red",
                "scenario": [
                    {
                        "type": "polygon",
                        "waypoints": [
                            {"lat": 41.27643339199013, "lon": 1.9882251146942735},
                            {"lat": 41.27651200718324, "lon": 1.9886048966534133},
                            {"lat": 41.27639811591117, "lon": 1.9886531764156814},
                            {"lat": 41.27630639801663, "lon": 1.9882870548851486}
                        ]
                    }
                ]
            },
            {
                "player": "blue",
                "scenario": [
                    {
                        "type": "polygon",
                        "waypoints": [
                            {"lat": 41.27630337434758, "lon": 1.988288395989656},
                            {"lat": 41.27639509224637, "lon": 1.9886531764156814},
                            {"lat": 41.27626104296622, "lon": 1.988712185014009},
                            {"lat": 41.27617134066259, "lon": 1.988351427901506}
                        ]
                    }
                ]
            },
            {
                "player": "green",
                "scenario": [
                    {
                        "type": "polygon",
                        "waypoints": [
                            {"lat": 41.276514022956185, "lon": 1.9886196488029952},
                            {"lat": 41.27660372478888, "lon": 1.9890139335281845},
                            {"lat": 41.27648983367683, "lon": 1.9890581899769302},
                            {"lat": 41.27640718690472, "lon": 1.988663905251741}
                        ]
                    }
                ]
            },
            {
                "player": "yellow",
                "scenario": [
                    {
                        "type": "polygon",
                        "waypoints": [
                            {"lat": 41.2763991237994, "lon": 1.9886672580130096},
                            {"lat": 41.2764847942425, "lon": 1.9890602016336913},
                            {"lat": 41.276363847701916, "lon": 1.989116528023004},
                            {"lat": 41.27627011397882, "lon": 1.988734313238382}
                        ]
                    }
                ]
            }
        ]
}


# Función para convertir coordenadas geográficas a píxeles
def geo_to_pixel(coords, img_shape):
    lat_min, lat_max = 41.27615, 41.27675  # Límites de latitud estimados
    lon_min, lon_max = 1.98815, 1.9892

    x = (coords[:, 0] - lon_min) / (lon_max - lon_min) * img_shape[1]
    y = (1 - (coords[:, 1] - lat_min) / (lat_max - lat_min)) * img_shape[0]
    return np.vstack((x, y)).T.astype(int)


# Función para extraer los puntos de los polígonos y círculos
def get_polygon_and_circle_points(player_data):
    polygon_points = []
    circle_points = []

    for scenario in player_data:
        if scenario["type"] == "polygon":
            polygon_points.extend([[point["lon"], point["lat"]] for point in scenario["waypoints"]])
        elif scenario["type"] == "circle":
            circle_points.append([scenario["lat"], scenario["lon"], scenario["radius"]])

    return np.array(polygon_points), circle_points


# Extraer los puntos de los polígonos y círculos para cada jugador
polygon_red_points, circle_red = get_polygon_and_circle_points(json_data["scenarios"][0]["scenario"])
polygon_blue_points, circle_blue = get_polygon_and_circle_points(json_data["scenarios"][1]["scenario"])
polygon_green_points, circle_green = get_polygon_and_circle_points(json_data["scenarios"][2]["scenario"])
polygon_yellow_points, circle_yellow = get_polygon_and_circle_points(json_data["scenarios"][3]["scenario"])

# Convertir coordenadas geográficas a píxeles
polygon_red_pixels = geo_to_pixel(polygon_red_points, image_clean.shape)
polygon_blue_pixels = geo_to_pixel(polygon_blue_points, image_clean.shape)
polygon_green_pixels = geo_to_pixel(polygon_green_points, image_clean.shape)
polygon_yellow_pixels = geo_to_pixel(polygon_yellow_points, image_clean.shape)

# Dibujar la imagen con las zonas roja, azul, verde y amarilla
fig, ax = plt.subplots(figsize=(8, 6))
ax.imshow(image_clean)

# Dibujar el área roja
polygon_red_patch = plt.Polygon(polygon_red_pixels, edgecolor='red', facecolor='red', alpha=0.4)
ax.add_patch(polygon_red_patch)

# Dibujar el área azul
polygon_blue_patch = plt.Polygon(polygon_blue_pixels, edgecolor='blue', facecolor='blue', alpha=0.4)
ax.add_patch(polygon_blue_patch)

# Dibujar el área verde
polygon_green_patch = plt.Polygon(polygon_green_pixels, edgecolor='green', facecolor='green', alpha=0.4)
ax.add_patch(polygon_green_patch)

# Dibujar el área amarilla
polygon_yellow_patch = plt.Polygon(polygon_yellow_pixels, edgecolor='yellow', facecolor='yellow', alpha=0.4)
ax.add_patch(polygon_yellow_patch)


# Dibujar los círculos de los jugadores (si hay)
def draw_circles(circles, color):
    for circle in circles:
        center = geo_to_pixel(np.array([[circle[1], circle[0]]]), image_clean.shape)[0]
        radius = int(circle[2] / (1 / (41.27675 - 41.27615)) * image_clean.shape[0])  # Estimación del radio en píxeles
        circle_patch = plt.Circle(center, radius, color=color, fill=True, alpha=0.3)
        ax.add_patch(circle_patch)


draw_circles(circle_red, "red")
draw_circles(circle_blue, "blue")
draw_circles(circle_green, "green")
draw_circles(circle_yellow, "yellow")

ax.axis('off')

# Guardar la nueva imagen generada
output_path_clean = r"C:\Users\LENOVO\Desktop\EETAC\TFG\2. Codig\multidronBoard\competencia\4_escenario_sin_obstaculo.png"
plt.savefig(output_path_clean, bbox_inches='tight', pad_inches=0)
plt.show()

print(f"Imagen guardada en: {output_path_clean}")
