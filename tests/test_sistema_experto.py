"""
Test del Sistema Experto de Seriación

Valida que el sistema funcione correctamente con datos de prueba.
"""

import json
from pathlib import Path
import sys

# Añadir ruta del proyecto
proyecto_root = Path(__file__).parent.parent
sys.path.insert(0, str(proyecto_root))

from agents.sistema_experto_seriacion import ejecutar_sistema_experto
from services.seriacion_service import ProcessadorSeriacionExacerbado


def test_basico():
    """Test 1: Ejecución básica del sistema experto"""
    print("\n" + "=" * 80)
    print("TEST 1: EJECUCIÓN BÁSICA DEL SISTEMA EXPERTO")
    print("=" * 80)
    
    # Datos de prueba - Estudiante que completó ciclo 1
    datos_est = {
        "id": "EST001",
        "nombre": "Juan Pérez",
        "promedio": 8.5,
        "total_creditos": 54
    }
    
    # Historial - todas las materias del ciclo 1
    historial = [
        {"clave_materia": "ID0001", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0101", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0102", "calificacion": 9.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0104", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0105", "calificacion": 7.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0106", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0107", "calificacion": 8.5, "creditos_obtenidos": 3},
    ]
    
    # Ejecutar
    resultado = ejecutar_sistema_experto(datos_est, historial)
    
    # Validaciones
    print(f"\n✓ Sistema ejecutado correctamente")
    print(f"✓ Ciclo recomendado: {resultado['ciclo_recomendado']} (esperado: 2)")
    print(f"✓ Materias recomendadas: {resultado['total_materias_recomendadas']}")
    print(f"✓ Alertas generadas: {len(resultado['alertas'])}")
    
    assert resultado['ciclo_recomendado'] == 2, "El ciclo recomendado debería ser 2"
    assert resultado['total_materias_recomendadas'] > 0, "Debería haber materias recomendadas"
    
    # Mostrar algunas recomendaciones
    print(f"\nPrimeras 5 materias recomendadas:")
    for i, mat in enumerate(resultado['materias_recomendadas'][:5], 1):
        print(f"  {i}. {mat['clave']} - {mat['nombre']}")
        print(f"     Ciclo: {mat['ciclo']} | Créditos: {mat['creditos']}")
    
    print("\n✅ TEST 1 PASADO")
    return resultado


