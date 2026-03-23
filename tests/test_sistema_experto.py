"""
Test del Sistema Experto de Seriacion

Valida que el sistema funcione correctamente con datos de prueba
usando claves reales del mapa curricular 2021ID.
"""

import json
from pathlib import Path
import sys

# Ruta del proyecto
proyecto_root = Path(__file__).parent.parent
sys.path.insert(0, str(proyecto_root))

from agents.sistema_experto_seriacion import ejecutar_sistema_experto
from services.seriacion_service import ProcessadorSeriacionExacerbado

# Cargar mapa una sola vez
RUTA_MAPA = proyecto_root / "data" / "mapa_curricular_2021ID_real_completo.json"
with open(RUTA_MAPA, 'r', encoding='utf-8') as _f:
    MAPA_DICT = json.load(_f)
MAPA_LISTA = []
for _clave, _info in MAPA_DICT.items():
    entrada = dict(_info)
    entrada["clave"] = str(_clave).strip().upper()
    MAPA_LISTA.append(entrada)

# --- Claves reales del ciclo 1 ---
# BASICAS: DP0001, DP0191, DP0194, ID0103, ID0105, II0002 (6 basicas)
# EL:      ID0160, ID0263 (2 eleccion libre)
CICLO1_BASICAS = ["DP0001", "DP0191", "DP0194", "ID0103", "ID0105", "II0002"]
CICLO1_EL = ["ID0160", "ID0263"]
CICLO1_TODAS = CICLO1_BASICAS + CICLO1_EL

# --- Claves reales del ciclo 2 ---
# BASICAS: DP0193, ID0106, ID0107, ID0108(req:ID0104), II0106(req:II0002), IT0161
# EL:      ID0161, IT0264


def _hacer_historial(claves, estatus="APROBADA"):
    """Helper para crear historial con claves dadas."""
    return [{"clave": c, "estatus": estatus, "calificacion": 8.0, "creditos": 6} for c in claves]


def test_basico():
    """Test 1: Estudiante con ciclo 1 completo avanza a ciclo 2"""
    print("\n" + "=" * 80)
    print("TEST 1: ESTUDIANTE CON CICLO 1 COMPLETO")
    print("=" * 80)

    # Aprobar TODAS las materias del ciclo 1 (6 basicas + 2 EL)
    historial = _hacer_historial(CICLO1_TODAS)

    resultado = ejecutar_sistema_experto(historial, MAPA_LISTA)

    print(f"\n  Ciclo actual: {resultado['ciclo_actual']}")
    print(f"  Materias candidatas: {resultado['candidatas_count']}")

    # Con todo el ciclo 1 completo (100%), debe avanzar al ciclo 2
    assert resultado['ciclo_actual'] >= 2, \
        f"Con ciclo 1 completo deberia estar en ciclo >=2, pero esta en {resultado['ciclo_actual']}"
    assert resultado['candidatas_count'] > 0, "Deberia haber materias candidatas del ciclo 2"

    print(f"\n  Materias candidatas:")
    for i, mat in enumerate(resultado['candidatas_detalles'][:8], 1):
        prereqs = mat.get('prerequisitos', [])
        prereq_str = f" (req: {', '.join(prereqs)})" if prereqs else ""
        print(f"    {i}. {mat['clave']} - {mat['nombre'][:45]}{prereq_str}")

    print("\n  TEST 1 PASADO")
    return resultado


def test_requisitos():
    """Test 2: Validacion de prerequisitos - materias con prereqs no cumplidos se eliminan"""
    print("\n" + "=" * 80)
    print("TEST 2: VALIDACION DE PREREQUISITOS")
    print("=" * 80)

    # Aprobar solo 5 de 6 basicas del ciclo 1 (SIN II0002)
    # II0106 del ciclo 2 requiere II0002 -> no debe ser candidata
    basicas_sin_ii = [c for c in CICLO1_BASICAS if c != "II0002"]
    historial = _hacer_historial(basicas_sin_ii + CICLO1_EL)

    resultado = ejecutar_sistema_experto(historial, MAPA_LISTA)

    print(f"\n  Ciclo actual: {resultado['ciclo_actual']}")
    print(f"  Candidatas iniciales: {resultado['debug']['candidatas_iniciales_count']}")
    print(f"  Eliminadas por Regla A (prerequisitos): {resultado['debug']['eliminadas_regla_a']}")
    print(f"  Candidatas finales: {resultado['candidatas_count']}")

    # Verificar que II0106 NO esta en candidatas (requiere II0002 que no esta aprobada)
    candidatas_claves = resultado['candidatas_claves']
    # II0002 debe estar como candidata (es del ciclo 1 y no fue aprobada)
    assert "II0002" in candidatas_claves, \
        "II0002 deberia ser candidata (no aprobada, sin prereqs)"

    # Verificar que TODAS las candidatas tienen prereqs cumplidos
    aprobadas = set(c.upper() for c in basicas_sin_ii + CICLO1_EL)
    for mat in resultado['candidatas_detalles']:
        for prereq in mat.get('prerequisitos', []):
            assert prereq in aprobadas, \
                f"Materia {mat['clave']} tiene prerequisito {prereq} no aprobado"

    print(f"\n  Candidatas (prerequisitos validados):")
    for mat in resultado['candidatas_detalles']:
        prereqs = mat.get('prerequisitos', [])
        prereq_str = f" (req: {', '.join(prereqs)})" if prereqs else ""
        print(f"    - {mat['clave']} - {mat['nombre'][:45]}{prereq_str}")

    print("\n  TEST 2 PASADO")
    return resultado


