import feedparser
import time
import urllib.parse
import json
import os
import re
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from datetime import datetime, timezone, timedelta
import random
import difflib
import unicodedata
from collections import defaultdict
from json_repair import repair_json

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()  # carga el archivo .env si existe

# ── Vertex AI (usa tus créditos de Google Cloud) ──
VERTEX_PROJECT  = os.environ.get("GOOGLE_CLOUD_PROJECT")
VERTEX_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
if not VERTEX_PROJECT:
    raise ValueError(
        "❌ Define GOOGLE_CLOUD_PROJECT en tu .env o como variable de entorno.\n"
        "   Ejemplo: GOOGLE_CLOUD_PROJECT=tu-project-id"
    )

try:
    vertexai.init(project=VERTEX_PROJECT, location=VERTEX_LOCATION)
    _gen_config = GenerationConfig(
        temperature=0.2,
        top_p=0.8,
        top_k=40,
        candidate_count=1,
        max_output_tokens=16384,
        response_mime_type="application/json",
    )
    _model = GenerativeModel("gemini-2.5-flash", generation_config=_gen_config)
    print(f"[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] ✅ Vertex AI inicializado · proyecto: {VERTEX_PROJECT} · región: {VERTEX_LOCATION}")
except Exception as _e:
    raise RuntimeError(f"❌ Error inicializando Vertex AI: {_e}") from _e

HORAS_ATRAS              = 24    # Solo noticias de las últimas N horas
RPD_LIMIT                = 500   # Vertex AI no tiene límite diario de requests
TAMANIO_BLOQUE           = 30    # Titulares por bloque enviado a la IA
PAUSE_ENTRE_BLOQUES      = 0     # Sin espera fija: el backoff de 429 cubre el throttling
MAX_SIN_FECHA_POR_FUENTE = 10    # Máximo de titulares sin fecha por fuente
MAX_TITULARES_POR_FUENTE = None  # Cap duro por fuente (None = sin límite)
REQUESTS_REALIZADOS      = 0

# Umbral de similitud para consolidación local previa a la IA
SIMILITUD_CONSOLIDACION_LOCAL = 0.88

# Máximo de rondas de consolidación IA — evita loop infinito si la IA no converge
MAX_RONDAS_CONSOLIDACION = 3

# Categorías temáticas — la IA asigna una por evento
CATEGORIAS = [
    "Política",
    "Economía",
    "Sociedad",
    "Internacional",
    "Deportes",
    "Cultura y Entretenimiento",
    "Catástrofes y Emergencias",
    "Ciencia y Tecnología",
]
CATEGORIAS_STR = ", ".join(CATEGORIAS)

