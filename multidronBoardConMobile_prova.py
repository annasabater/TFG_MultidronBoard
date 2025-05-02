import json
import math
import random
import threading
import tkinter as tk
import os
from tkinter import ttk

from tkinter import messagebox
from tkinter.simpledialog import askstring

import tkintermapview
from PIL import Image, ImageTk
import pyautogui
import win32gui
import glob

import paho.mqtt.client as mqtt

from dronLink.Dron import Dron
import geopy.distance
from geographiclib.geodesic import Geodesic
from ParameterManager import ParameterManager
from AutopilotControllerClass import AutopilotController

'''
Ejemplo de estructura de datos que representa un escenario para múltiples jugadores (multi escenario).
Los jugadores son el red, blue y green (el cuarto sería el yellow).
Para cada jugador tenemos una lista de fences. El primero es el de inclusión, que puede ser un poligono o un círculo.
El resto (si hay) son fences que representan obstáculos y pueden ser polígonos o círculos.

{
  "numPlayers": 3,
  "scenarios": [
    {
      "player": "red",
      "scenario": [
        {
          "type": "polygon",
          "waypoints": [
            {
              "lat": 41.27644776935058,
              "lon": 1.9882548704865997
            },
            {
              "lat": 41.27656972362127,
              "lon": 1.988883848500592
            },
            {
              "lat": 41.27648304540272,
              "lon": 1.9889368907028029
            },
            {
              "lat": 41.276382256631756,
              "lon": 1.9883025482707808
            }
          ]
        },
        {
          "type": "polygon",
          "waypoints": [
            {
              "lat": 41.276464903435425,
              "lon": 1.9884165421539137
            },
            {
              "lat": 41.27648304540272,
              "lon": 1.9885359004550764
            },
            {
              "lat": 41.27644776935058,
              "lon": 1.9885399237685988
            },
            {
              "lat": 41.27643063526124,
              "lon": 1.9884500697665999
            }
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
            {
              "lat": 41.27635524622633,
              "lon": 1.9883578031226534
            },
            {
              "lat": 41.27645704292634,
              "lon": 1.9889009504481692
            },
            {
              "lat": 41.27635855031422,
              "lon": 1.9888875394030947
            },
            {
              "lat": 41.276282958606416,
              "lon": 1.988344392077579
            }
          ]
        },
        {
          "type": "circle",
          "lat": 41.276362581869506,
          "lon": 1.9885468988582033,
          "radius": 2.669351637531348
        }
      ]
    },
    {
      "player": "green",
      "scenario": [
        {
          "type": "polygon",
          "waypoints": [
            {
              "lat": 41.27657020663036,
              "lon": 1.9889331369563479
            },
            {
              "lat": 41.27659943530579,
              "lon": 1.989017626540317
            },
            {
              "lat": 41.276431118271354,
              "lon": 1.9891021161242861
            },
            {
              "lat": 41.27640692896127,
              "lon": 1.9889894633456606
            }
          ]
        },
        {
          "type": "polygon",
          "waypoints": [
            {
              "lat": 41.276526867535786,
              "lon": 1.9889827578231234
            },
            {
              "lat": 41.27653089908068,
              "lon": 1.9890136032267947
            },
            {
              "lat": 41.27648755996002,
              "lon": 1.9890310375853915
            },
            {
              "lat": 41.276476473203594,
              "lon": 1.9890042154952425
            }
          ]
        }
      ]
    }
  ]
}
'''

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

import threading

lock = threading.Lock()




########## Funciones para la creación de multi escenarios #################################

def createBtnClick ():
    global mode_selected
    mode_selected = True
    global scenario
    scenario = []
    # limpiamos el mapa de los elementos que tenga
    clear()
    # quitamos los otros frames
    selectFrame.grid_forget()
    superviseFrame.grid_forget()
    # visualizamos el frame de creación
    createFrame.grid(row=1, column=0,  columnspan=3, padx=5, pady=5, sticky=tk.N +  tk.E + tk.W)

    createBtn['text'] = 'Creando...'
    createBtn['fg'] = 'white'
    createBtn['bg'] = 'green'

    selectBtn['text'] = 'Seleccionar'
    selectBtn['fg'] = 'black'
    selectBtn['bg'] = 'dark orange'

    superviseBtn['text'] = 'Supervisar'
    superviseBtn['fg'] = 'black'
    superviseBtn['bg'] = 'dark orange'

# iniciamos la creación de un fence tipo polígono
def definePoly(type):
    global fence, paths, polys
    global fenceType

    fenceType = type # 1 es inclusión y 2 es exclusión

    paths = []
    fence = {
        'type' : 'polygon',
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

mode_selected = False  # Indica si ya se ha seleccionado una opción Crear

# capturamos el siguiente click del mouse
def getFenceWaypoint (coords):
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
                    paths.append(map_widget.set_path([(lat,lon), coords], color=selectedColor, width=3))
                else:
                    paths.append(map_widget.set_path([(lat,lon), coords], color='black', width=3))
                # si es el segundo waypoint quito el marcador que señala la posición del primero
                if len(fence['waypoints']) == 1:
                    marker.delete()

            # guardo el nuevo waypoint
            fence['waypoints'].append ({'lat': coords[0], 'lon': coords[1]})
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
                fence['lat']= coords[0]
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
        for point in  fence['waypoints']:
            poly.append((point['lat'], point['lon']))

        if fenceType == 1:
            # polígono del color correspondiente al jugador
            polys.append(map_widget.set_polygon(poly,
                                        outline_color=selectedColor,
                                        fill_color=selectedColor,
                                        border_width=3))
        else:
            # polígono de color negro (obstaculo)
            polys.append(map_widget.set_polygon(poly,
                                                fill_color='black',
                                                outline_color="black",
                                                border_width=3))
    else:
        # Es un circulo y acabamos de marcar el límite del circulo
        # borro el marcador del centro
        marker.delete()
        center= (fence['lat'], fence['lon'])
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
                                                outline_color= selectedColor,
                                                fill_color=selectedColor,
                                                border_width=3))
        else:
            polys.append(map_widget.set_polygon(points,
                                                fill_color='black',
                                                outline_color="black",
                                                border_width=3))

    fence = None

