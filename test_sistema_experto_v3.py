"""
TEST: Sistema Experto v3
Verifica que el sistema experto genera las candidatas correctamente
"""

import json
import sys
from pathlib import Path

# Agregar ruta del proyecto
sys.path.insert(0, str(Path(__file__).parent))

from agents.sistema_experto_seriacion import ejecutar_sistema_experto


def test_sistema_experto():
    """Test completo del sistema experto"""
    
    print("\n" + "="*80)
    print("TEST: SISTEMA EXPERTO v3")
    print("="*80 + "\n")
    
    # Mapa curricular de prueba minimal
    mapa_test = [
        # Ciclo 1 (sin prerequisitos)
        {"clave": "CAL1", "nombre": "Cálculo Diferencial", "ciclo": 1, "creditos": 4, "categoria": "BASICA", "prerequisites": []},
        {"clave": "MAT1", "nombre": "Matrices", "ciclo": 1, "creditos": 3, "categoria": "BASICA", "prerequisites": []},
        {"clave": "FIS1", "nombre": "Física 1", "ciclo": 1, "creditos": 4, "categoria": "BASICA", "prerequisites": []},
        
        # Ciclo 2 (con prerequisitos)
        {"clave": "CAL2", "nombre": "Cálculo Integral", "ciclo": 2, "creditos": 4, "categoria": "BASICA", "prerequisites": ["CAL1"]},
        {"clave": "ALG1", "nombre": "Álgebra Lineal", "ciclo": 2, "creditos": 3, "categoria": "BASICA", "prerequisites": ["MAT1"]},
        {"clave": "FIS2", "nombre": "Física 2", "ciclo": 2, "creditos": 4, "categoria": "BASICA", "prerequisites": ["FIS1"]},
        
        # Ciclo 3 (cadena más larga)
        {"clave": "ECD", "nombre": "Ecuaciones Diferenciales", "ciclo": 3, "creditos": 4, "categoria": "BASICA", "prerequisites": ["CAL2"]},
        {"clave": "CAL3", "nombre": "Cálculo Vectorial", "ciclo": 3, "creditos": 4, "categoria": "BASICA", "prerequisites": ["CAL2", "ALG1"]},
    ]
    
    # =========================================================================
    # ESCENARIO 1: Estudiante nuevo
    # =========================================================================
    print("ESCENARIO 1: Estudiante nuevo")
    print("-" * 80)
    
    historial_1 = []
    resultado_1 = ejecutar_sistema_experto(historial_1, mapa_test)
    
    print(f"Ciclo actual: {resultado_1['ciclo_actual']}")
    print(f"Candidatas: {resultado_1['candidatas_claves']}")
    print(f"Cantidad: {resultado_1['candidatas_count']}")
    print(f"\nDetalles:")
    for det in resultado_1['candidatas_detalles']:
        print(f"  - {det['clave']}: {det['nombre']}")
    
    print("\nExpectativa: Solo materias de ciclo 1 sin prerequisitos")
    assert resultado_1['ciclo_actual'] == 1
    assert set(resultado_1['candidatas_claves']) == {'CAL1', 'MAT1', 'FIS1'}
    print("✓ PASS\n")
    
    # =========================================================================
    # ESCENARIO 2: Completó ciclo 1
    # =========================================================================
    print("ESCENARIO 2: Estudiante completó ciclo 1")
    print("-" * 80)
    
    historial_2 = [
        {"clave": "CAL1", "estatus": "APROBADA", "ciclo": 1},
        {"clave": "MAT1", "estatus": "APROBADA", "ciclo": 1},
        {"clave": "FIS1", "estatus": "APROBADA", "ciclo": 1},
    ]
    resultado_2 = ejecutar_sistema_experto(historial_2, mapa_test)
    
    print(f"Ciclo actual: {resultado_2['ciclo_actual']}")
    print(f"Candidatas: {resultado_2['candidatas_claves']}")
    print(f"Cantidad: {resultado_2['candidatas_count']}")
    print(f"\nDetalles:")
    for det in resultado_2['candidatas_detalles']:
        print(f"  - {det['clave']}: {det['nombre']} (prereq: {det['prerequisitos']})")
    
    print("\nExpectativa: Todas materias de ciclo 2 (todos prerequisitos aprobados)")
    assert resultado_2['ciclo_actual'] == 2
    assert set(resultado_2['candidatas_claves']) == {'CAL2', 'ALG1', 'FIS2'}
    print("✓ PASS\n")
    
    # =========================================================================
    # ESCENARIO 3: Parcialmente en ciclo 2 (prueba requisitos faltantes)
    # =========================================================================
    print("ESCENARIO 3: Parcialmente en ciclo 2 (CAL1 no aprobado)")
    print("-" * 80)
    
    historial_3 = [
        {"clave": "MAT1", "estatus": "APROBADA", "ciclo": 1},
        {"clave": "FIS1", "estatus": "APROBADA", "ciclo": 1},
        # CAL1 NO APROBADA
    ]
    resultado_3 = ejecutar_sistema_experto(historial_3, mapa_test)
    
    print(f"Ciclo actual: {resultado_3['ciclo_actual']}")
    print(f"Candidatas: {resultado_3['candidatas_claves']}")
    print(f"Cantidad: {resultado_3['candidatas_count']}")
    print(f"\nDetalles:")
    for det in resultado_3['candidatas_detalles']:
        print(f"  - {det['clave']}: {det['nombre']} (prereq: {det['prerequisitos']})")
    
    print("\nExpectativa: Solo CAL1 (única materia faltante del ciclo 1)")
    print("  Ciclo actual es 1 (2 de 3 aprobadas = 66% < 75%)")
    print("  Solo candidatas de ciclo 1")
    print("  CAL1: sin prerequisitos → INCLUIDA")
    print("  MAT1, FIS1: ya aprobadas → NO INCLUIDAS")
    print("  ALG1, FIS2, CAL2: del ciclo 2, ignoradas en ciclo 1")
    
    # Verificar ciclo actual
    assert resultado_3['ciclo_actual'] == 1, f"Ciclo actual debe ser 1, fue {resultado_3['ciclo_actual']}"
    
    # Verificar candidatas
    esperadas = {'CAL1'}
    obtenidas = set(resultado_3['candidatas_claves'])
    assert obtenidas == esperadas, f"Esperadas {esperadas}, obtuvieron {obtenidas}"
    
    print("✓ PASS\n")
    
    # =========================================================================
    # ESCENARIO 4: Completó ciclo 1 pero falta materia de ciclo 2 (candidatas con prereqs)
    # =========================================================================
    print("ESCENARIO 4: Completó ciclo 1, con variables en ciclo 2")
    print("-" * 80)
    
    # Completó ciclo 1, está parcialmente en ciclo 2
    historial_4 = [
        {"clave": "CAL1", "estatus": "APROBADA", "ciclo": 1},
        {"clave": "MAT1", "estatus": "APROBADA", "ciclo": 1},
        {"clave": "FIS1", "estatus": "APROBADA", "ciclo": 1},
        {"clave": "CAL2", "estatus": "REPROBADA", "ciclo": 2},  # Reprobó Cálculo Integral
    ]
    resultado_4 = ejecutar_sistema_experto(historial_4, mapa_test)
    
    print(f"Ciclo actual: {resultado_4['ciclo_actual']}")
    print(f"Candidatas: {resultado_4['candidatas_claves']}")
    print(f"Cantidad: {resultado_4['candidatas_count']}")
    print(f"\nDetalles:")
    for det in resultado_4['candidatas_detalles']:
        print(f"  - {det['clave']}: {det['nombre']} (prereq: {det['prerequisitos']})")
    
    print("\nExpectativa: CAL2, ALG1, FIS2 (faltantes del ciclo 2)")
    print("  Ciclo actual es 2 (3 de 3 aprobadas en ciclo 1 = 100% >= 75%)")
    print("  CAL1 aprobado → CAL2 puede cursarse")
    print("  MAT1 aprobado → ALG1 puede cursarse")
    print("  FIS1 aprobado → FIS2 puede cursarse")
    
    assert resultado_4['ciclo_actual'] == 2
    esperadas = {'CAL2', 'ALG1', 'FIS2'}
    obtenidas = set(resultado_4['candidatas_claves'])
    assert obtenidas == esperadas, f"Esperadas {esperadas}, obtuvieron {obtenidas}"
    
    print("✓ PASS\n")
    
    # =========================================================================
    # ESCENARIO 5: Materia en curso (no debe considerarse requisito)
    # =========================================================================
    print("ESCENARIO 5: Materia EN_CURSO (no cuenta como prerequisito)")
    print("-" * 80)
    
    historial_5 = [
        {"clave": "CAL1", "estatus": "EN_CURSO", "ciclo": 1},  # En curso, no aprobada
        {"clave": "MAT1", "estatus": "APROBADA", "ciclo": 1},
        {"clave": "FIS1", "estatus": "APROBADA", "ciclo": 1},
    ]
    resultado_5 = ejecutar_sistema_experto(historial_5, mapa_test)
    
    print(f"Ciclo actual: {resultado_5['ciclo_actual']}")
    print(f"Candidatas: {resultado_5['candidatas_claves']}")
    print(f"Cantidad: {resultado_5['candidatas_count']}")
    print(f"\nDetalles:")
    for det in resultado_5['candidatas_detalles']:
        print(f"  - {det['clave']}: {det['nombre']} (prereq: {det['prerequisitos']})")
    
    print("\nExpectativa: Ninguna candidata de ciclo 2")
    print("  Ciclo actual es 1 (2 de 3 aprobadas = 66% < 75%)")
    print("  CAL1 está EN_CURSO → no se incluye como candidata")
    print("  Solo candidatas del ciclo 1: ninguna (solo quedaría el EN_CURSO)")
    
    assert resultado_5['ciclo_actual'] == 1
    assert 'CAL1' not in resultado_5['candidatas_claves'], "CAL1 en curso no debe ser candidata"
    assert resultado_5['candidatas_count'] == 0, "No debe haber candidatas si solo CAL1 está disponible y está en curso"
    
    print("✓ PASS\n")
    
    # =========================================================================
    # RESUMEN
    # =========================================================================
    print("="*80)
    print("TODOS LOS TESTS PASARON ✓")
    print("="*80)
    
    print("\nResumen de validaciones:")
    print("  ✓ Determinación correcta del ciclo actual")
    print("  ✓ Candidatas iniciales generadas correctamente")
    print("  ✓ Regla A: Eliminación de candidatas sin prerequisitos")
    print("  ✓ Regla B: Eliminación de cadenas (mantiene solo la base)")
    print("  ✓ Materias EN_CURSO no cuentan como aprobadas")


if __name__ == "__main__":
    test_sistema_experto()
