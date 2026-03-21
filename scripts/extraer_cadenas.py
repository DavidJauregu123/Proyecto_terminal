#!/usr/bin/env python3
"""
Extrae las materias de cada cadena desde el MAPA IDEAL IDEIO 2021
"""

import openpyxl
from pathlib import Path
import json
import re

ruta = Path('data/MAPA IDEAL IDEIO 2021 (rev 2025).xlsx')
wb = openpyxl.load_workbook(ruta)
ws = wb.active

# Diccionario para almacenar materias por cadena
cadenas = {
    "CIENCIAS_EXACTAS": set(),
    "PROGRAMACION_SOFTWARE": set(),
    "INTELIGENCIA_DATOS": set(),
    "INGLES": set(),
    "CIERRE_PRACTICAS": set()
}

# Expresión regular para extraer claves
patron_clave = re.compile(r'([A-Z]{1,2}\d{3,4})')

print("Extrayendo materias de cada cadena...\n")

# Buscar en todas las celdas para encontrar encabezados de cadenas
for row_idx, row in enumerate(ws.iter_rows(values_only=False), 1):
    for cell in row:
        if cell.value and isinstance(cell.value, str):
            valor = cell.value.upper()
            
            # Detectar cadenas
            if 'CADENA DE CIENCIAS EXACTAS' in valor:
                print(f"[Fila {row_idx}] Encontrada: CIENCIAS EXACTAS")
            elif 'CADENA DE PROGRAMACIÓN' in valor:
                print(f"[Fila {row_idx}] Encontrada: PROGRAMACIÓN")
            elif 'CADENA DE INTELIGENCIA DE DATOS' in valor:
                print(f"[Fila {row_idx}] Encontrada: INTELIGENCIA DE DATOS")
            elif 'CADENA DE INGLÉS' in valor:
                print(f"[Fila {row_idx}] Encontrada: INGLÉS")
            elif 'CADENA DE CIERRE' in valor:
                print(f"[Fila {row_idx}] Encontrada: CIERRE Y PRÁCTICAS")
            
            # Buscar claves en todas las celdas
            match = patron_clave.search(str(cell.value))
            if match:
                clave = match.group(1)
                
                # Por ahora, clasificar por columna como hacíamos antes
                columna = re.match(r'([A-Z]+)', cell.coordinate).group(1)
                
                # Heurística: si está en ciertos rangos de columnas
                if columna in ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']:
                    cadenas["CIENCIAS_EXACTAS"].add(clave)
                elif columna in ['K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V']:
                    cadenas["PROGRAMACION_SOFTWARE"].add(clave)
                elif columna in ['W', 'X', 'Y', 'Z', 'AA', 'AB', 'AC', 'AD', 'AE', 'AF', 'AG', 'AH', 'AI', 'AJ', 'AK', 'AL', 'AM', 'AN', 'AO']:
                    cadenas["INTELIGENCIA_DATOS"].add(clave)
                elif 'ID0' in clave and clave.endswith('07'):
                    cadenas["INGLES"].add(clave)
                elif columna in ['AW', 'AX', 'AY', 'AZ', 'BA', 'BB', 'BC']:
                    cadenas["CIERRE_PRACTICAS"].add(clave)

print("\n\n=== MATERIAS EXTRAÍDAS POR CADENA ===\n")

for cadena, materias in cadenas.items():
    if materias:
        materias_sorted = sorted(list(materias))
        print(f"{cadena}:")
        print(f"  Total: {len(materias_sorted)}")
        print(f"  Claves: {materias_sorted}")
        print()

# Guardar como JSON
resultado = {
    cadena: sorted(list(materias)) 
    for cadena, materias in cadenas.items() 
    if materias
}

ruta_salida = Path('data/mapeo_cadenas_2021ID.json')
with open(ruta_salida, 'w', encoding='utf-8') as f:
    json.dump(resultado, f, indent=2, ensure_ascii=False)

print(f"\n✅ Mapeo de cadenas guardado en {ruta_salida}")
