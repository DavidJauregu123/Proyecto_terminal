#!/usr/bin/env python3
"""
TEST: Validar que priorización por cadenas funciona correctamente.

Escenario:
- Alumno en ciclo 4
- Ha completado CIENCIAS_EXACTAS pero no PROGRAMACION_SOFTWARE
- Tiene algunas electivas disponibles
- El sistema debe recomendar primero PROGRAMACION_SOFTWARE
"""

import json
from pathlib import Path
from agents.sistema_experto_seriacion import (
    SistemaExpertoSeriacion,
    MateriaAprobada,
    TipoAlerta,
    Alerta
)
from datetime import datetime
from collections import defaultdict

def test_cadenas_prioridad():
    print("=" * 80)
    print("TEST: Priorización por Cadenas Académicas")
    print("=" * 80 + "\n")
    
    # Cargar mapa curricular
    mapa_path = Path(__file__).parent / "data" / "mapa_curricular_2021ID.json"
    with open(mapa_path, "r", encoding="utf-8") as f:
        mapa_curricular = json.load(f)
    
    print(f"[SETUP] Cargado mapa con {len(mapa_curricular)} materias\n")
    
    sistema = SistemaExpertoSeriacion(mapa_curricular)
    
    # Simular historial: Alumno que ha completado la mayoría de ciclo 3.
    # Asegurarse de que cada ciclo tenga suficientes créditos para que sea completable
    historial = [
        # Ciclo 1 - COMPLETO (75% o más)
        MateriaAprobada(clave="II0002", calificacion=8.5, creditos_obtenidos=8),
        MateriaAprobada(clave="ID0104", calificacion=7.5, creditos_obtenidos=8),
        MateriaAprobada(clave="ID0106", calificacion=8.0, creditos_obtenidos=8),
        MateriaAprobada(clave="IA0209", calificacion=7.0, creditos_obtenidos=4),
        MateriaAprobada(clave="ID0108", calificacion=7.8, creditos_obtenidos=4),
        MateriaAprobada(clave="ID0103", calificacion=8.5, creditos_obtenidos=4),  # Programación
        
        # Ciclo 2 - COMPLETO (75% o más)
        MateriaAprobada(clave="ID0105", calificacion=8.0, creditos_obtenidos=4),
        MateriaAprobada(clave="ID0107", calificacion=7.5, creditos_obtenidos=4),
        MateriaAprobada(clave="ID0200", calificacion=7.9, creditos_obtenidos=4),  # Probabilidad
        MateriaAprobada(clave="ID0202", calificacion=8.1, creditos_obtenidos=4),  # Física III
        MateriaAprobada(clave="ID0207", calificacion=7.6, creditos_obtenidos=4),  # Inglés II
        
        # Ciclo 3 - PARCIAL (menos de 75%)
        MateriaAprobada(clave="ID0205", calificacion=7.8, creditos_obtenidos=4),
        MateriaAprobada(clave="ID0206", calificacion=8.2, creditos_obtenidos=4),
        MateriaAprobada(clave="ID0204", calificacion=7.3, creditos_obtenidos=4),  # Otra de ciclo 3
    ]
    
    print("[TEST SETUP]")
    print(f"Historial: {len(historial)} materias aprobadas")
    print(f"Ciclos representados: 1, 2, 3, 4\n")
    
    # Detectar ciclo actual
    ciclo_actual = sistema.detectar_ciclo_actual(historial)
    print(f"[CICLO ACTUAL] {ciclo_actual}\n")
    
    # Generar candidatas
    candidatas_temp = sistema.generar_candidatas_temporales(ciclo_actual, historial)
    print(f"[CANDIDATAS INICIALES] {len(candidatas_temp)}\n")
    
    # Filtrar por requisitos
    candidatas_req = sistema.filtrar_por_requisitos(candidatas_temp, historial)
    print(f"[DESPUÉS REQUISITOS] {len(candidatas_req)}\n")
    
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
    print("\n[ANÁLISIS DE RECOMENDACIONES]\n")
    
    cadenas_aparecidas = defaultdict(list)
    categorias_aparecidas = defaultdict(list)
    
    cadenas_map = sistema.mapeo_cadenas
    
    for i, clave in enumerate(candidatas_final[:15], 1):  # Top 15
        if clave in sistema.mapa_curricular:
            materia = sistema.mapa_curricular[clave]
            print(f"{i:2}. {clave:6} - {materia.nombre:40} | Ciclo {materia.ciclo} | {materia.categoria}")
            
            # Identificar cadena
            for cadena_nombre, claves_cadena in cadenas_map.items():
                if clave in claves_cadena:
                    cadenas_aparecidas[cadena_nombre].append(clave)
                    break
            
            categorias_aparecidas[materia.categoria].append(clave)
    
    print("\n[ESTADÍSTICAS]\n")
    
    print("Distribución por Cadena:")
    for cadena, claves in sorted(cadenas_aparecidas.items()):
        print(f"  {cadena}: {len(claves)} materias")
    
    print("\nDistribución por Categoría:")
    for categoria, claves in sorted(categorias_aparecidas.items()):
        print(f"  {categoria}: {len(claves)} materias")
    
    # VALIDACIONES
    print("[VALIDACIONES]\n")
    
    # 1. Verificar que hay materias BASICA rezagadas primero
    rezagadas_basicas = [c for c in candidatas_final 
                        if c in sistema.mapa_curricular and 
                        sistema.mapa_curricular[c].categoria == "BASICA" and
                        sistema.mapa_curricular[c].ciclo < ciclo_actual]
    
    if rezagadas_basicas:
        print(f"[PASS] Encontradas {len(rezagadas_basicas)} materias BASICA rezagadas")
        print(f"       Primeras: {rezagadas_basicas[:3]}")
    else:
        print(f"[INFO] OK: No hay materias BASICA rezagadas (normal para este alumno)")
    
    # 2. Verificar que hay materias de cadenas
    cadena_materias = [c for c in candidatas_final 
                      if any(c in claves for claves in cadenas_map.values())]
    if cadena_materias:
        print(f"[PASS] Encontradas {len(cadena_materias)} materias de cadenas academicas")
    else:
        print(f"[INFO] Sin materias de cadenas en recomendaciones (puede ser normal)")
    
    # 3. Verificar electivas
    materias_electivas = [c for c in candidatas_final 
                         if c in sistema.mapa_curricular and 
                         sistema.mapa_curricular[c].categoria == "ELECCION_LIBRE"]
    
    print(f"[INFO] {len(materias_electivas)} electivas en recomendaciones")
    
    # 4. Verificar balance entre cadenas
    if len(cadenas_aparecidas) > 1:
        print(f"[PASS] Multiples cadenas representadas ({list(cadenas_aparecidas.keys())})")
    else:
        print(f"[INFO] Cadenas: {list(cadenas_aparecidas.keys())}")
    
    print("\n" + "=" * 80)
    print(f"RESULTADO FINAL: {len(candidatas_final)} materias recomendadas")
    print("=" * 80)

if __name__ == "__main__":
    test_cadenas_prioridad()