# La siguiente función crea una imagen capturando el contenido de una ventana
def screenshot(window_title=None):
    # capturo una imagen del multi escenario para guardarla más tarde
    if window_title:
        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd:
            win32gui.SetForegroundWindow(hwnd)
            x, y, x1, y1 = win32gui.GetClientRect(hwnd)
            x, y = win32gui.ClientToScreen(hwnd, (x, y))
            x1, y1 = win32gui.ClientToScreen(hwnd, (x1 - x, y1 - y))
            # aquí le indico la zona de la ventana que me interesa, que es básicamente la zona del dronLab
            im = pyautogui.screenshot(region=(x+800, y+250, 730, 580))
            return im
        else:
            print('Window not found!')
    else:
        im = pyautogui.screenshot()
        return im

# guardamos los datos del escenario (imagen y fichero json)
def registerScenario ():
    global multiScenario

    # voy a guardar el multi escenario en el fichero con el nombre indicado en el momento de la creación
    jsonFilename = 'multiScenarios/' + name.get() + "_"+str(numPlayers)+".json"

    with open(jsonFilename, 'w') as f:
        json.dump(multiScenario, f)
    # aqui capturo el contenido de la ventana que muestra el Camp Nou (zona del cesped, que es dónde está el escenario)
    im = screenshot('Gestión de escenarios')
    imageFilename = 'multiScenarios/'+name.get()+ "_"+str(numPlayers)+".png"
    im.save(imageFilename)
    multiScenario = []
    # limpio el mapa
    clear()

# genera el poligono que aproxima al círculo
def getCircle ( lat, lon, radius):
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
def selectBtnClick ():
    global scenarios, current, polys
    scenarios = []
    # limpio el mapa
    clear()
    # elimino los otros frames
    createFrame.grid_forget()
    superviseFrame.grid_forget()
    # muestro el frame de selección
    selectFrame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    selectBtn['text'] = 'Seleccionando...'
    selectBtn['fg'] = 'white'
    selectBtn['bg'] = 'green'

    createBtn['text'] = 'Crear'
    createBtn['fg'] = 'black'
    createBtn['bg'] = 'dark orange'

    superviseBtn['text'] = 'Supervisar'
    superviseBtn['fg'] = 'black'
    superviseBtn['bg'] = 'dark orange'

# una vez elegido el numero de jugadores mostramos los multi escenarios que hay para ese número de jugadores
def selectScenarios (num):
    global scenarios, current, polys, drawingAction, traces
    global numPlayers
    global client, swarm

    numPlayers = num
    # cargamos en una lista las imágenes de todos los multi escenarios disponibles
    # para el número de jugadores indicado
    scenarios = []
    for file in glob.glob("multiScenarios/*_"+str(num)+".png"):
        scene = Image.open(file)
        scene = scene.resize((300, 200))
        scenePic = ImageTk.PhotoImage(scene)
        # en la lista guardamos el nombre que se le dió al escenario y la imagen
        scenarios.append({'name': file.split('.')[0], 'pic': scenePic})

    if len(scenarios) > 0:
        # mostramos ya en el canvas la imagen del primer multi escenario
        scenarioCanvas.create_image(0, 0, image=scenarios[0]['pic'], anchor=tk.NW)
        current = 0
        # no podemos seleccionar el anterior porque no hay anterior
        prevBtn['state'] = tk.DISABLED
        # y si solo hay 1 multi escenario tampoco hay siguiente
        if len(scenarios) == 1:
            nextBtn['state'] = tk.DISABLED
        else:
            nextBtn['state'] = tk.NORMAL

        sendBtn['state'] = tk.DISABLED
    else:
        messagebox.showinfo("showinfo",
                            "No hay escenarios para elegir")

    # aqui ya puedo poner en marcha el sevicio de autopiloto

    additionalEvents = [
        {'event': 'startDrawing', 'method':startDrawing},
        {'event': 'stopDrawing', 'method':stopDrawing},
        {'event': 'startRemovingDrawing', 'method':startRemovingDrawing},
        {'event': 'stopRemovingDrawing', 'method':stopRemovingDrawing},
        {'event': 'removeAll', 'method': removeAll}
    ]
    autopilotService = AutopilotController (numPlayers, numPlayers, additionalEvents)
    client, swarm = autopilotService.start()

# mostrar anterior
def showPrev ():
    global current
    current = current -1
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
def showNext ():
    global current
    current = current +1
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

