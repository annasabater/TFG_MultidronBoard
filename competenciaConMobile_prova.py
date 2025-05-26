import json
import math
import random
from tkinter import ttk
import tkinter as tk
import matplotlib.pyplot as plt
import uuid
from tkinter import messagebox
import tkintermapview
import pyautogui
import win32gui
import glob
from tkinter import Canvas
import paho.mqtt.client as mqtt
from dronLink.Dron import Dron
import geopy.distance
from geographiclib.geodesic import Geodesic
from ParameterManager import ParameterManager
from AutopilotControllerClass import AutopilotController
from math import radians, sin, cos, sqrt, atan2
from PIL import Image, ImageTk, ImageEnhance
from shapely.geometry import Point, Polygon
from shapely.affinity import rotate
import os, sys, time, threading
import requests
import socketio
from dotenv import load_dotenv
from tkinter.simpledialog import askstring
global swarm

session_id = None

load_dotenv()
SERVER_URL = os.getenv('SERVER_URL')
ADMIN_KEY = os.getenv('ADMIN_KEY', '')

if not SERVER_URL or not ADMIN_KEY:
    print("Debes definir SERVER_URL y ADMIN_KEY en tu .env")
    sys.exit(1)

PLAYER_COLORS  = ['rojo', 'azul', 'verde', 'amarillo']
PLAYER_EMAILS  = [os.getenv(f'DRON_{c.upper()}_EMAIL') for c in PLAYER_COLORS]

def color_of_id(id):          # 0-3 → 'rojo'…
    return PLAYER_COLORS[id]

def email_of_id(id):          # 0-3 → dron_rojo1@upc.edu …
    return PLAYER_EMAILS[id]


def login(email, password):
    resp = requests.post(
        f"{SERVER_URL}/api/auth/login",
        json={"email": email, "password": password}
    )
    if resp.status_code != 200:
        print(f"Login fallido para {email}: {resp.text}")
        sys.exit(1)
    return resp.json().get("accesstoken")


# --- crea un cliente socket para el profesor ---
sio_prof = socketio.Client(logger=False, engineio_logger=False)

@sio_prof.event(namespace='/professor')
def connect():
    print("Profesor conectado a /professor")

@sio_prof.event(namespace='/professor')
def connect_error(data):
    print("Error al conectar a /professor:", data)

try:
    sio_prof.connect(
        SERVER_URL,
        transports=['websocket'],
        namespaces=['/professor'],
        auth={'/professor': {'key': ADMIN_KEY}}
    )
except Exception as e:
    print("No pude conectar a /professor:", e)
    sys.exit(1)

def make_dron_client(color, token):
    sio = socketio.Client(logger=False, engineio_logger=False)

    @sio.event(namespace='/jocs')
    def connect():
        print(f"🔌 Dron {color} conectado a /jocs")

    # Nuevo handler para recibir actualizaciones de estado
    @sio.on('state_update', namespace='/jocs')
    def on_state_update(data):
        # data = { drone: "dron_rojo1@upc.edu", action, payload, by }
        if data.get('drone') != os.getenv(f"DRON_{color.upper()}_EMAIL"):
            return  # no es para este dron
        action  = data['action']
        payload = data.get('payload', {})

        pid = color_to_pid[color]
        # Mover
        if action == 'move':
            dx, dy = payload['dx'], payload['dy']
            lat, lon = positions[color]
            new_lat = lat + dy * 0.00005
            new_lon = lon + dx * 0.00005
            positions[color] = (new_lat, new_lon)
            mover_dron(swarm[pid], (new_lat, new_lon), player_id=pid)
        # Disparar
        elif action == 'fire':
            btype = payload.get('type', 'medium')
            shoot(pid, btype)
        else:
            print(f"Acción desconocida en Python: {action}")

    sio.connect(
        SERVER_URL,
        auth={'token': token},
        transports=['websocket'],
        namespaces=['/jocs']
    )
    return sio


DRONS = {
    'rojo':     (os.getenv('DRON_ROJO_EMAIL'),     os.getenv('DRON_ROJO_PASSWORD')),
    'azul':     (os.getenv('DRON_AZUL_EMAIL'),     os.getenv('DRON_AZUL_PASSWORD')),
    'verde':    (os.getenv('DRON_VERDE_EMAIL'),    os.getenv('DRON_VERDE_PASSWORD')),
    'amarillo': (os.getenv('DRON_AMARILLO_EMAIL'), os.getenv('DRON_AMARILLO_PASSWORD')),
}

dron_clients = {}

for color, (email, pwd) in DRONS.items():
    if not email or not pwd:
        print(f"Falta email/password para dron {color} en .env")
        sys.exit(1)
    token = login(email, pwd)
    dron_clients[color] = make_dron_client(color, token)

positions = { color: (0.0, 0.0) for color in dron_clients.keys() }
email_to_color = { creds[0]: color for color,creds in DRONS.items() }
color_to_pid   = {'rojo':0, 'azul':1, 'verde':2, 'amarillo':3}


@sio_prof.on('control', namespace='/professor')
def on_control(data):
    color_email = data['drone']
    action      = data['action']
    payload     = data.get('payload', {})

    color_key = email_to_color.get(color_email)
    if color_key is None:
        print(f"unknown drone email {color_email}")
        return

    pid = color_to_pid[color_key]
    dron = swarm[pid]

    if action == 'move':
        dx, dy = payload['dx'], payload['dy']
        lat, lon = positions[color_key]
        new_lat = lat + dy * 0.00005
        new_lon = lon + dx * 0.00005
        # guarda la nueva posición
        positions[color_key] = (new_lat, new_lon)
        mover_dron(dron, (new_lat, new_lon), player_id=pid)

    elif action == 'fire':
        btype = payload.get('type','medium')
        shoot(pid, btype)

    else:
        print(f"unknown action {action}")



active_bullets = [] # Lista para almacenar balas activas
players = []
teams = []
obstacles = []
buttons = []
flight_times = [0, 0, 0, 0]

eliminated_players = set()
flight_times_lock = threading.Lock()

respawn_time = 15  # Segundos
game_elapsed_seconds = 0
active_player_id = 0
game_duration = 1600  # Duración por defecto (8 minutos)

player_scores = {0: 0, 1: 0, 2: 0, 3: 0}
shot_counts = {"small_fast": 0, "medium": 0, "large_slow": 0}
player_zones = {}
last_valid_positions = {}
initial_positions = {} # guarda la posición inicial de cada dron
total_distances = {} # guarda la distancia total recorrida por cada dron
player_fences_completed = {}
should_reset_distance = {}

survival_mode = False
game_paused = False
mode_selected = False
tiempo_configurado = False
supervivencia_configurada = False
recording_enabled = False
game_timer_running = False
mirror_placement = False    # True si el usuario elige "Efecto Espejo", False si "Individual"
removing_obstacles = False  # True si estamos en modo eliminar obstáculos

obstaculosFrame = None      # Frame donde pondremos los botones
configuracionFrame = None
game_mode = None
direction_lines = [None, None, None, None]
start_times = [None, None, None, None]
game_clock_label = None
timeBtn = None
plotBtn = None
statsBtn = None


def haversine(lat1, lon1, lat2, lon2):
    # Radio de la Tierra en metros
    R = 6371000

    # Convertir grados a radianes
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    # Fórmula del Haversine
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Distancia en metros
    distance = R * c

    return distance

lock = threading.Lock()


########## Funciones para la creación de multi escenarios #################################
def createBtnClick():
    global gameModeFrame
    global mode_selected
    global scenario, selectedMultiScenario, multiScenario, obstacles, scenarios

    multiScenario = {'numPlayers': 0, 'scenarios': []}
    scenario = []
    selectedMultiScenario = None
    obstacles.clear()
    scenarios = []

    gameModeFrame.grid_remove()
    mode_selected = True

    selectFrame.grid_forget()
    superviseFrame.grid_forget()

    createFrame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    createBtn['text'] = 'Creando...'
    createBtn['fg'] = 'white'
    createBtn['bg'] = 'green'

    selectBtn['text'] = 'Seleccionar'
    selectBtn['fg'] = 'black'
    selectBtn['bg'] = 'dark orange'

    superviseBtn['text'] = 'Supervisar'
    superviseBtn['fg'] = 'black'
    superviseBtn['bg'] = 'dark orange'

    startGameBtn.grid_remove()
    for widget in controlFrame.winfo_children():
        if isinstance(widget, tk.LabelFrame) and widget.cget("text") == "Opciones de Disparo":
            widget.grid_remove()

    controlButtonsFrame.grid_remove()
    mostrar_controles_juego()
    mantener_escenario_visible()


# iniciamos la creación de un fence tipo polígono
def definePoly(type):
    global fence, paths, polys
    global fenceType

    fenceType = type

    paths = []
    fence = {
        'type': 'polygon',
        'waypoints': []
    }
    # informo del tema de los botones del mouse para que el usuario no se despiste
    messagebox.showinfo("showinfo",
                        "Con el boton izquierdo del ratón señala los waypoints\nCon el boton derecho cierra el polígono")


# iniciamos la creación de un fence tipo círculo
def defineCircle(type):
    global fence, paths, polys
    global fenceType, centerFixed

    fenceType = type  # 1 es inclusión y 2 es exclusión
    paths = []
    fence = {
        'type': 'circle'
    }
    centerFixed = False
    # informo del tema de los botones del mouse para que el usuario no se despiste
    messagebox.showinfo("showinfo",
                        "Con el boton izquierdo señala el centro\nCon el boton derecho marca el límite del círculo")


# capturamos el siguiente click del mouse
def getFenceWaypoint(coords):
    global marker, centerFixed
    global mode_selected

    # Evita que aparezca el error si aun no se ha seleccionado Crear
    if not mode_selected:
        return  # No hace nada si no hay un modo seleccionado

    # acabo de clicar con el botón izquierdo
    if fence:
        # hay un fence en marcha
        # veamos si el fence es un polígono o un círculo
        if fence['type'] == 'polygon':
            if len(fence['waypoints']) == 0:
                # es el primer waypoint del fence. Pongo un marcador
                if fenceType == 1:
                    # en el fence de inclusión (límites del escenario)
                    marker = map_widget.set_marker(coords[0], coords[1], icon=colorIcon, icon_anchor="center")
                else:
                    # es un obstáculo
                    marker = map_widget.set_marker(coords[0], coords[1], icon=black, icon_anchor="center")

            if len(fence['waypoints']) > 0:
                # trazo una línea desde el anterior a este
                lat = fence['waypoints'][-1]['lat']
                lon = fence['waypoints'][-1]['lon']
                # elijo el color según si es de inclusión o un obstáculo
                if fenceType == 1:
                    paths.append(map_widget.set_path([(lat, lon), coords], color=selectedColor, width=3))
                else:
                    paths.append(map_widget.set_path([(lat, lon), coords], color='black', width=3))
                # si es el segundo waypoint quito el marcador que señala la posición del primero
                if len(fence['waypoints']) == 1:
                    marker.delete()

            # guardo el nuevo waypoint
            fence['waypoints'].append({'lat': coords[0], 'lon': coords[1]})
        else:
            # es un círculo. El click indica la posición de centro del circulo
            if centerFixed:
                messagebox.showinfo("Error",
                                    "Marca el límite con el botón derecho del mouse")

            else:
                # ponemos un marcador del color adecuado para indicar la posición del centro
                if fenceType == 1:
                    marker = map_widget.set_marker(coords[0], coords[1], icon=colorIcon, icon_anchor="center")
                else:
                    marker = map_widget.set_marker(coords[0], coords[1], icon=black, icon_anchor="center")
                # guardamos la posicion de centro
                fence['lat'] = coords[0]
                fence['lon'] = coords[1]
                centerFixed = True
    else:
        messagebox.showinfo("error",
                            "No hay ningun fence en construccion\nIndica primero qué tipo de fence quieres")


# cerramos el fence
def closeFence(coords):
    global poly, polys, fence
    # estamos creando un fence y acabamos de darle al boton derecho del mouse para cerrar
    # el fence está listo
    if fence['type'] == 'polygon':
        scenario.append(fence)

        # substituyo los paths por un polígono
        for path in paths:
            path.delete()

        poly = []
        for point in fence['waypoints']:
            poly.append((point['lat'], point['lon']))

        if fenceType == 1:
            # polígono del color correspondiente al jugador
            polys.append(map_widget.set_polygon(poly,
                                                outline_color=selectedColor,
                                                fill_color=selectedColor,
                                                border_width=3,
                                                polygon_type="fence"
                                                ))

        else:
            # polígono de color negro (obstaculo)
            polys.append(map_widget.set_polygon(poly,
                                                outline_color="black",
                                                fill_color="black",
                                                border_width=3,
                                                polygon_type="obstacle"
                                                ))

    else:
        # Es un circulo y acabamos de marcar el límite del circulo
        # borro el marcador del centro
        marker.delete()
        center = (fence['lat'], fence['lon'])
        limit = (coords[0], coords[1])
        radius = geopy.distance.geodesic(center, limit).m
        # el radio del círculo es la distancia entre el centro y el punto clicado
        fence['radius'] = radius
        # ya tengo completa la definición del fence
        scenario.append(fence)
        # como no se puede dibujar un circulo con la librería tkintermapview, creo un poligono que aproxime al círculo
        points = getCircle(fence['lat'], fence['lon'], radius)

        # Dibujo en el mapa el polígono que aproxima al círculo, usando el color apropiado según el tipo y el jugador
        if fenceType == 1:
            polys.append(map_widget.set_polygon(points,
                                                outline_color=selectedColor,
                                                fill_color=selectedColor,
                                                border_width=3))
        else:
            polys.append(map_widget.set_polygon(points,
                                                fill_color='black',
                                                outline_color='black',
                                                border_width=3))

    fence = None


# La siguiente función crea una imagen capturando el contenido de una ventana
def screenshot(window_title=None):
    # Captura exactamente la parte del mapa visible, sin recortes fijos
    ventana.update()  # Asegura que la ventana esté actualizada
    x = map_widget.winfo_rootx()
    y = map_widget.winfo_rooty()
    w = map_widget.winfo_width()
    h = map_widget.winfo_height()

    im = pyautogui.screenshot(region=(x, y, w, h))
    return im


# guardamos los datos del escenario (imagen y fichero json)
def registerScenario():
    global multiScenario, obstacles, placing_obstacles

    escenario_name = name.get().strip()
    if not escenario_name:
        # Si está vacío, mostrar un aviso y no registrar
        messagebox.showerror("Falta nombre", "Por favor, introduce un nombre para el escenario antes de registrarlo.")
        return

    for scenario in multiScenario['scenarios']:
        scenario['scenario'].extend(obstacles)

    jsonFilename = f"competencia/{escenario_name}_{numPlayers}.json"
    with open(jsonFilename, 'w') as f:
        json.dump(multiScenario, f)

    im = screenshot('Gestión de escenarios')
    imageFilename = f"competencia/{escenario_name}_{numPlayers}.png"
    im.save(imageFilename)

    multiScenario.clear()
    clear()

    placing_obstacles = False
    map_widget.add_left_click_map_command(getFenceWaypoint)

    messagebox.showinfo("¡Listo!", f"Escenario '{escenario_name}' registrado correctamente.")


