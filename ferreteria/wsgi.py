"""
WSGI config for ferreteria project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ferreteria.settings')

# =========================================================================
# BLOQUE AUTOMÁTICO: INICIALIZACIÓN DE CARPETAS DE DOCUMENTOS FÍSICOS
# =========================================================================
try:
    from django.conf import settings
    # Obtenemos el diccionario con las rutas que definimos en settings.py
    carpetas = getattr(settings, "SUBCARPETAS_FERRETERIA", {})
    
    for nombre_carpeta, ruta_fisica in carpetas.items():
        # os.makedirs con exist_ok=True crea la carpeta si falta y no hace nada si ya existe
        if not os.path.exists(ruta_fisica):
            os.makedirs(ruta_fisica, exist_ok=True)
            print(f"[SISTEMA AUTOMÁTICO] Carpeta inicializada con éxito: {ruta_fisica}")
except Exception as e:
    print(f"[ALERTA SISTEMA] No se pudo verificar la estructura de carpetas: {e}")
# =========================================================================

application = get_wsgi_application()