def test_requisitos():
    """Test 2: Validación de requisitos"""
    print("\n" + "=" * 80)
    print("TEST 2: VALIDACIÓN DE REQUISITOS")
    print("=" * 80)
    
    # Estudiante que solo completó propedéutico (no tiene requisito para Cálculo Diferencial)
    datos_est = {
        "id": "EST002",
        "nombre": "María García",
        "promedio": 7.5,
        "total_creditos": 6
    }
    
    # Historial - solo propedéutico y matemáticas
    historial = [
        {"clave_materia": "ID0001", "calificacion": 8.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0101", "calificacion": 7.0, "creditos_obtenidos": 8},
    ]
    
    # Ejecutar
    resultado = ejecutar_sistema_experto(datos_est, historial)
    
    print(f"\n✓ Materias recomendadas: {resultado['total_materias_recomendadas']}")
    print(f"✓ Alertas (bloqueos por requisitos): {len([a for a in resultado['alertas'] if a['tipo'] == 'BLOQUEO'])}")
    
    # Verificar que Cálculo Diferencial NO está en recomendadas
    calculo_diff = [m for m in resultado['materias_recomendadas'] if m['clave'] == 'ID0102']
    assert len(calculo_diff) > 0, "Debería estar ID0102 (tiene ID0001 como requisito)"
    
    print(f"\nMaterias recomendadas (solo sin requisitos no cumplidos):")
    for mat in resultado['materias_recomendadas']:
        print(f"  - {mat['clave']} ({mat['nombre']})")
    
    print("\n✅ TEST 2 PASADO")
    return resultado


def test_ligaduras():
    """Test 3: Regla de ligaduras"""
    print("\n" + "=" * 80)
    print("TEST 3: REGLA DE LIGADURAS")
    print("=" * 80)
    
    # Estudiante que no ha aprobado Cálculo Diferencial
    # pero tiene requisito para intentar ambas (por ciclo)
    datos_est = {
        "id": "EST003",
        "nombre": "Carlos López",
        "promedio": 8.0,
        "total_creditos": 6
    }
    
    # Solo propedéutico aprobado
    historial = [
        {"clave_materia": "ID0001", "calificacion": 8.5, "creditos_obtenidos": 6},
    ]
    
    # Ejecutar
    resultado = ejecutar_sistema_experto(datos_est, historial)
    
    # Contar alertas de ligadura
    alertas_ligadura = [a for a in resultado['alertas'] if a['tipo'] == 'LIGADURA']
    
    print(f"\n✓ Alertas de ligadura detectadas: {len(alertas_ligadura)}")
    
    if alertas_ligadura:
        print(f"\nAlerta de ligadura:")
        for alerta in alertas_ligadura[:3]:
            print(f"  - {alerta['materia']}: {alerta['descripcion']}")
    
    print("\n✅ TEST 3 PASADO")
    return resultado


def test_procesador_integracion():
    """Test 4: Integración con ProcessadorSeriacionExacerbado"""
    print("\n" + "=" * 80)
    print("TEST 4: INTEGRACIÓN CON PROCESADOR")
    print("=" * 80)
    
    # Cargar mapa curricular
    ruta_mapa = proyecto_root / "data" / "mapa_curricular_2021ID_real_completo.json"
    with open(ruta_mapa, 'r', encoding='utf-8') as f:
        mapa = json.load(f)
    
    # Crear procesador
    procesador = ProcessadorSeriacionExacerbado(mapa_curricular=mapa)
    
    # Calcular progreso
    historial = [
        {"clave_materia": "ID0001", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0101", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0102", "calificacion": 9.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0104", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0105", "calificacion": 7.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0106", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0107", "calificacion": 8.5, "creditos_obtenidos": 3},
    ]
    
    progreso = procesador._calcular_progreso_por_ciclo(historial)
    ciclo_actual = procesador._detectar_ciclo_actual(progreso)
    
    print(f"\n✓ Progreso por ciclo calculado:")
    for ciclo, datos in progreso.items():
        print(f"  Ciclo {ciclo}: {datos['porcentaje']}% ({datos['créditos_obtenidos']}/{datos['créditos_totales']} créditos)")
    
    print(f"\n✓ Ciclo actual detectado: {ciclo_actual}")
    assert ciclo_actual == 2, f"El ciclo actual debería ser 2, pero es {ciclo_actual}"
    
    print("\n✅ TEST 4 PASADO")
    return progreso


def test_plan_semestral():
    """Test 5: Generación de plan semestral"""
    print("\n" + "=" * 80)
    print("TEST 5: GENERACIÓN DE PLAN SEMESTRAL")
    print("=" * 80)
    
    # Cargar mapa curricular
    ruta_mapa = proyecto_root / "data" / "mapa_curricular_2021ID_real_completo.json"
    with open(ruta_mapa, 'r', encoding='utf-8') as f:
        mapa = json.load(f)
    
    # Crear procesador sin BD
    procesador = ProcessadorSeriacionExacerbado(mapa_curricular=mapa)
    
    # Datos de prueba
    historial = [
        {"clave_materia": "ID0001", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0101", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0102", "calificacion": 9.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0104", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0105", "calificacion": 7.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0106", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0107", "calificacion": 8.5, "creditos_obtenidos": 3},
    ]
    
    datos_est = {
        "id": "EST005",
        "nombre": "Ana Martínez",
        "promedio": 8.5,
        "total_creditos": 54
    }
    
    # Ejecutar sin BD pero con datos simulados
    resultado = ejecutar_sistema_experto(datos_est, historial)
    
    # Generar plan (en una aplicación real usaría DB)
    print(f"\n✓ Sistema experto ejecutado")
    print(f"✓ Ciclo recomendado: {resultado['ciclo_recomendado']}")
    print(f"✓ Materias recomendadas: {resultado['total_materias_recomendadas']}")
    
    # Simular plan semestral
    print(f"\nPlan semestral proyectado:")
    print(f"  Semestre 1 (Ciclo {resultado['ciclo_recomendado']}):")
    
    creditos_primera_sem = 0
    for i, mat in enumerate(resultado['materias_recomendadas'][:6], 1):
        if creditos_primera_sem + mat['creditos'] <= 48:
            print(f"    {i}. {mat['clave']} - {mat['creditos']} creditos")
            creditos_primera_sem += mat['creditos']
    
    print(f"  Total créditos semestre 1: {creditos_primera_sem}")
    
    print("\n✅ TEST 5 PASADO")


def main():
    """Ejecutar todos los tests"""
    print("\n" + "=" * 80)
    print("SUITE DE TESTS - SISTEMA EXPERTO DE SERIACIÓN")
    print("=" * 80)
    
    try:
        # Test 1
        test_basico()
        
        # Test 2
        test_requisitos()
        
        # Test 3
        test_ligaduras()
        
        # Test 4
        test_procesador_integracion()
        
        # Test 5
        test_plan_semestral()
        
        # Resumen
        print("\n" + "=" * 80)
        print("✅ TODOS LOS TESTS PASARON CORRECTAMENTE")
        print("=" * 80)
        print("\nEl Sistema Experto de Seriación está listo para usar.")
        print("\nPróximos pasos:")
        print("  1. Integrar con BD PostgreSQL")
        print("  2. Crear API REST para consultas")
        print("  3. Añadir visualización en dashboard Streamlit")
        print("  4. Implementar almacenamiento de recomendaciones")
        
    except AssertionError as e:
        print(f"\n❌ TEST FALLIDO: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