# genera el poligono que aproxima al círculo
def getCircle(lat, lon, radius):
    # aquí creo el polígono que aproxima al círculo
    geod = Geodesic.WGS84
    points = []
    for angle in range(0, 360, 5):  # 5 grados de separación para suavidad
        # me da las coordenadas del punto que esta a una distancia radius del centro (lat, lon) con el ángulo indicado
        g = geod.Direct(lat, lon, angle, radius)
        lat2 = float(g["lat2"])
        lon2 = float(g["lon2"])
        points.append((lat2, lon2))
    return points


############################ Funciones para seleccionar multi escenario ##########################################
def selectBtnClick():
    global scenarios, current, polys
    global selectFrame, gameModeFrame
    global multiScenario, scenario, obstacles

    multiScenario = {'numPlayers': 0, 'scenarios': []}
    scenario = []
    obstacles.clear()

    # Limpia el mapa por si hay cosas dibujadas
    scenarios = []
    clear()

    # Sigue tu lógica actual:
    createFrame.grid_forget()
    superviseFrame.grid_forget()

    # Mostrar primero modo de juego y luego selección de escenario
    gameModeFrame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    selectFrame.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    selectBtn['text'] = 'Seleccionando...'
    selectBtn['fg'] = 'white'
    selectBtn['bg'] = 'green'

    createBtn['text'] = 'Crear'
    createBtn['fg'] = 'black'
    createBtn['bg'] = 'dark orange'

    superviseBtn['text'] = 'Supervisar'
    superviseBtn['fg'] = 'black'
    superviseBtn['bg'] = 'dark orange'

    # No mostrar disparo ni controles hasta que empiece el juego
    startGameBtn.grid_remove()
    for widget in controlFrame.winfo_children():
        if isinstance(widget, tk.LabelFrame) and widget.cget("text") == "Opciones de Disparo":
            widget.grid_remove()
    controlButtonsFrame.grid_remove()
    mostrar_controles_juego()
    mantener_escenario_visible()


# una vez elegido el numero de jugadores mostramos los multi escenarios que hay para ese número de jugadores
def selectScenarios(num):
    global scenarios, current, polys, drawingAction, traces
    global numPlayers, client, swarm

    numPlayers = num
    scenarios = []

    for file in glob.glob("competencia/*_" + str(num) + ".png"):
        scene = Image.open(file).resize((300, 200))
        scenarios.append({'name': file.split('.')[0], 'pic': ImageTk.PhotoImage(scene)})

    if len(scenarios) > 0:
        scenarioCanvas.create_image(0, 0, image=scenarios[0]['pic'], anchor=tk.NW)
        current = 0
        prevBtn['state'] = tk.DISABLED
        nextBtn['state'] = tk.NORMAL if len(scenarios) > 1 else tk.DISABLED
        sendBtn['state'] = tk.DISABLED
    else:
        messagebox.showinfo("showinfo", "No hay escenarios para elegir")

    # Inicializar el autopilot
    additionalEvents = [
        {'event': 'startDrawing', 'method': startDrawing},
        {'event': 'stopDrawing', 'method': stopDrawing},
        {'event': 'startRemovingDrawing', 'method': startRemovingDrawing},
        {'event': 'stopRemovingDrawing', 'method': stopRemovingDrawing},
        {'event': 'removeAll', 'method': removeAll}
    ]
    autopilotService = AutopilotController(numPlayers, numPlayers, additionalEvents)
    client, swarm = autopilotService.start()


# mostrar anterior
def showPrev():
    global current
    current = current - 1
    # mostramos el multi escenario anterior
    scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
    # deshabilitamos botones si no hay anterior o siguiente
    if current == 0:
        prevBtn['state'] = tk.DISABLED
    else:
        prevBtn['state'] = tk.NORMAL
    if current == len(scenarios) - 1:
        nextBtn['state'] = tk.DISABLED
    else:
        nextBtn['state'] = tk.NORMAL


# mostrar siguiente
def showNext():
    global current
    current = current + 1
    # muestro el siguiente
    scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
    # deshabilitamos botones si no hay anterior o siguiente
    if current == 0:
        prevBtn['state'] = tk.DISABLED
    else:
        prevBtn['state'] = tk.NORMAL
    if current == len(scenarios) - 1:
        nextBtn['state'] = tk.DISABLED
    else:
        nextBtn['state'] = tk.NORMAL


def clear():
    global paths, polys, fence, numPlayers, obstacles, placing_obstacles
    global multiScenario, scenario, mode_selected, name
    global createBtn, selectPlayersFrame

    # Reinicializa el contenido del campo nombre (de la entrada)
    name.set("")

    # Borrar los elementos gráficos del mapa
    for path in paths:
        path.delete()
    paths.clear()

    for poly in polys:
        try:
            poly.delete()
        except:
            pass
    polys.clear()

    # Reiniciar la variable fence y limpiar obstáculos
    fence = None
    obstacles.clear()

    # Reinicializar las estructuras de escenario
    scenario = []
    multiScenario = {'numPlayers': 0, 'scenarios': []}
    numPlayers = 0
    mode_selected = False  # Se sale del modo "creando"
    placing_obstacles = False
    map_widget.add_left_click_map_command(getFenceWaypoint)  # Restablecer el callback

    # Restablecer el botón "Crear" a su estado original
    createBtn['text'] = 'Crear'
    createBtn['fg'] = 'black'
    createBtn['bg'] = 'dark orange'

    # Borrar y reconstruir la sección de selección de número de jugadores
    for widget in selectPlayersFrame.winfo_children():
        widget.destroy()

    tk.Label(selectPlayersFrame, text='Selecciona el número de jugadores') \
        .grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N+tk.E+tk.W)
    # Configurar las columnas para que se expandan proporcionalmente
    for i in range(4):
        selectPlayersFrame.columnconfigure(i, weight=1)
    # Crear botones para 1 a 4 jugadores
    for i in range(1, 5):
        tk.Button(
            selectPlayersFrame,
            text=str(i),
            bg="dark orange",
            font=("Arial", 9),
            command=lambda n=i: selectNumPlayers(n)
        ).grid(row=1, column=i - 1, padx=5, pady=5, sticky="nsew")
    createBtnClick()


# borramos el escenario que esta a la vista
def deleteScenario():
    global current

    msg_box = messagebox.askquestion(
        "Confirmar eliminación",
        "¿Estás seguro de que quieres eliminar el escenario?",
        icon="warning",
    )
    if msg_box == "yes":
        # Si el usuario confirma, borramos los archivos
        os.remove(scenarios[current]['name'] + '.png')
        os.remove(scenarios[current]['name'] + '.json')
        scenarios.remove(scenarios[current])

        # Muestro el siguiente (o anterior) escenario si hay más
        if len(scenarios) != 0:
            if len(scenarios) == 1:
                current = 0
                scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
                prevBtn['state'] = tk.DISABLED
                nextBtn['state'] = tk.DISABLED
            else:
                if current == 0:
                    scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
                    prevBtn['state'] = tk.DISABLED
                    if len(scenarios) > 1:
                        nextBtn['state'] = tk.NORMAL
                else:
                    scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
                    prevBtn['state'] = tk.NORMAL
                    if current == len(scenarios) - 1:
                        nextBtn['state'] = tk.DISABLED
                    else:
                        nextBtn['state'] = tk.NORMAL

            # Limpia el mapa si corresponde
            clear()
    else:
        # Si el usuario cancela, no hacemos nada
        return


# dibujamos en el mapa el multi escenario
def drawScenario(multiScenario):
    global polys

    # borro los elementos que haya en el mapa
    for poly in polys:
        poly.delete()
    # vamos a recorrer la lista de escenarios
    scenarios = multiScenario['scenarios']
    for element in scenarios:
        color = element['player']
        # cojo el escenario de este cugador
        scenario = element['scenario']
        # ahora dibujamos el escenario
        # el primer fence es el de inclusión
        inclusion = scenario[0]
        if inclusion['type'] == 'polygon':
            poly = []
            for point in inclusion['waypoints']:
                poly.append((point['lat'], point['lon']))
            polys.append(map_widget.set_polygon(poly,
                                                outline_color=color,
                                                fill_color=color,
                                                border_width=3))
        else:
            # el fence es un círculo. Como no puedo dibujar circulos en el mapa
            # creo el polígono que aproximará al círculo
            poly = getCircle(inclusion['lat'], inclusion['lon'], inclusion['radius'])
            polys.append(map_widget.set_polygon(poly,
                                                outline_color=color,
                                                fill_color=color,
                                                border_width=3))
        # ahora voy a dibujar los obstáculos
        for i in range(1, len(scenario)):
            fence = scenario[i]
            if fence['type'] == 'polygon':
                poly = []
                for point in fence['waypoints']:
                    poly.append((point['lat'], point['lon']))
                polys.append(map_widget.set_polygon(poly,
                                                    outline_color="black",
                                                    fill_color="black",
                                                    border_width=3,
                                                    polygon_type="obstacle"
                                                    ))

            else:
                poly = getCircle(fence['lat'], fence['lon'], fence['radius'])
                polys.append(map_widget.set_polygon(poly,
                                                    outline_color="black",
                                                    fill_color="black",
                                                    border_width=3,
                                                    polygon_type="obstacle"
                                                    ))


# seleccionar el multi escenario que está a la vista
def selectScenario():
    global polys, selectedMultiScenario, placing_obstacles, obstacles
    placing_obstacles = False  # Desactivar colocación de obstáculos al seleccionar un mapa

    for poly in polys:
        poly.delete()

    with open(scenarios[current]['name'] + '.json') as f:
        selectedMultiScenario = json.load(f)

    obstacles.clear()
    for scn in selectedMultiScenario['scenarios']:

        for obs in scn['scenario'][1:]:
            obstacles.append(obs)

    drawScenario(selectedMultiScenario)
    sendBtn['state'] = tk.NORMAL


# envia los datos del multi escenario seleccionado al enjambre
def sendScenario():
    global swarm, selectedMultiScenario, obstacles

    if not selectedMultiScenario:
        messagebox.showinfo("Error", "No hay escenario seleccionado.")
        return

    # Agregar los obstáculos a cada subescenario
    for scenario in selectedMultiScenario['scenarios']:
        scenario['scenario'].extend(obstacles)

    # Función auxiliar para enviar el escenario a un dron
    def send_to_drone(idx):
        try:
            swarm[idx].setScenario(selectedMultiScenario['scenarios'][idx]['scenario'])
        except Exception as e:
            print(f"Error al enviar escenario al dron {idx}: {e}")

    threads = []
    # Enviar a cada dron en un hilo separado
    for i in range(len(swarm)):
        t = threading.Thread(target=send_to_drone, args=(i,), daemon=True)
        threads.append(t)
        t.start()

    # Esperar (con timeout) a que todos los hilos terminen para no bloquear la interfaz indefinidamente
    for t in threads:
        t.join(timeout=10)

    sendBtn['bg'] = 'green'
    # Mostrar las opciones de configuración y asignar zonas a cada jugador
    mostrar_configuracion_juego()
    assign_player_zones()


