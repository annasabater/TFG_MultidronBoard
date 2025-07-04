# TFG: Implementació d'un joc de combat de drons amb Flutter, Node.js i Python

Aquest projecte ofereix un entorn de competició de drons en temps real a través de tres scripts i permet definir àrees de vol i paràmetres de partida (durada, supervivència, 2 vs 2), dibuixar obstacles manualment i replicar-los automàticament amb Mode Mirall, iniciar, pausar i reiniciar el joc des de l’estació o la web, gestionar la lògica de combat (dispar, col·lisions, puntuacions) i configurar les regles de respawn segons el mode de joc.

Scripts:
combatSinMobile.py: S’executa quan es vol jugar sense integrar l’app mòbil (solament estació de terra).
combatConMobile.py: S’executa quan es vol jugar amb el backend i el frontend Flutter (versió amb web mòbil).
qr.py (opcional): Genera un codi QR per connectar-hi la web mòbil; cal executar-lo conjuntament amb combatConMobile.py.


## Taula de continguts

1. [Configuració de l’entorn](#configuració-de-lentorn)
2. [Instal·lació de l'entorn](#instal·lació-de-dependències)
3. [Vídeos](#vídeos)


## Configuració de l’entorn

Crea un fitxer `.env` a la carpeta arrel que contingui el següent:  

SERVER_URL=https://XXXX.ngrok-free.app
WEB_URL=https://XXXX.ngrok-free.app
ADMIN_KEY=profe1234

DRON_ROJO_EMAIL=dron_rojo1@upc.edu
DRON_ROJO_PASSWORD=Dron_rojo1*

DRON_AZUL_EMAIL=dron_azul1@upc.edu
DRON_AZUL_PASSWORD=Dron_azul1*

DRON_VERDE_EMAIL=dron_verde1@upc.edu
DRON_VERDE_PASSWORD=Dron_verde1*

DRON_AMARILLO_EMAIL=dron_amarillo1@upc.edu
DRON_AMARILLO_PASSWORD=Dron_amarillo1*


## Instal·lació de l'entorn

urllib3
python-dotenv
tkintermapview
pyautogui
python-socketio
requests
pymavlink
geopy
geographiclib
shapely
Pillow
pygame


## Vídeos

Enllaç del vídeo de funcionament: https://www.youtube.com/watch?v=esVt7HLI734
Enllaç del vídeo del recorregut pel codi: https://www.youtube.com/watch?v=mCd6iSzXLA0
Enllaç del vídeo demostratiu del script qr.py per a la generació del codi QR: https://www.youtube.com/watch?v=au_gs2SIiac





