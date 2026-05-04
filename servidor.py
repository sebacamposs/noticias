#!/usr/bin/env python3
"""
servidor.py — Levanta monitor_autoload.html en http://localhost:8080
Coloca este archivo en la misma carpeta que monitor_autoload.html y los JSON
Ejecuta: python servidor.py
"""
import http.server, socketserver, webbrowser, os, sys

PORT = 8080
DIR  = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

os.chdir(DIR)
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    url = f"http://localhost:{PORT}/monitor_autoload.html"
    print(f"✅ Servidor iniciado en {url}")
    print(f"📁 Sirviendo desde: {DIR}")
    print(f"   Presiona Ctrl+C para detener\n")
    try:
        webbrowser.open(url)
    except:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n⚠️  Servidor detenido")
        sys.exit(0)