'''
# Limpiamos el mapa
def clear ():
    global paths, fence, polys
    name.set ("")
    for path in paths:
        path.delete()
    for poly in polys:
        poly.delete()

    paths = []
    polys = []
'''
def clear():
    global paths, polys, fence, numPlayers
    name.set("")
    for path in paths:
        path.delete()
    for poly in polys:
        poly.delete()

    paths, polys, fence = [], [], None
    numPlayers = 0

    # Restaurar la pantalla de selección de jugadores
    for widget in selectPlayersFrame.winfo_children():
        widget.destroy()

    tk.Label(selectPlayersFrame, text='Selecciona el número de jugadores').grid(row=0, column=0, columnspan=4, padx=5, pady=5)
    for i in range(1, 5):
        tk.Button(selectPlayersFrame, text=str(i), bg="dark orange", command=lambda n=i: selectNumPlayers(n)).grid(row=1, column=i-1, padx=5, pady=5)

# borramos el escenario que esta a la vista
def deleteScenario ():
    global current
    msg_box = messagebox.askquestion(
        "Atención",
        "¿Seguro que quieres eliminar este escenario?",
        icon="warning",
    )
    if msg_box == "yes":
        # borro los dos ficheros que representan el multi escenario seleccionado
        os.remove(scenarios[current]['name'] + '.png')
        os.remove(scenarios[current]['name'] + '.json')
        scenarios.remove (scenarios[current])
        # muestro el multi escenario anterior (o el siguiente si no hay anterior o ninguno si tampoco hay siguiente)
        if len (scenarios) != 0:
            if len (scenarios) == 1:
                # solo queda un escenario
                current = 0
                scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
                prevBtn['state'] = tk.DISABLED
                nextBtn['state'] = tk.DISABLED
            else:
                # quedan más multi escenarios
                if current == 0:
                    # hemos borrado el primer multi escenario de la lista. Mostramos el nuevo primero
                    scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
                    prevBtn['state'] = tk.DISABLED
                    if len (scenarios) > 1:
                        nextBtn['state'] = tk.NORMAL
                else:
                    # mostramos
                    scenarioCanvas.create_image(0, 0, image=scenarios[current]['pic'], anchor=tk.NW)
                    prevBtn['state'] = tk.NORMAL
                    if current == len (scenarios) -1:
                        nextBtn['state'] = tk.DISABLED
                    else:
                        nextBtn['state'] = tk.NORMAL
            clear()

# dibujamos en el mapa el multi escenario
def drawScenario (multiScenario):
    global polys

    # borro los elementos que haya en el mapa
    for poly in polys:
        poly.delete()
    # vamos a recorrer la lista de escenarios
    scenarios = multiScenario ['scenarios']
    for element in scenarios:
        color = element ['player']
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
                                                    border_width=3))
            else:
                poly = getCircle(fence['lat'], fence['lon'], fence['radius'])
                polys.append(map_widget.set_polygon(poly,
                                                    outline_color="black",
                                                    fill_color="black",
                                                    border_width=3))

# seleccionar el multi escenario que está a la vista
def selectScenario():
    global polys, selectedMultiScenario, numPlayers
    # limpio el mapa
    for poly in polys:
        poly.delete()
    # cargamos el fichero json con el multi escenario seleccionado (el que está en la posición current de la lista9
    f = open(scenarios[current]['name'] +'.json')
    selectedMultiScenario = json.load (f)
    # dibujo el escenario
    drawScenario(selectedMultiScenario)
    # habilito el botón para enviar el escenario al enjambre
    sendBtn['state'] = tk.NORMAL

# envia los datos del multi escenario seleccionado al enjambre
def sendScenario ():
    # enviamos a cada dron del enjambre el escenario que le toca
    global swarm
    global connected, dron, dronIcons
    global altitudes

    for i in range (0,len(swarm)):
        swarm[i].setScenario(selectedMultiScenario['scenarios'][i]['scenario'])

    sendBtn['bg'] = 'green'

# carga el multi escenario que hay ahora en el enjambre
# NO ESTA OPERATIVO
def loadScenario ():
    # ESTO NO ESTA OPERATIVO
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
        messagebox.showinfo("showinfo",
                        "No hay ningún escenario cargado en el dron")
''''''
# preparo los botones para crear el escenario de cada jugador
def createPlayer (color):
    # aqui vamos a crear el escenario para uno de los jugadores, el que tiene el color indicado como parámetro
    global colorIcon
    global selectedColor, scenario
    selectedColor = color
    # veamos en que caso estamos
    if color == 'red':
        # empezamos a crear el escenario de este jugador
        if 'Crea' in redPlayerBtn['text']:
            colorIcon = red
            redPlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario rojo"
            scenario = []
        # damos por terminado el escenario de este jugador
        elif 'Clica' in redPlayerBtn['text']:
            redPlayerBtn['text'] = "Escenario rojo listo"
            # lo añadimos a la estructura del multi escenario
            multiScenario ['scenarios'].append ({
                'player': 'red',
                'scenario': scenario
            })

    # ahora lo mismo para el resto de jugadores
    elif color == 'blue':
        if 'Crea' in bluePlayerBtn['text']:
            colorIcon = blue
            bluePlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario azul"
            scenario = []
        elif 'Clica' in bluePlayerBtn['text']:
            bluePlayerBtn['text'] = "Escenario azul listo"
            multiScenario['scenarios'].append({
                'player': 'blue',
                'scenario': scenario
            })

    elif color == 'green':
        if 'Crea' in greenPlayerBtn['text']:
            colorIcon = green
            greenPlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario verde"
            scenario = []
        elif 'Clica' in greenPlayerBtn['text']:
            greenPlayerBtn['text'] = "Escenario verde listo"
            multiScenario['scenarios'].append({
                'player': 'green',
                'scenario': scenario
            })
    else:
        if 'Crea' in yellowPlayerBtn['text']:
            colorIcon = yellow
            yellowPlayerBtn['text'] = "Clica aquí cuando hayas acabado el escenario amarillo"
            scenario = []
        elif 'Clica' in yellowPlayerBtn['text']:
                yellowPlayerBtn['text'] = "Escenario amarillo listo"
                multiScenario['scenarios'].append({
                    'player': 'yellow',
                    'scenario': scenario
                })

