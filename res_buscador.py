"""
Buscador de RUTs en el Registro de Empresas y Sociedades (RES)
- Lee RUTs desde un archivo TXT (uno por línea)
- Busca en todos los años 2013-2025
- Exporta resultados a Excel
"""

import requests
import pandas as pd
from io import StringIO
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURACIÓN — ajusta estas rutas
# ─────────────────────────────────────────────
ARCHIVO_RUTS  = "D:/Software/Noticias/files/noticias/ruts.txt"
ARCHIVO_EXCEL = "D:/Software/Noticias/files/noticias/resultados_res.xlsx"

# ─────────────────────────────────────────────
# TODAS LAS URLs 2013-2025
# ─────────────────────────────────────────────
URLS = {
    2013: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/fd2b91b0-eb8e-45f1-98d0-1f3316bb6468/download/2013-sociedades-por-fecha-rut-constitucion.csv",
    2014: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/ba5d9b2a-c292-45f5-9767-93420c62529e/download/2014-sociedades-por-fecha-rut-constitucion.csv",
    2015: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/6ffd416f-376f-40a8-9537-0d739f29fac9/download/2015-sociedades-por-fecha-rut-constitucion.csv",
    2016: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/288b0a7d-2d40-4c59-a312-2cc562cfe4eb/download/2016-sociedades-por-fecha-rut-constitucion_v3.csv",
    2017: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/667eef5c-0896-424b-baf1-d13356d40326/download/2017-sociedades-por-fecha-rut-constitucion.csv",
    2018: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/ca45026b-4dde-44b0-8725-64446a95f69d/download/2018-sociedades-por-fecha-rut-constitucion-v2.csv",
    2019: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/0d0d0ffb-fb28-4314-9bf0-8402353c9448/download/2019-sociedades-por-fecha-rut-constitucion-v3.csv",
    2020: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/1ad6cd82-8859-4601-a993-043009279f45/download/2020-sociedades-por-fecha-rut-constitucion.csv",
    2021: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/d5c69cb4-2fa8-4e92-906f-34776a30ce59/download/2021-sociedades-por-fecha-rut-constitucion.csv",
    2022: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/3e286353-146d-47aa-ac42-e2f36e703d1f/download/2022-sociedades-por-fecha-rut-constitucion.csv",
    2023: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/2fbe5f40-6c3d-42e6-8a84-e6ddce56d888/download/2023-sociedades-por-fecha-rut-constitucion.csv",
    2024: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/42ee8c8c-59cf-42e4-89af-ec19a87dbf8d/download/2024-sociedades-por-fecha-rut-constitucion.csv",
    2025: "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/71c8e355-226a-461e-809a-870c2275a178/download/2025-sociedades-por-fecha-rut-constitucion.csv",
}


# ─────────────────────────────────────────────
# NORMALIZACIÓN DE RUT
# ─────────────────────────────────────────────
def normalizar_rut(rut):
    """
    Cualquier formato → número base sin puntos ni dígito verificador.
    76.634.948-K  →  76634948
    76634948-K    →  76634948
    76634948      →  76634948
    """
    rut = str(rut).strip().upper()
    rut = rut.replace(".", "")
    rut = rut.split("-")[0]
    return rut


# ─────────────────────────────────────────────
# LEER RUTS DESDE ARCHIVO
# ─────────────────────────────────────────────
def leer_ruts(path):
    ruts = []
    with open(path, "r", encoding="utf-8") as f:
        for linea in f:
            rut = linea.strip()
            if rut:
                ruts.append(normalizar_rut(rut))
    print(f"✅ {len(ruts)} RUTs cargados desde {path}")
    return ruts