# ─────────────────────────────────────────────
# FUENTES: (dominio, nombre_display, región)
# ─────────────────────────────────────────────
SOURCES_RSS = [
    ("emol.com", "Emol", "Nacional", None),
    ("latercera.com", "La Tercera", "Nacional", "https://latercera.com/rss"),
    ("biobiochile.cl", "BioBioChile", "Nacional", None),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_3___1.xml"),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_6___1.xml"),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_2___1.xml"),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_7___1.xml"),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_1___1.xml"),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_5___1.xml"),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_4___1.xml"),
    ("cooperativa.cl", "Cooperativa", "Nacional", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_8___1.xml"),
    ("elmostrador.cl", "El Mostrador", "Nacional", None),
    ("eldesconcierto.cl", "El Desconcierto", "Nacional", None),
    ("elciudadano.com", "El Ciudadano", "Nacional", "https://elciudadano.com/feed/"),
    ("publimetro.cl", "Publimetro", "Nacional", None),
    ("lunmas.cl", "Las Últimas Noticias", "Nacional", "https://lunmas.cl/feed/"),
    ("lacuarta.com", "La Cuarta", "Nacional", None),
    ("theclinic.cl", "The Clinic", "Nacional", "https://theclinic.cl/feed/"),
    ("ciperchile.cl", "Ciper", "Nacional", "https://ciperchile.cl/feed/"),
    ("lahora.cl", "La Hora", "Nacional", None),
    ("lasegunda.com", "La Segunda", "Nacional", None),
    ("eldinamo.cl", "El Dínamo", "Nacional", None),
    ("lanacion.cl", "La Nación", "Nacional", "https://lanacion.cl/feed/"),
    ("cambio21.cl", "Cambio21", "Nacional", "https://cambio21.cl/rss"),
    ("hoyxhoy.cl", "hoyXhoy", "Nacional", None),
    ("elsiglo.cl", "El Siglo", "Nacional", "https://elsiglo.cl/feed/"),
    ("duplos.cl", "Duplos", "Nacional", "https://duplos.cl/rss/"),
    ("diariosurnoticias.com", "Sur Noticias", "Nacional", "https://diariosurnoticias.com/feed/"),
    ("elperiodista.cl", "El Periodista", "Nacional", "https://elperiodista.cl/feed/"),
    ("larazon.cl", "La Razón", "Nacional", "https://larazon.cl/feed/"),
    ("cronicadigital.cl", "Crónica Digital", "Nacional", "https://cronicadigital.cl/feed/"),
    ("nuevopoder.cl", "Nuevo Poder", "Nacional", "https://nuevopoder.cl/feed/"),
    ("df.cl", "Diario Financiero", "Nacional", None),
    ("latercera.com/canal/pulso/", "Pulso", "Nacional", "https://latercera.com/rss/"),
    ("elpais.com/chile", "El País", "Nacional", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/chile/portada"),
    ("t13.cl", "Tele13", "Nacional", None),
    ("chilevision.cl/noticias", "Chilevisión Noticias", "Nacional", None),
    ("meganoticias.cl", "Meganoticias", "Nacional", None),
    ("tvn.cl/noticias", "TVN Noticias", "Nacional", None),
    ("cnnchile.com", "CNN Chile", "Nacional", "https://cnnchile.com/rss.xml"),
    ("elclarin.cl", "El Clarín", "Nacional", None),
    ("interferencia.cl", "Interferencia", "Nacional", None),

    # Arica y Parinacota
    ("estrellaarica.cl", "La Estrella de Arica", "Arica y Parinacota", None),
    ("elmorrocotudo.cl", "El Morrocotudo", "Arica y Parinacota", "https://www.elmorrocotudo.cl/taxonomy/term/4/0/feed"),
    ("elmorrocotudo.cl", "El Morrocotudo", "Arica y Parinacota", "https://www.elmorrocotudo.cl/taxonomy/term/5/0/feed"),
    ("elmorrocotudo.cl", "El Morrocotudo", "Arica y Parinacota", "https://www.elmorrocotudo.cl/taxonomy/term/6/0/feed"),
    ("elmorrocotudo.cl", "El Morrocotudo", "Arica y Parinacota", "https://www.elmorrocotudo.cl/taxonomy/term/7/0/feed"),
    ("elmorrocotudo.cl", "El Morrocotudo", "Arica y Parinacota", "https://www.elmorrocotudo.cl/taxonomy/term/8/0/feed"),
    ("elmorrocotudo.cl", "El Morrocotudo", "Arica y Parinacota", "https://www.elmorrocotudo.cl/taxonomy/term/9/0/feed"),
    ("aricaldia.cl", "Arica al Día", "Arica y Parinacota", "https://aricaldia.cl/feed/"),
    ("aricahoy.cl", "Arica Hoy", "Arica y Parinacota", "https://aricahoy.cl/feed/"),
    ("chasquis.cl", "Chasquis", "Arica y Parinacota", None),
    ("arica365.cl", "Arica365", "Arica y Parinacota", None),

    # Tarapacá
    ("estrellaiquique.cl", "La Estrella de Iquique", "Tarapacá", None),
    ("elboyaldia.cl", "El Boyaldía", "Tarapacá", "https://www.elboyaldia.cl/taxonomy/term/4/0/feed"),
    ("elboyaldia.cl", "El Boyaldía", "Tarapacá", "https://www.elboyaldia.cl/taxonomy/term/5/0/feed"),
    ("elboyaldia.cl", "El Boyaldía", "Tarapacá", "https://www.elboyaldia.cl/taxonomy/term/6/0/feed"),
    ("elboyaldia.cl", "El Boyaldía", "Tarapacá", "https://www.elboyaldia.cl/taxonomy/term/7/0/feed"),
    ("elboyaldia.cl", "El Boyaldía", "Tarapacá", "https://www.elboyaldia.cl/taxonomy/term/8/0/feed"),
    ("elboyaldia.cl", "El Boyaldía", "Tarapacá", "https://www.elboyaldia.cl/taxonomy/term/9/0/feed"),
    ("diariolongino.cl", "El Longino", "Tarapacá", "https://diariolongino.cl/feed/"),
    ("elsoldeiquique.cl", "El Sol de Iquique", "Tarapacá", "https://elsoldeiquique.cl/feed/"),
    ("elreporterodeiquique.com", "El Reportero", "Tarapacá", "https://elreporterodeiquique.com/feed/"),
    ("tarapacaonline.cl", "Tarapacá Online", "Tarapacá", "https://tarapacaonline.cl/feed/"),

    # Antofagasta
    ("diarioantofagasta.cl", "El Diario de Antofagasta", "Antofagasta", "https://diarioantofagasta.cl/feed/"),
    ("mercurioantofagasta.cl", "El Mercurio de Antofagasta", "Antofagasta", None),
    ("elnortero.cl", "El Nortero", "Antofagasta", None),
    ("estrellaantofagasta.cl", "La Estrella de Antofagasta", "Antofagasta", None),
    ("antofagastanoticias.cl", "Antofagasta Noticias", "Antofagasta", "https://antofagastanoticias.cl/feed/"),
    ("elamerica.cl", "El América", "Antofagasta", "https://elamerica.cl/feed/"),
    ("mercuriocalama.cl", "El Mercurio de Calama", "Antofagasta", None),
    ("enlalinea.cl", "En la Línea", "Antofagasta", "https://enlalinea.cl/feed/"),
    ("estrellatocopilla.cl", "La Estrella de Tocopílla", "Antofagasta", None),

    # Atacama
    ("atacamanoticias.cl", "Atacama Noticias", "Atacama", "https://atacamanoticias.cl/feed/"),
    ("tierramarillano.cl", "Tierramarillano", "Atacama", "https://tierramarillano.cl/feed/"),
    ("elquehaydecierto.cl", "El Quehaydesierto", "Atacama", None),
    ("diarioatacama.cl", "El Diario de Atacama", "Atacama", None),
    ("atacamaenlinea.cl", "Atacama en Línea", "Atacama", "https://atacamaenlinea.cl/rss.xml"),
    ("chanarcillo.cl", "Diario Chañarcillo", "Atacama", "https://chanarcillo.cl/feed/"),

    # Coquimbo
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/noticias/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/pais/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/region/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/economia/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/deportes/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/policial/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/mundo/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/comercial/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/ciencia/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/salud/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/actualidad/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/educacion/"),
    ("diarioeldia.cl", "El Día", "Coquimbo", "https://www.diarioeldia.cl/rss/politica/"),
    ("elobservatodo.cl", "El Observatodo", "Coquimbo", "https://www.elobservatodo.cl/taxonomy/term/4/0/feed"),
    ("elobservatodo.cl", "El Observatodo", "Coquimbo", "https://www.elobservatodo.cl/taxonomy/term/5/0/feed"),
    ("elobservatodo.cl", "El Observatodo", "Coquimbo", "https://www.elobservatodo.cl/taxonomy/term/6/0/feed"),
    ("elobservatodo.cl", "El Observatodo", "Coquimbo", "https://www.elobservatodo.cl/taxonomy/term/7/0/feed"),
    ("elobservatodo.cl", "El Observatodo", "Coquimbo", "https://www.elobservatodo.cl/taxonomy/term/8/0/feed"),
    ("elobservatodo.cl", "El Observatodo", "Coquimbo", "https://www.elobservatodo.cl/taxonomy/term/9/0/feed"),
    ("laserenaonline.cl", "La Serena Online", "Coquimbo", "https://laserenaonline.cl/feed/"),
    ("elserenense.cl", "El Serenense", "Coquimbo", "https://elserenense.cl/feed/"),
    ("elovallino.cl", "El Ovallino", "Coquimbo", "https://elovallino.cl/feed/"),
    ("ovallehoy.cl", "Ovalle Hoy", "Coquimbo", "https://ovallehoy.cl/feed/"),
    ("laperladellimari.cl", "La Perla del Limarí", "Coquimbo", "https://laperladellimari.cl/feed/"),
    ("diariolaregion.cl", "La Región", "Coquimbo", "https://diariolaregion.cl/feed/"),
    ("elregional.cl", "El Regional", "Coquimbo", None),
    ("elcoquimbano.cl", "El Coquimbano", "Coquimbo", "https://elcoquimbano.cl/feed/"),

    # Valparaíso
    ("mercuriovalpo.cl", "El Mercurio de Valparaíso", "Valparaíso", None),
    ("epicentrochile.com", "Epicentro Chile", "Valparaíso", "https://epicentrochile.com/feed/"),
    ("diariolaquinta.cl", "La Quinta", "Valparaíso", "https://diariolaquinta.cl/feed/"),
    ("elmartutino.cl", "El Martutino", "Valparaíso", "https://www.elmartutino.cl/taxonomy/term/4/0/feed"),
    ("elmartutino.cl", "El Martutino", "Valparaíso", "https://www.elmartutino.cl/taxonomy/term/5/0/feed"),
    ("elmartutino.cl", "El Martutino", "Valparaíso", "https://www.elmartutino.cl/taxonomy/term/6/0/feed"),
    ("elmartutino.cl", "El Martutino", "Valparaíso", "https://www.elmartutino.cl/taxonomy/term/7/0/feed"),
    ("elmartutino.cl", "El Martutino", "Valparaíso", "https://www.elmartutino.cl/taxonomy/term/8/0/feed"),
    ("elmartutino.cl", "El Martutino", "Valparaíso", "https://www.elmartutino.cl/taxonomy/term/9/0/feed"),
    ("estrellavalpo.cl", "La Estrella de Valparaíso", "Valparaíso", None),
    ("laregionhoy.cl", "La Región Hoy", "Valparaíso", "https://laregionhoy.cl/feed/"),
    ("observador.cl", "El Observador", "Valparaíso", "https://observador.cl/feed/"),
    ("estrellaquillota.cl", "La Estrella de Quillota", "Valparaíso", None),
    ("masnoticia.cl", "Más Noticia", "Valparaíso", None),
    ("eltrabajo.cl", "El Trabajo", "Valparaíso", None),
    ("elaconcagua.cl", "El Aconcagua", "Valparaíso", "https://elaconcagua.cl/feed/"),
    ("aconcaguadigital.cl", "Aconcagua Digital", "Valparaíso", None),
    ("lidermelipilla.cl", "El Líder de Melipilla - Talagante", "Valparaíso", None),
    ("lidersanantonio.cl", "El Líder de San Antonio", "Valparaíso", None),
    ("elproa.cl", "El Proa", "Valparaíso", "https://elproa.cl/feed/"),
    ("elandino.cl", "El Andino", "Valparaíso", None),
    ("losandesonline.cl", "Los Andes Online", "Valparaíso", None),
    ("elinformador.cl", "El Informador", "Valparaíso", None),

    # O'Higgins
    ("eltipografo.cl", "El Tipógrafo", "O'Higgins", None),
    ("elrancaguino.cl", "El Rancagüino", "O'Higgins", "https://elrancaguino.cl/feed/"),
    ("diarioelpulso.cl", "El Pulso", "O'Higgins", "https://diarioelpulso.cl/feed/"),
    ("elrancahuaso.cl", "El Rancahuaso", "O'Higgins", "https://www.elrancahuaso.cl/taxonomy/term/4/0/feed"),
    ("elrancahuaso.cl", "El Rancahuaso", "O'Higgins", "https://www.elrancahuaso.cl/taxonomy/term/5/0/feed"),
    ("elrancahuaso.cl", "El Rancahuaso", "O'Higgins", "https://www.elrancahuaso.cl/taxonomy/term/6/0/feed"),
    ("elrancahuaso.cl", "El Rancahuaso", "O'Higgins", "https://www.elrancahuaso.cl/taxonomy/term/7/0/feed"),
    ("elrancahuaso.cl", "El Rancahuaso", "O'Higgins", "https://www.elrancahuaso.cl/taxonomy/term/8/0/feed"),
    ("elrancahuaso.cl", "El Rancahuaso", "O'Higgins", "https://www.elrancahuaso.cl/taxonomy/term/9/0/feed"),
    ("elcachapoal.cl", "El Cachapoal", "O'Higgins", "https://elcachapoal.cl/feed/"),
    ("lanoticia.cl", "La Noticia", "O'Higgins", "https://lanoticia.cl/feed/"),
    ("horadenoticias.cl", "Hora de Noticias", "O'Higgins", "https://horadenoticias.cl/feed/"),
    ("diarioelcondor.cl", "El Cóndor", "O'Higgins", None),
    ("hdn.cl", "HDN", "O'Higgins", None),
    ("diarioviregion.cl", "Diario VI Región", "O'Higgins", None),
    ("latribunadecolchagua.cl", "La Tribuna de Colchagua", "O'Higgins", "https://latribunadecolchagua.cl/feed/"),
    ("diarioelmarino.cl", "El Marino", "O'Higgins", "https://diarioelmarino.cl/actualidad/feed/"),

    # Maule
    ("elamaule.cl", "El Amaule", "Maule", "https://www.elamaule.cl/taxonomy/term/4/0/feed"),
    ("elamaule.cl", "El Amaule", "Maule", "https://www.elamaule.cl/taxonomy/term/5/0/feed"),
    ("elamaule.cl", "El Amaule", "Maule", "https://www.elamaule.cl/taxonomy/term/6/0/feed"),
    ("elamaule.cl", "El Amaule", "Maule", "https://www.elamaule.cl/taxonomy/term/7/0/feed"),
    ("elamaule.cl", "El Amaule", "Maule", "https://www.elamaule.cl/taxonomy/term/8/0/feed"),
    ("elamaule.cl", "El Amaule", "Maule", "https://www.elamaule.cl/taxonomy/term/9/0/feed"),
    ("redmaule.com", "Red Maule", "Maule", None),
    ("diarioelcentro.cl", "Diario el Centro", "Maule", "https://diarioelcentro.cl/feed/"),
    ("atentos.cl", "Atentos", "Maule", "https://atentos.cl/feed/"),
    ("elmauleinforma.cl", "El Maule Informa", "Maule", "https://elmauleinforma.cl/feed/"),
    ("diariotalca.cl", "Diario Talca", "Maule", "https://diariotalca.cl/feed/"),
    ("diarioelheraldo.cl", "El Heraldo", "Maule", "https://diarioelheraldo.cl/feed"),
    ("linaresenlinea.cl", "Linares en línea", "Maule", "https://linaresenlinea.cl/feed/"),
    ("lectoronline.cl", "El Lector", "Maule", None),
    ("linaresnoticia.cl", "Linares Noticia", "Maule", None),
    ("septimapaginanoticias.cl", "Séptima Página Noticias", "Maule", None),
    ("diariolaprensa.cl", "La Prensa", "Maule", None),
    ("diariocurico.cl", "Diario Curicó", "Maule", "https://diariocurico.cl/feed/"),
    ("prensacurico.cl", "Prensa Curicó", "Maule", None),
    ("cronicanoticias.cl", "Crónica Noticias", "Maule", "https://cronicanoticias.cl/feed/"),
    ("diariocauquenes.cl", "Diario Cauquenes", "Maule", "https://diariocauquenes.cl/feed/"),
    ("cauquenesnet.cl", "Cauquenesnet", "Maule", "https://cauquenesnet.cl/feed/"),

    # Biobío
    ("pagina7.cl", "Página 7", "Biobío", None),
    ("diarioconcepcion.cl", "Diario Concepción", "Biobío", "https://diarioconcepcion.cl/rss.xml"),
    ("sabes.cl", "Sabes", "Biobío", None),
    ("resumen.cl", "Resumen", "Biobío", None),
    ("elsur.cl", "El Sur", "Biobío", None),
    ("estrellaconcepcion.cl", "La Estrella de Concepción", "Biobío", None),
    ("elconcecuente.cl", "El Concecuente", "Biobío", "https://www.elconcecuente.cl/taxonomy/term/4/0/feed"),
    ("elconcecuente.cl", "El Concecuente", "Biobío", "https://www.elconcecuente.cl/taxonomy/term/5/0/feed"),
    ("elconcecuente.cl", "El Concecuente", "Biobío", "https://www.elconcecuente.cl/taxonomy/term/6/0/feed"),
    ("elconcecuente.cl", "El Concecuente", "Biobío", "https://www.elconcecuente.cl/taxonomy/term/7/0/feed"),
    ("elconcecuente.cl", "El Concecuente", "Biobío", "https://www.elconcecuente.cl/taxonomy/term/8/0/feed"),
    ("elconcecuente.cl", "El Concecuente", "Biobío", "https://www.elconcecuente.cl/taxonomy/term/9/0/feed"),
    ("latribuna.cl", "La Tribuna", "Biobío", "https://latribuna.cl/rss.xml"),
    ("elcontraste.cl", "El Contraste", "Biobío", "https://elcontraste.cl/feed/"),
    ("angelino.cl", "Angelino", "Biobío", None),

    # Ñuble
    ("ladiscusion.cl", "La Discusión", "Ñuble", "https://ladiscusion.cl/feed/"),
    ("chillanonline.cl", "Chillán Online", "Ñuble", None),
    ("cronicachillan.cl", "Crónica Chillán", "Ñuble", None),
    ("elsancarlino.cl", "El Sancarlino", "Ñuble", None),
    ("sancarlosonline.cl", "San Carlos Online", "Ñuble", "https://sancarlosonline.cl/rss.xml"),
    ("sancarlosaldia.cl", "San Carlos al día", "Ñuble", None),
    ("lafontana.cl", "La Fontana", "Ñuble", "https://lafontana.cl/feed/"),

    # Araucanía
    ("araucaniadiario.cl", "Araucanía Diario", "Araucanía", None),
    ("clave9.cl", "Clave 9", "Araucanía", "https://clave9.cl/feed/"),
    ("araucanianoticias.cl", "Araucanía Noticias", "Araucanía", "https://araucanianoticias.cl/feed/"),
    ("laopinon.cl", "La Opiñón", "Araucanía", "https://www.laopinon.cl/taxonomy/term/4/0/feed"),
    ("laopinon.cl", "La Opiñón", "Araucanía", "https://www.laopinon.cl/taxonomy/term/5/0/feed"),
    ("laopinon.cl", "La Opiñón", "Araucanía", "https://www.laopinon.cl/taxonomy/term/6/0/feed"),
    ("laopinon.cl", "La Opiñón", "Araucanía", "https://www.laopinon.cl/taxonomy/term/7/0/feed"),
    ("laopinon.cl", "La Opiñón", "Araucanía", "https://www.laopinon.cl/taxonomy/term/8/0/feed"),
    ("laopinon.cl", "La Opiñón", "Araucanía", "https://www.laopinon.cl/taxonomy/term/9/0/feed"),
    ("temucodiario.cl", "Temuco Diario", "Araucanía", "https://temucodiario.cl/feed/"),
    ("primeranota.cl", "Primera Nota", "Araucanía", None),
    ("prensaciudadana.cl", "Prensa Ciudadana", "Araucanía", "https://prensaciudadana.cl/feed/"),
    ("alertanoticiastemuco.cl", "Alerta Noticias", "Araucanía", "https://alertanoticiastemuco.cl/feed/"),
    ("lasnoticiasdemalleco.cl", "Las Noticias", "Araucanía", "https://lasnoticiasdemalleco.cl/feed/"),
    ("malleco7.cl", "Malleco 7", "Araucanía", "https://malleco7.cl/feed/"),
    ("angolnoticiasnew.cl", "Angol Noticias", "Araucanía", "https://angolnoticiasnew.cl/feed/"),
    ("eldiariodelaaraucania.cl", "El Diario de la Araucanía", "Araucanía", None),
    ("noticiasdellago.cl", "Noticias del Lago", "Araucanía", "https://noticiasdellago.cl/feed/"),
    ("australtemuco.cl", "El Austral de Temuco", "Araucanía", None),

    # Los Ríos
    ("diariodevaldivia.cl", "Diario de Valdivia", "Los Ríos", None),
    ("rioenlinea.cl", "Río en Línea", "Los Ríos", None),
    ("diariolaguino.cl", "Diario Laguino", "Los Ríos", None),
    ("elnaveghable.cl", "El Naveghable", "Los Ríos", None),
    ("periodicolosrios.cl", "Los Ríos", "Los Ríos", None),
    ("losriosaldia.cl", "Los Ríos al Día", "Los Ríos", None),
    ("noticiaslosrios.cl", "Noticias los Ríos", "Los Ríos", "https://noticiaslosrios.cl/feed/"),
    ("diarioelranco.cl", "El Ranco", "Los Ríos", "https://diarioelranco.cl/feed/"),
    ("diariolaunion.cl", "La Unión", "Los Ríos", None),
    ("lavozdepaillaco.cl", "La voz de Paillaco", "Los Ríos", None),
    ("diariopaillaco.cl", "Diario Paillaco", "Los Ríos", None),
    ("lapaila.cl", "El Paila", "Los Ríos", None),
    ("diariocorral.cl", "Diario Corral", "Los Ríos", None),
    ("diarioriobueno.cl", "Diario Río Bueno", "Los Ríos", None),
    ("diariofutrono.cl", "Diario Futrono", "Los Ríos", None),
    ("diariolagoranco.cl", "Diario Lago Ranco", "Los Ríos", None),
    ("diariolanco.cl", "Diario Lanco", "Los Ríos", None),
    ("diariomafil.cl", "Diario Máfil", "Los Ríos", None),
    ("eldiariopanguipulli.cl", "El Diario Panguipulli", "Los Ríos", None),
    ("centralnoticias.cl", "Central Noticias", "Los Ríos", None),
    ("diariosanjose.cl", "Diario San José", "Los Ríos", None),
    ("australvaldivia.cl", "Diario Austral de Valdivia", "Los Ríos", None),

    # Los Lagos
    ("australosorno.cl", "El Austral de Osorno", "Los Lagos", None),
    ("ellanquihue.cl", "El Llanquihue", "Los Lagos", None),
    ("elinsular.cl", "El Insular", "Los Lagos", None),
    ("elrepuertero.cl", "El Repuertero", "Los Lagos", "https://www.elrepuertero.cl/taxonomy/term/4/0/feed"),
    ("elrepuertero.cl", "El Repuertero", "Los Lagos", "https://www.elrepuertero.cl/taxonomy/term/5/0/feed"),
    ("elrepuertero.cl", "El Repuertero", "Los Lagos", "https://www.elrepuertero.cl/taxonomy/term/6/0/feed"),
    ("elrepuertero.cl", "El Repuertero", "Los Lagos", "https://www.elrepuertero.cl/taxonomy/term/7/0/feed"),
    ("elrepuertero.cl", "El Repuertero", "Los Lagos", "https://www.elrepuertero.cl/taxonomy/term/8/0/feed"),
    ("elrepuertero.cl", "El Repuertero", "Los Lagos", "https://www.elrepuertero.cl/taxonomy/term/9/0/feed"),
    ("diariodepuertomontt.cl", "Diario de Puerto Montt", "Los Lagos", None),
    ("datossur.cl", "Datos Sur", "Los Lagos", "https://datossur.cl/index.php?format=feed&type=rss"),
    ("diariochiloe.cl", "Diario Chiloé", "Los Lagos", None),
    ("guardiandelsur.cl", "Gurdián del Sur", "Los Lagos", "https://guardiandelsur.cl/feed/"),
    ("paislobo.cl", "Paislobo", "Los Lagos", None),
    ("elvacanudo.cl", "El Vacanudo", "Los Lagos", "https://www.elvacanudo.cl/taxonomy/term/4/0/feed"),
    ("elvacanudo.cl", "El Vacanudo", "Los Lagos", "https://www.elvacanudo.cl/taxonomy/term/5/0/feed"),
    ("elvacanudo.cl", "El Vacanudo", "Los Lagos", "https://www.elvacanudo.cl/taxonomy/term/6/0/feed"),
    ("elvacanudo.cl", "El Vacanudo", "Los Lagos", "https://www.elvacanudo.cl/taxonomy/term/7/0/feed"),
    ("elvacanudo.cl", "El Vacanudo", "Los Lagos", "https://www.elvacanudo.cl/taxonomy/term/8/0/feed"),
    ("elvacanudo.cl", "El Vacanudo", "Los Lagos", "https://www.elvacanudo.cl/taxonomy/term/9/0/feed"),
    ("diariodeosorno.cl", "Diario de Osorno", "Los Lagos", None),
    ("laestrellachiloe.cl", "La Estrella de Chiloé", "Los Lagos", None),
    ("noticiaschiloe.cl", "Noticias Chiloé", "Los Lagos", "https://noticiaschiloe.cl/feed/"),
    ("eha.cl", "El Heraldo Austral", "Los Lagos", None),
    ("diariopuertovaras.cl", "Diario Puerto Varas", "Los Lagos", "https://diariopuertovaras.cl/feed/"),
    ("elcalbucano.cl", "El Calbucano", "Los Lagos", "https://elcalbucano.cl/feed/"),
    ("elhuemul.cl", "El Huemul", "Los Lagos", "https://elhuemul.cl/feed/"),
    ("laopiniondechiloe.cl", "La Opinión de Chiloé", "Los Lagos", "https://laopiniondechiloe.cl/feed/"),

    # Aysén
    ("eldivisadero.cl", "El Divisadero", "Aysén", None),
    ("diarioregionalaysen.cl", "Diario Regional De Aysén", "Aysén", None),
    ("elpatagondomingo.cl", "El Patagón Domingo", "Aysén", None),
    ("aysenahora.cl", "Aysen Ahora", "Aysén", "https://aysenahora.cl/feed/"),

    # Magallanes
    ("laprensaaustral.cl", "La Prensa Austral", "Magallanes", "https://laprensaaustral.cl/feed/"),
    ("elpinguino.com", "El Pingüino", "Magallanes", "https://elpinguino.com/feed/"),
    ("elmagallanico.com", "El Magallánico", "Magallanes", "https://elmagallanico.com/feed/"),
    ("ovejeronoticias.cl", "Ovejero Noticias", "Magallanes", "https://ovejeronoticias.cl/feed/"),
    ("eltirapiedras.cl", "El Tirapiedras", "Magallanes", "https://eltirapiedras.cl/feed/"),
    ("opinionsur.cl", "Opinión Sur", "Magallanes", "https://opinionsur.cl/feed/"),
]







# ─────────────────────────────────────────────
# CONGLOMERADOS MEDIÁTICOS
# ─────────────────────────────────────────────
CONGLOMERADOS = {
    # ── Grupo El Mercurio ──
    "El Mercurio":                    "El Mercurio S.A.P",
    "Las Últimas Noticias":           "El Mercurio S.A.P",
    "La Segunda":                     "El Mercurio S.A.P",
    "hoyXhoy":                        "El Mercurio S.A.P",
    "La Estrella de Arica":           "El Mercurio S.A.P",
    "La Estrella de Iquique":         "El Mercurio S.A.P",
    "El Mercurio de Antofagasta":     "El Mercurio S.A.P",
    "La Estrella de Antofagasta":     "El Mercurio S.A.P",
    "El Mercurio de Calama":          "El Mercurio S.A.P",
    "La Estrella de Tocopilla":       "El Mercurio S.A.P",
    "El Diario de Atacama":           "El Mercurio S.A.P",
    "El Mercurio de Valparaíso":      "El Mercurio S.A.P",
    "La Estrella de Valparaíso":      "El Mercurio S.A.P",
    "La Estrella de Quillota":        "El Mercurio S.A.P",
    "El Trabajo":                     "El Mercurio S.A.P",
    "El Líder de Melipilla - Talagante": "El Mercurio S.A.P",
    "El Líder de San Antonio":        "El Mercurio S.A.P",
    "Diario Talca":                   "El Mercurio S.A.P",
    "El Sur":                         "El Mercurio S.A.P",
    "La Estrella de Concepción":      "El Mercurio S.A.P",
    "La Tribuna":                     "El Mercurio S.A.P",
    "Crónica Chillán":                "El Mercurio S.A.P",
    "Las Noticias":                   "El Mercurio S.A.P",
    "Diario Austral de Valdivia":     "El Mercurio S.A.P",
    "La Estrella de Chiloé":          "El Mercurio S.A.P",
    "El Austral de Osorno":           "El Mercurio S.A.P",
    "El Llanquihue":                  "El Mercurio S.A.P",
    "El Austral de Temuco":           "El Mercurio S.A.P",
    "La Prensa Austral":              "El Mercurio S.A.P",
    "El Pingüino":                    "El Mercurio S.A.P",
    "El Divisadero":                  "El Mercurio S.A.P",
    # ── Grupo Copesa ──
    "La Tercera":                     "COPESA",
    "Pulso":                          "COPESA",
    "La Cuarta":                      "COPESA",
    "Radio Agricultura":              "COPESA",
    # ── Medios Mi Voz ──
    "El Morrocotudo":                 "Medios Mi Voz",
    "El Boyaldía":                    "Medios Mi Voz",
    "El Nortero":                     "Medios Mi Voz",
    "El Quehaydecierto":              "Medios Mi Voz",
    "El Observatodo":                 "Medios Mi Voz", 
    "El Martutino":                   "Medios Mi Voz",
    "El Rancahuaso":                  "Medios Mi Voz",
    "El Amaule":                      "Medios Mi Voz",
    "El Concecuente":                 "Medios Mi Voz",
    "La Opiñón":                      "Medios Mi Voz",
    "El Naveghable":                  "Medios Mi Voz",
    "El Repuertero":                  "Medios Mi Voz",
    "El Vacanudo":                    "Medios Mi Voz",
    "El Magallanews":                 "Medios Mi Voz",
    # ── Grupo Luksic (Canal 13 / Tele13) ──
    # "Tele13":                         "Grupo Luksic",
    # "CNN Chile":                      "Grupo Luksic",
    # ── Grupo Bethia (Megamedia) ──
    # "Meganoticias":                   "Grupo Bethia",
    # ── TVN (estatal) ──
    # "TVN Noticias":                   "TVN (estatal)",
    # ── Chilevisión (Warner Bros. Discovery) ──
    # "Chilevisión Noticias":           "Warner Bros. Discovery",
    # ── Grupo Claro (VTR / Publimetro) ──
    # "Publimetro":                     "Grupo Claro",
}

def get_conglomerado(fuente: str) -> str:
    return CONGLOMERADOS.get(fuente, "Independiente")


# ─────────────────────────────────────────────
# MAPEO DE FUENTES
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# FUENTES IMPRESA (CMS Papel Digital)
# ─────────────────────────────────────────────
FUENTES_IMPRESA = [
    ("estrellaarica.cl",       "La Estrella de Arica",       "Arica y Parinacota"),
    ("estrellaiquique.cl",     "La Estrella de Iquique",      "Tarapacá"),
    ("estrellaantofagasta.cl", "La Estrella de Antofagasta",  "Antofagasta"),
    ("estrellatocopilla.cl",   "La Estrella de Tocopílla",    "Antofagasta"),
    ("estrellavalpo.cl",       "La Estrella de Valparaíso",   "Valparaíso"),
    ("estrellaquillota.cl",    "La Estrella de Quillota",     "Valparaíso"),
    ("estrellaconcepcion.cl",  "La Estrella de Concepción",   "Biobío"),
    ("laestrellachiloe.cl",    "La Estrella de Chiloé",       "Los Lagos"),
]

_IMPRESA_SKIP = {
    "editorial", "comentarios", "desde el morro", "para los perdidos",
    "de nuestro archivo", "zoom", "agro estratégico", "emergencias",
    "farmacia de turno", "guerra contra el planeta", "humor",
    "tablas de mareas", "el oráculo", "condorito",
}

def _es_titulo_impresa_valido(titulo):
    t = titulo.lower().strip()
    if not t or len(t) < 8:
        return False
    if t in _IMPRESA_SKIP:
        return False
    if len(t.split()) < 3:
        return False
    return True

def _scrape_impresa(dominio, nombre, region):
    import urllib.request, re as _re
    from datetime import date
    hoy = date.today()
    url = "https://www.{}/impresa/{}/{:02d}/{:02d}/papel/".format(
        dominio, hoy.year, hoy.month, hoy.day
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read(200_000).decode("utf-8", errors="ignore")
    except Exception:
        return []

    pat = _re.compile(
        r'<a[^>]+href=["\']([^"\']+/full/[^"\']+)["\'][^>]*>.*?<h5[^>]*>(.*?)</h5>',
        _re.DOTALL
    )
    resultados = []
    visto = set()
    for href, titulo_raw in pat.findall(html):
        titulo = _re.sub(r"<[^>]+>", "", titulo_raw).strip()
        if not _es_titulo_impresa_valido(titulo):
            continue
        if titulo.lower() in visto:
            continue
        visto.add(titulo.lower())
        link = href if href.startswith("http") else "https://www.{}{}".format(dominio, href)
        resultados.append({
            "title":      titulo,
            "source":     nombre,
            "region":     region,
            "fecha":      hoy.strftime("%Y-%m-%d 00:00"),
            "link":       link,
            "source_url": link,
            "_impresa":   True,
        })
    return resultados


def _construir_mapeo_fuentes():
    mapeo = {}
    for dominio, nombre, *_ in SOURCES_RSS:
        clave_dominio = re.sub(r'\.(com|cl|net|org)\b.*', '', dominio).strip().lower()
        mapeo[clave_dominio] = nombre
        mapeo[nombre.lower().strip()] = nombre
    return mapeo

MAPEO_FUENTES  = _construir_mapeo_fuentes()
FUENTES_VALIDAS = {nombre for _, nombre, *_ in SOURCES_RSS}

_TITULOS_BASURA = re.compile(
    r'^(cerrar(\s+sesi[oó]n)?'
    r'|close'
    r'|suscr[ií]be(te)?(\s+para\b.*)?'
    r'|suscribirse(\s.*)?'
    r'|inicia[r]?\s+sesi[oó]n(\s.*)?'
    r'|inicio\s+de\s+sesi[oó]n'
    r'|log\s*in'
    r'|sign\s*in'
    r'|acceso\s*(exclusivo|digital|premium|para\b.*)?'
    r'|suscripci[oó]n(\s.*)?'
    r'|paywall'
    r'|registr[aá](te|rme)(\s.*)?'
    r'|para\s+continuar\s+(leyendo|con\b.*)?'
    r'|continuar\s+leyendo(\s.*)?'
    r'|leer\s+m[aá]s(\s.*)?'
    r'|ver\s+m[aá]s(\s.*)?'
    r'|home'
    r'|inicio$'
    r'|portada$'
    r'|loading'
    r'|cargando'
    r'|\\.|\s*)$',
    re.IGNORECASE
)

def _norm_titulo_sin_fuente(titulo: str) -> str:
    return re.sub(r'\s+-\s+\S+.*$', '', titulo.strip()).strip()

def _es_titular_basura(titulo: str) -> bool:
    t = titulo.strip()
    if len(t) < 8:
        return True
    if t.startswith('- '):
        return True
    parte = _norm_titulo_sin_fuente(t)
    if len(parte.split()) == 1:
        return True
    if parte.lower() == 'actualidad':
        return True
    if _TITULOS_BASURA.match(t):
        return True
    if parte != t and _TITULOS_BASURA.match(parte):
        return True
    return False

_URL_BASURA = re.compile(
    r'/(etiquetas?|tags?|categorias?|temas?|secciones?|topicos?|keyword|author|autores?|search|buscar)/',
    re.IGNORECASE
)

_DOMAIN_TAG_PATTERNS = {
    'elrepuertero.cl':   ['/etiquetas/', '/user/'],
    'elmorrocotudo.cl':  ['/etiquetas/', '/user/'],
    'elrancahuaso.cl':   ['/etiquetas/', '/user/'],
    'elobservatodo.cl':  ['/etiquetas/', '/user/'],
    'elmartutino.cl':    ['/etiquetas/', '/user/'],
    'elboyaldia.cl':     ['/etiquetas/', '/user/'],
    'elinsular.cl':      ['/etiquetas/', '/user/'],
    'laopinon.cl':       ['/etiquetas/', '/user/'],
    'elvacanudo.cl':     ['/etiquetas/', '/user/'],
    'elconcecuente.cl':  ['/etiquetas/', '/user/'],
    'elamaule.cl':       ['/etiquetas/', '/user/'],
    'diarioelcentro.cl': ['/tema/'],
}

def _es_url_basura(url: str) -> bool:
    if not url:
        return False
    if _URL_BASURA.search(url):
        return True
    for dominio, patrones in _DOMAIN_TAG_PATTERNS.items():
        if dominio in url:
            for pat in patrones:
                if pat in url:
                    return True
    return False

_VERB_RE = re.compile(
    r'\b\w+(ó|aron|ieron|ió|aba|ían|ará|será|han?|fue|son|está[nb]?|van|'
    r'ado|ada|idos|idas|ando|endo)\b',
    re.IGNORECASE
)

def _es_etiqueta(titulo: str) -> bool:
    t = titulo.strip()
    t_limpio = re.sub(r'\s*-\s*\S+\.\S+\s*$', '', t).strip()
    if not t_limpio or not t_limpio[0].islower():
        return False
    if re.search(r'[.!?;:()\"\u2018\u201c\u201d\u2014\u2013,]', t_limpio):
        return False
    if _VERB_RE.search(t_limpio):
        return False
    if len(t_limpio.split()) > 6:
        return False
    return True

def log(mensaje):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {mensaje}")

def parsear_fecha(entry):
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    return None

def normalizar_fuente(nombre_fuente):
    nombre_lower = nombre_fuente.lower().strip()
    if nombre_lower in MAPEO_FUENTES:
        return MAPEO_FUENTES[nombre_lower]
    for clave, valor in MAPEO_FUENTES.items():
        if clave in nombre_lower or nombre_lower in clave:
            return valor
    nombre_limpio = re.sub(r'\s*[-–|·]\s*.*$', '', nombre_lower).strip()
    nombre_limpio = re.sub(r'\.(com|cl|net|org)\b.*', '', nombre_limpio).strip()
    if nombre_limpio in MAPEO_FUENTES:
        return MAPEO_FUENTES[nombre_limpio]
    for clave, valor in MAPEO_FUENTES.items():
        if clave in nombre_limpio or nombre_limpio in clave:
            return valor
    return None

def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def _norm_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = _strip_accents(s)
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def validar_categoria(categoria):
    if categoria in CATEGORIAS:
        return categoria
    cat_lower = (categoria or "").lower()
    for c in CATEGORIAS:
        if c.lower() in cat_lower or cat_lower in c.lower():
            return c
    if categoria:
        log(f"⚠️ Categoría inválida recibida de la IA: '{categoria}' → asignando 'Sin categoría'")
    return "Sin categoría"

def _extract_json_block(texto: str) -> str:
    if not texto:
        return ""
    texto = re.sub(r"```(?:json)?\s*|\s*```", "", texto, flags=re.IGNORECASE).strip()
    texto = (texto
             .replace("\u201c", '"').replace("\u201d", '"')
             .replace("\u2018", "'").replace("\u2019", "'"))
    first_brace  = texto.find("{")
    first_brack  = texto.find("[")
    candidates   = [i for i in [first_brace, first_brack] if i != -1]
    if not candidates:
        return texto.strip()
    start = min(candidates)
    last_brace   = texto.rfind("}")
    last_brack   = texto.rfind("]")
    end_candidates = [i for i in [last_brace, last_brack] if i != -1]
    if not end_candidates:
        return texto[start:].strip()
    end = max(end_candidates)
    if end < start:
        return texto[start:].strip()
    return texto[start:end+1].strip()

def _safe_json_load(texto: str):
    recortado = _extract_json_block(texto)
    try:
        return json.loads(repair_json(recortado))
    except Exception:
        return None

def _json_repair_prompt(texto_original: str) -> str:
    return f"""Re-emite EXACTAMENTE el mismo contenido de la respuesta anterior,
pero como JSON válido estricto (sin texto extra, sin markdown).
No agregues ni elimines elementos. Solo corrige el formato JSON.

RESPUESTA ANTERIOR:
{texto_original}
"""

# ─────────────────────────────────────────────
# DETECCIÓN DE TITULARES YA CLASIFICADOS
# ─────────────────────────────────────────────
def _construir_indice_clasificados(titulos_clasificados):
    normalizados = [_norm_text(t) for t in titulos_clasificados if t]
    bigrams = set()
    for t in normalizados:
        palabras = t.split()
        for i in range(len(palabras) - 1):
            bigrams.add((palabras[i], palabras[i+1]))
    return normalizados, bigrams

def _titulo_fue_clasificado(titulo_original, normalizados_clasificados, bigrams_clasificados):
    a = _norm_text(titulo_original)
    if not a:
        return False
    palabras_a = a.split()
    bigrams_a = set()
    for i in range(len(palabras_a) - 1):
        bigrams_a.add((palabras_a[i], palabras_a[i+1]))
    if bigrams_a and bigrams_clasificados and not (bigrams_a & bigrams_clasificados):
        return False
    for b in normalizados_clasificados:
        if not b:
            continue
        if a in b or b in a:
            return True
        if abs(len(a) - len(b)) / max(len(a), len(b), 1) > 0.5:
            continue
        score = difflib.SequenceMatcher(None, a, b).ratio()
        if score >= 0.88:
            return True
    return False

# ─────────────────────────────────────────────
# FASE 1: RECOLECCIÓN DE TITULARES
# ─────────────────────────────────────────────
def _resolver_url_con_playwright(link: str, page) -> str:
    """
    Resuelve la URL real de un link de Google News usando una página Playwright ya abierta.
    Devuelve la URL real si la obtiene, o string vacío si falla.
    """
    try:
        url_capturada = [None]

        def _on_nav(frame, _u=url_capturada):
            u = frame.url
            if u and "google.com" not in u and u.startswith("http"):
                _u[0] = u

        page.on("framenavigated", _on_nav)
        try:
            page.goto(link, wait_until="commit", timeout=20000)
            waited = 0
            while url_capturada[0] is None and waited < 5000:
                page.wait_for_timeout(200)
                waited += 200
                cur = page.url
                if cur and "google.com" not in cur:
                    url_capturada[0] = cur
                    break
        finally:
            page.remove_listener("framenavigated", _on_nav)

        return url_capturada[0] or ""
    except Exception:
        return ""


def fase_recoleccion(checkpoint_file: str = None) -> list:
    if checkpoint_file and os.path.exists(checkpoint_file):
        log(f"♻️  Cargando checkpoint de recolección: {checkpoint_file}")
        with open(checkpoint_file, encoding='utf-8') as f:
            titulares = json.load(f)
        log(f"✅ {len(titulares)} titulares cargados desde checkpoint")
        return titulares

    # Dominios que requieren resolución de URL real para filtrar etiquetas
    _DOMINIOS_PLAYWRIGHT = set(_DOMAIN_TAG_PATTERNS.keys())
    _fuentes_playwright = {d for d, *_ in SOURCES_RSS if d in _DOMINIOS_PLAYWRIGHT}
    _usar_playwright = len(_fuentes_playwright) > 0

    pw_page = None
    pw_browser = None
    pw_instance = None

    if _usar_playwright:
        try:
            from playwright.sync_api import sync_playwright
            pw_instance = sync_playwright().start()
            pw_browser  = pw_instance.chromium.launch(headless=True)
            pw_page     = pw_browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            ).new_page()
            # Bloquear recursos innecesarios para acelerar
            pw_page.route(
                "**/*.{woff,woff2,ttf,otf,eot,png,jpg,jpeg,gif,svg,css}",
                lambda r: r.abort()
            )
            log(f"🎭 Playwright listo para resolver URLs de {len(_fuentes_playwright)} fuentes problemáticas")
        except ImportError:
            log("⚠️  Playwright no instalado — URLs de fuentes problemáticas no se resolverán")
            _usar_playwright = False
        except Exception as e:
            log(f"⚠️  Error iniciando Playwright para recolección: {e}")
            _usar_playwright = False

    log(f"🛰️  Recopilando noticias de las últimas {HORAS_ATRAS}h ({len(SOURCES_RSS)} fuentes)...")
    limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_ATRAS)

    titulares = []
    sin_fecha_total = 0
    sin_fecha_por_fuente = defaultdict(int)
    # URLs ya vistas por fuente — evita duplicados entre secciones del mismo medio
    urls_vistas_por_fuente = defaultdict(set)

    for source_domain, source_nombre, source_region, source_rss in SOURCES_RSS:
        # Usar RSS nativo si está disponible, si no caer a Google News
        if source_rss:
            rss_url = source_rss
            fuente_rss = "nativo"
        else:
            query_encoded = urllib.parse.quote(f"site:{source_domain}")
            rss_url = (
                f"https://news.google.com/rss/search"
                f"?q={query_encoded}&hl=es-419&gl=CL&ceid=CL:es-419"
            )
            fuente_rss = "google"

        try:
            feed = feedparser.parse(rss_url)
            # Si el RSS nativo falla, intentar Google News como respaldo
            if source_rss and not feed.entries:
                query_encoded = urllib.parse.quote(f"site:{source_domain}")
                rss_url = (
                    f"https://news.google.com/rss/search"
                    f"?q={query_encoded}&hl=es-419&gl=CL&ceid=CL:es-419"
                )
                feed = feedparser.parse(rss_url)
                fuente_rss = "google (fallback)"
            incluidos = 0

            for entry in feed.entries:
                if MAX_TITULARES_POR_FUENTE is not None and incluidos >= MAX_TITULARES_POR_FUENTE:
                    break

                fecha_dt = parsear_fecha(entry)
                if fecha_dt is None:
                    if sin_fecha_por_fuente[source_nombre] >= MAX_SIN_FECHA_POR_FUENTE:
                        continue
                    sin_fecha_por_fuente[source_nombre] += 1
                    sin_fecha_total += 1
                    fecha_str = "Sin fecha"
                    incluir = True
                else:
                    incluir = fecha_dt >= limite
                    fecha_str = fecha_dt.strftime('%Y-%m-%d %H:%M')

                if incluir:
                    # Filtro de título primero (no requiere URL real)
                    if _es_titular_basura(entry.title) or _es_etiqueta(entry.title):
                        continue
                    # Extraer source_url ANTES de filtrar por URL
                    # entry.link es una URL de redirección de Google News, no la URL real
                    # Los patrones de dominio (_DOMAIN_TAG_PATTERNS) necesitan la URL real
                    source_url = ""
                    if hasattr(entry, 'source') and isinstance(entry.source, dict):
                        source_url = entry.source.get('href', '')
                    if not source_url and hasattr(entry, 'links'):
                        for lnk in entry.links:
                            href = lnk.get('href', '')
                            if href and 'google.com' not in href:
                                source_url = href
                                break
                    # Filtrar por URL real
                    # Para dominios problemáticos sin source_url, resolver con Playwright
                    url_a_filtrar = source_url
                    if not url_a_filtrar:
                        if _usar_playwright and pw_page and source_domain in _DOMINIOS_PLAYWRIGHT:
                            url_a_filtrar = _resolver_url_con_playwright(entry.link, pw_page)
                        if not url_a_filtrar:
                            url_a_filtrar = entry.link
                    if _es_url_basura(url_a_filtrar):
                        continue
                                    # Deduplicar por URL real dentro de la misma fuente
                    _url_dedup = source_url if source_url else entry.link
                    if _url_dedup and _url_dedup in urls_vistas_por_fuente[source_nombre]:
                        continue
                    if _url_dedup:
                        urls_vistas_por_fuente[source_nombre].add(_url_dedup)
                    titulares.append({
                        "title":         entry.title,
                        "source":        source_nombre,
                        "region":        source_region,
                        "conglomerado":  get_conglomerado(source_nombre),
                        "fecha":         fecha_str,
                        "link":          entry.link,
                        "source_url":    source_url,
                    })
                    incluidos += 1

            log(f"   [{source_region}] {source_nombre}: {incluidos}/{len(feed.entries)} [{fuente_rss}]")
        except Exception as e:
            log(f"⚠️  Error obteniendo {source_domain}: {e}")

        time.sleep(0.15)

        if checkpoint_file:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(titulares, f, ensure_ascii=False)

    # ── Fase impresa: ediciones del día (CMS Papel Digital) ──
    log(f"📰 Scrapeando ediciones impresas ({len(FUENTES_IMPRESA)} medios)...")
    impresa_total = 0
    for imp_dom, imp_nom, imp_reg in FUENTES_IMPRESA:
        imp_tits = _scrape_impresa(imp_dom, imp_nom, imp_reg)
        urls_fuente = urls_vistas_por_fuente[imp_nom]
        nuevos = 0
        for t in imp_tits:
            if t["link"] not in urls_fuente:
                urls_fuente.add(t["link"])
                titulares.append(t)
                nuevos += 1
        log(f"   [{imp_reg}] {imp_nom} (impresa): {nuevos} titulares")
        impresa_total += nuevos
        time.sleep(0.5)
    log(f"   📰 Impresa total: {impresa_total} titulares nuevos")

    log(f"✅ Total: {len(titulares)} noticias ({sin_fecha_total} sin fecha, limitadas por fuente)")

    # Cerrar Playwright de recolección si estaba activo
    if pw_browser:
        try:
            pw_browser.close()
        except Exception:
            pass
    if pw_instance:
        try:
            pw_instance.stop()
        except Exception:
            pass
        log("🔒 Playwright de recolección cerrado")

    return titulares