# elijo el número de jugadores
def selectNumPlayers (num):
    global redPlayerBtn, bluePlayerBtn, greenPlayerBtn, yellowPlayerBtn
    global multiScenario
    global numPlayers
    numPlayers = num
    # empezamos a preparar la estructura de datos del multi escenario
    multiScenario = {
        'numPlayers': num,  # numero de jugadores
        'scenarios': []     # un escenario para cada jugador
    }
    # colocamos los botones que permiten crear el escenario para cada uno de los jugadores

    # Eliminar botones anteriores
    for widget in selectPlayersFrame.winfo_children():
        if isinstance(widget, tk.Button) and "Crea el escenario" in widget.cget("text"):
            widget.destroy()

    buttons = []
    colors = [('red', 'rojo'), ('blue', 'azul'), ('green', 'verde'), ('yellow', 'amarillo')]

    #Actualiza los botones de la cantidad de numero de jugadores en Crear
    for i in range(num):
        color, label = colors[i]
        btn = tk.Button(selectPlayersFrame, text=f"Crea el escenario para el jugador {label}", bg=color, fg='white',
                        command=lambda c=color: createPlayer(c))
        btn.grid(row=2 + i, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
        buttons.append(btn)

    redPlayerBtn, bluePlayerBtn, greenPlayerBtn, yellowPlayerBtn = (buttons + [None] * (4 - num))
    
'''
    if num == 1:
        redPlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador rojo", bg="red", fg = 'white',
                                 command=lambda: createPlayer('red'))
        redPlayerBtn.grid(row=2, column=0, columnspan = 4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    if num == 2:
        redPlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador rojo", bg="red", fg='white',
                                command = lambda: createPlayer('red'))
        redPlayerBtn.grid(row=2, column=0, columnspan = 4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

        bluePlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador azul", bg="blue", fg='white',
                                command = lambda: createPlayer('blue'))
        bluePlayerBtn.grid(row=3, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    if num == 3:
        redPlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador rojo", bg="red",
                                 fg='white',
                                 command=lambda: createPlayer('red'))
        redPlayerBtn.grid(row=2, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

        bluePlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador azul", bg="blue",
                                  fg='white',
                                  command=lambda: createPlayer('blue'))
        bluePlayerBtn.grid(row=3, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
        greenPlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador verde", bg="green", fg='white',
                                command = lambda: createPlayer('green'))
        greenPlayerBtn.grid(row=4, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    if num == 4:
        redPlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador rojo", bg="red",
                                 fg='white',
                                 command=lambda: createPlayer('red'))
        redPlayerBtn.grid(row=2, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

        bluePlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador azul", bg="blue",
                                  fg='white',
                                  command=lambda: createPlayer('blue'))
        bluePlayerBtn.grid(row=3, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
        greenPlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador verde", bg="green",
                                   fg='white',
                                   command=lambda: createPlayer('green'))
        greenPlayerBtn.grid(row=4, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

        yellowPlayerBtn = tk.Button(selectPlayersFrame, text="Crea el escenario para el jugador amarillo", bg="yellow", fg='black',
                                command = lambda: createPlayer('yellow'))
        yellowPlayerBtn.grid(row=5, column=0,columnspan = 4,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
'''

# me contecto a los drones del enjambre
def connect ():
    global swarm
    global connected, dron, dronIcons
    global altitudes, modos
    global telemetriaFrame, controlesFrama

    if not connected:

        if connectOption.get () == 'Simulation':
            # nos conectaremos a los simuladores de los drones
            connectionStrings = []
            base = 5763
            for i in range(0, numPlayers):
                port = base + i * 10
                connectionStrings.append('tcp:127.0.0.1:' + str(port))
            baud = 115200
        else:
            # nos conectaremos a los drones reales a través de las radios de telemetría
            # los puertos ya los hemos indicado y estan en comPorts, separados por comas
            connectionStrings = comPorts.split(',')
            baud = 57600


        colors = ['red', 'blue', 'green', 'yellow']
        altitudes = []
        modos = []

        dronIcons = [None, None, None, None]

        textColor = 'white'

        for i in range(0, numPlayers):
            # identificamos el dron
            dron = swarm[i]
            dron.changeNavSpeed(1) # que vuele a 1 m/s
            # nos conectamos
            print ('voy a onectar ', i, connectionStrings[i], baud)
            dron.connect(connectionStrings[i], baud)
            print ('conectado')
            if i == 3:
                textColor = 'black'
            # colocamos los botones para aterrizar y cambiar de modo, cada uno con el color que toca
            tk.Button(controlesFrame, bg=colors[i], fg=textColor, text='Aterrizar',
                      command=lambda d=swarm[i]: d.Land(blocking=False)) \
                .grid(row=0, column=i, padx=2, pady=2, sticky=tk.N + tk.E + tk.W)
            tk.Button(controlesFrame, bg=colors[i], fg=textColor, text='Modo guiado',
                      command=lambda d=swarm[i]: d.setFlightMode('GUIDED')) \
                .grid(row=1, column=i, padx=2, pady=2, sticky=tk.N + tk.E + tk.W)
            tk.Button(controlesFrame, bg=colors[i], fg=textColor, text='Modo break',
                      command=lambda d=swarm[i]: d.setFlightMode('BRAKE')) \
                .grid(row=2, column=i, padx=2, pady=2, sticky=tk.N + tk.E + tk.W)
            # colocamos las labels para mostrar las alturas de los drones
            altitudes.append(tk.Label(telemetriaFrame, text='', borderwidth=1, relief="solid"))
            altitudes[-1].grid(row=0, column=i, padx=2, pady=2, sticky=tk.N + tk.E + tk.W)
            modos.append(tk.Label(telemetriaFrame, text='', borderwidth=1, relief="solid"))
            modos[-1].grid(row=1, column=i, padx=2, pady=2, sticky=tk.N + tk.E + tk.W)
            # solicitamos datos de telemetria del dron
            dron.send_telemetry_info(processTelemetryInfo)

        connected = True
        connectBtn['bg'] = 'green'


# evantos que no trata el Autopilot Service y se tratan aqui:
def startDrawing (id ):
    global drawingAction
    print ('start drawing')
    drawingAction [id] = 'startDrawing'

def stopDrawing (id):
    global drawingAction
    drawingAction [id] = 'nothing'

def startRemovingDrawing (id):
    global drawingAction
    drawingAction[id] = 'remove'

def stopRemovingDrawing (id):
    global drawingAction
    drawingAction[id] = 'nothing'

def removeAll (id):
    global traces
    for item in traces[id]:
        if  item['marker'] != None:
                item['marker'].delete()
    traces[id] = []


################### Funciones para supervisar el multi escenario #########################

def superviseBtnClick ():
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

# creamos la ventana para gestionar los parámetros de los drones del enjambre
def adjustParameters ():
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
    label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E +tk.S+ tk.W)

    closeBtn = tk.Button(QRWindow, text="Cerrar", bg="dark orange", command = lambda: QRWindow.destroy())
    closeBtn.grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E +tk.S+tk.W)

    QRWindow.mainloop()




