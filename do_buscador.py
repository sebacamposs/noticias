"""
Buscador de RUTs en el Diario Oficial Electrónico
- Recorre todas las ediciones desde 17-08-2016 hasta hoy
- Obtiene el número de edición automáticamente desde la página
- Busca cada RUT en la sección Empresas y Cooperativas
- Descarga PDFs cuando encuentra coincidencias
- Reanudable si se interrumpe
- Exporta resultados a Excel
"""

import re
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import date, timedelta
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
ARCHIVO_RUTS     = "D:/Software/Noticias/files/noticias/ruts.txt"
ARCHIVO_EXCEL    = "D:/Software/Noticias/files/noticias/resultados_do.xlsx"
CARPETA_PDFS     = Path("D:/Software/Noticias/files/noticias/pdfs_do")
ARCHIVO_PROGRESO = "D:/Software/Noticias/files/noticias/do_progreso.txt"
CARPETA_PDFS.mkdir(exist_ok=True)

FECHA_INICIO = date(2016, 8, 17)
PAUSA        = 0.5
TIMEOUT      = 15
HEADERS      = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

BASE_INDEX   = "https://www.diariooficial.interior.gob.cl/edicionelectronica/index.php"
BASE_EMPRESAS = "https://www.diariooficial.interior.gob.cl/edicionelectronica/empresas_cooperativas.php"


# ─────────────────────────────────────────────
# NORMALIZACIÓN
# ─────────────────────────────────────────────
def calcular_dv(numero):
    try:
        reversed_digits = map(int, reversed(str(numero)))
        factors = [2, 3, 4, 5, 6, 7]
        total = sum(d * factors[i % 6] for i, d in enumerate(reversed_digits))
        r = 11 - (total % 11)
        if r == 11: return "0"
        if r == 10: return "K"
        return str(r)
    except Exception:
        return "0"

def normalizar_rut(rut):
    rut = str(rut).strip().upper().replace(".", "")
    partes = rut.split("-")
    numero = partes[0]
    dv     = partes[1] if len(partes) > 1 else calcular_dv(numero)
    return numero, dv

def leer_ruts(path):
    ruts = {}  # numero -> dv
    with open(path, "r", encoding="utf-8") as f:
        for linea in f:
            rut = linea.strip()
            if rut:
                numero, dv = normalizar_rut(rut)
                ruts[numero] = dv
    print(f"✅ {len(ruts)} RUTs únicos cargados")
    return ruts


# ─────────────────────────────────────────────
# OBTENER NÚMERO DE EDICIÓN
# ─────────────────────────────────────────────
def obtener_edicion(fecha, session):
    """Obtiene el número de edición para una fecha dada."""
    fecha_str = fecha.strftime("%d-%m-%Y")
    url = f"{BASE_INDEX}?date={fecha_str}"
    try:
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        match = re.search(r'Edici[oó]n\s+N[uú]m\.\s+([\d\.]+)', r.text)
        if match:
            return int(match.group(1).replace(".", ""))
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
# PROGRESO
# ─────────────────────────────────────────────
def cargar_progreso():
    p = Path(ARCHIVO_PROGRESO)
    if p.exists():
        try:
            return date.fromisoformat(p.read_text().strip())
        except Exception:
            pass
    return None

def guardar_progreso(fecha):
    Path(ARCHIVO_PROGRESO).write_text(fecha.isoformat())


# ─────────────────────────────────────────────
# GENERAR FECHAS (lunes a sábado)
# ─────────────────────────────────────────────
def fechas_habiles(desde, hasta):
    fecha = desde
    while fecha <= hasta:
        if fecha.weekday() < 6:
            yield fecha
        fecha += timedelta(days=1)


# ─────────────────────────────────────────────
# CONSULTAR UNA EDICIÓN
# ─────────────────────────────────────────────
def obtener_tipo_actuacion(fila, todas_filas):
    """Encuentra el tipo de actuación más cercano anterior a la fila."""
    tipo_actual = "DESCONOCIDO"
    for f in todas_filas:
        texto = f.get_text(strip=True).upper()
        # Detectar por texto en vez de por clase
        for t in ["CONSTITUCIÓN", "MODIFICACIÓN", "DISOLUCIÓN", "MIGRACIÓN", "TRANSFORMACIÓN"]:
            if texto == t:  # coincidencia exacta
                tipo_actual = t
                break
        if f == fila:
            return tipo_actual
    return tipo_actual


def consultar_edicion(fecha, edicion, ruts_buscados, session):
    """
    Descarga la página de Empresas y Cooperativas y busca los RUTs.
    Retorna lista de coincidencias.
    """
    fecha_str = fecha.strftime("%d-%m-%Y")
    url = f"{BASE_EMPRESAS}?date={fecha_str}&edition={edicion}"

    try:
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        r.encoding = "utf-8"
    except Exception:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    todas_filas  = soup.find_all("tr")
    coincidencias = []

    for fila in todas_filas:
        if "content" not in fila.get("class", []):
            continue

        celdas = fila.find_all("td")
        if not celdas:
            continue

        texto = celdas[0].get_text(separator=" ", strip=True)

        # Buscar cada RUT en el texto de la fila
        for numero, dv in ruts_buscados.items():
            # Generar variantes del RUT con y sin puntos
            variantes = [
                f"{numero}-{dv}",           # 76634948-K
                f"{numero}-{dv}*",          # 76634948-K*
            ]
            # Con puntos: 76.634.948-K
            if len(numero) >= 7:
                n = numero
                con_puntos = ""
                if len(n) == 7:
                    con_puntos = f"{n[0]}.{n[1:4]}.{n[4:]}"
                elif len(n) == 8:
                    con_puntos = f"{n[0:2]}.{n[2:5]}.{n[5:]}"
                elif len(n) == 9:
                    con_puntos = f"{n[0:3]}.{n[3:6]}.{n[6:]}"
                if con_puntos:
                    variantes.append(f"{con_puntos}-{dv}")
                    variantes.append(f"{con_puntos}-{dv}*")

            for variante in variantes:
                if variante.upper() in texto.upper():
                    link = celdas[1].find("a") if len(celdas) > 1 else None
                    coincidencias.append({
                        "fecha":    fecha.isoformat(),
                        "edicion":  edicion,
                        "rut":      f"{numero}-{dv}",
                        "empresa":  texto,
                        "tipo":     obtener_tipo_actuacion(fila, todas_filas),
                        "url_pdf":  link["href"] if link else None,
                        "cve":      link.get_text(strip=True) if link else None,
                    })
                    break  # encontrado, no seguir buscando variantes

    return coincidencias