# ─────────────────────────────────────────────
# LLAMADAS A VERTEX AI
# ─────────────────────────────────────────────
def llamar_ia(prompt, intento=1, max_intentos=4, allow_repair=True):
    global REQUESTS_REALIZADOS

    try:
        REQUESTS_REALIZADOS += 1
        response = _model.generate_content(prompt)
        texto = (response.text or "").strip()

        parsed = _safe_json_load(texto)
        if parsed is not None:
            return parsed

        if allow_repair:
            log("🛠️ Respuesta no era JSON válido. Intentando reparación...")
            return llamar_ia(_json_repair_prompt(texto), intento=1, max_intentos=2, allow_repair=False)

        log(f"⚠️ No se pudo parsear JSON. Muestra: {texto[:200]}...")
        return None

    except Exception as e:
        error_str = str(e)
        if ("429" in error_str) or ("RESOURCE_EXHAUSTED" in error_str):
            base = 8
            wait_time = min(120, base * (2 ** (intento - 1))) + random.uniform(0, 3)
            log(f"⏳ Cuota/429. Backoff {wait_time:.1f}s (intento {intento}/{max_intentos})...")
            time.sleep(wait_time)
            if intento < max_intentos:
                return llamar_ia(prompt, intento + 1, max_intentos, allow_repair=allow_repair)
            log("❌ Máximo de reintentos alcanzado por 429/cuota")
            return None
        log(f"⚠️ Error de API: {e}")
        return None

