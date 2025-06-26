import os, datetime, itertools
from pathlib import Path

import qrcode
from dotenv import load_dotenv
from PIL import Image, ImageTk
import tkinter as tk


# Cargar WEB_URL
load_dotenv() # lee .env del cwd
url = os.getenv("WEB_URL")
if not url:
    raise SystemExit(" WEB_URL no encontrado en .env")


# Crear imagen
today  = datetime.date.today().strftime("%Y-%m-%d")      # 2025-06-23
qr_dir = Path("qr") / today                              # qr/2025-06-23
qr_dir.mkdir(parents=True, exist_ok=True)

# Buscar siguiente versión disponible
def next_filename():
    base = qr_dir / f"{today}.png"
    if not base.exists():
        return base
    for i in itertools.count(1):
        cand = qr_dir / f"{today}_v{i}.png"
        if not cand.exists():
            return cand

out_file = next_filename()

# Generar y guardar QR
img = qrcode.make(url)
img.save(out_file)
print(f"Guardado: {os.path.relpath(out_file, Path.cwd())}")

# Mostrar en pantalla
root = tk.Tk()
root.title("QR de WEB_URL")
qr_tk = ImageTk.PhotoImage(img.resize((300, 300), Image.NEAREST))

tk.Label(root, image=qr_tk).pack(padx=20, pady=20)
tk.Label(root, text=url, fg="blue").pack(pady=(0, 20))

root.mainloop()