'''


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("connected OK Returned code=", rc)
    else:
        print("Bad connection Returned code=", rc)

def publish_event (id, event):
    # al ser drones idenificados dronLink_old nos pasa siempre en primer lugar el identificador
    # del dron que ha hecho la operación
    # lo necesito para identificar qué jugador debe hacer caso a la respuesta
    global client
    client.publish('multiPlayerDash/mobileApp/'+event+'/'+str(id))

# aqui recibimos las publicaciones que hacen las web apps desde las que están jugando
def on_message(client, userdata, message):
    # el formato del topic siempre será:
    # multiPlayerDash/mobileApp/COMANDO/NUMERO
    # el número normalmente será el número del jugador (entre el 0 y el 3)
    # excepto en el caso de la petición de conexión
    global playersCount
    parts = message.topic.split ('/')
    command = parts[2]
    if command == 'connect':
        # el cuarto trozo del topic es un número aleatorio que debo incluir en la respuesta
        # para que ésta sea tenida en cuenta solo por el jugador que ha hecho la petición
        randomId = parts[3]
        if playersCount == numPlayers:
            # ya no hay sitio para más jugadores
            client.publish('multiPlayerDash/mobileApp/notAccepted/'+randomId)
        else:
            # aceptamos y le asignamos el identificador del siguiente jugador
            client.publish('multiPlayerDash/mobileApp/accepted/'+randomId, playersCount)
            print ('se ha conectado el ', playersCount)
            playersCount = playersCount+1

    if command == 'arm_takeOff':
        # en este comando y en los siguientes, el último trozo del topic identifica al jugador que hace la petición
        id = int (parts[3])
        dron = swarm[id]
        if dron.state == 'connected':
            dron.arm()
            # operación no bloqueante. Cuando acabe publicará el evento correspondiente
            dron.takeOff(5, blocking=False, callback=publish_event, params='flying')

    if command == 'go':
        id = int (parts[3])
        dron = swarm[id]
        if dron.state == 'flying':
            direction = message.payload.decode("utf-8")
            dron.go(direction)

    if command == 'Land':
        id = int (parts[3])
        dron = swarm[id]
        if dron.state == 'flying':
            # operación no bloqueante. Cuando acabe publicará el evento correspondiente
            dron.Land(blocking=False, callback=publish_event, params='landed')

    if command == 'RTL':
        id = int (parts[3])
        dron = swarm[id]
        if dron.state == 'flying':
            # operación no bloqueante. Cuando acabe publicará el evento correspondiente
            dron.RTL(blocking=False, callback=publish_event, params='atHome')

    if command == 'startDrawing':
        id = int (parts[3])
        drawingAction [id] = 'startDrawing'

    if command == 'stopDrawing':
        id = int (parts[3])
        drawingAction [id] = 'nothing'

    if command == 'startRemovingDrawing':
        id = int (parts[3])
        drawingAction[id] = 'remove'

    if command == 'stopRemovingDrawing':
        id = int (parts[3])
        drawingAction[id] = 'nothing'
    if command == 'removeAll':
        id = int(parts[3])
        for item in traces[id]:
            if  item['marker'] != None:
                item['marker'].delete()
        traces[id] = []'''



