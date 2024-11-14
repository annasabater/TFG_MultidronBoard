import threading
import time

import paho.mqtt.client as mqtt
import json
from dronLink.Dron import Dron
import random

class AutopilotController:
    def __init__(self, numDrons, numPlayers, additionalEvents = None):
        self.numDrons = numDrons # numero de drones que hay que gestionar
        self.numPlayers = numPlayers
        self.playersCount = 0
        self.additionalEvents = additionalEvents

    def start (self):
        clientName = "multiPlayerDash" + str(random.randint(1000, 9000))
        self.client = mqtt.Client(clientName, transport="websockets")

        broker_address = "dronseetac.upc.edu"
        broker_port = 8000

        self.client.username_pw_set(
            'dronsEETAC', 'mimara1456.'
        )
        print('me voy a conectar')
        self.client.connect(broker_address, broker_port)
        print('Connected to dronseetac.upc.edu:8000')

        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        self.client.connect(broker_address, broker_port)

        self._stop_event = threading.Event()

        self.swarm = []

        for i in range(self.numDrons):
            self.swarm.append(Dron (i))

        # me subscribo a cualquier mensaje  que venga del mobileApp
        self.client.subscribe('mobileApp/multiPlayerDash/#')
        self.client.loop_start()
        print('AutopilotSerivce awaiting requests')
        return self.client, self.swarm

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("connected OK Returned code=", rc)
        else:
            print("Bad connection Returned code=", rc)



    def publish_event (self, id, event):
        # al ser drones idenificados dronLink_old nos pasa siempre en primer lugar el identificador
        # del dron que ha hecho la operación
        # lo necesito para identificar qué jugador debe hacer caso a la respuesta
        if self.additionalEvents:
            for item in self.additionalEvents:
                if item['event'] == 'publish_event':
                    item['method'](id, event)
                    return

        self.client.publish('multiPlayerDash/mobileApp/'+event+'/'+str(id))

    # aqui recibimos las publicaciones que hacen las web apps desde las que están jugando
    def on_message(self, client, userdata, message):
        # el formato del topic siempre será:
        # multiPlayerDash/mobileApp/COMANDO/NUMERO
        # el número normalmente será el número del jugador (entre el 0 y el 3)
        # excepto en el caso de la petición de conexión
        parts = message.topic.split ('/')
        print ('recibo ', message)
        command = parts[2]
        print('command ', command)
        res = None
        if self.additionalEvents:
            for item in self.additionalEvents:
                if item['event'] == command:
                    item['method'](int(parts[3]))
                    break

        if command == 'connect':
            # el cuarto trozo del topic es un número aleatorio que debo incluir en la respuesta
            # para que ésta sea tenida en cuenta solo por el jugador que ha hecho la petición
            randomId = parts[3]
            if self.playersCount == self.numPlayers:
                # ya no hay sitio para más jugadores
                self.client.publish('multiPlayerDash/mobileApp/notAccepted/'+randomId)
            else:
                # aceptamos y le asignamos el identificador del siguiente jugador
                self.client.publish('multiPlayerDash/mobileApp/accepted/'+randomId, self.playersCount)
                print ('se ha conectado el ', self.playersCount)
                self.playersCount = self.playersCount+1

        if command == 'arm_takeOff':
            # en este comando y en los siguientes, el último trozo del topic identifica al jugador que hace la petición
            id = int (parts[3])
            print ('takeoff ', id)
            dron = self.swarm[id]
            if dron.state == 'connected':
                dron.arm()
                # operación no bloqueante. Cuando acabe publicará el evento correspondiente
                dron.takeOff(5, blocking=False, callback=self.publish_event, params='flying')

        if command == 'go':
            id = int (parts[3])
            dron = self.swarm[id]
            if dron.state == 'flying':
                direction = message.payload.decode("utf-8")
                dron.go(direction)

        if command == 'Land':
            id = int (parts[3])
            dron = self.swarm[id]
            if dron.state == 'flying':
                # operación no bloqueante. Cuando acabe publicará el evento correspondiente
                dron.Land(blocking=False, callback=self.publish_event, params='landed')

        if command == 'RTL':
            id = int (parts[3])
            dron = self.swarm[id]
            if dron.state == 'flying':
                # operación no bloqueante. Cuando acabe publicará el evento correspondiente
                dron.RTL(blocking=False, callback=self.publish_event, params='atHome')