# ─────────────────────────────────────────────
# FASE 2A: AGRUPACIÓN POR BLOQUES
# ─────────────────────────────────────────────
def agrupar_con_ia(lista_titulares: list, eventos_previos: list = None) -> list:
    titulares_texto = "\n".join([
        f"{t['_indice_global']}. [{t['source']} / {t['region']}] {t['title']}"
        for t in lista_titulares
    ])

    contexto_previo = ""
    if eventos_previos:
        nombres = [
            e.get('evento', '')[:60]
            for e in eventos_previos[-50:]
            if e.get('evento', '')
        ]
        contexto_previo = (
            "\nEVENTOS YA DETECTADOS (no dupliques si es el mismo hecho):\n"
            + "\n".join(f"- {n}" for n in nombres)
            + "\n"
        )

    prompt = f"""Eres un analista de medios chilenos experto en identificar hechos noticiosos específicos.

DEFINICIÓN CLAVE — qué es un EVENTO:
Un evento es UN HECHO CONCRETO con lugar, actores y momento específico.
✅ CORRECTO: "Incendio en bodega de Valparaíso", "Boric anuncia reforma previsional", "Chile vence a Venezuela 2-0"
❌ INCORRECTO: "Economía chilena", "Seguridad ciudadana", "Política nacional" — estos son TEMAS, no eventos.

REGLA FUNDAMENTAL: si dos titulares no hablan del MISMO hecho específico (misma acción, mismo lugar, mismos actores), NO los agrupes. Crea un evento separado para cada uno, aunque sean del mismo tema.
{contexto_previo}
TITULARES A CLASIFICAR:
{titulares_texto}

INSTRUCCIONES:
1. Lee cada titular e identifica el hecho concreto que describe (qué pasó, dónde, quién).
2. Agrupa SOLO los titulares que hablan del MISMO hecho específico (mismo episodio, misma acción).
3. Los titulares del mismo tema pero de distintos hechos van en eventos SEPARADOS.
4. TODOS los titulares deben quedar asignados. Si un titular no coincide con ningún otro, crea un evento de una sola noticia para él.
5. Nombra cada evento de forma específica: incluye lugar o actor cuando sea relevante. Evita nombres genéricos.
6. Asigna categoría eligiendo EXACTAMENTE una de: {CATEGORIAS_STR}
7. Si el mismo hecho ya aparece en "Eventos ya detectados", usa ese mismo nombre exacto.

FORMATO (solo índices numéricos en "titulares"):
[
  {{
    "evento": "Nombre específico del evento",
    "categoria": "Una categoría de la lista",
    "titulares": [1, 5, 12]
  }}
]

Responde SOLO con JSON válido, sin markdown ni texto adicional.
"""
    return llamar_ia(prompt)