# configuración del frame con los botones 2 min, 5 min, 8 min y supervivencia
def mostrar_configuracion_juego():
    global configuracionFrame, numPlayers

    configuracionFrame.grid(row=8, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

    # Limpiar cualquier botón previo
    for widget in configuracionFrame.winfo_children():
        widget.destroy()

    # --- Botones de tiempo y supervivencia ---
    tk.Button(configuracionFrame, text="2 min", bg="dark orange",
              command=lambda: seleccionar_configuracion_tiempo(2)) \
        .grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

    tk.Button(configuracionFrame, text="5 min", bg="dark orange",
              command=lambda: seleccionar_configuracion_tiempo(5)) \
        .grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    tk.Button(configuracionFrame, text="8 min", bg="dark orange",
              command=lambda: seleccionar_configuracion_tiempo(8)) \
        .grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

    tk.Button(configuracionFrame, text="Modo Supervivencia", bg="dark orange",
              command=seleccionar_modo_supervivencia) \
        .grid(row=0, column=3, padx=5, pady=5, sticky="nsew")

    # Si tenemos 4 jugadores, mostramos “2 vs 2”
    if numPlayers == 4:
        tk.Button(configuracionFrame, text="2 vs 2", bg="dark orange",
                  command=seleccionar_tiempo_teams
                  ) \
            .grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")


def seleccionar_tiempo_teams():
    global game_mode, game_duration, survival_mode

    game_mode = "teams"  # Modo de juego 2 vs 2

    # Creamos la ventana emergente
    top = tk.Toplevel()
    top.title("Tiempo de Juego (2 vs 2)")
    top.geometry("700x550")
    top.grab_set()  # Evita clics fuera hasta que se cierre

    tk.Label(
        top,
        text="Selecciona la duración\npara el modo 2 vs 2",
        font=("Arial", 10, "bold")
    ).pack(pady=10)

    # Función para asignar un tiempo en minutos
    def set_tiempo(minutos):
        global game_duration, survival_mode
        survival_mode = False          # Desactivamos supervivencia
        game_duration = minutos * 60   # Convertimos a segundos
        top.destroy()                  # Cerramos la ventana emergente
        configuracionFrame.grid_remove()   # Oculta tu frame de config
        startGameBtn.grid(row=9, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        messagebox.showinfo("Modo 2 vs 2", f"Has seleccionado {minutos} minutos.")

    # Función para modo supervivencia
    def set_supervivencia():
        global survival_mode, game_duration
        survival_mode = True
        game_duration = None           # Sin límite de tiempo
        top.destroy()
        configuracionFrame.grid_remove()
        startGameBtn.grid(row=9, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        messagebox.showinfo("Modo 2 vs 2", "Has seleccionado Modo Supervivencia.")

    # Botones para cada opción
    tk.Button(top, text="2 min", bg="dark orange", command=lambda: set_tiempo(2)) \
        .pack(pady=5, fill="x")
    tk.Button(top, text="5 min", bg="dark orange", command=lambda: set_tiempo(5)) \
        .pack(pady=5, fill="x")
    tk.Button(top, text="8 min", bg="dark orange", command=lambda: set_tiempo(8)) \
        .pack(pady=5, fill="x")

    tk.Button(top, text="Modo Supervivencia", bg="dark orange", command=set_supervivencia) \
        .pack(pady=10, fill="x")


# Al seleccionar tiempo
def seleccionar_configuracion_tiempo(minutos):
    global game_duration, survival_mode
    survival_mode = False
    game_duration = minutos * 60
    messagebox.showinfo("Tiempo del Juego", f"Tiempo configurado a {minutos} minutos.")
    ocultar_botones_configuracion()


# Al seleccionar supervivencia
def seleccionar_modo_supervivencia():
    global survival_mode, game_duration
    survival_mode = True
    game_duration = None  # Juego sin límite de tiempo
    messagebox.showinfo("Modo Supervivencia", "Modo supervivencia activado.")
    ocultar_botones_configuracion()


# oculta los botones tras haber elegido una opción
def ocultar_botones_configuracion():
    global configuracionFrame, startGameBtn

    for widget in configuracionFrame.winfo_children():
        widget.destroy()

    configuracionFrame.grid_remove()

    # Muestra solo el botón de iniciar juego
    startGameBtn.grid(row=9, column=0, columnspan=3, padx=5, pady=5, sticky="ew")


# ubicación de las opciones de disparo
def display_shooting_options():
    shootingFrame = tk.LabelFrame(controlFrame, text='Opciones de Disparo', font=("Arial", 8, "bold"))
    shootingFrame.grid(row=9, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

    # Configurar las columnas para expandirse proporcionalmente
    for i in range(3):
        shootingFrame.columnconfigure(i, weight=1)

    tk.Button(shootingFrame, text="Bala Pequeña", bg="dark orange",
              command=lambda: shoot(active_player_id, "small_fast")) \
        .grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
    tk.Button(shootingFrame, text="Bala Mediana", bg="dark orange",
              command=lambda: shoot(active_player_id, "medium")) \
        .grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
    tk.Button(shootingFrame, text="Bala Grande", bg="dark orange",
              command=lambda: shoot(active_player_id, "large_slow")) \
        .grid(row=0, column=2, padx=5, pady=5, sticky="nsew")


# carga el multi escenario que hay ahora en el enjambre
def loadScenario():
    # voy a mostrar el escenario que hay cargado en el dron
    global connected, dron

    if not connected:
        dron = Dron()
        connection_string = 'tcp:127.0.0.1:5763'
        baud = 115200
        dron.connect(connection_string, baud)
        connected = True
    scenario = dron.getScenario()
    if scenario:
        drawScenario(scenario)
    else:
        messagebox.showinfo("showinfo","No hay ningún escenario cargado en el dron")


def punto_dentro_poligono(point, polygon):
    # Asegúrate que es dict con lat/lon
    if isinstance(point, dict):
        lat, lon = float(point['lat']), float(point['lon'])
    else:
        lat, lon = float(point[0]), float(point[1])  # fallback si es tupla

    inside = False
    j = len(polygon) - 1

    for i in range(len(polygon)):
        p1 = polygon[i]
        p2 = polygon[j]

        if not isinstance(p1, dict) or 'lat' not in p1 or 'lon' not in p1:
            continue  # ignora puntos mal formateados

        lat_i = float(p1['lat'])
        lon_i = float(p1['lon'])
        lat_j = float(p2['lat'])
        lon_j = float(p2['lon'])

        if ((lon_i > lon) != (lon_j > lon)) and \
                (lat < (lat_j - lat_i) * (lon - lon_i) / ((lon_j - lon_i) + 1e-12) + lat_i):
            inside = not inside
        j = i

    return inside


def mover_dron(dron, nueva_pos, player_id=None):
    # Si el dron no está "active", no se mueve
    if players[player_id]['status'] != 'active':
        print(f"El dron {player_id} está en estado {players[player_id]['status']} y no puede moverse.")
        return

    if verificar_colision(nueva_pos, player_id):
        print(f"Jugador {player_id} intenta passar per un obstacle. Tornant a la posició anterior.")
        if player_id in last_valid_positions:
            prev_pos = last_valid_positions[player_id]
            dron.goto(prev_pos[0], prev_pos[1], 5)
        return
    dron.goto(nueva_pos[0], nueva_pos[1], 5)
    last_valid_positions[player_id] = nueva_pos


#Devuelve el obstáculo en 'pos' si 'pos' está dentro de su polígono, o None si no hay obstáculo ahí
def obtener_obstaculo_en_pos(pos):
    for obstacle in obstacles:
        if obstacle['type'] == 'polygon':
            if punto_dentro_poligono(pos, obstacle['waypoints']):
                return obstacle
    return None


def verificar_colision(pos, player_id=None):
    # Verificar obstáculos definidos en tiempo real
    for obs in obstacles:
        if obs["type"] == "polygon":
            if punto_dentro_poligono(pos, obs["waypoints"]):
                return True
        elif obs["type"] == "circle":
            center = (obs["lat"], obs["lon"])
            radius = obs["radius"]
            if geopy.distance.geodesic(center, pos).m <= radius:
                return True

    # Verificar los obstáculos definidos en el escenario del jugador
    if player_id is not None and selectedMultiScenario:
        player_scenario = selectedMultiScenario["scenarios"][player_id]["scenario"]
        for obs in player_scenario[1:]:  # El primero es el área permitida, los siguientes son obstáculos
            if obs["type"] == "polygon":
                if punto_dentro_poligono(pos, obs["waypoints"]):
                    return True
            elif obs["type"] == "circle":
                center = (obs["lat"], obs["lon"])
                radius = obs["radius"]
                if geopy.distance.geodesic(center, pos).m <= radius:
                    return True

    return False


def esquivar_obstaculo(dron, nueva_pos):
    # Lógica simple para esquivar obstáculos: intentar moverse en una dirección ligeramente diferente
    delta = 0.0001  # Pequeño cambio en la posición
    alternativas = [
        (nueva_pos[0] + delta, nueva_pos[1]),
        (nueva_pos[0] - delta, nueva_pos[1]),
        (nueva_pos[0], nueva_pos[1] + delta),
        (nueva_pos[0], nueva_pos[1] - delta)
    ]
    for alt_pos in alternativas:
        if not verificar_colision(alt_pos):
            dron.go_to(alt_pos)
            return
    print("No se encontró una ruta alternativa.")


def eliminar_obstaculo(coords):
    global obstacles, polys

    # Convertimos coords a un diccionario lat/lon para reusar tu "punto_dentro_poligono"
    click_point = {'lat': coords[0], 'lon': coords[1]}

    # Recorremos la lista de obstáculos al revés para poder borrar
    for obs in reversed(obstacles):
        if obs['type'] == 'polygon':
            if punto_dentro_poligono(click_point, obs['waypoints']):
                # Lo eliminamos de 'obstacles'
                obstacles.remove(obs)
                # Y del mapa
                obs_points = [(p['lat'], p['lon']) for p in obs['waypoints']]
                for poly in polys[:]:
                    if list(poly.position_list) == obs_points:
                        poly.delete()
                        polys.remove(poly)
                        break
                break  # dejamos de buscar tras eliminar uno


def distancia(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def snap_a_vecino(click_coords, width, height, inclinacion_deg, margen_snap=0.0000125, gap=0.0000002):
    rad = math.radians(inclinacion_deg)
    cos_r, sin_r = math.cos(rad), math.sin(rad)

    direcciones = [
        (2 * width + gap, 0),   # Derecha
        (-2 * width - gap, 0),  # Izquierda
        (0, 2 * height + gap),  # Arriba
        (0, -2 * height - gap)  # Abajo
    ]

    for obstaculo in obstacles:
        wp = obstaculo['waypoints']
        centro = (
            sum(p['lat'] for p in wp) / 4,
            sum(p['lon'] for p in wp) / 4
        )

        for dx, dy in direcciones:
            dx_rot = dx * cos_r - dy * sin_r
            dy_rot = dx * sin_r + dy * cos_r
            candidato = (centro[0] + dx_rot, centro[1] + dy_rot)

            dist = math.hypot(candidato[0] - click_coords[0], candidato[1] - click_coords[1])
            if dist < margen_snap:
                return candidato  # Retorna posición encajada

    return click_coords  # Si no encaja con ninguno, deja la posición original


def fence_to_waypoints(fence):

    if fence["type"] == "polygon":
        return fence["waypoints"]

    elif fence["type"] == "circle":
        circle_points = getCircle(fence["lat"], fence["lon"], fence["radius"])
        return [{"lat": lat, "lon": lon} for (lat, lon) in circle_points]

    else:
        return []


def get_bounding_box_from_waypoints(waypoints):
    lats = [p["lat"] for p in waypoints]
    lons = [p["lon"] for p in waypoints]

    return {
        'min_lat': min(lats),
        'max_lat': max(lats),
        'min_lon': min(lons),
        'max_lon': max(lons)
    }


def mirror_obstacle(obstacle):

    if selectedMultiScenario and selectedMultiScenario.get('scenarios'):
        scenario_source = selectedMultiScenario
    else:
        scenario_source = multiScenario

    # Cantidad real de jugadores
    total_players = scenario_source.get('numPlayers', 0)

    # -- FENCE DEL JUGADOR 0 (Rojo) --
    fence_roja = scenario_source['scenarios'][0]['scenario'][0]
    red_poly = fence_to_polygon(fence_roja)

    # REFLEJO HACIA EL JUGADOR 1 (Azul) SOLO SI >=2 JUGADORES
    if total_players >= 2:
        fence_azul = scenario_source['scenarios'][1]['scenario'][0]
        blue_poly = fence_to_polygon(fence_azul)

        new_obs_blue = mirror_obstacle_center_to_center(obstacle, red_poly, blue_poly)
        if new_obs_blue:
            obstacles.append(new_obs_blue)
            poly_draw = map_widget.set_polygon(
                [(p['lat'], p['lon']) for p in new_obs_blue['waypoints']],
                fill_color='black', outline_color='black', border_width=1
            )
            polys.append(poly_draw)

    # REFLEJO HACIA EL JUGADOR 2 (Verde) SOLO SI >=3 JUGADORES
    if total_players >= 3:
        fence_verde = scenario_source['scenarios'][2]['scenario'][0]
        green_poly = fence_to_polygon(fence_verde)

        new_obs_green = mirror_obstacle_center_to_center(obstacle, red_poly, green_poly)
        if new_obs_green:
            obstacles.append(new_obs_green)
            poly_draw = map_widget.set_polygon(
                [(p['lat'], p['lon']) for p in new_obs_green['waypoints']],
                fill_color='black', outline_color='black', border_width=1
            )
            polys.append(poly_draw)

    # REFLEJO HACIA EL JUGADOR 3 (Amarillo) SOLO SI ==4 JUGADORES
    if total_players >= 4:
        fence_amarilla = scenario_source['scenarios'][3]['scenario'][0]
        yellow_poly = fence_to_polygon(fence_amarilla)

        new_obs_yellow = mirror_obstacle_center_to_center(obstacle, red_poly, yellow_poly)
        if new_obs_yellow:
            obstacles.append(new_obs_yellow)
            poly_draw = map_widget.set_polygon(
                [(p['lat'], p['lon']) for p in new_obs_yellow['waypoints']],
                fill_color='black', outline_color='black', border_width=1
            )
            polys.append(poly_draw)


def fence_to_polygon(fence):
    if fence["type"] == "polygon":
        coords = [(p["lon"], p["lat"]) for p in fence["waypoints"]]
        return Polygon(coords)
    elif fence["type"] == "circle":
        circle_pts = getCircle(fence["lat"], fence["lon"], fence["radius"])
        coords = [(lon, lat) for (lat, lon) in circle_pts]
        return Polygon(coords)
    else:
        return None

import math
from shapely.geometry import Polygon, LineString
from shapely import affinity

def mirror_obstacle_center_to_center(obstacle, red_poly, blue_poly):

    # Convertir obstáculo a Polygon de Shapely (si es circle, convertir primero)
    if obstacle['type'] == 'circle':
        circle_pts = getCircle(obstacle['lat'], obstacle['lon'], obstacle['radius'])
        obstacle['waypoints'] = [{'lat': p[0], 'lon': p[1]} for p in circle_pts]
        obstacle['type'] = 'polygon'

    obs_coords = [(pt['lon'], pt['lat']) for pt in obstacle['waypoints']]
    obs_poly = Polygon(obs_coords)
    if obs_poly.is_empty:
        print("Obstáculo vacío, nada que reflejar.")
        return None

    # Hallar centroides de rojos y azules
    centro_rojo = red_poly.centroid
    centro_azul = blue_poly.centroid

    # Crear una línea de 'eje' => de centro_rojo a centro_azul
    eje_line = LineString([centro_rojo, centro_azul])
    if eje_line.length == 0:
        print("Los centros de rojo y azul son idénticos, no hay línea para reflejar.")
        return None

    # Calcular ángulo de esa línea para “acostarla” (rotar a horizontal)
    x0, y0 = eje_line.coords[0]
    x1, y1 = eje_line.coords[1]
    dx = x1 - x0
    dy = y1 - y0
    angle_radians = math.atan2(dy, dx)
    angle_degs = -angle_radians * 180.0 / math.pi  # rotación en grados con signo

    # Rotamos el obstáculo => la línea pasa a estar horizontal
    origin_pt = eje_line.centroid
    obs_rotado = affinity.rotate(obs_poly, angle_degs, origin=origin_pt, use_radians=False)

    # Flip horizontal (x=-1) en torno al mismo 'origin_pt'
    obs_flipped = affinity.scale(obs_rotado, xfact=-1, yfact=1, origin=origin_pt)

    # Desrotamos volviendo a +angle
    obs_final = affinity.rotate(obs_flipped, -angle_degs, origin=origin_pt, use_radians=False)

    # Intersección con la zona azul (para no salirnos)
    intersec = obs_final.intersection(blue_poly)
    if intersec.is_empty:
        print("No hay intersección tras reflejar, nada que mostrar.")
        return None

    # Manejar si es MultiPolygon
    if intersec.geom_type == 'MultiPolygon':
        biggest_area = 0
        chosen_poly = None
        for geom in intersec.geoms:
            if geom.area > biggest_area:
                biggest_area = geom.area
                chosen_poly = geom
        if not chosen_poly:
            return None
        intersec = chosen_poly

    if intersec.geom_type != 'Polygon':
        print(f"Intersección final no es polígono simple: {intersec.geom_type}")
        return None

    # Convertir a dict con waypoints lat/lon
    final_coords = list(intersec.exterior.coords)
    new_wps = [{'lat': y, 'lon': x} for (x, y) in final_coords]
    return {
        'type': 'polygon',
        'waypoints': new_wps,
        'altitude': obstacle.get('altitude', 5)
    }


def punto_dentro_poligonos_dibujados(punto):
    for poly in polys:
        try:
            vertices = poly.position_list
            if punto_dentro_poligono_dic(punto, vertices):
                return True
        except:
            continue
    return False


def punto_dentro_poligono_dic(p, poly):
    x, y = p
    inside = False
    j = len(poly) - 1

    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def createPlayer(color):
    global colorIcon, selectedColor, scenario, player_fences_completed, multiScenario
    selectedColor = color

    if color not in player_fences_completed:
        player_fences_completed[color] = False

    if color == 'red':

        if 'Crea' in redPlayerBtn['text']:
            colorIcon = red
            redPlayerBtn['text'] = "Definiendo límites del escenario rojo..."
            scenario = []

        elif 'Definiendo' in redPlayerBtn['text']:
            redPlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario rojo"
            player_fences_completed['red'] = True

            # Añadimos el escenario al multiScenario
            multiScenario['scenarios'].append({
                'player': 'red',
                'scenario': scenario.copy()
            })
            messagebox.showinfo("Escenario Creado", "Escenario 'Rojo' creado con éxito")

    elif color == 'blue':

        if 'Crea' in bluePlayerBtn['text']:
            colorIcon = blue
            bluePlayerBtn['text'] = "Definiendo límites del escenario azul..."
            scenario = []

        elif 'Definiendo' in bluePlayerBtn['text']:
            bluePlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario azul"
            player_fences_completed['blue'] = True
            multiScenario['scenarios'].append({
                'player': 'blue',
                'scenario': scenario.copy()
            })
            messagebox.showinfo("Escenario Creado", "Escenario 'Azul' creado con éxito")

    elif color == 'green':

        if 'Crea' in greenPlayerBtn['text']:
            colorIcon = green
            greenPlayerBtn['text'] = "Definiendo límites del escenario verde..."
            scenario = []

        elif 'Definiendo' in greenPlayerBtn['text']:
            greenPlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario verde"
            player_fences_completed['green'] = True
            multiScenario['scenarios'].append({
                'player': 'green',
                'scenario': scenario.copy()
            })
            messagebox.showinfo("Escenario Creado", "Escenario 'Verde' creado con éxito")

    elif color == 'yellow':

        if 'Crea' in yellowPlayerBtn['text']:
            colorIcon = yellow
            yellowPlayerBtn['text'] = "Definiendo límites del escenario amarillo..."
            scenario = []

        elif 'Definiendo' in yellowPlayerBtn['text']:
            yellowPlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario amarillo"
            player_fences_completed['yellow'] = True
            multiScenario['scenarios'].append({
                'player': 'yellow',
                'scenario': scenario.copy()
            })
            messagebox.showinfo("Escenario Creado", "Escenario 'Amarillo' creado con éxito")

    check_all_fences_completed()


# elijo el número de jugadores
def selectNumPlayers(num):
    global redPlayerBtn, bluePlayerBtn, greenPlayerBtn, yellowPlayerBtn
    global multiScenario
    global numPlayers
    global buttons
    global selectPlayersFrame

    for b in buttons:
        if b is not None:
            b.destroy()
    buttons.clear()

    for widget in selectPlayersFrame.winfo_children():
        if isinstance(widget, tk.Button) and "Crea el escenario para el jugador" in widget.cget("text"):
            widget.destroy()

    # Fijas el número de jugadores y reinicias la estructura multiScenario
    numPlayers = num
    multiScenario = {
        'numPlayers': num,
        'scenarios': []
    }

    # Creamos tantos botones como numPlayers
    colors = [('red', 'rojo'), ('blue', 'azul'), ('green', 'verde'), ('yellow', 'amarillo')]

    for i in range(num):
        color, label = colors[i]
        btn = tk.Button(
            selectPlayersFrame,
            text=f"Crea el escenario para el jugador {label}",
            bg=color,
            fg="white",
            font=("Arial", 8, "bold"),
            width=25,
            height=2,
            command=lambda c=color: createPlayer(c)
        )
        btn.grid(row=2 + i, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
        buttons.append(btn)

    while len(buttons) < 4:
        buttons.append(None)

    redPlayerBtn, bluePlayerBtn, greenPlayerBtn, yellowPlayerBtn = buttons[0], buttons[1], buttons[2], buttons[3]


#Verifica si todos los jugadores han definido su área y cierra el fence. Luego habilita la colocación de obstáculos.
def check_all_fences_closed():
    global numPlayers, multiScenario, map_widget
    if len(multiScenario['scenarios']) == numPlayers:  # Si ya se definieron todas las áreas
        messagebox.showinfo("Configuración de Obstáculos", "Pon en el mapa los obstáculos")
        map_widget.add_left_click_map_command(colocar_obstaculo)


def esperar_telemetria_valida(dron, timeout=8):
    print("Esperando telemetría válida del dron...")
    start = time.time()
    while time.time() - start < timeout:
        if dron.lat != 0 and dron.lon != 0:
            print(f"Telemetría válida: ({dron.lat}, {dron.lon})")
            return True
        time.sleep(1)
    return False


def get_bounding_box(waypoints):

    lats = [wp['lat'] for wp in waypoints]
    lons = [wp['lon'] for wp in waypoints]
    return {
        'min_lat': min(lats),
        'max_lat': max(lats),
        'min_lon': min(lons),
        'max_lon': max(lons)
    }


def mirror_and_rotate_obstacle_shapely(obstacle, base_fence, target_fence, angle_deg=60):
    base_bbox   = get_bounding_box(base_fence['waypoints'])
    target_bbox = get_bounding_box(target_fence['waypoints'])

    # Construir la lista de waypoints del obstáculo
    obs_wps = obstacle['waypoints']  # [{'lat':..., 'lon':...}, ...]

    mirrored_coords = []
    for wp in obs_wps:
        lat = wp['lat']
        lon = wp['lon']

        # Posición normalizada en la zona base (0..1)
        rel_lat = (lat - base_bbox['min_lat']) / (base_bbox['max_lat'] - base_bbox['min_lat'] + 1e-12)
        rel_lon = (lon - base_bbox['min_lon']) / (base_bbox['max_lon'] - base_bbox['min_lon'] + 1e-12)

        # Reflejamos en el eje horizontal => invertimos 'lon'
        new_lat = target_bbox['min_lat'] + rel_lat * (target_bbox['max_lat'] - target_bbox['min_lat'])
        new_lon = target_bbox['max_lon'] - rel_lon * (target_bbox['max_lon'] - target_bbox['min_lon'])

        mirrored_coords.append( (new_lon, new_lat) )  # en shapely: (x, y)=(lon, lat)

    # 2) Crear polígono shapely a partir de mirrored_coords
    poly_mirrored = Polygon(mirrored_coords)

    # 3) Rotar -20° (en grados; origin='centroid' o un punto X)
    #  Nota: Con shapely, rotate(geom, angle, use_radians=False) rota en sentido antihorario.
    rotated_poly = rotate(poly_mirrored, angle_deg, origin='centroid', use_radians=False)

    # 4) Extraer las coords finales en formato lat/lon
    final_waypoints = []
    for (x, y) in rotated_poly.exterior.coords:
        final_waypoints.append({'lat': y, 'lon': x})

    # 5) Construir el nuevo obstáculo
    new_obstacle = {
        'type': 'polygon',
        'waypoints': final_waypoints,
        'altitude': obstacle.get('altitude', 5)
    }
    return new_obstacle


def calcular_centro(waypoints):
    lat_sum = sum(p['lat'] for p in waypoints)
    lon_sum = sum(p['lon'] for p in waypoints)
    return lat_sum / len(waypoints), lon_sum / len(waypoints)


# Asegurar que map_widget está definido antes de usar add_left_click_map_command
def inicializar_mapa():
    global map_widget
    map_widget = tkintermapview.TkinterMapView(mapaFrame, width=2000, height=1200, corner_radius=0)
    map_widget.grid(row=1, column=0, padx=5, pady=5)
    map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)
    map_widget.set_position(41.2764478, 1.9886568)
    map_widget.set_zoom(20)


def startDrawing(id):
    global drawingAction
    print('start drawing')
    drawingAction[id] = 'startDrawing'


def stopDrawing(id):
    global drawingAction
    drawingAction[id] = 'nothing'


def startRemovingDrawing(id):
    global drawingAction
    drawingAction[id] = 'remove'


def stopRemovingDrawing(id):
    global drawingAction
    drawingAction[id] = 'nothing'


def removeAll(id):
    global traces
    for item in traces[id]:
        if item['marker'] != None:
            item['marker'].delete()
    traces[id] = []


################### Funciones para supervisar el multi escenario #########################
def superviseBtnClick():
    global gameModeFrame

    gameModeFrame.grid_remove()
    # quitamos los otros dos frames
    selectFrame.grid_forget()
    createFrame.grid_forget()
    # visualizamos el frame de creación
    superviseFrame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    createBtn['text'] = 'Crear'
    createBtn['fg'] = 'black'
    createBtn['bg'] = 'dark orange'

    selectBtn['text'] = 'Seleccionar'
    selectBtn['fg'] = 'black'
    selectBtn['bg'] = 'dark orange'

    superviseBtn['text'] = 'Supervisando...'
    superviseBtn['fg'] = 'white'
    superviseBtn['bg'] = 'green'

    # Ocultar el botón "Iniciar Juego" y las opciones de disparo
    startGameBtn.grid_remove()
    for widget in controlFrame.winfo_children():
        if isinstance(widget, tk.LabelFrame) and widget.cget("text") == "Opciones de Disparo":
            widget.grid_remove()

    controlButtonsFrame.grid_remove()
    mostrar_controles_juego()
    mantener_escenario_visible()


def setupControlButtons():
    global controlButtonsFrame

    controlButtonsFrame = tk.LabelFrame(controlFrame, text='Controles', font=("Arial", 8, "bold"))
    controlButtonsFrame.grid(row=9, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

    # Crear botones en la misma fila
    btn_pausar = tk.Button(controlButtonsFrame, text="Pausar", bg="dark orange", command=pauseGame)
    btn_pausar.grid(row=0, column=0, padx=3, pady=3, sticky="nsew")

    btn_reanudar = tk.Button(controlButtonsFrame, text="Reanudar", bg="dark orange", command=resumeGame)
    btn_reanudar.grid(row=0, column=1, padx=3, pady=3, sticky="nsew")

    btn_finalizar = tk.Button(controlButtonsFrame, text="Finalizar", bg="dark orange", command=endGame)
    btn_finalizar.grid(row=0, column=2, padx=3, pady=3, sticky="nsew")

    btn_reiniciar = tk.Button(controlButtonsFrame, text="Reiniciar", bg="dark orange", command=restartGame)
    btn_reiniciar.grid(row=0, column=3, padx=3, pady=3, sticky="nsew")

    # Asegurar que cada columna se expanda proporcionalmente
    for i in range(4):
        controlButtonsFrame.grid_columnconfigure(i, weight=1)

    controlButtonsFrame.grid_remove()


def mostrar_botones_cambio_dron():
    global active_player_id, numPlayers

    colores = ['Rojo', 'Azul', 'Verde', 'Amarillo']
    colores_fondos = ['red', 'blue', 'green', 'yellow']

    # Frame para los botones de control de jugador
    if hasattr(mostrar_botones_cambio_dron, "frame") and mostrar_botones_cambio_dron.frame.winfo_exists():
        mostrar_botones_cambio_dron.frame.destroy()

    frame = tk.LabelFrame(controlFrame, text="Seleccionar Dron Activo", font=("Arial", 8, "bold"))
    mostrar_botones_cambio_dron.frame = frame
    frame.grid(row=8, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

    for i in range(numPlayers):
        tk.Button(
            frame,
            text=f"Dron {colores[i]}",
            bg=colores_fondos[i],
            fg="white",
            font=("Arial", 8, "bold"),
            command=lambda idx=i: cambiar_dron(idx)
        ).grid(row=0, column=i, padx=3, pady=3, sticky="nsew")
        frame.grid_columnconfigure(i, weight=1)


def cambiar_dron(idx):
    global active_player_id

    active_player_id = idx
    colores = ['Rojo', 'Azul', 'Verde', 'Amarillo']
    messagebox.showinfo("Cambio de Control", f"Ahora controlas el dron: {colores[idx]}")


# creamos la ventana para gestionar los parámetros de los drones del enjambre
def adjustParameters():
    global swarm

    # voy a mostrar la ventana de gestión de los parámetros
    parameterManagementWindow = tk.Tk()
    parameterManagementWindow.title("Gestión de parámetros")
    parameterManagementWindow.rowconfigure(0, weight=1)
    parameterManagementWindow.rowconfigure(1, weight=1)

    # voy a crear un manager para cada dron
    managers = []

    for i in range(0, len(swarm)):
        parameterManagementWindow.columnconfigure(i, weight=1)
        dronManager = ParameterManager(parameterManagementWindow, swarm, i)
        managers.append(dronManager)
        # coloco el frame correspondiente a este manager en la ventana de gestión de parámetros
        dronFrame = dronManager.buildFrame()
        dronFrame.grid(row=0, column=i, padx=50, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)
    managers[0].setManagers(managers)
    tk.Button(parameterManagementWindow, text='Cerrar', bg="dark orange",
              command=lambda: parameterManagementWindow.destroy()) \
        .grid(row=1, column=0, columnspan=len(swarm), padx=2, pady=2, sticky=tk.N + tk.E + tk.W)

    parameterManagementWindow.mainloop()


def showQR():
    global QRimg
    QRWindow = tk.Toplevel()
    QRWindow.title("Código QR para mobile web app")
    QRWindow.rowconfigure(0, weight=1)
    QRWindow.rowconfigure(1, weight=1)
    QRWindow.columnconfigure(0, weight=1)

    QRimg = Image.open("images/QR.png")
    QRimg = ImageTk.PhotoImage(QRimg)
    label = tk.Label(QRWindow, image=QRimg)
    label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.S + tk.W)

    closeBtn = tk.Button(QRWindow, text="Cerrar", bg="dark orange", command=lambda: QRWindow.destroy())
    closeBtn.grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.S + tk.W)

    QRWindow.mainloop()


def eliminateDrone(drone_id):
    global eliminated_players, survival_mode

    players[drone_id]['status'] = 'eliminated'
    swarm[drone_id].Land(blocking=False)
    eliminated_players.add(drone_id)

    # Actualizar el icono del dron tras aterrizar (puedes usar un pequeño delay si es necesario)
    threading.Thread(target=update_drone_icon_on_landing, args=(drone_id,), daemon=True).start()

    if survival_mode:
        checkGameEnd()
    else:
        threading.Thread(target=respawnDrone, args=(drone_id,), daemon=True).start()


def update_drone_icon_on_landing(drone_id):
    pos = dronIcons[drone_id].position
    dronIcons[drone_id].delete()
    dronIcons[drone_id] = map_widget.set_marker(pos[0], pos[1],
                                                icon=dronLandedPictures[drone_id],
                                                icon_anchor="center")
    # Cambiar status a "landed"
    players[drone_id]['status'] = "landed"


def update_drone_icon_on_takeoff(drone_id):
    pos = dronIcons[drone_id].position
    dronIcons[drone_id].delete()
    dronIcons[drone_id] = map_widget.set_marker(pos[0], pos[1],
                                                icon=dronPictures[drone_id],
                                                icon_anchor="center")


def checkGameEnd():
    global survival_mode, players, game_mode

    # Jugadores vivos
    active_players = [p for p in players if p['status'] == 'active']

    #  Caso TODOS CONTRA TODOS en supervivencia
    if game_mode == "free_for_all" and survival_mode:
        if len(active_players) <= 1:
            if len(active_players) == 1:
                winner_id = active_players[0]['id']
                messagebox.showinfo("Fin del Juego",
                                    f"¡El jugador {winner_id + 1} ha ganado en modo supervivencia (último en pie)!")
            else:
                messagebox.showinfo("Fin del Juego", "No quedó ningún jugador con vida.")
            endGame()
            show_game_stats()
        return

    #  Caso 2 vs 2 en supervivencia
    if game_mode == "teams":
        # Contamos cuántos quedan activos en cada equipo
        active_team0 = sum(1 for p in players if p['team'] == 0 and p['status'] == 'active')
        active_team1 = sum(1 for p in players if p['team'] == 1 and p['status'] == 'active')

        # Si equipo 0 se quedó sin drones activos, gana equipo 1
        if active_team0 == 0:
            messagebox.showinfo("Fin del Juego", "¡Equipo Verde-Amarillo (drones 2 y 3) ha ganado!")
            endGame()
            show_game_stats()
            return

        # Si equipo 1 se quedó sin drones activos, gana equipo 0
        if active_team1 == 0:
            messagebox.showinfo("Fin del Juego", "¡Equipo Rojo-Azul (drones 0 y 1) ha ganado!")
            endGame()
            show_game_stats()
            return


# Mostrar estadísticas adaptadas
def displayResults():
    results = "Resultados:\n"

    if game_mode == "free_for_all":
        for player in players:
            results += f"Jugador {player['id']}: {player_scores[player['id']]} puntos\n"

    elif game_mode == "teams":
        team_scores = {"Rojo-Azul": player_scores[0] + player_scores[1],
                       "Verde-Amarillo": player_scores[2] + player_scores[3]}
        ganador = max(team_scores, key=team_scores.get)
        results += f"Equipo Rojo-Azul: {team_scores['Rojo-Azul']} puntos\n"
        results += f"Equipo Verde-Amarillo: {team_scores['Verde-Amarillo']} puntos\n"
        results += f"\nEquipo ganador: {ganador}!"


def crear_ventana():
    global startGameBtn
    global map_widget
    global createBtn, selectBtn, superviseBtn, createFrame, name, selectFrame, scene, scenePic, scenarios, current
    global superviseFrame
    global prevBtn, nextBtn, sendBtn, connectBtn
    global scenarioCanvas
    global i_wp, e_wp
    global paths, fence, polys
    global connected
    global selectPlayersFrame
    global red, blue, green, yellow, black, dronPictures
    global connectOption
    global playersCount
    global client
    global drawingAction, traces, dronLittlePictures
    global QRimg
    global colors
    global lock
    global telemetriaFrame, controlesFrame, controlFrame, mapaFrame
    global frontMarkers
    global gameModeFrame
    global dronPictures, dronLittlePictures, dronLandedPictures, colors, map_widget, dronIcons
    global bullet_small_image, bullet_medium_image, bullet_large_image

    playersCount = 0
    connected = False

    # aqui indicare, para cada dron, si estamos pintando o no
    drawingAction = ['nothing'] * 4  # nothing, draw o remove

    # y aqui ire guardando los rastros
    traces = [[], [], [], []]

    # para guardar datos y luego poder borrarlos
    paths = []
    fence = []
    polys = []
    frontMarkers = [None, None, None, None]

    ventana = tk.Tk()
    ventana.title("Gestión de escenarios")
    ventana.geometry('3100x1500')

    # El panel principal tiene una fila y dos columnas
    ventana.rowconfigure(0, weight=1)
    ventana.columnconfigure(0, weight=1)
    ventana.columnconfigure(1, weight=1)

    ventana.bind("<Up>", lambda e: mover_dron_teclado("arriba"))
    ventana.bind("<Down>", lambda e: mover_dron_teclado("abajo"))
    ventana.bind("<Left>", lambda e: mover_dron_teclado("izquierda"))
    ventana.bind("<Right>", lambda e: mover_dron_teclado("derecha"))
    ventana.bind("<space>", lambda e: disparar_con_teclado())

    # controlFrame = tk.LabelFrame(ventana, text = 'Control')
    controlFrame = tk.LabelFrame(ventana, text='Control', font=("Arial", 8, "bold"))
    controlFrame.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    # El frame de control aparece en la primera columna
    controlFrame.rowconfigure(0, weight=1)
    controlFrame.rowconfigure(1, weight=1)
    controlFrame.columnconfigure(0, weight=1)
    controlFrame.columnconfigure(1, weight=1)
    controlFrame.columnconfigure(2, weight=1)

    # Definir selectFrame antes de usarlo en selectBtnClick()
    selectFrame = tk.LabelFrame(controlFrame, text='Selecciona escenario', font=("Arial", 8, "bold"))

    # Frame de modos de juego (dentro de selectFrame)
    gameModeFrame = tk.LabelFrame(selectFrame, text='Modo de Juego')
    gameModeFrame.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    gameModeFrame.rowconfigure(0, weight=1)
    gameModeFrame.columnconfigure(0, weight=1)
    gameModeFrame.columnconfigure(1, weight=1)

    # Inicialmente, ocultamos el gameModeFrame
    gameModeFrame.grid_remove()

    # Ocultar el selectFrame al inicio (porque la pestaña inicial es "Crear")
    selectFrame.grid_forget()

    # botones para crear/seleccionar/supervisar
    createBtn = tk.Button(controlFrame, text="Crear", bg="dark orange", command=createBtnClick)
    createBtn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    selectBtn = tk.Button(controlFrame, text="Seleccionar", bg="dark orange", command=selectBtnClick)
    selectBtn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    superviseBtn = tk.Button(controlFrame, text="Supervisar", bg="dark orange", command=superviseBtnClick)
    superviseBtn.grid(row=0, column=2, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    ################################# frame para crear escenario  ###################################################
    createFrame = tk.LabelFrame(controlFrame, text='Crear escenario', font=("Arial", 8, "bold"))
    # la visualización del frame se hace cuando se clica el botón de crear
    createFrame.rowconfigure(0, weight=1)
    createFrame.rowconfigure(1, weight=1)
    createFrame.rowconfigure(2, weight=1)
    createFrame.rowconfigure(3, weight=1)
    createFrame.rowconfigure(4, weight=1)
    createFrame.rowconfigure(5, weight=1)
    createFrame.rowconfigure(6, weight=1)
    createFrame.rowconfigure(7, weight=1)
    createFrame.rowconfigure(8, weight=1)
    createFrame.rowconfigure(9, weight=1)
    createFrame.columnconfigure(0, weight=1)

    tk.Label(createFrame, text='Escribe el nombre aquí') \
        .grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    # el nombre se usará para poner nombre al fichero con la imagen y al fichero json con el escenario
    name = tk.StringVar()
    tk.Entry(createFrame, textvariable=name) \
        .grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    selectPlayersFrame = tk.LabelFrame(createFrame, text='Jugadores', font=("Arial", 8, "bold"))
    selectPlayersFrame.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")
    selectPlayersFrame.rowconfigure(0, weight=1)
    selectPlayersFrame.rowconfigure(1, weight=1)
    selectPlayersFrame.rowconfigure(2, weight=1)
    selectPlayersFrame.rowconfigure(3, weight=1)
    selectPlayersFrame.rowconfigure(4, weight=1)
    selectPlayersFrame.rowconfigure(5, weight=1)
    selectPlayersFrame.rowconfigure(6, weight=1)

    selectPlayersFrame.columnconfigure(0, weight=1)
    selectPlayersFrame.columnconfigure(1, weight=1)
    selectPlayersFrame.columnconfigure(2, weight=1)
    selectPlayersFrame.columnconfigure(3, weight=1)
    tk.Label(selectPlayersFrame, text='Selecciona el número de jugadores'). \
        grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="1", bg="dark orange", command=lambda: selectNumPlayers(1)) \
        .grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="2", bg="dark orange", command=lambda: selectNumPlayers(2)) \
        .grid(row=1, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="3", bg="dark orange", command=lambda: selectNumPlayers(3)) \
        .grid(row=1, column=2, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="4", bg="dark orange", command=lambda: selectNumPlayers(4)) \
        .grid(row=1, column=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    inclusionFenceFrame = tk.LabelFrame(createFrame, text='Definición de los límites del escenario')
    inclusionFenceFrame.grid(row=3, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    inclusionFenceFrame.rowconfigure(0, weight=1)
    inclusionFenceFrame.columnconfigure(0, weight=1)
    inclusionFenceFrame.columnconfigure(1, weight=1)

    # el fence de inclusión puede ser un poligono o un círculo
    # el parámetro 1 en el command indica que es fence de inclusion
    polyInclusionFenceBtn = tk.Button(inclusionFenceFrame, text="Polígono", bg="dark orange",
                                      command=lambda: definePoly(1))
    polyInclusionFenceBtn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    circleInclusionFenceBtn = tk.Button(inclusionFenceFrame, text="Círculo", bg="dark orange",
                                        command=lambda: defineCircle(1))
    circleInclusionFenceBtn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    registerBtn = tk.Button(createFrame, text="Registra escenario", bg="dark orange", command=registerScenario)
    registerBtn.grid(row=5, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    clearBtn = tk.Button(createFrame, text="Limpiar", bg="dark orange", command=clear)
    clearBtn.grid(row=6, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    ################################ frame para seleccionar escenarios ############################################
    selectFrame = tk.LabelFrame(controlFrame, text='Selecciona escenario', font=("Arial", 8, "bold"))

    # la visualización del frame se hace cuando se clica el botón de seleccionar
    selectFrame.rowconfigure(0, weight=1)
    selectFrame.rowconfigure(1, weight=1)
    selectFrame.rowconfigure(2, weight=1)
    selectFrame.rowconfigure(3, weight=1)
    selectFrame.rowconfigure(4, weight=1)
    selectFrame.rowconfigure(5, weight=1)
    selectFrame.rowconfigure(6, weight=1)
    selectFrame.rowconfigure(7, weight=1)
    selectFrame.columnconfigure(0, weight=1)
    selectFrame.columnconfigure(1, weight=1)
    selectFrame.columnconfigure(2, weight=1)
    selectFrame.columnconfigure(3, weight=1)

    tk.Label(selectFrame, text='Selecciona el número de jugadores'). \
        grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="1", bg="dark orange", command=lambda: selectScenarios(1)) \
        .grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="2", bg="dark orange", command=lambda: selectScenarios(2)) \
        .grid(row=1, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="3", bg="dark orange", command=lambda: selectScenarios(3)) \
        .grid(row=1, column=2, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="4", bg="dark orange", command=lambda: selectScenarios(4)) \
        .grid(row=1, column=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    # se muestran las imágenes de los escenarios disponibles
    scenarioCanvas = tk.Canvas(selectFrame, width=300, height=200, bg='grey')
    scenarioCanvas.grid(row=2, column=0, columnspan=4, padx=5, pady=5)

    prevBtn = tk.Button(selectFrame, text="<<", bg="dark orange", command=showPrev)
    prevBtn.grid(row=3, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    selectScenarioBtn = tk.Button(selectFrame, text="Seleccionar", bg="dark orange", command=selectScenario)
    selectScenarioBtn.grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    nextBtn = tk.Button(selectFrame, text=">>", bg="dark orange", command=showNext)
    nextBtn.grid(row=3, column=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    # La función de cargar el multi escenario que hay en ese momento en los drones no está operativa aún
    loadBtn = tk.Button(selectFrame, text="Cargar el escenario que hay en el dron", bg="dark orange", state=tk.DISABLED,
                        command=loadScenario)
    loadBtn.grid(row=4, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    # pequeño frame para configurar la conexión
    connectFrame = tk.Frame(selectFrame)
    connectFrame.grid(row=5, column=0, columnspan=4, padx=5, pady=3, sticky=tk.N + tk.E + tk.W)
    connectFrame.rowconfigure(0, weight=1)
    connectFrame.rowconfigure(1, weight=1)
    connectFrame.rowconfigure(2, weight=1)
    connectFrame.columnconfigure(0, weight=1)
    connectFrame.columnconfigure(1, weight=1)

    connectBtn = tk.Button(connectFrame, text="Conectar", bg="dark orange", command=connect)
    connectBtn.grid(row=0, column=0, rowspan=2, padx=5, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # se puede elegir entre conectarse al simulador o conectarse al dron real
    # en el segundo caso hay que especificar en qué puertos están conectadas las radios de telemetría
    connectOption = tk.StringVar()
    connectOption.set('Simulation')  # por defecto se trabaja en simulación
    option1 = tk.Radiobutton(connectFrame, text="Simulación", variable=connectOption, value="Simulation")
    option1.grid(row=0, column=1, padx=5, pady=3, sticky=tk.N + tk.S + tk.W)


    # se activa cuando elegimos la conexión en modo producción. Aquí especificamos los puertos en los que están
    # conectadas las radios de telemetría

    def ask_Ports():
        global comPorts
        comPorts = askstring('Puertos', "Indica los puertos COM separados por comas (por ejemplo: 'COM3,COM21,COM7')")

    option2 = tk.Radiobutton(connectFrame, text="Producción", variable=connectOption, value="Production",
                             command=ask_Ports)
    option2.grid(row=1, column=1, padx=5, pady=3, sticky=tk.N + tk.S + tk.W)

    sendBtn = tk.Button(selectFrame, text="Enviar escenario", bg="dark orange", command=sendScenario)
    sendBtn.grid(row=6, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    deleteBtn = tk.Button(selectFrame, text="Eliminar escenario", bg="red", fg='white', command=deleteScenario)
    deleteBtn.grid(row=7, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    ########################## frame para supervisar ####################################################
    superviseFrame = tk.LabelFrame(controlFrame, text='Supervisar vuelos', font=("Arial", 8, "bold"))
    superviseFrame.rowconfigure(0, weight=1)
    superviseFrame.rowconfigure(1, weight=1)
    superviseFrame.rowconfigure(2, weight=1)
    superviseFrame.rowconfigure(3, weight=1)
    superviseFrame.columnconfigure(0, weight=1)
    superviseFrame.columnconfigure(1, weight=1)
    superviseFrame.columnconfigure(2, weight=1)
    superviseFrame.columnconfigure(3, weight=1)

    global timeBtn, plotBtn, statsBtn

    timeBtn = tk.Button(superviseFrame, text="Ver Distancia de Vuelo", bg="dark orange", command=showFlightDistances)
    plotBtn = tk.Button(superviseFrame, text="Informe Visual", bg="dark orange", command=plotFlightReport)
    statsBtn = tk.Button(superviseFrame, text="Mostrar Estadísticas", bg="dark orange", command=show_game_stats)

    parametersBtn = tk.Button(superviseFrame, text="Ajustar parámetros", bg="dark orange", command=adjustParameters)
    parametersBtn.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    controlesFrame = tk.LabelFrame(superviseFrame, text='Controles')
    controlesFrame.grid(row=1, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    controlesFrame.rowconfigure(0, weight=1)
    controlesFrame.rowconfigure(1, weight=1)
    controlesFrame.rowconfigure(3, weight=1)
    controlesFrame.columnconfigure(0, weight=1)
    controlesFrame.columnconfigure(1, weight=1)
    controlesFrame.columnconfigure(2, weight=1)
    controlesFrame.columnconfigure(3, weight=1)

    # debajo de este label colocaremos las alturas en las que están los drones
    # las colocaremos cuando sepamos cuántos drones tenemos en el enjambre
    telemetriaFrame = tk.LabelFrame(superviseFrame, text='Telemetría (altitud y modo de vuelo')
    telemetriaFrame.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    telemetriaFrame.rowconfigure(0, weight=1)
    telemetriaFrame.rowconfigure(1, weight=1)
    telemetriaFrame.columnconfigure(0, weight=1)
    telemetriaFrame.columnconfigure(1, weight=1)
    telemetriaFrame.columnconfigure(2, weight=1)
    telemetriaFrame.columnconfigure(3, weight=1)

    showQRBtn = tk.Button(superviseFrame, text="Mostrar código QR de mobile web APP", bg="dark orange", command=showQR)
    showQRBtn.grid(row=3, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    #################### Frame para el mapa, en la columna de la derecha #####################
    # mapaFrame = tk.LabelFrame(ventana, text='Mapa')
    mapaFrame = tk.LabelFrame(ventana, text='Mapa', font=("Arial", 8, "bold"))

    mapaFrame.grid(row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    mapaFrame.rowconfigure(0, weight=1)
    mapaFrame.rowconfigure(1, weight=1)
    mapaFrame.columnconfigure(0, weight=1)

    # creamos el widget para el mapa
    map_widget = tkintermapview.TkinterMapView(mapaFrame, width=1900, height=1350, corner_radius=0)
    map_widget.grid(row=1, column=0, padx=5, pady=5)
    map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga",
                               max_zoom=24)
    map_widget.set_position(41.2764478, 1.9886568)  # Coordenadas del dronLab
    map_widget.set_zoom(21)

    # indicamos que capture los eventos de click sobre el mouse
    map_widget.add_right_click_menu_command(label="Cierra el fence", command=closeFence, pass_coords=True)
    map_widget.add_left_click_map_command(getFenceWaypoint)

    # ahora cargamos las imagenes de los iconos que vamos a usar
    im = Image.open("images/red.png").convert("RGBA")
    r, g, b, a = im.split()
    rgb = Image.merge("RGB", (r, g, b))
    enhancer = ImageEnhance.Brightness(rgb)
    rgb_dark = enhancer.enhance(0.9)
    r2, g2, b2 = rgb_dark.split()
    im_dark = Image.merge("RGBA", (r2, g2, b2, a))
    im_resized = im_dark.resize((25, 25), Image.LANCZOS)
    red = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im_dark.resize((15, 15), Image.LANCZOS)
    littleRed = ImageTk.PhotoImage(im_resized_plus)

    im = Image.open("images/blue.png").convert("RGBA")
    r, g, b, a = im.split()
    rgb = Image.merge("RGB", (r, g, b))
    enhancer = ImageEnhance.Brightness(rgb)
    rgb_dark = enhancer.enhance(0.9)
    r2, g2, b2 = rgb_dark.split()
    im_dark = Image.merge("RGBA", (r2, g2, b2, a))
    im_resized = im_dark.resize((25, 25), Image.LANCZOS)
    blue = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im_dark.resize((15, 15), Image.LANCZOS)
    littleBlue = ImageTk.PhotoImage(im_resized_plus)

    im = Image.open("images/green.png").convert("RGBA")
    r, g, b, a = im.split()
    rgb = Image.merge("RGB", (r, g, b))
    enhancer = ImageEnhance.Brightness(rgb)
    rgb_dark = enhancer.enhance(0.9)
    r2, g2, b2 = rgb_dark.split()
    im_dark = Image.merge("RGBA", (r2, g2, b2, a))
    im_resized = im_dark.resize((25, 25), Image.LANCZOS)
    green = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im_dark.resize((15, 15), Image.LANCZOS)
    littleGreen = ImageTk.PhotoImage(im_resized_plus)

    im = Image.open("images/yellow.png").convert("RGBA")
    r, g, b, a = im.split()
    rgb = Image.merge("RGB", (r, g, b))
    enhancer = ImageEnhance.Brightness(rgb)
    rgb_dark = enhancer.enhance(0.9)
    r2, g2, b2 = rgb_dark.split()
    im_dark = Image.merge("RGBA", (r2, g2, b2, a))
    im_resized = im_dark.resize((25, 25), Image.LANCZOS)
    yellow = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im_dark.resize((15, 15), Image.LANCZOS)
    littleYellow = ImageTk.PhotoImage(im_resized_plus)

    im = Image.open("images/black.png")
    bullet_small_image = ImageTk.PhotoImage(im.resize((15, 15), Image.LANCZOS))
    bullet_medium_image = ImageTk.PhotoImage(im.resize((18, 18), Image.LANCZOS))
    bullet_large_image = ImageTk.PhotoImage(im.resize((21, 21), Image.LANCZOS))

    # Lista de iconos para drones en vuelo
    dronPictures = [red, blue, green, yellow]
    colors = ['red', 'blue', 'green', 'yellow']
    dronLittlePictures = [littleRed, littleBlue, littleGreen, littleYellow]

    # Ahora cargamos los iconos para cuando el dron aterrice
    im = Image.open("images/red_line.png")
    im_resized = im.resize((25, 25), Image.LANCZOS)
    red_line = ImageTk.PhotoImage(im_resized)

    im = Image.open("images/blue_line.png")
    im_resized = im.resize((25, 25), Image.LANCZOS)
    blue_line = ImageTk.PhotoImage(im_resized)

    im = Image.open("images/green_line.png")
    im_resized = im.resize((25, 25), Image.LANCZOS)
    green_line = ImageTk.PhotoImage(im_resized)

    im = Image.open("images/yellow_line.png")
    im_resized = im.resize((25, 25), Image.LANCZOS)
    yellow_line = ImageTk.PhotoImage(im_resized)

    # Creamos la lista con los iconos para drones ya aterrizados
    dronLandedPictures = [red_line, blue_line, green_line, yellow_line]

    # Add buttons for game mode selection
    gameModeFrame = tk.LabelFrame(controlFrame, text='Modo de Juego')
    gameModeFrame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    gameModeFrame.rowconfigure(0, weight=1)
    gameModeFrame.columnconfigure(0, weight=1)
    gameModeFrame.columnconfigure(1, weight=1)

    # Crear el botón "Iniciar Juego"
    startGameBtn = tk.Button(controlFrame, text="Iniciar Juego", bg="dark orange", fg="black",
                             command=startGame, font=("Arial", 9), height=2)

    startGameBtn.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    startGameBtn.grid_remove()  # Lo ocultamos hasta que se presione "Enviar Escenario"

    # Crear botones en el panel principal de control
    global configuracionFrame

    configuracionFrame = tk.LabelFrame(controlFrame)
    configuracionFrame.grid(row=8, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

    tk.Button(configuracionFrame, text="2 min", command=lambda: set_game_duration(2)).grid(row=0, column=0, padx=5, pady=5)
    tk.Button(configuracionFrame, text="5 min", command=lambda: set_game_duration(5)).grid(row=0, column=1, padx=5, pady=5)
    tk.Button(configuracionFrame, text="8 min", command=lambda: set_game_duration(8)).grid(row=0, column=2, padx=5, pady=5)
    tk.Button(configuracionFrame, text="Modo Supervivencia", command=toggle_survival_mode).grid(row=1, column=0, columnspan=3, padx=5, pady=5)

    startGameBtn.grid_remove()
    configuracionFrame.grid_remove()
    return ventana


# Función para establecer el modo de juego
def setGameMode(mode):
    global game_mode

    game_mode = mode
    if mode == "free_for_all":
        message = "Modo de juego 'Todos contra todos' seleccionado."
    elif mode == "teams":
        message = "Modo de juego '2 vs 2' seleccionado."
    else:
        message = "Modo desconocido"

    messagebox.showinfo("Modo de Juego", message)
    startGameBtn.grid(row=9, column=0, columnspan=4, padx=5, pady=5, sticky="ew")


def startFlightTimer(drone_id):
    global start_times, flight_times_lock
    with flight_times_lock:
        start_times[drone_id] = time.time()


def stopFlightTimer(drone_id):
    global flight_times, start_times, flight_times_lock
    with flight_times_lock:
        if start_times[drone_id]:
            flight_times[drone_id] += time.time() - start_times[drone_id]
            start_times[drone_id] = None


def haversine_distance(coord1, coord2):
    # Calcula la distancia en metros entre dos coordenadas GPS usando la fórmula de Haversine.
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    R = 6371000  # Radio de la Tierra en metros
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def showFlightDistances():
    global total_distances, colors

    if not total_distances:
        messagebox.showinfo("Sin datos", "No hay datos de vuelo disponibles.")
        return

    distances = []

    for id, distance in total_distances.items():
        color_name = colors[id] if id < len(colors) else f"Dron {id + 1}"
        distances.append(f"{color_name}: {round(distance, 2)} metros recorridos")

    messagebox.showinfo("Distancias de Vuelo", "\n".join(distances))


def plotFlightReport():
    global traces, scenarios, current, selectedMultiScenario

    if not traces or not selectedMultiScenario:
        messagebox.showinfo("Sin datos", "No hay datos de vuelo o no hay escenario seleccionado.")
        return

    # Se asume que cada escenario tiene un "name" para la imagen base
    scenario_name = scenarios[current]['name']
    image_path = scenario_name + ".png"

    if not os.path.exists(image_path):
        messagebox.showerror("Error", f"No se encontró la imagen: {image_path}")
        return

    original_image = Image.open(image_path)
    orig_w, orig_h = original_image.size

    scale_factor = 1  # Modifica este factor si deseas escalar la imagen
    new_w = int(orig_w * scale_factor)
    new_h = int(orig_h * scale_factor)

    scaled_image = original_image.resize((new_w, new_h), Image.LANCZOS)

    # Obtener el bounding box geográfico del escenario
    min_lat, max_lat, min_lon, max_lon = get_scenario_bounding_box(selectedMultiScenario)
    # Convertir las latitudes mínimas y máximas a coordenadas Mercator:
    min_y = lat_to_mercator(min_lat)
    max_y = lat_to_mercator(max_lat)

    if min_lat == max_lat or min_lon == max_lon:
        messagebox.showerror("Error", "El bounding box del escenario es inválido.")
        return

    report_window = tk.Toplevel()
    report_window.title("Informe Visual de Rutas (Escalado)")
    report_window.geometry(f"{new_w}x{new_h}")

    canvas = Canvas(report_window, width=new_w, height=new_h)
    canvas.pack()

    scenario_photo = ImageTk.PhotoImage(scaled_image)
    canvas.create_image(0, 0, image=scenario_photo, anchor="nw")


    # Función para convertir una latitud y longitud en coordenadas para el canvas utilizando Mercator
    def latlon_to_xy_canvas(lat, lon):
        # La coordenada X se calcula de forma lineal (la proyección en X es lineal en la mayoría de mapas web)
        x = (lon - min_lon) / (max_lon - min_lon) * new_w
        # Para Y, usamos la proyección Mercator para que la escala vertical sea la correcta
        y = (max_y - lat_to_mercator(lat)) / (max_y - min_y) * new_h
        return x, y

    # Colores para cada dron
    dron_colors = ["red", "blue", "green", "yellow"]

    # Dibujar la ruta de cada dron
    for dron_id, dron_trace in enumerate(traces):
        if not dron_trace:
            continue  # Si no hay datos para ese dron, saltar
        color_line = dron_colors[dron_id % 4]

        # Dibujar línea entre cada par de puntos consecutivos del rastreo
        for i in range(len(dron_trace) - 1):
            lat1, lon1 = dron_trace[i]['pos']
            lat2, lon2 = dron_trace[i + 1]['pos']
            x1, y1 = latlon_to_xy_canvas(lat1, lon1)
            x2, y2 = latlon_to_xy_canvas(lat2, lon2)
            canvas.create_line(x1, y1, x2, y2, fill=color_line, width=2)

    canvas.image = scenario_photo  # Para evitar que la imagen se elimine del caché


def get_scenario_bounding_box(multiScenario):

    min_lat = 999999
    max_lat = -999999
    min_lon = 999999
    max_lon = -999999

    for element in multiScenario['scenarios']:
        scenario = element['scenario']
        for fence in scenario:
            if fence['type'] == 'polygon':
                for wp in fence['waypoints']:
                    lat = wp['lat']
                    lon = wp['lon']
                    if lat < min_lat:
                        min_lat = lat
                    if lat > max_lat:
                        max_lat = lat
                    if lon < min_lon:
                        min_lon = lon
                    if lon > max_lon:
                        max_lon = lon

            elif fence['type'] == 'circle':
                c_lat = fence['lat']
                c_lon = fence['lon']
                r = fence['radius']
                deg_lat = r / 111320.0
                deg_lon = r / (111320.0 * math.cos(math.radians(c_lat)))
                lat_min = c_lat - deg_lat
                lat_max = c_lat + deg_lat
                lon_min = c_lon - deg_lon
                lon_max = c_lon + deg_lon

                if lat_min < min_lat:
                    min_lat = lat_min
                if lat_max > max_lat:
                    max_lat = lat_max
                if lon_min < min_lon:
                    min_lon = lon_min
                if lon_max > max_lon:
                    max_lon = lon_max
    return min_lat, max_lat, min_lon, max_lon


# Convierte una latitud (en grados)
def lat_to_mercator(lat):

    lat_rad = math.radians(lat)
    return math.log(math.tan(math.pi/4 + lat_rad/2))


bullet_types = {
    "small_fast": {"speed": 250},
    "medium": {"speed": 150},
    "large_slow": {"speed": 70}
}


def shoot(player_id, bullet_type):
    global bullet_small_image, bullet_medium_image, bullet_large_image
    global frontMarkers, traces, map_widget, bullet_types, shot_counts, game_paused

    if game_paused:
        print("Disparo bloqueado: el juego está en pausa.")
        return

    # Bloquear si no está en status active
    if players[player_id]['status'] != 'active':
        print(f"El dron {player_id} está en estado {players[player_id]['status']} y no puede disparar.")
        return

    bullet_info = bullet_types[bullet_type]
    shot_counts[player_id][bullet_type] += 1  # Disparo por jugador
    players[player_id]['shots'] += 1  # Contar disparos totales

    if not traces[player_id]:
        print(f"No hay datos de telemetría para el dron {player_id}")
        return

    last_telemetry = traces[player_id][-1]
    start_pos = frontMarkers[player_id].position
    heading = last_telemetry['heading']

    # Seleccionar la imagen adecuada según el tipo de bala
    if bullet_type == "small_fast":
        bullet_icon = bullet_small_image
    elif bullet_type == "medium":
        bullet_icon = bullet_medium_image
    elif bullet_type == "large_slow":
        bullet_icon = bullet_large_image
    else:
        bullet_icon = bullet_medium_image  # Por defecto, mediana

    # Crear marcador de la bala utilizando el icono seleccionado
    bullet_marker = map_widget.set_marker(start_pos[0], start_pos[1], icon=bullet_icon, icon_anchor="center")

    step_size = bullet_info['speed'] / 10000000  # Escala

    # Iniciar movimiento de la bala en un hilo separado
    bullet_thread = threading.Thread(target=move_bullet, args=(bullet_marker, start_pos, heading, step_size, player_id))
    bullet_thread.start()
    active_bullets.append(bullet_marker)


def eliminateDrone(drone_id):
    global eliminated_players, survival_mode

    # Actualizar estado y aterrizar el dron
    players[drone_id]['status'] = 'eliminated'
    swarm[drone_id].Land(blocking=False)
    eliminated_players.add(drone_id)

    # Llamar a la función para actualizar el icono del dron a la versión de aterrizaje
    # Se lanza en un thread para no bloquear la interfaz.
    threading.Thread(target=update_drone_icon_on_landing, args=(drone_id,), daemon=True).start()

    # Verificar si se debe terminar la partida
    checkGameEnd()

    # Si no es modo supervivencia, se respawnea el dron después de 10 segundos
    if not survival_mode:
        threading.Thread(target=respawnDrone, args=(drone_id,), daemon=True).start()


def check_collision_with_drone(bullet_pos, shooter_id, threshold_meters=1):
    global players, swarm

    for i, player in enumerate(players):
        if i == shooter_id or player['status'] != 'active':
            continue

        dron_lat = swarm[i].lat
        dron_lon = swarm[i].lon
        if dron_lat == 0 and dron_lon == 0:
            continue

        dist = haversine_distance(bullet_pos, (dron_lat, dron_lon))
        if dist <= threshold_meters:
            return i  # Impacto al jugador i

    return None


def update_score(event_type, player_id):
    if event_type == "obstacle":
        player_scores[player_id] += 1
    elif event_type == "drone":
        player_scores[player_id] += 10
    update_mini_scores()


def check_point_collision_with_obstacles(point, obstacles):
    for obstacle in obstacles:
        if obstacle['type'] != 'polygon':
            continue
        polygon = obstacle['waypoints']
        if punto_dentro_poligono({'lat': point[0], 'lon': point[1]}, polygon):
            return True
    return False

def get_bbox(obstacle):
    # Para obstáculo tipo polígono, usamos los waypoints
    # para tipo círculo, usamos la aproximación a círculo

    if obstacle['type'] == 'polygon':
        pts = [(p['lat'], p['lon']) for p in obstacle['waypoints']]
    elif obstacle['type'] == 'circle':
        pts = getCircle(obstacle['lat'], obstacle['lon'], obstacle['radius'])
    min_lat = min(p[0] for p in pts)
    max_lat = max(p[0] for p in pts)
    min_lon = min(p[1] for p in pts)
    max_lon = max(p[1] for p in pts)
    return (min_lat, max_lat, min_lon, max_lon)


def initializePlayers(num_players):
    global players, teams, shot_counts, player_scores
    players = [{'id': i, 'status': 'active', 'eliminations': 0, 'shots': 0, 'team': None} for i in range(num_players)]
    shot_counts = {i: {"small_fast": 0, "medium": 0, "large_slow": 0} for i in range(num_players)}
    player_scores = {i: 0 for i in range(num_players)}

    if game_mode == "teams":
        teams = [0, 1] * (num_players // 2)
        for i, player in enumerate(players):
            player['team'] = teams[i]


def show_game_stats():
    global shot_counts, player_scores, numPlayers, game_mode

    stats_window = tk.Toplevel()
    stats_window.title("📊 Estadísticas del Juego")
    stats_window.geometry("1700x550")
    stats_window.configure(bg="white")

    style = ttk.Style()
    style.configure("Treeview.Heading", font=("Arial", 8, "bold"))
    style.configure("Treeview", font=("Arial", 8, "bold"), rowheight=40)

    table_frame = tk.Frame(stats_window, bg="white")
    table_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    # Título
    title_label = tk.Label(table_frame, text="📊 Estadísticas del Juego", font=("Arial", 14, "bold"), bg="white")
    title_label.pack(pady=5)

    # mostrar los datos de cada dron
    columns = ("Dron","Pequeña", "Mediana", "Grande", "Puntos")
    tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=numPlayers)
    tree.pack(fill=tk.BOTH, expand=True)

    # encabezados
    for col in columns:
        tree.heading(col, text=col, anchor="center")
        tree.column(col, anchor="center", width=120)

    tree.column("Dron", anchor="w", width=200)

    # Colores Rojo, Azul, Verde, Amarillo
    dron_colors = ["#FF6666", "#66A3FF", "#66FF66", "#FFD966"]
    dron_names = ["Dron 1", "Dron 2", "Dron 3", "Dron 4"]

    # Configurar colores para cada fila
    for i in range(numPlayers):
        tree.tag_configure(f"dron_{i}", background=dron_colors[i])

    # Agregar datos de cada dron a la tabla
    for i in range(numPlayers):
        if i in player_scores:
            tree.insert(
                "", "end",
                values=(
                    dron_names[i],
                    shot_counts[i]["small_fast"],
                    shot_counts[i]["medium"],
                    shot_counts[i]["large_slow"],
                    player_scores[i]
                ),
                tags=(f"dron_{i}",)
            )

    # comprobamos si el modo de juego es (2 vs 2)
    if game_mode == "teams":
        # Calculamos los puntos de cada equipo
        team_scores = {
            "Rojo-Azul": player_scores[0] + player_scores[1],
            "Verde-Amarillo": player_scores[2] + player_scores[3]
        }
        ganador = max(team_scores, key=team_scores.get)

        # Mostramos la informacion en otro label
        team_info = (
            f"Equipo Rojo-Azul: {team_scores['Rojo-Azul']} puntos\n"
            f"Equipo Verde-Amarillo: {team_scores['Verde-Amarillo']} puntos\n"
            f"Ganador: {ganador}"
        )

        tk.Label(
            table_frame,
            text=team_info,
            font=("Arial", 12, "bold"),
            bg="white",
            fg="black"
        ).pack(pady=10)

    # Botón para cerrar la ventana de estadísticas
    close_btn = tk.Button(stats_window, text="Cerrar", command=stats_window.destroy, bg="dark orange", fg="white", font=("Arial", 8, "bold"))
    close_btn.pack(pady=10)


# Función para pausar el juego (los drones no pueden moverse ni disparar)
def pauseGame():
    global game_paused, game_timer_running

    if not connected:
        messagebox.showwarning("Sin conexión", "No hay drones conectados.")
        return

    game_paused = True
    game_timer_running = False  # Detener el temporizador

    for dron in swarm:
        dron.setFlightMode('BRAKE')  # Frena los drones

    # Deshabilitar los botones de disparo
    for widget in controlFrame.winfo_children():
        if isinstance(widget, tk.LabelFrame) and widget.cget("text") == "Opciones de Disparo":
            for btn in widget.winfo_children():
                btn.config(state=tk.DISABLED)

    messagebox.showinfo("Juego Pausado", "El juego ha sido pausado. Los drones no pueden moverse ni disparar.")


# reanudar el juego (se habilita el movimiento y disparo)
def resumeGame():
    global game_paused, game_timer_running

    if not connected:
        messagebox.showwarning("Sin conexión", "No hay drones conectados.")
        return

    game_paused = False
    game_timer_running = True  # reanudar el temporizador
    update_game_clock()

    for dron in swarm:
        dron.setFlightMode('GUIDED')  # reanuda el movimiento de los drones

    # Habilitar los botones de disparo
    for widget in controlFrame.winfo_children():
        if isinstance(widget, tk.LabelFrame) and widget.cget("text") == "Opciones de Disparo":
            for btn in widget.winfo_children():
                btn.config(state=tk.NORMAL)

    messagebox.showinfo("Juego Reanudado", "Los drones pueden moverse y disparar nuevamente.")


# Función para finalizar el juego
def stopGame():
    global player_scores, shot_counts, eliminated_players

    for dron in swarm:
        dron.Land(blocking=False)

    # Reiniciar las estadísticas
    eliminated_players.clear()
    player_scores = {0: 0, 1: 0, 2: 0, 3: 0}
    shot_counts = {"small_fast": 0, "medium": 0, "large_slow": 0}

    messagebox.showinfo("Juego Finalizado", "El juego ha terminado.")


# Función para reiniciar el juego
def restartGame():
    global eliminated_players, player_scores, shot_counts, traces
    global game_elapsed_seconds, game_timer_running, recording_enabled
    global total_distances

    eliminated_players.clear()
    shot_counts = {i: {"small_fast": 0, "medium": 0, "large_slow": 0} for i in range(numPlayers)}
    player_scores = {i: 0 for i in range(numPlayers)}
    traces[:] = [[], [], [], []]
    total_distances.clear()

    game_elapsed_seconds = 0
    game_timer_running = False
    recording_enabled = True

    for i in range(numPlayers):
        area = selectedMultiScenario['scenarios'][i]['scenario'][0]
        if area['type'] == 'polygon':
            lat, lon = calcular_centro(area['waypoints'])
        else:
            lat, lon = area['lat'], area['lon']

        try:
            swarm[i].setFlightMode('GUIDED')
            swarm[i].arm()
            time.sleep(1)
            swarm[i].takeOff(5, blocking=True)
            swarm[i].goto(lat, lon, 5)

            # reiniciamos la distancia
            initial_positions[i] = (lat, lon)
            total_distances[i] = 0

        except Exception as e:
            print(f"Error reiniciando dron {i}: {e}")

    # Volver a colocar a los drones en sus zonas
    for i, player in enumerate(players):
        area = selectedMultiScenario['scenarios'][i]['scenario'][0]
        if area['type'] == 'polygon':
            lat, lon = calcular_centro(area['waypoints'])
        else:
            lat, lon = area['lat'], area['lon']

        try:
            swarm[i].setFlightMode('GUIDED')
            swarm[i].arm()
            time.sleep(1)
            swarm[i].takeOff(5, blocking=True)
            swarm[i].goto(lat, lon, 5)
            initial_positions[i] = (lat, lon)
            total_distances[i] = 0
            should_reset_distance[i] = False
            total_distances[i] = 0

        except Exception as e:
            print(f"Error reiniciando dron {i}: {e}")

    startGame()
    messagebox.showinfo("Juego Reiniciado", "El juego ha sido reiniciado.")


def update_game_clock():
    global game_elapsed_seconds, game_clock_label, game_timer_running
    global game_duration, survival_mode

    if not game_timer_running:
        return

    if survival_mode:
        tiempo_limite = 8 * 60

        if game_elapsed_seconds >= tiempo_limite:
            endGame()
            return

        # mostramos el tiempo transcurrido desde 0
        mins, secs = divmod(game_elapsed_seconds, 60)
        game_clock_label.config(text=f"⏱ {mins:02d}:{secs:02d}")

        game_elapsed_seconds += 1
        game_clock_label.after(1000, update_game_clock)

    else:
        if game_elapsed_seconds >= game_duration:
            endGame()
            return

        tiempo_restante = game_duration - game_elapsed_seconds
        mins, secs = divmod(tiempo_restante, 60)
        game_clock_label.config(text=f"{mins:02d}:{secs:02d}")

        game_elapsed_seconds += 1
        game_clock_label.after(1000, update_game_clock)


def mostrar_mini_tablas():
    global players, player_scores

    if not players:
        return

    for i, player in enumerate(players):
        mini_frame = tk.LabelFrame(
            mapaFrame,
            text=f"Jugador {i+1}",
            bg=colors[i],
            fg="white",
            font=("Arial", 8, "bold")
        )
        mini_frame.place(x=20 + i * 180, y=30)

        tk.Label(
            mini_frame,
            text=f"Puntos: {player_scores.get(i, 0)}",
            bg=colors[i],
            fg="white"
        ).pack(padx=5, pady=5)


def update_mini_scores():
    for widget in mapaFrame.winfo_children():
        if isinstance(widget, tk.LabelFrame) and widget.cget("text").startswith("Jugador"):
            jugador_index = int(widget.cget("text").split()[-1]) - 1
            for label in widget.winfo_children():
                if isinstance(label, tk.Label) and "Puntos:" in label.cget("text"):
                    label.config(text=f"Puntos: {player_scores[jugador_index]}")


def assign_player_zones():
    global player_zones

    player_zones = {}
    for i, player_scenario in enumerate(selectedMultiScenario['scenarios']):
        fence = player_scenario['scenario'][0]  # El primer fence es la zona válida
        player_zones[i] = fence


def is_inside_player_area(player_id, pos):
    global player_zones

    if player_id not in player_zones:
        return True

    fence = player_zones[player_id]

    if fence['type'] == 'polygon':
        return punto_dentro_poligono(pos, fence['waypoints'])
    elif fence['type'] == 'circle':
        center = (fence['lat'], fence['lon'])
        dist = geopy.distance.geodesic(center, pos).m
        return dist <= fence['radius']
    return True


def cambiar_dron_activo():
    global active_player_id, numPlayers

    active_player_id = (active_player_id + 1) % numPlayers
    colores = ['Rojo', 'Azul', 'Verde', 'Amarillo']
    color_texto = colores[active_player_id] if active_player_id < len(colores) else f"Jugador {active_player_id+1}"
    messagebox.showinfo("Cambio de Control", f"Ahora controlas el dron: {color_texto}")


def mover_dron_teclado(direccion):
    global active_player_id, swarm

    dron = swarm[active_player_id]
    lat, lon = dron.lat, dron.lon
    paso = 0.00003  # Pequeño desplazamiento

    if direccion == "arriba":
        nueva_pos = (lat + paso, lon)
    elif direccion == "abajo":
        nueva_pos = (lat - paso, lon)
    elif direccion == "izquierda":
        nueva_pos = (lat, lon - paso)
    elif direccion == "derecha":
        nueva_pos = (lat, lon + paso)
    else:
        return

    mover_dron(dron, nueva_pos, player_id=active_player_id)


def disparar_con_teclado():
    global active_player_id
    shoot(active_player_id, "medium")


def mostrar_controles_juego():
    if not game_timer_running:
        return

    display_shooting_options()
    mostrar_botones_cambio_dron()

    controlButtonsFrame.grid(row=10, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)


def mantener_escenario_visible():
    if 'selectedMultiScenario' in globals() and selectedMultiScenario:
        drawScenario(selectedMultiScenario)
    elif 'multiScenario' in globals() and multiScenario and isinstance(multiScenario, dict) and multiScenario.get('scenarios'):
        drawScenario(multiScenario)


# Configuración del tiempo del juego
def set_game_duration(minutes):
    global game_duration, survival_mode

    game_duration = minutes * 60
    survival_mode = False  # Desactiva supervivencia
    messagebox.showinfo("Tiempo del Juego", f"Tiempo configurado a {minutes} minutos.\nModo Supervivencia desactivado.")
    mostrar_boton_iniciar_juego()


# Reinicio de drones tras eliminación
def respawnDrone(drone_id):
    if survival_mode:
        return
    else:
        time.sleep(10)  # Espera 10 segundos
        players[drone_id]['status'] = 'active'
        swarm[drone_id].takeOff(5, blocking=False)
        eliminated_players.discard(drone_id)
        # Restaurar el icono de vuelo
        update_drone_icon_on_takeoff(drone_id)


# Activar modo supervivencia
def toggle_survival_mode():
    global survival_mode, game_duration

    survival_mode = True
    game_duration = None  # Desactiva la duracion
    messagebox.showinfo("Modo Supervivencia", "Modo supervivencia activado.\nJuego sin límite de tiempo.")
    mostrar_boton_iniciar_juego()


def mostrar_boton_iniciar_juego():
    global startGameBtn
    startGameBtn.grid(row=9, column=0, columnspan=3, padx=5, pady=5, sticky="ew")


def check_all_fences_completed():
    global player_fences_completed, numPlayers

    if sum(player_fences_completed.values()) == numPlayers:
        messagebox.showinfo("Configuración de Obstáculos", "Pon en el mapa los obstáculos")
        mostrar_opciones_obstaculos_en_createFrame()


def mostrar_opciones_obstaculos_en_createFrame():
    global obstaculosFrame

    obstaculosFrame = tk.LabelFrame(createFrame, text="Opciones de Obstáculos", font=("Arial", 8, "bold"))
    obstaculosFrame.grid(row=4, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    obstaculosFrame.columnconfigure(0, weight=1)

    btn_individual = tk.Button(
        obstaculosFrame, text="Individual", bg="dark orange",
        command=lambda: set_mirror_mode(False)
    )
    btn_individual.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

    btn_espejo = tk.Button(
        obstaculosFrame, text="Efecto Espejo", bg="dark orange",
        command=lambda: set_mirror_mode(True)
    )
    btn_espejo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    btn_eliminar = tk.Button(
        obstaculosFrame, text="Eliminar Obstáculo", bg="dark orange",
        command=activar_modo_eliminar_obstaculo
    )
    btn_eliminar.grid(row=0, column=2, padx=5, pady=5, sticky="ew")


def activar_modo_eliminar_obstaculo():
    global removing_obstacles, mirror_placement

    removing_obstacles = True
    mirror_placement = False  # No estamos en modo espejo
    map_widget.add_left_click_map_command(eliminar_obstaculo)
    print("Modo Eliminar Obstáculo activado")


def set_mirror_mode(value):
    global mirror_placement, removing_obstacles

    mirror_placement = value
    removing_obstacles = False

    map_widget.add_left_click_map_command(colocar_obstaculo)

    if value:
        print("Modo de colocación: Efecto Espejo activado")
    else:
        print("Modo de colocación: Individual")


 # Este bucle se ejecuta mientras el juego esté corriendo en modo supervivencia
def survival_check_loop():
    global players, game_timer_running, survival_mode

    while game_timer_running and survival_mode:
        active_players = [p for p in players if p['status'] == 'active']
        if len(active_players) <= 1:
            # Si solo queda uno (o ninguno), finalizamos el juego
            endGame()
            break
        time.sleep(1)  # Espera 1 segundo antes de la siguiente comprobación


# me contecto a los drones del enjambre
@sio_prof.event(namespace='/professor')
def connect():
    print("(/professor) conectado")
    global swarm
    global connected, dron, dronIcons
    global altitudes, modos
    global telemetriaFrame, controlesFrame

    if not connected:
        if connectOption.get() == 'Simulation':
            connectionStrings = [f'tcp:127.0.0.1:{5763 + i * 10}' for i in range(numPlayers)]
            baud = 115200
        else:
            connectionStrings = comPorts.split(',')
            baud = 57600

        colors = ['red', 'blue', 'green', 'yellow']
        altitudes = []
        modos = []
        dronIcons = [None, None, None, None]
        textColor = 'white'

        for i in range(numPlayers):
            dron = swarm[i]
            dron.changeNavSpeed(1)

            try:
                dron.connect(connectionStrings[i], baud)
                print(f"Dron {i} conectado.")
            except Exception as e:
                print(f"Error al conectar dron {i}: {e}")
                continue

            # Enviar telemetría
            dron.send_telemetry_info(processTelemetryInfo)

            if connectOption.get() == 'Simulation':
                dron.lat = 41.2763 + 0.00005 * i
                dron.lon = 1.9884 + 0.00005 * i
                dron.alt = 0.5

            # Esperar a tener telemetría válida
            if not esperar_telemetria_valida(dron, timeout=8):
                print(f"No se recibió telemetría válida del dron {i}.")
                continue

            print(f"Preparando dron {i} para despegar y situarse en su zona...")

            try:
                dron.setFlightMode('GUIDED')
                dron.arm()
                time.sleep(1)  # Esperar armado
                dron.takeOff(5, blocking=True)
                print(f"Dron {i} despegó correctamente.")

                # Mover a su zona de inicio (centro del área del jugador)
                area = selectedMultiScenario['scenarios'][i]['scenario'][0]
                if area['type'] == 'polygon':
                    lat, lon = calcular_centro(area['waypoints'])
                else:  # tipo círculo
                    lat, lon = area['lat'], area['lon']

                print(f"Moviendo dron {i} a ({lat}, {lon})...")
                dron.goto(lat, lon, 5)
            except Exception as e:
                print(f"Error al mover el dron {i} a su zona: {e}")

            # Crear botones y etiquetas
            if i == 3:
                textColor = 'black'

            tk.Button(controlesFrame, bg=colors[i], fg=textColor, text='Aterrizar',
                      command=lambda d=swarm[i]: d.Land(blocking=False)).grid(row=0, column=i)
            tk.Button(controlesFrame, bg=colors[i], fg=textColor, text='Modo guiado',
                      command=lambda d=swarm[i]: d.setFlightMode('GUIDED')).grid(row=1, column=i)
            tk.Button(controlesFrame, bg=colors[i], fg=textColor, text='Modo break',
                      command=lambda d=swarm[i]: d.setFlightMode('BRAKE')).grid(row=2, column=i)

            altitudes.append(tk.Label(telemetriaFrame, text='', borderwidth=1, relief="solid"))
            altitudes[-1].grid(row=0, column=i)
            modos.append(tk.Label(telemetriaFrame, text='', borderwidth=1, relief="solid"))
            modos[-1].grid(row=1, column=i)

        connected = True
        connectBtn['bg'] = 'green'


def endGame():
    global game_timer_running, game_paused, ventana
    game_timer_running = False
    game_paused = True

    controlButtonsFrame.grid_remove()

    ventana.unbind("<Up>")
    ventana.unbind("<Down>")
    ventana.unbind("<Left>")
    ventana.unbind("<Right>")
    ventana.unbind("<space>")

    displayResults()
    ventana.after(500, show_game_stats)

    sio_prof.emit(
        'endCompetition',
        {'sessionId': session_id},
        namespace='/professor'
    )


def startGame():
    global players, eliminated_players, recording_enabled
    global game_clock_label, game_timer_running, game_elapsed_seconds
    global session_id

    # si no tenemos session_id, pedirla y unirse a la sala
    if session_id is None:
        session_id = askstring("Sesión", "Session ID para empezar la partida:")
        if not session_id:
            return  # si cancela, no seguimos

        # cada dron se une a /jocs
        for color, client in dron_clients.items():
            client.emit('join', {'sessionId': session_id}, namespace='/jocs')

        # avisar al profesor para arrancar la competición
        sio_prof.emit(
            'startCompetition',
            {'sessionId': session_id},
            namespace='/professor'
        )
        print("startCompetition enviado")

    eliminated_players.clear()
    initializePlayers(numPlayers)

    for player in players:
        swarm[player['id']].takeOff(5, blocking=False)

    messagebox.showinfo("Inicio del Juego", "El juego ha comenzado!")
    print("Se ha iniciado el juego")
    startGameBtn['bg'] = 'green'
    mostrar_botones_cambio_dron()
    display_shooting_options()
    controlButtonsFrame.grid(row=10, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    timeBtn.grid(row=5, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    plotBtn.grid(row=6, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    statsBtn.grid(row=7, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    if game_clock_label is None:
        game_clock_label = tk.Label(mapaFrame, text="⏱ 00:00", font=("Arial", 14, "bold"), fg="black", bg="white")
        game_clock_label.place(x=1800, y=10)
    game_elapsed_seconds = 0
    game_timer_running = True

    update_game_clock()
    mostrar_mini_tablas()
    recording_enabled = True

    # Si estamos en modo supervivencia, iniciamos el hilo que comprueba constantemente los drones activos
    if survival_mode:
        threading.Thread(target=survival_check_loop, daemon=True).start()

    for color_key, (email, _) in DRONS.items():
        idx = color_to_pid[color_key]
        scene = selectedMultiScenario['scenarios'][idx]['scenario']

        area = scene[0]
        dron_clients[color_key].emit(
            'fence',
            {
                'sessionId': session_id,
                'drone': email,
                'fenceType': idx,
                'geometry': area['waypoints'] if area['type'] == "polygon" else {
                    'lat': area['lat'], 'lon': area['lon'], 'radius': area['radius']
                },
                'event': 'add'
            },
            namespace='/jocs'
        )

        for obst in scene[1:]:
            obstacles.append(obst)
            poly = map_widget.set_polygon(
                [(p['lat'], p['lon']) for p in obst['waypoints']],
                fill_color='black', outline_color='black', border_width=1
            )
            polys.append(poly)

            dron_clients[color_key].emit(
                'obstacle',
                {
                    'sessionId': session_id,
                    'drone': email,
                    'type': obst['type'],
                    'geometry': obst['waypoints'],
                    'event': 'add'
                },
                namespace='/jocs'
            )


def processTelemetryInfo(pid: int, info: dict):
    global dronIcons, frontMarkers, traces, lock, direction_lines
    global altitudes, modos, recording_enabled
    global initial_positions, total_distances, last_valid_positions

    lat     = info.get('lat', 0.0)
    lon     = info.get('lon', 0.0)
    alt     = info.get('alt', 0.0)
    heading = info.get('heading', 0.0)
    mode    = info.get('flightMode', "Unknown")
    speed   = info.get('groundSpeed', 0.0)
    pos     = (lat, lon)

    # Descartar telemetría inválida
    if lat == 0 and lon == 0:
        return

    # Restricciones de zona y obstáculos
    if not is_inside_player_area(pid, pos) or verificar_colision(pos, pid):
        if pid in last_valid_positions:
            swarm[pid].goto(*last_valid_positions[pid], 5)
        return

    last_valid_positions[pid] = pos

    # Pintar o actualizar icono del dron
    if not dronIcons[pid]:
        dronIcons[pid]    = map_widget.set_marker(lat, lon, icon=dronPictures[pid], icon_anchor="center")
        frontMarkers[pid] = map_widget.set_marker(lat, lon, icon=dronLittlePictures[pid], icon_anchor="center")
    else:
        dronIcons[pid].set_position(lat, lon)

    # Marca de dirección
    nose_lat = lat + 0.000008 * math.cos(math.radians(heading))
    nose_lon = lon + 0.000008 * math.sin(math.radians(heading))
    frontMarkers[pid].set_position(nose_lat, nose_lon)

    if direction_lines[pid]:
        direction_lines[pid].delete()
    tip_lat = nose_lat + 0.00090 * math.cos(math.radians(heading))
    tip_lon = nose_lon + 0.00090 * math.sin(math.radians(heading))
    direction_lines[pid] = map_widget.set_path(
        [(nose_lat, nose_lon), (tip_lat, tip_lon)],
        color="black", width=2
    )

    # UI de altitud y modo
    if pid < len(altitudes):
        altitudes[pid]['text'] = f"Alt: {alt:.1f} m"
        modos[pid]['text']     = f"Mode: {mode}"

    # Guardar traza y distancia
    if recording_enabled:
        with lock:
            traces[pid].append({'pos':pos, 'alt':alt, 'speed':speed, 'heading':heading})
        if pid not in initial_positions:
            initial_positions[pid] = pos
            total_distances[pid]   = 0
        prev = traces[pid][-2]['pos'] if len(traces[pid])>1 else pos
        total_distances[pid] += haversine_distance(prev, pos)

    # Emitir evento al backend
    color = color_of_id(pid)
    email = email_of_id(pid)
    dron_clients[color].emit(
        'telemetry',
        {'sessionId': session_id,
         'drone'    : email,
         'lat'      : lat,
         'lon'      : lon,
         'heading'  : heading},
        namespace='/jocs'
    )


def move_bullet(marker, start_pos, heading, step, shooter_id):
    lat, lon = start_pos
    bullet_id = str(uuid.uuid4())

    color = color_of_id(shooter_id)
    email = email_of_id(shooter_id)

    # Crear bala
    dron_clients[color].emit('bullet',
        {'sessionId': session_id, 'drone': email,
         'bulletId': bullet_id,
         'lat': lat, 'lon': lon,
         'event': 'create'},
        namespace='/jocs')

    dist = 0
    maxd = 10000
    while dist < maxd:
        lat += step * math.cos(math.radians(heading))
        lon += step * math.sin(math.radians(heading))
        marker.set_position(lat, lon)
        dist += haversine_distance(start_pos, (lat, lon))

        # Mover bala
        dron_clients[color].emit('bullet',
            {'sessionId': session_id, 'drone': email,
             'bulletId': bullet_id, 'lat': lat, 'lon': lon, 'event': 'move'},
            namespace='/jocs')

        # Colisión contra obstáculo
        hit = next((o for o in obstacles
                    if o['type']=='polygon' and
                       Polygon([(wp['lon'],wp['lat']) for wp in o['waypoints']]).contains(Point(lon,lat))), None)
        if hit:
            destroy_obstacle(hit, shooter_id)
            break

        # Colisión contra dron
        victim = check_collision_with_drone((lat, lon), shooter_id)
        if victim is not None:
            eliminateDrone(victim)
            break

        time.sleep(0.01)

    # Destruir bala
    marker.delete()
    dron_clients[color].emit('bullet',
        {'sessionId': session_id, 'drone': email,
         'bulletId': bullet_id, 'event': 'destroy'},
        namespace='/jocs')


def destroy_obstacle(obstacle, remover_id: int = 0):
    global obstacles, polys, selectedMultiScenario

    tol = 1e-5
    bbox = get_bbox(obstacle)

    # Borrar del mapa
    for poly in polys[:]:
        try:
            gen = {
              'type': 'polygon',
              'waypoints': [{'lat': p[0], 'lon': p[1]} for p in poly.position_list]
            }
            if get_bbox(gen) == bbox:
                poly.delete()
                polys.remove(poly)
        except:
            pass

    # Borrar de la lista interna
    if obstacle in obstacles:
        obstacles.remove(obstacle)

    # Borrar del escenario cargado
    for scn in selectedMultiScenario.get('scenarios', []):
        if obstacle in scn['scenario'][1:]:
            scn['scenario'].remove(obstacle)

    color = color_of_id(remover_id)
    email = email_of_id(remover_id)
    print(f"[DEBUG] Emitting obstacle remove: {obstacle['waypoints']}")
    dron_clients[color].emit(
        'obstacle',
        {
            'sessionId': session_id,
            'drone':     email,
            'type':      obstacle['type'],
            'geometry':  obstacle['waypoints'],
            'event':     'remove'
        },
        namespace='/jocs'
    )


def colocar_obstaculo(coords, placer_id: int = 0):
    global obstacles, polys

    if removing_obstacles:
        return
    if not punto_dentro_poligonos_dibujados(coords):
        messagebox.showerror("Error", "¡El obstáculo debe estar dentro del área!")
        return

    # Calcula los vértices del polígono
    W, H, angle = 0.0000095, 0.0000095, -15
    rad = math.radians(angle)
    cx, cy = snap_a_vecino(coords, W, H, angle)
    pts = [
        (cx +  W*math.cos(rad) - H*math.sin(rad), cy +  W*math.sin(rad) + H*math.cos(rad)),
        (cx -  W*math.cos(rad) - H*math.sin(rad), cy -  W*math.sin(rad) + H*math.cos(rad)),
        (cx -  W*math.cos(rad) + H*math.sin(rad), cy -  W*math.sin(rad) - H*math.cos(rad)),
        (cx +  W*math.cos(rad) + H*math.sin(rad), cy +  W*math.sin(rad) - H*math.cos(rad))
    ]

    obst = {
        'type': 'polygon',
        'waypoints': [{'lat': p[0], 'lon': p[1]} for p in pts],
        'altitude': 5
    }

    obstacles.append(obst)
    poly_widget = map_widget.set_polygon(
        [(p['lat'], p['lon']) for p in obst['waypoints']],
        fill_color='black', outline_color='black', border_width=1
    )
    polys.append(poly_widget)
    if mirror_placement and numPlayers > 1:
        mirror_obstacle(obst)

    color = color_of_id(placer_id)
    email = email_of_id(placer_id)
    print(f"[DEBUG] Emitting obstacle add: {obst['waypoints']}")
    dron_clients[color].emit(
        'obstacle',
        {
            'sessionId': session_id,
            'drone':     email,
            'type':      obst['type'],
            'geometry':  obst['waypoints'],
            'event':     'add'
        },
        namespace='/jocs'
    )


if __name__ == "__main__":

    ventana = crear_ventana()
    setupControlButtons()
    ventana.mainloop()

    sio_prof.disconnect(namespace='/professor')
    for c in dron_clients.values():
        c.disconnect(namespace='/jocs')