def test_cadenas_seriacion():
    """Test 3: Regla de cadenas de seriacion (Regla B)"""
    print("\n" + "=" * 80)
    print("TEST 3: REGLA DE CADENAS DE SERIACION")
    print("=" * 80)

    # Estudiante nuevo: solo 1 materia aprobada
    historial = _hacer_historial(["DP0001"])

    resultado = ejecutar_sistema_experto(historial, MAPA_LISTA)

    eliminadas_b = resultado['debug']['eliminadas_regla_b']
    print(f"\n  Ciclo actual: {resultado['ciclo_actual']}")
    print(f"  Candidatas iniciales: {resultado['debug']['candidatas_iniciales_count']}")
    print(f"  Eliminadas por Regla A: {resultado['debug']['eliminadas_regla_a']}")
    print(f"  Eliminadas por Regla B (cadenas): {eliminadas_b}")
    print(f"  Candidatas finales: {resultado['candidatas_count']}")

    if eliminadas_b > 0:
        print(f"\n  La Regla B elimino {eliminadas_b} materia(s) por cadena de seriacion")

    print(f"\n  Materias candidatas finales:")
    for mat in resultado['candidatas_detalles']:
        print(f"    - {mat['clave']} - {mat['nombre'][:45]} (ciclo {mat['ciclo']})")

    print("\n  TEST 3 PASADO")
    return resultado


def test_procesador_integracion():
    """Test 4: Integracion con ProcessadorSeriacionExacerbado"""
    print("\n" + "=" * 80)
    print("TEST 4: INTEGRACION CON PROCESADOR")
    print("=" * 80)

    procesador = ProcessadorSeriacionExacerbado(mapa_curricular=MAPA_DICT)

    # Historial con creditos reales de ciclo 1
    historial_creditos = []
    for clave in CICLO1_BASICAS:
        cred = MAPA_DICT.get(clave, {}).get("creditos", 6)
        historial_creditos.append({"clave_materia": clave, "creditos_obtenidos": cred})

    progreso = procesador._calcular_progreso_por_ciclo(historial_creditos)
    ciclo_actual = procesador._detectar_ciclo_actual(progreso)

    print(f"\n  Progreso por ciclo:")
    for ciclo, datos in sorted(progreso.items()):
        estado = "[completado]" if datos['completado'] else ""
        print(f"    Ciclo {ciclo}: {datos['porcentaje']}% "
              f"({datos['creditos_obtenidos']}/{datos['creditos_totales']} cred) {estado}")

    print(f"\n  Ciclo actual detectado por procesador: {ciclo_actual}")

    # El ciclo 1 con todas las basicas deberia tener buen progreso
    assert 1 in progreso, "Debe haber progreso para ciclo 1"

    print("\n  TEST 4 PASADO")
    return progreso


def test_reglas_completas():
    """Test 5: Todas las reglas aplicadas (A, B, C, D, E) con ciclo 1 completo"""
    print("\n" + "=" * 80)
    print("TEST 5: EJECUCION COMPLETA CON TODAS LAS REGLAS")
    print("=" * 80)

    historial = _hacer_historial(CICLO1_TODAS)

    resultado = ejecutar_sistema_experto(historial, MAPA_LISTA)

    debug = resultado['debug']
    print(f"\n  Ciclo actual: {resultado['ciclo_actual']}")
    print(f"  Especialidad detectada: {resultado.get('especialidad_detectada', 'Ninguna')}")
    print(f"\n  Desglose de reglas:")
    print(f"    Candidatas iniciales: {debug['candidatas_iniciales_count']}")
    print(f"    Eliminadas Regla A (prerequisitos):  {debug['eliminadas_regla_a']}")
    print(f"    Eliminadas Regla B (cadenas):        {debug['eliminadas_regla_b']}")
    print(f"    Eliminadas Regla C (cuota EL):       {debug['eliminadas_regla_c']}")
    print(f"    Eliminadas Regla D (preespecialidad): {debug['eliminadas_regla_d']}")
    print(f"    Eliminadas Regla E (practicas PID):   {debug['eliminadas_regla_e']}")
    print(f"    Candidatas finales: {resultado['candidatas_count']}")

    creditos_total = sum(m.get('creditos', 0) for m in resultado['candidatas_detalles'])
    print(f"\n  Creditos totales de candidatas: {creditos_total}")

    # Verificaciones basicas
    assert resultado['candidatas_count'] > 0, "Debe haber candidatas"
    total_eliminadas = (debug['eliminadas_regla_a'] + debug['eliminadas_regla_b'] +
                        debug['eliminadas_regla_c'] + debug['eliminadas_regla_d'] +
                        debug['eliminadas_regla_e'])
    assert debug['candidatas_iniciales_count'] >= resultado['candidatas_count'], \
        "Las candidatas finales no pueden ser mas que las iniciales"
    assert debug['candidatas_iniciales_count'] - total_eliminadas == resultado['candidatas_count'], \
        "El conteo de eliminadas debe sumar correctamente"

    print(f"\n  Plan candidato:")
    for i, mat in enumerate(resultado['candidatas_detalles'][:8], 1):
        print(f"    {i}. {mat['clave']} - {mat['nombre'][:45]} ({mat['creditos']} cred, ciclo {mat['ciclo']})")

    print("\n  TEST 5 PASADO")
    return resultado


def main():
    """Ejecutar todos los tests"""
    print("\n" + "=" * 80)
    print("SUITE DE TESTS - SISTEMA EXPERTO DE SERIACION")
    print("=" * 80)

    try:
        test_basico()
        test_requisitos()
        test_cadenas_seriacion()
        test_procesador_integracion()
        test_reglas_completas()

        print("\n" + "=" * 80)
        print("TODOS LOS TESTS PASARON CORRECTAMENTE")
        print("=" * 80)

    except AssertionError as e:
        print(f"\nTEST FALLIDO: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