# ─────────────────────────────────────────────
# CONSOLIDACIÓN LOCAL
# ─────────────────────────────────────────────
def consolidar_local(eventos: list) -> list:
    if len(eventos) <= 1:
        return eventos

    log(f"🔧 Consolidación local: {len(eventos)} eventos antes...")

    padre = list(range(len(eventos)))

    def find(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def union(x, y):
        padre[find(x)] = find(y)

    nombres_norm = [_norm_text(e.get('evento', '')) for e in eventos]

    for i in range(len(eventos)):
        for j in range(i + 1, len(eventos)):
            if find(i) == find(j):
                continue
            a, b = nombres_norm[i], nombres_norm[j]
            if abs(len(a) - len(b)) / max(len(a), len(b), 1) > 0.4:
                continue
            score = difflib.SequenceMatcher(None, a, b).ratio()
            if score >= SIMILITUD_CONSOLIDACION_LOCAL:
                union(i, j)

    grupos = defaultdict(list)
    for i in range(len(eventos)):
        grupos[find(i)].append(i)

    resultado = []
    fusionados = 0
    for raiz, indices in grupos.items():
        if len(indices) == 1:
            resultado.append(eventos[indices[0]])
            continue
        candidatos = sorted(indices, key=lambda i: len(eventos[i].get('titulares', [])), reverse=True)
        evento_base = dict(eventos[candidatos[0]])
        titulares_combinados = []
        for idx in candidatos:
            titulares_combinados.extend(eventos[idx].get('titulares', []))
        evento_base['titulares'] = titulares_combinados
        resultado.append(evento_base)
        fusionados += len(indices) - 1

    log(f"✅ Consolidación local: {len(eventos)} → {len(resultado)} eventos ({fusionados} fusiones)")
    return resultado

def _consolidar_chunk_ia(eventos: list) -> list:
    eventos_texto = json.dumps(eventos, ensure_ascii=False, indent=2)
    prompt = f"""Eres un analista de medios chilenos. Se procesaron noticias en bloques separados.
Es posible que el MISMO hecho noticioso aparezca varias veces con nombres distintos.

EVENTOS DETECTADOS:
{eventos_texto}

TAREA:
1. Identifica eventos que corresponden al mismo hecho real aunque tengan nombres distintos.
2. Fusiona esos eventos en uno solo, combinando TODOS sus titulares sin eliminar ninguno.
3. Elige el nombre más descriptivo para el evento fusionado.
4. Mantén los eventos únicos tal como están.
5. Conserva o reasigna la categoría eligiendo EXACTAMENTE una de esta lista: {CATEGORIAS_STR}

CRITERIO DE FUSIÓN — solo fusiona si estás SEGURO de que es el mismo hecho:
- Mismo hecho, mismo lugar, mismos actores, misma acción: FUSIONAR
- Mismo hecho en etapas distintas del MISMO día: FUSIONAR
- Misma historia pero enfoque distinto (anuncio vs reacción): FUSIONAR
- Mismo tema pero distintos lugares: "Incendio en Valparaíso" + "Incendio en Concepción" → NO fusionar
- Mismo tema pero distintos actores: dos accidentes distintos aunque sean del mismo tipo → NO fusionar
- Similar pero diferente: "Debate reforma previsional" + "Boric firma reforma previsional" → NO fusionar (distintas etapas no confirmadas como mismo hecho)

REGLA FUNDAMENTAL: si tienes cualquier duda sobre si dos eventos son el mismo hecho, NO fusiones. Es mejor tener duplicados que perder cobertura.

REGLAS TÉCNICAS:
- No elimines ningún índice de titular en el proceso de fusión.
- Ante la duda, NO fusionar.

Responde SOLO con JSON válido, sin markdown ni explicaciones.

FORMATO DE RESPUESTA:
[
  {{
    "evento": "Nombre corto y descriptivo",
    "categoria": "Una categoría de la lista",
    "titulares": [1, 5, 12, 23]
  }}
]
"""
    return llamar_ia(prompt)

def _pregrupar_candidatos(eventos: list, umbral: float = 0.25) -> tuple:
    """
    Pre-agrupa eventos por similitud léxica de sus nombres ANTES de enviarlos a la IA.
    Devuelve:
      - candidatos: lista de grupos (cada grupo es una lista de eventos) que tienen
                    similitud suficiente para merecer revisión IA
      - unicos:     lista de eventos sin ningún parecido con otros — se saltan la IA

    Usa similitud Jaccard sobre palabras clave (sin stopwords ni palabras genéricas).
    Un umbral bajo (0.25) es conservador: solo agrupa si comparten palabras específicas.
    """
    # Palabras demasiado genéricas para ser discriminativas
    _GENERICAS = {
        'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'en', 'y', 'a',
        'por', 'con', 'para', 'se', 'al', 'lo', 'su', 'es', 'que', 'o',
        # genéricas de noticias — aparecen en muchos eventos distintos
        'incendio', 'accidente', 'muerto', 'muertos', 'herido', 'heridos',
        'detenido', 'detenidos', 'caso', 'nuevo', 'nueva', 'gran', 'primer',
        'primera', 'segundo', 'segunda', 'tras', 'ante', 'sobre', 'entre',
        'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'mas',
        'gobierno', 'ministro', 'ministra', 'presidente', 'region', 'ciudad',
    }

    def palabras_clave(evento):
        texto = _strip_accents((evento.get('evento') or '').lower())
        palabras = re.findall(r'[a-z]{3,}', texto)
        return set(w for w in palabras if w not in _GENERICAS)

    def jaccard(kw_a, kw_b):
        if not kw_a or not kw_b:
            return 0.0
        inter = len(kw_a & kw_b)
        union = len(kw_a | kw_b)
        return inter / union if union else 0.0

    n = len(eventos)
    kws = [palabras_clave(ev) for ev in eventos]

    # Union-Find
    padre = list(range(n))

    def find(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def union(x, y):
        padre[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j):
                continue
            if not kws[i] or not kws[j]:
                continue
            if jaccard(kws[i], kws[j]) >= umbral:
                union(i, j)

    # Separar grupos de candidatos vs únicos
    grupos = defaultdict(list)
    for i in range(n):
        grupos[find(i)].append(i)

    candidatos = []
    unicos = []
    for raiz, indices in grupos.items():
        if len(indices) == 1:
            unicos.append(eventos[indices[0]])
        else:
            candidatos.append([eventos[i] for i in indices])

    return candidatos, unicos


def fase_consolidacion(hechos_por_bloques: list, chunk_size: int = 80) -> list:
    # Paso 1: consolidación local sin costo de API
    hechos = consolidar_local(hechos_por_bloques)

    if len(hechos) <= 1:
        return hechos

    # Paso 2: pre-agrupación léxica — separa candidatos a fusión de eventos únicos
    candidatos_grupos, unicos = _pregrupar_candidatos(hechos)
    candidatos_planos = [ev for grupo in candidatos_grupos for ev in grupo]

    log(f"🔍 Pre-agrupación: {len(candidatos_planos)} eventos candidatos a fusión, "
        f"{len(unicos)} únicos (se saltan la IA)")

    # Si no hay candidatos, no hay nada que consolidar con IA
    if not candidatos_planos:
        log(f"✅ Sin duplicados candidatos — {len(hechos)} eventos finales")
        return hechos

    log("🔀 Consolidación IA: fusionando duplicados residuales entre bloques...")

    if len(candidatos_planos) <= chunk_size:
        if PAUSE_ENTRE_BLOQUES > 0:
            time.sleep(PAUSE_ENTRE_BLOQUES)
        resultado = _consolidar_chunk_ia(candidatos_planos)
        if resultado:
            resultado = consolidar_local(resultado)
            resultado_final = resultado + unicos
            log(f"✅ {len(hechos_por_bloques)} → {len(resultado_final)} eventos únicos")
            return resultado_final
        log("⚠️ Falló la consolidación IA. Se usan los eventos de la consolidación local.")
        return hechos

    log(f"📦 {len(candidatos_planos)} candidatos — consolidando en rondas de {chunk_size} "
        f"(máx {MAX_RONDAS_CONSOLIDACION} rondas)...")
    ronda = candidatos_planos
    ronda_num = 1
    eventos_anterior = len(ronda) + 1

    while len(ronda) > chunk_size and ronda_num <= MAX_RONDAS_CONSOLIDACION:
        if len(ronda) >= eventos_anterior:
            log(f"   ⏹️  Sin reducción tras ronda {ronda_num - 1} ({len(ronda)} eventos). Deteniendo consolidación IA.")
            break
        eventos_anterior = len(ronda)

        log(f"   Ronda {ronda_num}/{MAX_RONDAS_CONSOLIDACION}: {len(ronda)} eventos...")
        nueva_ronda = []
        for i in range(0, len(ronda), chunk_size):
            chunk = ronda[i:i + chunk_size]
            if PAUSE_ENTRE_BLOQUES > 0:
                time.sleep(PAUSE_ENTRE_BLOQUES)
            resultado_chunk = _consolidar_chunk_ia(chunk)
            if resultado_chunk:
                nueva_ronda.extend(resultado_chunk)
            elif len(chunk) > 40:
                # Chunk falló (probablemente MAX_TOKENS) — dividir en dos y reintentar
                log(f"   ↩️  Chunk falló, dividiendo en dos mitades...")
                mid = len(chunk) // 2
                for sub in [chunk[:mid], chunk[mid:]]:
                    sub_resultado = _consolidar_chunk_ia(sub)
                    nueva_ronda.extend(sub_resultado if sub_resultado else sub)
            else:
                nueva_ronda.extend(chunk)
        ronda = consolidar_local(nueva_ronda)
        ronda_num += 1

    if len(ronda) <= chunk_size and len(ronda) > 1:
        log(f"   Consolidación final: {len(ronda)} eventos...")
        if PAUSE_ENTRE_BLOQUES > 0:
            time.sleep(PAUSE_ENTRE_BLOQUES)
        resultado_final = _consolidar_chunk_ia(ronda)
        if resultado_final:
            resultado_final = consolidar_local(resultado_final)
            resultado_final = resultado_final + unicos
            log(f"✅ {len(hechos_por_bloques)} → {len(resultado_final)} eventos únicos")
            return resultado_final

    resultado_final = ronda + unicos
    log(f"✅ Consolidación terminada: {len(hechos_por_bloques)} → {len(resultado_final)} eventos "
        f"({len(ronda)} consolidados + {len(unicos)} únicos sin procesar)")
    return resultado_final

# ─────────────────────────────────────────────
# FASE DE IMÁGENES
# ─────────────────────────────────────────────
import urllib.request
import html as html_lib

_HEADERS_IMG = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}
_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'"][^>]+content=["\']([^"\']+)["\'"][^>]*/?>|'
    r'<meta[^>]+content=["\']([^"\']+)["\'"][^>]+property=["\']og:image["\'"][^>]*/?>',
    re.IGNORECASE)
