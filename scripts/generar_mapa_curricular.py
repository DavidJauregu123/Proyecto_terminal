"""
Genera data/mapa_curricular_2021ID.json a partir del historial_academico PDF.
Uso: python scripts/generar_mapa_curricular.py <ruta_pdf>
"""
import sys
import json
import re
import pdfplumber
from pathlib import Path

def generar_mapa(ruta_pdf: str) -> dict:
    mapa = {}
    
    # Mapeo de nombre de ciclo a número
    nombres_ciclo = {
        "primer ciclo": 1,
        "segundo ciclo": 2,
        "tercer ciclo": 3,
        "cuarto ciclo": 4,
        "tercer y cuarto ciclo": 3,   # elección libre compartida
        "primer al cuarto ciclo": 0,  # co-curricular
    }
    
    # Regex para líneas de materia:
    # "1,2 DP0001 Nombre de la materia 6 10" o "1,2 DP0001 Nombre 6" (sin calif)
    patron_materia = re.compile(
        r'^[\d,al\s]+\s+([A-Z]{2,4}\d{4})\s+(.+?)\s+(\d+)\s*([\d.S]+)?\s*$'
    )
    
    ciclo_actual = 0
    categoria_actual = "BÁSICA"
    
    with pdfplumber.open(ruta_pdf) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            for linea in texto.splitlines():
                linea_lower = linea.strip().lower()
                
                # Detectar ciclo
                for nombre, num in nombres_ciclo.items():
                    if linea_lower == nombre or linea_lower.startswith(nombre):
                        ciclo_actual = num
                        break
                
                # Detectar categoría
                if linea.strip().upper() in ("BÁSICA", "BASICA", "ELECCIÓN LIBRE",
                                              "ELECCI\u00d3N LIBRE", "CO-CURRICULAR"):
                    categoria_actual = linea.strip().upper()
                elif "PRE-ESPECIALIDAD" in linea.upper():
                    categoria_actual = "PRE-ESPECIALIDAD"
                
                # Detectar materia
                match = patron_materia.match(linea.strip())
                if match:
                    clave = match.group(1)
                    nombre_mat = match.group(2).strip()
                    creditos = int(match.group(3))
                    calif_str = match.group(4) or ""
                    
                    calificacion = None
                    if calif_str and calif_str not in ("S", ""):
                        try:
                            calificacion = float(calif_str)
                        except ValueError:
                            pass
                    
                    mapa[clave] = {
                        "ciclo": ciclo_actual,
                        "categoria": categoria_actual,
                        "creditos": creditos,
                        "calificacion": calificacion
                    }
    
    return mapa


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/generar_mapa_curricular.py <ruta_historial_pdf>")
        sys.exit(1)
    
    ruta = sys.argv[1]
    mapa = generar_mapa(ruta)
    
    output = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID.json"
    output.parent.mkdir(exist_ok=True)
    
    with open(output, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2)
    
    print(f"Mapa generado: {len(mapa)} materias")
    ciclos = {}
    for v in mapa.values():
        c = v["ciclo"]
        ciclos[c] = ciclos.get(c, 0) + 1
    for c in sorted(ciclos):
        label = {1: "Primer Ciclo", 2: "Segundo Ciclo", 3: "Tercer/Cuarto Ciclo",
                 4: "Cuarto Ciclo", 0: "Co-curricular"}.get(c, f"Ciclo {c}")
        print(f"  {label}: {ciclos[c]} materias")
    print(f"Guardado en: {output}")
