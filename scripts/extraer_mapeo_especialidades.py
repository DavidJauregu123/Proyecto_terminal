#!/usr/bin/env python3
"""
Extrae el mapeo de especialidades del MAPA IDEAL IDEIO 2021
y crea un archivo JSON con las materias de cada especialidad
"""

import openpyxl
from pathlib import Path
import json
import re

ruta = Path('data/MAPA IDEAL IDEIO 2021 (rev 2025).xlsx')
wb = openpyxl.load_workbook(ruta)
ws = wb.active

# Diccionario para almacenar materias por especialidad
especializaciones = {
    "TICS": set(),
    "BUSINESS_INTELLIGENCE": set()
}

# Mapeo de columnas a especialidades
columnas_especializaciones = {
    "BO": "TICS",  # Innovación en TIC
    "BW": "BUSINESS_INTELLIGENCE",  # Inteligencia Organizacional
    "CA": "BUSINESS_INTELLIGENCE",  # Parece continuar BI
    "BS": "TICS",  # Parece continuar TICS
}

# Expresión regular para extraer claves de materia
patron_clave = re.compile(r'([A-Z]{1,2}\d{3,4})')

print("Extrayendo materias de preespecialidad...")

# Iterar sobre todas las filas y columnas
for row in ws.iter_rows(values_only=False):
    for cell in row:
        if cell.value and isinstance(cell.value, str):
            # Extraer columna
            columna = re.match(r'([A-Z]+)', cell.coordinate).group(1)
            
            # Si es una columna de especialidad
            if columna in columnas_especializaciones:
                # Buscar clave de materia
                match = patron_clave.search(cell.value)
                if match:
                    clave = match.group(1)
                    especializacion = columnas_especializaciones[columna]
                    especializaciones[especializacion].add(clave)
                    print(f"  Encontrado: {clave} → {especializacion}")

# Convertir sets a lists y guardar
resultado = {
    "TICS": sorted(list(especializaciones["TICS"])),
    "BUSINESS_INTELLIGENCE": sorted(list(especializaciones["BUSINESS_INTELLIGENCE"]))
}

# Guardar como JSON
ruta_salida = Path('data/mapeo_especialidades_2021ID.json')
with open(ruta_salida, 'w', encoding='utf-8') as f:
    json.dump(resultado, f, indent=2, ensure_ascii=False)

print(f"\n✅ Mapeo guardado en {ruta_salida}")
print(f"\nRESUMEN:")
print(f"  TICS: {len(resultado['TICS'])} materias")
print(f"    {resultado['TICS']}")
print(f"\n  BUSINESS INTELLIGENCE: {len(resultado['BUSINESS_INTELLIGENCE'])} materias")
print(f"    {resultado['BUSINESS_INTELLIGENCE']}")