_TIMEOUT_IMG = 6

# Dominios que siempre devuelven links directos (no pasan por Google News redirect)
# Para estos usamos requests directamente sin Playwright
_REQUESTS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-CL,es;q=0.9",
}

def _og_image_via_requests(url: str, timeout: int = 20) -> str | None:
    """Extrae og:image usando requests. Thread-safe, timeout real de Python."""
    try:
        import requests as _req
        r = _req.get(url, headers=_REQUESTS_HEADERS, timeout=timeout,
                     allow_redirects=True, stream=True)
        # Leer solo los primeros 200KB para no bajar páginas completas
        content = b""
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > 200_000:
                break
        html = content.decode("utf-8", errors="ignore")
        m = _OG_RE.search(html)
        if m:
            img = m.group(1) or m.group(2)
            if img:
                img = html_lib.unescape(img.strip())
                return img if img.startswith("http") else None
    except Exception:
        pass
    return None

def _resolver_google_url_playwright(page, link: str, timeout_ms: int = 15000) -> str | None:
    """Usa Playwright para resolver un redirect de Google News. Devuelve URL real."""
    try:
        url_capturada = [None]
        def _on_nav(frame, _u=url_capturada):
            u = frame.url
            if u and "google.com" not in u and u.startswith("http"):
                _u[0] = u
        page.on("framenavigated", _on_nav)
        try:
            page.goto(link, wait_until="commit", timeout=timeout_ms)
            waited = 0
            while url_capturada[0] is None and waited < timeout_ms:
                page.wait_for_timeout(200)
                waited += 200
                cur = page.url
                if cur and "google.com" not in cur:
                    url_capturada[0] = cur
                    break
        finally:
            page.remove_listener("framenavigated", _on_nav)
        return url_capturada[0]
    except Exception:
        return None