# ─────────────────────────────────────────────
# DESCARGAR PDF
# ─────────────────────────────────────────────
def descargar_pdf(url_pdf, rut, fecha, tipo):
    if not url_pdf:
        return None
    nombre = f"{rut.replace('-','')}_{fecha}_{tipo}_{url_pdf.split('/')[-1]}"
    ruta   = CARPETA_PDFS / nombre
    if ruta.exists():
        return str(ruta)
    try:
        r = requests.get(url_pdf, timeout=30, headers=HEADERS)
        r.raise_for_status()
        ruta.write_bytes(r.content)
        return str(ruta)
    except Exception as e:
        print(f"      ⚠️  Error PDF: {e}")
        return None


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":

    ruts = leer_ruts(ARCHIVO_RUTS)
    hoy  = date.today()

    # Resumir si hay progreso guardado
    ultimo_progreso = cargar_progreso()
    if ultimo_progreso:
        fecha_inicio = ultimo_progreso + timedelta(days=1)
        print(f"⚠️  Resumiendo desde {fecha_inicio}")
        resultados_previos = []
        if Path(ARCHIVO_EXCEL).exists():
            try:
                df_prev = pd.read_excel(ARCHIVO_EXCEL, sheet_name="Resultados")
                resultados_previos = df_prev.to_dict("records")
                print(f"   {len(resultados_previos)} resultados previos cargados")
            except Exception:
                resultados_previos = []
    else:
        fecha_inicio       = FECHA_INICIO
        resultados_previos = []

    todas_fechas = list(fechas_habiles(fecha_inicio, hoy))
    total        = len(todas_fechas)
    print(f"\nFecha inicio:   {fecha_inicio}")
    print(f"Fecha fin:      {hoy}")
    print(f"Días a revisar: {total}")
    print(f"Tiempo estimado: ~{total * PAUSA * 2 / 60:.0f} minutos")
    print(f"\nBuscando {len(ruts)} RUTs...\n" + "="*55)

    session          = requests.Session()
    todos_resultados = resultados_previos.copy()
    encontrados      = 0
    sin_edicion      = 0

    for i, fecha in enumerate(todas_fechas, 1):
        # Mostrar progreso cada 100 días
        if i % 100 == 0 or i == 1:
            pct = i / total * 100
            print(f"  [{i:>4}/{total}] {fecha} ({pct:.0f}%) | encontrados: {encontrados} | sin edición: {sin_edicion}")

        # Obtener número de edición
        edicion = obtener_edicion(fecha, session)
        time.sleep(PAUSA)

        if not edicion:
            sin_edicion += 1
            continue

        # Buscar RUTs en esa edición
        coincidencias = consultar_edicion(fecha, edicion, ruts, session)
        time.sleep(PAUSA)

        if coincidencias is None:
            continue

        for c in coincidencias:
            encontrados += 1
            print(f"\n  🎯 [{fecha}] {c['rut']} — {c['empresa'][:60]} ({c['tipo']})")

            ruta_pdf = descargar_pdf(
                c["url_pdf"],
                c["rut"].replace("-", ""),
                fecha.isoformat(),
                c["tipo"]
            )
            c["ruta_pdf_local"] = ruta_pdf
            todos_resultados.append(c)

        # Guardar progreso cada 100 días
        if i % 100 == 0:
            guardar_progreso(fecha)
            if todos_resultados:
                pd.DataFrame(todos_resultados).to_excel(
                    ARCHIVO_EXCEL,
                    sheet_name="Resultados",
                    index=False
                )
                print(f"  💾 Progreso guardado ({len(todos_resultados)} resultados)")

    # ── Exportar final ────────────────────────
    print(f"\n{'='*55}")
    print(f"Búsqueda completada")
    print(f"Total coincidencias: {encontrados}")
    print(f"Días sin edición:    {sin_edicion}")

    if todos_resultados:
        df = pd.DataFrame(todos_resultados)

        with pd.ExcelWriter(ARCHIVO_EXCEL, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Resultados", index=False)

            # Última aparición por RUT
            df.sort_values("fecha", ascending=False)\
              .drop_duplicates("rut")\
              .to_excel(writer, sheet_name="Último registro", index=False)

            # Una hoja por tipo
            for tipo in df["tipo"].unique():
                df[df["tipo"] == tipo].to_excel(
                    writer, sheet_name=tipo[:31], index=False
                )

        # Limpiar archivo de progreso
        Path(ARCHIVO_PROGRESO).unlink(missing_ok=True)
        print(f"✅ Exportado a {ARCHIVO_EXCEL}")
    else:
        print("⚠️  No se encontraron coincidencias")