def crear_ventana():

    global map_widget
    global createBtn,selectBtn, superviseBtn, createFrame, name, selectFrame, scene, scenePic,scenarios, current
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
    playersCount = 0

    connected = False
    # aqui indicare, para cada dron, si estamos pintando o no
    drawingAction = ['nothing']*4 # nothing, draw o remove
    # y aqui ire guardando los rastros
    traces = [[], [], [], []]

    # para guardar datos y luego poder borrarlos
    paths = []
    fence = []
    polys = []


    ventana = tk.Tk()
    ventana.title("Gestión de escenarios")
    ventana.geometry ('2400x1200')

    # El panel principal tiene una fila y dos columnas
    ventana.rowconfigure(0, weight=1)
    ventana.columnconfigure(0, weight=1)
    ventana.columnconfigure(1, weight=1)

    #controlFrame = tk.LabelFrame(ventana, text = 'Control')
    controlFrame = tk.LabelFrame(ventana, text='Control', font=("Arial", 10, "bold"))
    controlFrame.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    # El frame de control aparece en la primera columna
    controlFrame.rowconfigure(0, weight=1)
    controlFrame.rowconfigure(1, weight=1)
    controlFrame.columnconfigure(0, weight=1)
    controlFrame.columnconfigure(1, weight=1)
    controlFrame.columnconfigure(2, weight=1)


    # botones para crear/seleccionar/supervisar
    createBtn = tk.Button(controlFrame, text="Crear", bg="dark orange", command = createBtnClick)
    createBtn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    selectBtn = tk.Button(controlFrame, text="Seleccionar", bg="dark orange", command = selectBtnClick)
    selectBtn.grid(row=0, column=1,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    superviseBtn = tk.Button(controlFrame, text="Supervisar", bg="dark orange", command=superviseBtnClick)
    superviseBtn.grid(row=0, column=2,  padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    ################################# frame para crear escenario  ###################################################
    createFrame = tk.LabelFrame(controlFrame, text='Crear escenario', font=("Arial", 8, "bold"))
    # la visualización del frame se hace cuando se clica el botón de crear
    #createFrame.grid(row=1, column=0,  columnspan=3, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
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

    tk.Label (createFrame, text='Escribe el nombre aquí')\
        .grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    # el nombre se usará para poner nombre al fichero con la imagen y al fichero json con el escenario
    name = tk.StringVar()
    tk.Entry(createFrame, textvariable=name)\
        .grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    selectPlayersFrame = tk.LabelFrame(createFrame, text='Jugadores', font=("Arial", 8, "bold"))
    selectPlayersFrame.grid(row=2, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
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
    tk.Label (selectPlayersFrame, text = 'Selecciona el número de jugadores').\
        grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="1", bg="dark orange", command = lambda:  selectNumPlayers (1))\
        .grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="2", bg="dark orange", command=lambda: selectNumPlayers(2)) \
        .grid(row=1, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="3", bg="dark orange", command=lambda: selectNumPlayers(3)) \
        .grid(row=1, column=2, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectPlayersFrame, text="4", bg="dark orange", command=lambda: selectNumPlayers(4)) \
        .grid(row=1, column=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    inclusionFenceFrame = tk.LabelFrame (createFrame, text ='Definición de los límites del escenario')
    inclusionFenceFrame.grid(row=3, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    inclusionFenceFrame.rowconfigure(0, weight=1)
    inclusionFenceFrame.columnconfigure(0, weight=1)
    inclusionFenceFrame.columnconfigure(1, weight=1)
    # el fence de inclusión puede ser un poligono o un círculo
    # el parámetro 1 en el command indica que es fence de inclusion
    polyInclusionFenceBtn = tk.Button(inclusionFenceFrame, text="Polígono", bg="dark orange", command = lambda:  definePoly (1))
    polyInclusionFenceBtn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    circleInclusionFenceBtn = tk.Button(inclusionFenceFrame, text="Círculo", bg="dark orange", command = lambda:  defineCircle (1))
    circleInclusionFenceBtn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    # los obstacilos son fences de exclusión y pueden ser también polígonos o círculos
    # el parámetro 2 en el command indica que son fences de exclusión
    obstacleFrame = tk.LabelFrame(createFrame, text='Definición de los obstaculos del escenario')
    obstacleFrame.grid(row=4, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    obstacleFrame.rowconfigure(0, weight=1)
    obstacleFrame.columnconfigure(0, weight=1)
    obstacleFrame.columnconfigure(1, weight=1)

    polyObstacleBtn = tk.Button(obstacleFrame, text="Polígono", bg="dark orange", command = lambda: definePoly (2))
    polyObstacleBtn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    circleObstacleBtn = tk.Button(obstacleFrame, text="Círculo", bg="dark orange", command=lambda: defineCircle(2))
    circleObstacleBtn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    registerBtn = tk.Button(createFrame, text="Registra escenario", bg="dark orange", command = registerScenario)
    registerBtn.grid(row=5, column=0, padx=5, pady=5, sticky=tk.N +tk.E + tk.W)

    clearBtn = tk.Button(createFrame, text="Limpiar", bg="dark orange", command=clear)
    clearBtn.grid(row=6, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    ################################ frame para seleccionar escenarios ############################################
    selectFrame = tk.LabelFrame(controlFrame, text='Selecciona escenario', font=("Arial", 8, "bold"))

    # la visualización del frame se hace cuando se clica el botón de seleccionar
    #selectFrame.grid(row=1, column=0,  columnspan=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

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


    tk.Label (selectFrame, text = 'Selecciona el número de jugadores').\
        grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="1", bg="dark orange", command = lambda:  selectScenarios (1))\
        .grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="2", bg="dark orange", command=lambda: selectScenarios(2)) \
        .grid(row=1, column=1, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="3", bg="dark orange", command=lambda: selectScenarios(3)) \
        .grid(row=1, column=2, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    tk.Button(selectFrame, text="4", bg="dark orange", command=lambda: selectScenarios(4)) \
        .grid(row=1, column=3, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    # en este canvas se mostrarán las imágenes de los escenarios disponibles
    scenarioCanvas = tk.Canvas(selectFrame, width=300, height=200, bg='grey')
    scenarioCanvas.grid(row = 2, column=0, columnspan=4, padx=5, pady=5)

    prevBtn = tk.Button(selectFrame, text="<<", bg="dark orange", command = showPrev)
    prevBtn.grid(row=3, column=0, padx=5, pady=5, sticky=tk.N +  tk.E + tk.W)
    selectScenarioBtn = tk.Button(selectFrame, text="Seleccionar", bg="dark orange", command = selectScenario)
    selectScenarioBtn.grid(row=3, column=1, columnspan = 2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    nextBtn = tk.Button(selectFrame, text=">>", bg="dark orange", command = showNext)
    nextBtn.grid(row=3, column=3, padx=5, pady=5, sticky=tk.N +  tk.E + tk.W)

    # La función de cargar el multi escenario que hay en ese momento en los drones no está operativa aún
    loadBtn = tk.Button(selectFrame, text="Cargar el escenario que hay en el dron", bg="dark orange", state = tk.DISABLED, command=loadScenario)
    loadBtn.grid(row=4, column=0,columnspan = 4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    # pequeño frame para configurar la conexión
    connectFrame = tk.Frame(selectFrame)
    connectFrame.grid(row=5, column=0, columnspan=4, padx=5, pady=3, sticky=tk.N  + tk.E + tk.W)
    connectFrame.rowconfigure(0, weight=1)
    connectFrame.rowconfigure(1, weight=1)
    connectFrame.rowconfigure(2, weight=1)
    connectFrame.columnconfigure(0, weight=1)
    connectFrame.columnconfigure(1, weight=1)

    connectBtn = tk.Button(connectFrame, text="Conectar", bg="dark orange", command = connect)
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
    sendBtn.grid(row=6, column=0,columnspan = 4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    deleteBtn = tk.Button(selectFrame, text="Eliminar escenario", bg="red", fg = 'white', command = deleteScenario)
    deleteBtn.grid(row=7, column=0, columnspan = 4, padx=5, pady=5, sticky=tk.N +  tk.E + tk.W)

    ########################## frame para supervisar ####################################################
    superviseFrame = tk.LabelFrame(controlFrame, text='Supervisar vuelos', font=("Arial", 8, "bold"))
    # la visualización del frame se hace cuando se clica el botón de supervisar
    # superviseFrame.grid(row=1, column=0,  columnspan=3, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    superviseFrame.rowconfigure(0, weight=1)
    superviseFrame.rowconfigure(1, weight=1)
    superviseFrame.rowconfigure(2, weight=1)
    superviseFrame.rowconfigure(3, weight=1)


    superviseFrame.columnconfigure(0, weight=1)
    superviseFrame.columnconfigure(1, weight=1)
    superviseFrame.columnconfigure(2, weight=1)
    superviseFrame.columnconfigure(3, weight=1)

    plotBtn = tk.Button(superviseFrame, text="Generar Informe Visual", bg="dark orange", command=plotFlightReport)
    plotBtn.grid(row=6, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    timeBtn = tk.Button(superviseFrame, text="Ver Distacia de Vuelo", bg="dark orange", command=showFlightDistances)
    timeBtn.grid(row=5, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)

    parametersBtn = tk.Button(superviseFrame, text="Ajustar parámetros", bg="dark orange", command=adjustParameters)
    parametersBtn.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky=tk.N + tk.E + tk.W)
    # debajo de este label colocaremos botones para aterrizar los drones.
    # los colocaremos cuando sepamos cuántos drones tenemos en el enjambre

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
    #mapaFrame = tk.LabelFrame(ventana, text='Mapa')
    mapaFrame = tk.LabelFrame(ventana, text='Mapa', font=("Arial", 10, "bold"))

    mapaFrame.grid(row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    mapaFrame.rowconfigure(0, weight=1)
    mapaFrame.rowconfigure(1, weight=1)
    mapaFrame.columnconfigure(0, weight=1)

    # creamos el widget para el mapa
    map_widget = tkintermapview.TkinterMapView(mapaFrame, width=1400, height=1000, corner_radius=0)
    map_widget.grid(row=1, column=0, padx=5, pady=5)
    map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga",
                                    max_zoom=22)
    map_widget.set_position( 41.2764478, 1.9886568)  # Coordenadas del dronLab
    map_widget.set_zoom(20)


    # indicamos que capture los eventos de click sobre el mouse
    map_widget.add_right_click_menu_command(label="Cierra el fence", command=closeFence, pass_coords=True)
    map_widget.add_left_click_map_command(getFenceWaypoint)

    # ahora cargamos las imagenes de los iconos que vamos a usar

    # iconos para representar cada dron (circulo de color) y para marcar su rastro (círculo más pequeño del mismo color)
    im = Image.open("images/red.png")
    im_resized = im.resize((20, 20), Image.LANCZOS)
    red = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im.resize((10, 10), Image.LANCZOS)
    littleRed = ImageTk.PhotoImage(im_resized_plus)

    im = Image.open("images/blue.png")
    im_resized = im.resize((20, 20), Image.LANCZOS)
    blue = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im.resize((10, 10), Image.LANCZOS)
    littleBlue = ImageTk.PhotoImage(im_resized_plus)

    im = Image.open("images/green.png")
    im_resized = im.resize((20, 20), Image.LANCZOS)
    green = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im.resize((10, 10), Image.LANCZOS)
    littleGreen = ImageTk.PhotoImage(im_resized_plus)


    im = Image.open("images/yellow.png")
    im_resized = im.resize((20, 20), Image.LANCZOS)
    yellow = ImageTk.PhotoImage(im_resized)
    im_resized_plus = im.resize((10, 10), Image.LANCZOS)
    littleYellow = ImageTk.PhotoImage(im_resized_plus)


    im = Image.open("images/black.png")
    im_resized = im.resize((20, 20), Image.LANCZOS)
    black = ImageTk.PhotoImage(im_resized)

    dronPictures = [red, blue, green, yellow]
    colors =['red', 'blue', 'green', 'yellow']
    # para dibujar los rastros
    dronLittlePictures = [littleRed, littleBlue, littleGreen, littleYellow]

    '''# nos conectamos al broker para recibir las ordenes de los que vuelan con la web app
    clientName = "multiPlayerDash" + str(random.randint(1000, 9000))
    client = mqtt.Client(clientName,transport="websockets")


    broker_address = "dronseetac.upc.edu"
    broker_port = 8000

    client.username_pw_set(
        'dronsEETAC', 'mimara1456.'
    )
    print('me voy a conectar')
    client.connect(broker_address, broker_port )
    print('Connected to dronseetac.upc.edu:8000')

    client.on_message = on_message
    client.on_connect = on_connect
    client.connect(broker_address, broker_port)

    # me subscribo a cualquier mensaje  que venga del autopilot service
    client.subscribe('mobileApp/multiPlayerDash/#')
    client.loop_start()
    # para garantizar acceso excluyente a las estructuras para pintar el rastro
    lock = threading.Lock()'''

    return ventana
import csv

import time
import threading

flight_times = [0, 0, 0, 0]
start_times = [None, None, None, None]
flight_times_lock = threading.Lock()

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


import geopy.distance

import geopy.distance
from math import radians, sin, cos, sqrt, atan2

import geopy.distance
from math import radians, sin, cos, sqrt, atan2


def haversine_distance(coord1, coord2):

    #Calcula la distancia en metros entre dos coordenadas GPS usando la fórmula de Haversine.
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    R = 6371000  # Radio de la Tierra en metros
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


# Diccionario para guardar la posición inicial de cada dron
initial_positions = {}

# Diccionario para guardar la distancia total recorrida por cada dron
total_distances = {}


def processTelemetryInfo(id, telemetry_info):
    global dronIcons, colors, traces, lock, altitudes, modos, initial_positions, total_distances

    lat = telemetry_info.get('lat', 0)
    lon = telemetry_info.get('lon', 0)
    alt = telemetry_info.get('alt', 0)
    modo = telemetry_info.get('flightMode', "Desconocido")
    speed = telemetry_info.get('groundSpeed', 0)
    heading = telemetry_info.get('heading', 0)

    if lat == 0 and lon == 0:
        print(f"⚠️ Dron {id}: Datos de telemetría inválidos, ignorando paquete.")
        return

    # Si es la primera vez que recibimos datos de este dron, guardamos su posición inicial
    if id not in initial_positions:
        initial_positions[id] = (lat, lon)
        total_distances[id] = 0  # Reiniciar la distancia recorrida

    # Calcular distancia recorrida desde la última posición
    last_pos = traces[id][-1]['pos'] if traces[id] else initial_positions[id]
    segment_distance = haversine_distance(last_pos, (lat, lon))
    total_distances[id] += segment_distance

    # Muestra la distancia recorrida
    #print(f"Dron {id} ({colors[id]}): {round(total_distances[id], 2)} metros recorridos.")

    # Si es el primer paquete de este dron, poner el icono en el mapa
    if not dronIcons[id]:
        dronIcons[id] = map_widget.set_marker(lat, lon, icon=dronPictures[id], icon_anchor="center")
    else:
        dronIcons[id].set_position(lat, lon)  # Actualizar la posición en el mapa

    # Actualizanla altitud y el modo de vuelo en la interfaz
    if id < len(altitudes) and id < len(modos):
        altitudes[id]['text'] = f"Altitud: {round(alt, 2)}m"
        modos[id]['text'] = f"Modo: {modo}"

    # Guardar la telemetría
    with lock:
        if traces[id] is None:
            traces[id] = []
        traces[id].append({
            'pos': (lat, lon),
            'alt': alt,
            'speed': speed,
            'heading': heading,
            'flightMode': modo
        })


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


import matplotlib.pyplot as plt

def plotFlightReport():
    global traces
    if not traces:
        messagebox.showinfo("Sin datos", "No hay datos de vuelo disponibles.")
        return

    plt.figure(figsize=(10, 6))
    for i, trace in enumerate(traces):
        latitudes = [point['pos'][0] for point in trace]
        longitudes = [point['pos'][1] for point in trace]
        plt.plot(longitudes, latitudes, label=f"Dron {i + 1}")

    plt.xlabel("Longitud")
    plt.ylabel("Latitud")
    plt.title("Rutas de vuelo")
    plt.legend()
    plt.show()




if __name__ == "__main__":
    ventana = crear_ventana()
    ventana.mainloop()
