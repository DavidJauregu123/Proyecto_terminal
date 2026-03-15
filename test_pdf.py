import sys
import importlib

# Limpiar caché de módulos
if 'parsers' in sys.modules:
    del sys.modules['parsers']
if 'kardex_parser' in sys.modules:
    del sys.modules['kardex_parser']

from parsers import KardexParser

pdf_path = r"C:\Users\david\OneDrive\Escritorio\proyecto terminal\pdf_pruebas\estudiante_cardexfgomez242.pdf"
parser = KardexParser()

try:
    datos = parser.parse_kardex(pdf_path)
    print("=== DATOS DEL ESTUDIANTE ===")
    print(f"Matrícula: {datos.matricula}")
    print(f"Nombre: {datos.nombre}")
    print(f"Plan: {datos.plan_estudios}\n")
    
    # Debug: Ver todos los periodos
    periodos = sorted(set(m.periodo for m in datos.materias))
    print(f"Periodos encontrados: {periodos}\n")
    
    # Buscar materias específicas: DP0194, LI1103, TA0002
    claves_buscar = ["DP0194", "LI1103", "TA0002", "DP0193"]
    
    print("=== BÚSQUEDA DE MATERIAS ESPECÍFICAS ===")
    for clave_buscar in claves_buscar:
        registros = [m for m in datos.materias if m.clave == clave_buscar]
        if registros:
            print(f"\n{clave_buscar}:")
            for m in registros:
                print(f"  {m.periodo}: Cal={m.calificacion}, Créditos={m.creditos}, Estatus={m.estatus}")
        else:
            print(f"\n{clave_buscar}: NO ENCONTRADA")
    
    # Contar materias con 0 créditos
    print("\n=== MATERIAS CON 0 CRÉDITOS ===")
    materias_0 = [m for m in datos.materias if m.creditos == 0]
    print(f"Total: {len(materias_0)}")
    for m in materias_0:
        if m.periodo == "202601":  # Mostrar solo el último período
            print(f"{m.clave} ({m.periodo}): Estatus={m.estatus}")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
