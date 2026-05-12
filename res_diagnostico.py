import requests
import pandas as pd
from io import StringIO

URL_2024 = "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/42ee8c8c-59cf-42e4-89af-ec19a87dbf8d/download/2024-sociedades-por-fecha-rut-constitucion.csv"

# Solo bajar los primeros 50KB
headers = {"Range": "bytes=0-51200"}
r = requests.get(URL_2024, headers=headers, timeout=30)
r.encoding = "utf-8"

# Leer solo las primeras filas (puede haber una línea incompleta al final, ignorarla)
df = pd.read_csv(StringIO(r.text), on_bad_lines="skip")

print("Columnas:", df.columns.tolist())
print("\nPrimeras 3 filas:")
print(df.head(3).to_string())