# ─────────────────────────────────────────────
# DESCARGAR CSV EN CHUNKS
# ─────────────────────────────────────────────
def descargar_csv(url, year):
    headers = {"User-Agent": "Mozilla/5.0"}
    contenido = b""

    try:
        with requests.get(url, stream=True, timeout=120, headers=headers) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    contenido += chunk
    except Exception as e:
        if not contenido:
            print(f"  ❌ {year}: error de descarga — {e}")
            return pd.DataFrame()
        print(f"  ⚠️  {year}: descarga incompleta ({len(contenido)/1e6:.1f} MB), procesando igual...")
    
    for encoding in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            texto = contenido.decode(encoding)
            df = pd.read_csv(StringIO(texto), sep=";", on_bad_lines="skip", low_memory=False)
            df["RUT_NORM"] = df["RUT"].apply(normalizar_rut)
            return df
        except Exception:
            continue

    print(f"  ❌ {year}: no se pudo parsear")
    return pd.DataFrame()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":

    # 1. Leer RUTs
    if not Path(ARCHIVO_RUTS).exists():
        print(f"❌ No se encontró {ARCHIVO_RUTS}")
        print("   Crea el archivo con un RUT por línea, ej:")
        print("   76634948")
        print("   77.195.728-5")
        exit()

    ruts     = leer_ruts(ARCHIVO_RUTS)
    from collections import Counter
    conteo = Counter(ruts)
    duplicados = {rut: n for rut, n in conteo.items() if n > 1}
    if duplicados:
        print(f"⚠️  {len(duplicados)} RUTs duplicados en el archivo:")
        for rut, n in sorted(duplicados.items()):
            print(f"   {rut} aparece {n} veces")

    ruts_set = set(ruts)

    # 2. Buscar en cada año
    todos_resultados = []
    print(f"\nBuscando {len(ruts_set)} RUTs en {len(URLS)} años...\n" + "=" * 55)

    for year, url in sorted(URLS.items()):
        print(f"  [{year}] Descargando...", end=" ", flush=True)
        df_año = descargar_csv(url, year)

        if df_año.empty:
            continue

        encontrados = df_año[df_año["RUT_NORM"].isin(ruts_set)].copy()

        if not encontrados.empty:
            encontrados.insert(0, "Año", year)
            todos_resultados.append(encontrados)
            print(f"✅ {len(df_año):,} filas → {len(encontrados)} coincidencias")
        else:
            print(f"✅ {len(df_año):,} filas → sin coincidencias")

    # 3. Consolidar
    print("\n" + "=" * 55)

    if not todos_resultados:
        print("⚠️  No se encontró ningún RUT en los datasets.")
        exit()

    df_final = pd.concat(todos_resultados, ignore_index=True)
    df_final = df_final.drop(columns=["RUT_NORM"], errors="ignore")
    df_final = df_final.sort_values(["RUT", "Año"])

    print(f"Total registros encontrados: {len(df_final)}")
    print("\nResumen:")
    for rut in sorted(df_final["RUT"].unique()):
        años = df_final[df_final["RUT"] == rut]["Año"].tolist()
        nombre = df_final[df_final["RUT"] == rut]["Razon Social"].iloc[0]
        print(f"  {rut}  {nombre:45}  años: {años}")

    # 4. Exportar a Excel
    print(f"\nExportando a {ARCHIVO_EXCEL}...")
    with pd.ExcelWriter(ARCHIVO_EXCEL, engine="openpyxl") as writer:

        # Hoja con todos los resultados
        df_final.to_excel(writer, sheet_name="Todos", index=False)

        # Una hoja por año
        for year in sorted(df_final["Año"].unique()):
            df_año = df_final[df_final["Año"] == year]
            df_año.to_excel(writer, sheet_name=str(year), index=False)

        # Registro más reciente por RUT
        df_reciente = (df_final
                       .sort_values("Año", ascending=False)
                       .drop_duplicates("RUT")
                       .sort_values("RUT"))
        df_reciente.to_excel(writer, sheet_name="Más reciente", index=False)

    hojas = ["Todos"] + [str(y) for y in sorted(df_final["Año"].unique())] + ["Más reciente"]
    print(f"✅ Listo — hojas: {' | '.join(hojas)}")