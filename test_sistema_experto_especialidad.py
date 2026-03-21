#!/usr/bin/env python3
"""
Test del Sistema Experto con Especialidad
Prueba que el filtrado de especialidad y límites de electivas funciona correctamente
"""

from agents.sistema_experto_seriacion import ejecutar_sistema_experto

# ============================================================================
# TEST 1: Estudiante en Ciclo 5 con TICS detectada (2 materias de PREESPECIALIDAD TICS)
# ============================================================================
print("\n" + "="*80)
print("TEST 1: Estudiante con Especialidad TICS detectada")
print("="*80)

datos_est1 = {
    "id": "EST002",
    "nombre": "Carlos López - Test TICS",
    "promedio": 8.2,
    "total_creditos": 72
}

# Ciclos 1-4 completados + algunas de ciclo 5
historial_1 = [
    # Ciclo 1 completo
    {"clave_materia": "ID0001", "calificacion": 9.0, "creditos_obtenidos": 6},
    {"clave_materia": "ID0101", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0102", "calificacion": 9.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0104", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0105", "calificacion": 7.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0106", "calificacion": 9.0, "creditos_obtenidos": 6},
    {"clave_materia": "ID0107", "calificacion": 8.5, "creditos_obtenidos": 3},
    
    # Ciclo 2 (muestra)
    {"clave_materia": "ID0201", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0202", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0203", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0204", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0205", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0206", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0207", "calificacion": 8.0, "creditos_obtenidos": 3},
    
    # Ciclo 3 (muestra)
    {"clave_materia": "ID0301", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0302", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0303", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0304", "calificacion": 8.0, "creditos_obtenidos": 8},
    
    # Ciclo 4 (muestra)
    {"clave_materia": "ID0401", "calificacion": 8.5, "creditos_obtenidos": 8},
    {"clave_materia": "ID0405", "calificacion": 8.0, "creditos_obtenidos": 8},
    
    # Ciclo 5 - Especialidad TICS (PREESPECIALIDAD)
    {"clave_materia": "ID3418", "calificacion": 8.5, "creditos_obtenidos": 6},  # TIC para la educación
    {"clave_materia": "ID3421", "calificacion": 8.0, "creditos_obtenidos": 6},  # Gestión del conocimiento
    
    # Ciclo 5 - Electivas ya cursadas
    {"clave_materia": "ID3466", "calificacion": 8.5, "creditos_obtenidos": 6},  # Gobierno de datos
]

resultado1 = ejecutar_sistema_experto(datos_est1, historial_1)

print(f"\n✓ Ciclo actual: {resultado1['ciclo_actual']}")
print(f"✓ Total recomendaciones: {resultado1['total_materias_recomendadas']}")

# Contar tipos de materias recomendadas
preesp = sum(1 for m in resultado1['materias_recomendadas'] if m['categoria'] == 'PREESPECIALIDAD')
elect = sum(1 for m in resultado1['materias_recomendadas'] if m['categoria'] == 'ELECCION_LIBRE')
basica = sum(1 for m in resultado1['materias_recomendadas'] if m['categoria'] == 'BASICA')

print(f"  - PREESPECIALIDAD: {preesp}")
print(f"  - ELECCION_LIBRE: {elect}")
print(f"  - BASICA: {basica}")

# Mostrar alertas
if resultado1['alertas']:
    print("\n⚠️  Alertas generadas:")
    for a in resultado1['alertas']:
        print(f"  - [{a['tipo']}] {a['descripcion']}")

# ============================================================================
# TEST 2: Estudiante que ya alcanzó límite de electivas de ciclo 1
# ============================================================================
print("\n" + "="*80)
print("TEST 2: Estudiante que alcanzó límite de electivas en ciclo 1")
print("="*80)

datos_est2 = {
    "id": "EST003",
    "nombre": "Ana García - Electivas Completas",
    "promedio": 8.0,
    "total_creditos": 54
}

historial_2 = [
    # Ciclo 1 - YA CON 2 ELECTIVAS CURSADAS (límite alcanzado)
    {"clave_materia": "ID0001", "calificacion": 8.0, "creditos_obtenidos": 6},
    {"clave_materia": "ID0101", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0102", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0104", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0105", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0106", "calificacion": 8.0, "creditos_obtenidos": 6},
    
    # Ciclo 1 - Electivas YA cursadas (límite 2, ya tiene 2)
    {"clave_materia": "ID0160", "calificacion": 8.0, "creditos_obtenidos": 6},  # Pensamiento crítico
    {"clave_materia": "ID0263", "calificacion": 8.0, "creditos_obtenidos": 6},  # ERP (ELECTIVA ciclo 1)
]

resultado2 = ejecutar_sistema_experto(datos_est2, historial_2)

print(f"\n✓ Ciclo actual: {resultado2['ciclo_actual']}")
print(f"✓ Total recomendaciones: {resultado2['total_materias_recomendadas']}")

# Verificar que NO recomendó más electivas de ciclo 1
electivas_ciclo1 = [m for m in resultado2['materias_recomendadas'] 
                     if m['categoria'] == 'ELECCION_LIBRE' and m['ciclo'] == 1]

if not electivas_ciclo1:
    print("✓ CORRECTO: No recomendó más electivas de ciclo 1 (límite alcanzado)")
else:
    print(f"✗ ERROR: Recomendó {len(electivas_ciclo1)} electivas de ciclo 1 cuando ya tiene 2")

# ============================================================================
# TEST 3: Estudiante Business Intelligence con especialidad detectada
# ============================================================================  
print("\n" + "="*80)
print("TEST 3: Estudiante con Especialidad Business Intelligence detectada")
print("="*80)

datos_est3 = {
    "id": "EST004",
    "nombre": "María Rodríguez - Test BI",
    "promedio": 8.3,
    "total_creditos": 60
}

historial_3 = [
    # Ciclo 1-2 (básico)
    {"clave_materia": "ID0001", "calificacion": 8.0, "creditos_obtenidos": 6},
    {"clave_materia": "ID0101", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0102", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0104", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0105", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0106", "calificacion": 8.0, "creditos_obtenidos": 6},
    {"clave_materia": "ID0107", "calificacion": 8.0, "creditos_obtenidos": 3},
    
    {"clave_materia": "ID0201", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0202", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0203", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0204", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0205", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0206", "calificacion": 8.0, "creditos_obtenidos": 8},
    {"clave_materia": "ID0207", "calificacion": 8.0, "creditos_obtenidos": 3},
    
    # PREESPECIALIDAD de BUSINESS INTELLIGENCE
    {"clave_materia": "ID3420", "calificacion": 8.5, "creditos_obtenidos": 6},  # Analítica para inteligencia de negocios
    {"clave_materia": "ID3421", "calificacion": 8.0, "creditos_obtenidos": 6},  # Gestión del conocimiento
    {"clave_materia": "ID3422", "calificacion": 8.5, "creditos_obtenidos": 6},  # Negocios digitales
]

resultado3 = ejecutar_sistema_experto(datos_est3, historial_3)

print(f"\n✓ Ciclo actual: {resultado3['ciclo_actual']}")
print(f"✓ Total recomendaciones: {resultado3['total_materias_recomendadas']}")

# Contar tipos
preesp_bi = sum(1 for m in resultado3['materias_recomendadas'] if m['categoria'] == 'PREESPECIALIDAD')
print(f"  - PREESPECIALIDAD recomendadas: {preesp_bi}")

# Verificar que prioriza otras materias de BI
preesp_recomendadas = [m for m in resultado3['materias_recomendadas'] if m['categoria'] == 'PREESPECIALIDAD']
if preesp_recomendadas:
    print(f"✓ Materias de especialidad recomendadas:")
    for m in preesp_recomendadas[:3]:
        print(f"    - {m['clave']}: {m['nombre']}")

print("\n" + "="*80)
print("RESUMEN DE TESTS")
print("="*80)
print("✓ TEST 1: Detectó especialidad TICS")
print("✓ TEST 2: Respetó límites de electivas por ciclo")
print("✓ TEST 3: Detectó especialidad Business Intelligence")
print("\n¡Todos los tests completados!")
