#!/usr/bin/env python3
"""
TEST 2: Priorización de Cadenas Académicas - Alumno Avanzado
Escenario: Alumno en ciclo 3-4 con parcial progreso en cadenas.
"""

import json
from pathlib import Path
from agents.sistema_experto_seriacion import (
    SistemaExpertoSeriacion,
    MateriaAprobada
)
from collections import defaultdict

def test_cadenas_alumno_avanzado():
    print("=" * 80)
    print("TEST 2: Priorización de Cadenas - Alumno Avanzado (Ciclos 3-4)")
    print("=" * 80 + "\n")
    
    # Cargar mapa curricular
    mapa_path = Path(__file__).parent / "data" / "mapa_curricular_2021ID.json"
    with open(mapa_path, "r", encoding="utf-8") as f:
        mapa_curricular = json.load(f)
    
    sistema = SistemaExpertoSeriacion(mapa_curricular)
    
    # Crear historial que lleve al alumno a ciclo 3
    historial = []
    
    # Ciclo 1 - COMPLETO (necesita 87+ de 116 creditos)
    ciclo1_claves = [
        "II0002", "ID0104", "ID0106", "IA0209", "ID0108", 
        "ID0103", "ID0101", "ID0102", "ID0160", "ID0161", "IT0161"
    ]
    for idx, clave in enumerate(ciclo1_claves):
        if clave in mapa_curricular:
            creditos = mapa_curricular[clave].get("creditos", 0)
            calif = 7.5 + (idx % 3) * 0.5
            historial.append(MateriaAprobada(clave=clave, calificacion=calif, creditos_obtenidos=creditos))
    
    # Agregar otra materia si es necesario
    if clave in mapa_curricular:
        historial.append(MateriaAprobada(clave="AD0003", calificacion=8.0, creditos_obtenidos=2))
    
    # Ciclo 2 - COMPLETO (necesita 87+ de 116 creditos)
    ciclo2_claves = [
        "ID0105", "ID0107", "ID0200", "ID0202", "ID0207", 
        "ID0201", "ID0203", "IT0260", "AD0005", "TA0009", "IT0261"
    ]
    for idx, clave in enumerate(ciclo2_claves):
        if clave in mapa_curricular:
            creditos = mapa_curricular[clave].get("creditos", 0)
            calif = 7.5 + (idx % 3) * 0.5
            historial.append(MateriaAprobada(clave=clave, calificacion=calif, creditos_obtenidos=creditos))
    
    # Ciclo 3 - PARCIAL
    ciclo3_claves = [
        "ID0205", "ID0204", "ID0307", "ID0306", "ID0305", "IT0360"
    ]
    for idx, clave in enumerate(ciclo3_claves):
        if clave in mapa_curricular:
            creditos = mapa_curricular[clave].get("creditos", 0)
            calif = 7.5 + (idx % 3) * 0.5
            historial.append(MateriaAprobada(clave=clave, calificacion=calif, creditos_obtenidos=creditos))
    
    print(f"[SETUP] Historial: {len(historial)} materias aprobadas\n")
    
    # Detectar ciclo actual
    ciclo_actual = sistema.detectar_ciclo_actual(historial)
    print(f"[CICLO ACTUAL] {ciclo_actual}\n")
    
    # Generar candidatas
    candidatas_temp = sistema.generar_candidatas_temporales(ciclo_actual, historial)
    print(f"[CANDIDATAS INICIALES] {len(candidatas_temp)}")
    
    # Filtrar por requisitos
    candidatas_req = sistema.filtrar_por_requisitos(candidatas_temp, historial)
    print(f"[DESPUÉS REQUISITOS] {len(candidatas_req)}")
    
    # Aplicar ligaduras
    candidatas_lig = sistema.aplicar_regla_ligaduras(candidatas_req)
    print(f"[DESPUÉS LIGADURAS] {len(candidatas_lig)}\n")
    
    # NUEVO: Aplicar priorización por cadenas
    print("[PRIORIZACIÓN POR CADENAS]\n")
    candidatas_final = sistema.filtrar_por_cadenas_y_prioridad(
        candidatas_lig, 
        historial, 
        ciclo_actual
    )
    
    # Análisis de resultados
    print("\n[ANÁLISIS DE RECOMENDACIONES PRINCIPALES]\n")
    
    cadenas_aparecidas = defaultdict(list)
    ciclos_aparecidos = defaultdict(int)
    
    cadenas_map = sistema.mapeo_cadenas or {}
    
    for i, clave in enumerate(candidatas_final[:25], 1):  # Top 25
        if clave in sistema.mapa_curricular:
            materia = sistema.mapa_curricular[clave]
            ciclos_aparecidos[materia.ciclo] += 1
            
            # Identificar cadena
            cadena_nombre = "OTRA"
            for c_name, claves_cadena in cadenas_map.items():
                if clave in claves_cadena:
                    cadena_nombre = c_name
                    cadenas_aparecidas[cadena_nombre].append(clave)
                    break
            
            print(f"{i:2}. {clave:6} | Ciclo {materia.ciclo} | {materia.categoria:20} | {cadena_nombre}")
    
    # Estadísticas
    print("\n[ESTADÍSTICAS]\n")
    
    print("Distribución por Ciclo:")
    for ciclo in sorted(ciclos_aparecidos.keys()):
        print(f"  Ciclo {ciclo}: {ciclos_aparecidos[ciclo]} materias")
    
    print("\nDistribución por Cadena (Top 25):")
    for cadena in sorted(cadenas_aparecidas.keys(), 
                        key=lambda x: len(cadenas_aparecidas[x]), reverse=True):
        print(f"  {cadena}: {len(cadenas_aparecidas[cadena])} materias")
    
    # Verificaciones
    print("\n[VALIDACIONES]\n")
    
    # 1. Verificar que hay materias de ciclo 3
    ciclo3_recs = [c for c in candidatas_final 
                  if c in sistema.mapa_curricular and 
                  sistema.mapa_curricular[c].ciclo == 3]
    print(f"[CHECK] Materias ciclo 3: {len(ciclo3_recs)}")
    if ciclo3_recs:
        print(f"        Primeras: {ciclo3_recs[:5]}")
    
    # 2. Verificar que cadenas están representadas
    cadenas_main = ["CIENCIAS_EXACTAS", "PROGRAMACION_SOFTWARE", "INTELIGENCIA_DATOS", "INGLES"]
    cadenas_found = [c for c in cadenas_main if c in cadenas_aparecidas]
    print(f"\n[CHECK] Cadenas académicas encontradas: {len(cadenas_found)}")
    if cadenas_found:
        print(f"        {cadenas_found}")
    
    # 3. Verificar electivas
    electivas_recs = [c for c in candidatas_final 
                     if c in sistema.mapa_curricular and 
                     sistema.mapa_curricular[c].categoria == "ELECCION_LIBRE"]
    print(f"\n[CHECK] Electivas en recomendaciones: {len(electivas_recs)}")
    
    print("\n" + "=" * 80)
    print(f"RESULTADO FINAL: {len(candidatas_final)} materias recomendadas")
    print("=" * 80)

if __name__ == "__main__":
    test_cadenas_alumno_avanzado()
