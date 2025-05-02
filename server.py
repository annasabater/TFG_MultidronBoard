# server.py
import socketio

# el servidor permite CORS desde cualquier origen (tu Flutter en localhost o dispositivo)
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

# mapeo fijo:
EMAIL_TO_COLOR = {
    'dron_azul1@upc.edu':   'blau',
    'dron_verde1@upc.edu':  'verd',
    'dron_rojo1@upc.edu':   'vermell',
    'dron_amarillo1@upc.edu':'groc'
}

@sio.on('connect', namespace='/jocs')
def connect(sid, environ):
    print('Client connected:', sid)

@sio.on('join', namespace='/jocs')
def on_join(sid, data):
    email = data.get('email')
    color = EMAIL_TO_COLOR.get(email)
    if not color:
        return sio.emit('error', {'msg':'Usuari no permès'}, room=sid, namespace='/jocs')
    # metemos al cliente en la sala 'competencia'
    sio.enter_room(sid, 'competencia', namespace='/jocs')
    # le enviamos el mensaje de espera
    sio.emit('waiting',
             {'msg': f"Esperant a que s'uneixin altres jugadors, vosté és el jugador de color {color}"},
             room=sid, namespace='/jocs')

@sio.on('start_game', namespace='/jocs')
def on_start(sid, data):
    # cuando el profesor llama a este evento
    sio.emit('game_started', {}, room='competencia', namespace='/jocs')
    print("Partida iniciada, notificant clients…")

if __name__ == '__main__':
    import eventlet
    print("Servidor Socket.IO escoltant a http://0.0.0.0:8000")
    eventlet.wsgi.server(eventlet.listen(('', 8000)), app)
