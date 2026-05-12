"""
Explorador del Registro de Empresas y Sociedades (RES)
Fuente: datos.gob.cl
"""

import re
import json
import requests
import pandas as pd
from io import StringIO

BASE_API = "https://datos.gob.cl/api/3/action"
BASE_CSV = "https://datos.gob.cl/dataset/363edd60-4919-4ff1-b85f-f8e14d61285a/resource/{rid}/download/{year}-sociedades-por-fecha-rut-constitucion{suffix}.csv"

# Resource IDs conocidos (los que encontramos en la búsqueda)
RESOURCE_IDS_CONOCIDOS = {
    2017: "667eef5c-0896-424b-baf1-d13356d40326",
    2018: "ca45026b-4dde-44b0-8725-64446a95f69d",
    2022: "3e286353-146d-47aa-ac42-e2f36e703d1f",
    2024: "42ee8c8c-59cf-42e4-89af-ec19a87dbf8d",
    2025: "71c8e355-226a-461e-809a-870c2275a178",
}

# Algunos años tienen sufijo distinto en el nombre del archivo
SUFIJOS = {
    2018: "-v2",
}


# ─────────────────────────────────────────────
# 1. OBTENER TODOS LOS RESOURCE IDs SCRAPEANDO
# ─────────────────────────────────────────────
def obtener_resource_ids():
    """
    Obtiene los resource IDs scrapeando la página del dataset.
    Fallback a los IDs conocidos si falla.
    """
    url = "https://datos.gob.cl/dataset/registro-de-empresas-y-sociedades"
    print(f"  Consultando: {url}")
    
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        
        # Buscar pares año + UUID en el HTML
        # El patrón es: /resource/UUID en links cerca de "año XXXX"
        uuids = re.findall(r'/resource/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', r.text)
        years = re.findall(r'a[ñn]o[_ ](\d{4})', r.text, re.IGNORECASE)
        
        result = {}
        for year, uuid in zip(years, uuids):
            result[int(year)] = uuid
        
        if result:
            print(f"  ✅ Encontrados {len(result)} años")
            for y, u in sorted(result.items()):
                print(f"     {y}: {u}")
            return result
        else:
            raise ValueError("No se encontraron pares año/UUID")
            
    except Exception as e:
        print(f"  ⚠️  Scraping falló ({e}), usando IDs conocidos")
        return RESOURCE_IDS_CONOCIDOS


# ─────────────────────────────────────────────
# 2. DESCARGAR CSV COMPLETO DE UN AÑO
# ─────────────────────────────────────────────
def descargar_csv(year, resource_id):
    sufijo = SUFIJOS.get(year, "")
    url = BASE_CSV.format(rid=resource_id, year=year, suffix=sufijo)
    print(f"  GET {url}")
    
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        print(f"  ❌ HTTP {r.status_code}")
        return pd.DataFrame()
    
    r.encoding = "utf-8"
    try:
        df = pd.read_csv(StringIO(r.text))
        print(f"  ✅ {len(df):,} filas | columnas: {df.columns.tolist()}")
        return df
    except Exception as e:
        print(f"  ❌ Error al parsear CSV: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# 3. BUSCAR VÍA API CKAN (sin bajar CSV completo)
# ─────────────────────────────────────────────
def buscar_api(resource_id, rut=None, nombre=None, limit=20):
    url = f"{BASE_API}/datastore_search"
    params = {"resource_id": resource_id, "limit": limit}
    
    if rut:
        params["filters"] = json.dumps({"rut": rut})
    if nombre:
        params["q"] = nombre
    
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        
        if data.get("success"):
            total   = data["result"]["total"]
            records = data["result"]["records"]
            print(f"  ✅ API OK | Total: {total} | Retornados: {len(records)}")
            return pd.DataFrame(records)
        else:
            print(f"  ❌ API falló: {data.get('error', {})}")
            return pd.DataFrame()
    except Exception as e:
        print(f"  ❌ Excepción: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# 4. BUSCAR DENTRO DE UN DataFrame
# ─────────────────────────────────────────────
def buscar_en_df(df, rut=None, nombre=None):
    if df.empty:
        return df
    
    mascara = pd.Series([True] * len(df), index=df.index)
    
    if rut:
        rut_cols = [c for c in df.columns if "rut" in c.lower()]
        if rut_cols:
            mascara &= df[rut_cols[0]].astype(str).str.contains(str(rut), na=False)
    
    if nombre:
        nom_cols = [c for c in df.columns if any(x in c.lower() for x in ["razon", "nombre", "social"])]
        if nom_cols:
            mascara &= df[nom_cols[0]].astype(str).str.contains(nombre, case=False, na=False)
    
    return df[mascara]


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    
    # ── PASO 1: Obtener resource IDs ──────────
    print("=" * 55)
    print("PASO 1: Obtener resource IDs")
    print("=" * 55)
    resource_ids = obtener_resource_ids()
    ultimo_year  = max(resource_ids.keys())
    ultimo_id    = resource_ids[ultimo_year]
    print(f"\n→ Usando año {ultimo_year} (id: {ultimo_id})")

    # ── PASO 2: Intentar API CKAN ─────────────
    print(f"\n{'=' * 55}")
    print(f"PASO 2: Probar API CKAN (año {ultimo_year})")
    print("=" * 55)
    df = buscar_api(ultimo_id, nombre="Mi Voz")

    # ── PASO 3: Si API falla, bajar CSV ───────
    if df.empty:
        print(f"\n{'=' * 55}")
        print(f"PASO 3: Descargar CSV directo (año {ultimo_year})")
        print("=" * 55)
        df_full = descargar_csv(ultimo_year, ultimo_id)
        
        if not df_full.empty:
            df = buscar_en_df(df_full, nombre="Mi Voz")
            print(f"\nResultados para 'Mi Voz': {len(df)}")

    # ── PASO 4: Mostrar y guardar ─────────────
    if not df.empty:
        print("\n" + df.to_string())
        df.to_csv("resultados_mi_voz.csv", index=False, encoding="utf-8-sig")
        print("\n✅ Guardado en resultados_mi_voz.csv")
    else:
        print("\n⚠️  Sin resultados.")

    # ── EXTRA: Ver columnas disponibles ───────
    print(f"\n{'=' * 55}")
    print("EXTRA: Ver columnas del dataset")
    print("=" * 55)
    df_muestra = buscar_api(ultimo_id, limit=1)
    if not df_muestra.empty:
        print("Columnas:", df_muestra.columns.tolist())
        print("\nEjemplo fila:")
        print(df_muestra.iloc[0].to_dict())