def _buscar_imagen_evento(hecho, titulares_por_indice, pw_page, timeout_requests=20):
    """
    Busca og:image para un evento.
    - URLs directas (RSS nativo, impresa): requests en thread con timeout real
    - URLs Google News: Playwright para resolver redirect, luego requests
    Devuelve (imagen_url, fallo_info | None)
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    titulares = hecho.get("titulares", [])
    candidatos = list(titulares)
    random.shuffle(candidatos)

    for item in candidatos[:3]:
        if isinstance(item, int):
            crudo = titulares_por_indice.get(item, {})
            link = crudo.get("source_url", "") or crudo.get("link", "")
        elif isinstance(item, dict):
            crudo = item
            link = item.get("source_url", "") or item.get("link", "")
        else:
            crudo = {}
            link = ""
        if not link:
            continue

        es_google = "news.google.com" in link or "google.com/rss" in link

        # Para Google News: resolver URL real con Playwright primero
        if es_google and pw_page is not None:
            real_url = _resolver_google_url_playwright(pw_page, link, timeout_ms=15000)
            if not real_url:
                continue
        else:
            real_url = link

        # Ahora obtener og:image via requests en thread con timeout real de Python
        dominio = re.sub(r"https?://([^/]+).*", r"\1", real_url)
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_og_image_via_requests, real_url, timeout_requests)
            try:
                img = fut.result(timeout=timeout_requests + 3)
            except FutureTimeout:
                return None, {
                    "evento": hecho.get("evento", ""),
                    "url": real_url,
                    "dominio": dominio,
                    "razon": f"thread_timeout_{timeout_requests}s",
                    "fuente_rss": "nativo" if not es_google else "google",
                }
            except Exception as e:
                return None, {
                    "evento": hecho.get("evento", ""),
                    "url": real_url,
                    "dominio": dominio,
                    "razon": str(e)[:120],
                    "fuente_rss": "nativo" if not es_google else "google",
                }

        if img:
            return img, None
        else:
            # Registrar fallo pero seguir intentando con siguiente candidato
            pass

    return None, None


def fase_imagenes(hechos_finales, titulares_por_indice):
    # Verificar requests disponible
    try:
        import requests as _req  # noqa
    except ImportError:
        log("⚠️  'requests' no instalado — instalando...")
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "pip", "install", "requests",
                        "--break-system-packages", "-q"], check=False)

    total = len(hechos_finales)
    log(f"🌐 Buscando imágenes para {total} eventos (requests + Playwright para redirects)...")

    # Playwright solo para resolver redirects de Google News
    pw = pw_browser = pw_page = None
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        pw_browser = pw.chromium.launch(headless=True)
        ctx = pw_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="es-CL",
        )
        pw_page = ctx.new_page()
        pw_page.set_default_timeout(20000)
        pw_page.route("**/*.{woff,woff2,ttf,otf,eot,png,jpg,jpeg,gif,svg,css}",
                      lambda r: r.abort())
    except Exception as e:
        log(f"⚠️  Playwright no disponible para resolver redirects: {e}")

    encontradas = 0
    _fallos_img = []

    try:
        for i, hecho in enumerate(hechos_finales, 1):
            img, fallo = _buscar_imagen_evento(
                hecho, titulares_por_indice, pw_page, timeout_requests=20
            )
            hecho["imagen"] = img
            if img:
                encontradas += 1
            if fallo:
                _fallos_img.append(fallo)

            if i % 25 == 0 or i == total:
                log(f"   {i}/{total} — {encontradas} con imagen, {i - encontradas} sin imagen")

    finally:
        if pw_browser:
            try:
                pw_browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
            log("🔒 Chromium cerrado")

    log(f"✅ Imágenes: {encontradas}/{total} eventos con imagen")

    # ── Log de fallos acumulado ──
    log_file = "log_imagenes_fallidas.json"
    historial = []
    if os.path.exists(log_file):
        try:
            with open(log_file, encoding="utf-8") as f:
                historial = json.load(f)
        except Exception:
            historial = []
    if _fallos_img:
        from collections import Counter
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        dominios_fallo = Counter(f["dominio"] for f in _fallos_img)
        razones = Counter(f["razon"] for f in _fallos_img)
        historial.append({
            "timestamp": ts,
            "total_fallos": len(_fallos_img),
            "por_dominio": dict(dominios_fallo.most_common(20)),
            "por_razon": dict(razones),
            "detalle": _fallos_img[:200],
        })
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(historial[-30:], f, ensure_ascii=False, indent=2)
        log(f"📋 Log fallos imágenes: {len(_fallos_img)} fallos guardados en {log_file}")
        top3 = dominios_fallo.most_common(3)
        log(f"   Top dominios sin imagen: {', '.join(f'{d}({n})' for d,n in top3)}")



def fase_exportar(hechos_finales: list, titulares_crudos: list,
               titulares_por_indice: dict, timestamp: str):


    # ── Exportar JSON para la UI ──
    json_data = {
        "timestamp":       timestamp,
        "total_titulares": len(titulares_crudos),
        "eventos": []
    }
    for hecho in hechos_finales:
        titulares_evento = []
        for item in hecho.get('titulares', []):
            idx   = item if isinstance(item, int) else item.get('indice')
            crudo = titulares_por_indice.get(idx, {})
            fuente_raw  = crudo.get('source', '') or (item.get('fuente','') if isinstance(item,dict) else '')
            fuente_norm = normalizar_fuente(fuente_raw) or fuente_raw
            titulares_evento.append({
                "fuente":        fuente_norm,
                "region":        crudo.get('region', '') or (item.get('region','') if isinstance(item,dict) else ''),
                "titular":       crudo.get('title',  '') or (item.get('texto', '') if isinstance(item,dict) else ''),
                "fecha":         crudo.get('fecha',  '') or (item.get('fecha', '') if isinstance(item,dict) else ''),
                "link":          crudo.get('link',   '') or (item.get('link',  '') if isinstance(item,dict) else ''),
                "conglomerado":  get_conglomerado(fuente_norm),
            })
        fuentes_set  = {t["fuente"]  for t in titulares_evento if t["fuente"]}
        regiones_set = {t["region"]  for t in titulares_evento if t["region"]}
        json_data["eventos"].append({
            "evento":      hecho.get('evento', ''),
            "categoria":   validar_categoria(hecho.get('categoria', '')),
            "n_titulares": len(titulares_evento),
            "fuentes":     sorted(fuentes_set),
            "regiones":    sorted(regiones_set),
            "imagen":      hecho.get('imagen', None),
            "titulares":   titulares_evento,
        })

    json_filename = f"Monitoreo_Chile_{timestamp}.json"
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    log(f"✅ JSON exportado: '{json_filename}'")

    with open("latest.json", 'w', encoding='utf-8') as f:
        json.dump({"file": json_filename}, f)
    log(f"📌 latest.json actualizado → {json_filename}")


# ─────────────────────────────────────────────
# FASE 2B: PROCESAMIENTO IA POR BLOQUES
# ─────────────────────────────────────────────
def fase_ia(titulares_crudos: list, checkpoint_ia: str = None) -> tuple:
    for i, t in enumerate(titulares_crudos, 1):
        t['_indice_global'] = i

    titulares_por_indice = {t['_indice_global']: t for t in titulares_crudos}

    max_bloques = RPD_LIMIT - 2
    total_titulares_a_procesar = min(len(titulares_crudos), max_bloques * TAMANIO_BLOQUE)
    total_bloques = (total_titulares_a_procesar + TAMANIO_BLOQUE - 1) // TAMANIO_BLOQUE

    hechos_por_bloques = []
    bloques_ok = 0
    bloques_fallidos = []
    bloque_inicio = 0

    if checkpoint_ia and os.path.exists(checkpoint_ia):
        try:
            with open(checkpoint_ia, encoding='utf-8') as f:
                estado = json.load(f)
            hechos_por_bloques = estado.get('hechos', [])
            bloques_ok         = estado.get('bloques_ok', 0)
            bloque_inicio      = estado.get('siguiente_indice', 0)
            bloques_fallidos   = estado.get('bloques_fallidos', [])
            bloque_retoma = bloque_inicio // TAMANIO_BLOQUE + 1
            log(f"♻️  Checkpoint IA: {bloques_ok} bloques completados, retomando desde bloque {bloque_retoma}/{total_bloques}...")
        except Exception as e:
            log(f"⚠️ No se pudo leer checkpoint IA ({e}), empezando desde cero.")
            hechos_por_bloques = []; bloques_ok = 0; bloque_inicio = 0; bloques_fallidos = []

    log(f"🧠 Procesando bloques {bloque_inicio // TAMANIO_BLOQUE + 1}–{total_bloques} ({TAMANIO_BLOQUE} titulares/bloque)...")

    for bloque_num, i in enumerate(range(bloque_inicio, total_titulares_a_procesar, TAMANIO_BLOQUE),
                                    bloque_inicio // TAMANIO_BLOQUE + 1):
        bloque = titulares_crudos[i:i + TAMANIO_BLOQUE]
        log(f"   Bloque {bloque_num}/{total_bloques} ({len(bloque)} titulares, índices {bloque[0]['_indice_global']}–{bloque[-1]['_indice_global']})...")

        resultado = agrupar_con_ia(bloque, eventos_previos=hechos_por_bloques)

        if resultado:
            # Sanidad: si la IA devuelve más eventos que titulares, el JSON está corrupto
            if len(resultado) > len(bloque):
                log(f"   ⚠️ Bloque {bloque_num} anómalo: {len(resultado)} eventos para {len(bloque)} titulares — descartado.")
                bloques_fallidos.append(bloque)
            else:
                hechos_por_bloques.extend(resultado)
                log(f"   ✅ {len(resultado)} eventos identificados")
                bloques_ok += 1
        else:
            log(f"   ⚠️ Error en bloque {bloque_num} — se reintentará al final.")
            bloques_fallidos.append(bloque)

        if checkpoint_ia:
            try:
                with open(checkpoint_ia, 'w', encoding='utf-8') as f:
                    json.dump({
                        'hechos':           hechos_por_bloques,
                        'bloques_ok':       bloques_ok,
                        'siguiente_indice': i + TAMANIO_BLOQUE,
                        'bloques_fallidos':  bloques_fallidos,
                    }, f, ensure_ascii=False)
            except Exception as e:
                log(f"⚠️ No se pudo guardar checkpoint IA: {e}")

        if PAUSE_ENTRE_BLOQUES > 0 and bloque_num < total_bloques:
            time.sleep(PAUSE_ENTRE_BLOQUES)

    if bloques_fallidos:
        log(f"🔄 Reintentando {len(bloques_fallidos)} bloques fallidos...")
        aun_fallidos = []
        for idx, bloque in enumerate(bloques_fallidos, 1):
            log(f"   Reintento {idx}/{len(bloques_fallidos)} ({len(bloque)} titulares)...")
            resultado = agrupar_con_ia(bloque, eventos_previos=hechos_por_bloques)
            if resultado:
                if len(resultado) > len(bloque):
                    log(f"   ⚠️ Reintento anómalo: {len(resultado)} eventos para {len(bloque)} titulares — descartado.")
                else:
                    hechos_por_bloques.extend(resultado)
                    log(f"   ✅ {len(resultado)} eventos recuperados")
                    bloques_ok += 1
            else:
                log(f"   ❌ Bloque sigue fallando. {len(bloque)} titulares perdidos definitivamente.")
                aun_fallidos.append(bloque)
        if aun_fallidos:
            log(f"⚠️ {sum(len(b) for b in aun_fallidos)} titulares no pudieron procesarse.")

    log(f"📦 Eventos antes de consolidar: {len(hechos_por_bloques)} (de {bloques_ok} bloques exitosos)")

    if checkpoint_ia and os.path.exists(checkpoint_ia):
        os.remove(checkpoint_ia)
        log(f"🗑️  Checkpoint IA eliminado: {checkpoint_ia}")

    return hechos_por_bloques, titulares_por_indice, bloques_ok

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    log("🚀 Iniciando monitoreo de medios Chile (nacional + regional)...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    checkpoint_file = f"checkpoint_titulares_{timestamp}.json"
    titulares_crudos = fase_recoleccion(checkpoint_file=checkpoint_file)

    if not titulares_crudos:
        log("❌ No se encontraron titulares")
        return

    backup_file = f"backup_titulares_{timestamp}.json"
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(titulares_crudos, f, ensure_ascii=False, indent=2)
    log(f"💾 Backup final guardado: {backup_file}")

    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    checkpoint_ia = f"checkpoint_ia_{timestamp}.json"
    if os.path.exists(checkpoint_ia):
        log(f"♻️  Se encontró checkpoint de fase IA: {checkpoint_ia}")
    else:
        log(f"📝 Se creará checkpoint de fase IA en: {checkpoint_ia}")

    hechos_por_bloques, titulares_por_indice, bloques_ok = fase_ia(
        titulares_crudos, checkpoint_ia=checkpoint_ia
    )

    if not hechos_por_bloques:
        log("❌ No se pudieron agrupar eventos")
        return

    if bloques_ok > 1:
        log(f"⏸️  Esperando {PAUSE_ENTRE_BLOQUES}s antes de consolidar...")
        time.sleep(PAUSE_ENTRE_BLOQUES)
        hechos_finales = fase_consolidacion(hechos_por_bloques)
    else:
        log("ℹ️  Un solo bloque exitoso, consolidación local solamente.")
        hechos_finales = consolidar_local(hechos_por_bloques)

    hechos_finales = sorted(
        hechos_finales,
        key=lambda x: len(x.get('titulares', [])),
        reverse=True
    )

    fase_imagenes(hechos_finales, titulares_por_indice)

    fase_exportar(hechos_finales, titulares_crudos, titulares_por_indice, timestamp)

    log(f"📈 Eventos únicos: {len(hechos_finales)}")
    log(f"📊 Requests utilizados: {REQUESTS_REALIZADOS}/{RPD_LIMIT}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n⚠️ Proceso interrumpido por el usuario")
    except Exception as e:
        log(f"❌ Error crítico: {e}")
        raise