import pdfplumber
from pathlib import Path
from parsers import KardexParser

pdf_path = Path(r"C:\Users\david\OneDrive\Escritorio\proyecto terminal\pdf_pruebas\estudiante_cardexfgomez241.pdf")

parser = KardexParser()
datos = parser.parse_kardex(str(pdf_path))

print("=" * 80)
print(f"ANÁLISIS DEL PDF: {pdf_path.name}")
print("=" * 80)
print(f"Matrícula: {datos.matricula}")
print(f"Nombre: {datos.nombre}\n")

# Periodos
periodos = sorted(set(m.periodo for m in datos.materias))
print(f"Períodos encontrados: {periodos}")
print(f"Último período: {max(m.periodo for m in datos.materias)}\n")

# Materias del ÚLTIMO período
ultimo_periodo = max(m.periodo for m in datos.materias)
print(f"=== MATERIAS DEL ÚLTIMO PERÍODO ({ultimo_periodo}) ===")
materias_ultimo = [m for m in datos.materias if m.periodo == ultimo_periodo]
for m in materias_ultimo:
    print(f"{m.clave}: {m.nombre}")
    print(f"  Calificación: {m.calificacion}, Créditos: {m.creditos}, Estatus: {m.estatus}\n")

# Verificar problema específico: DP0194 en 202601
print(f"\n=== VERIFICACIÓN ESPECÍFICA ===")
dp0194_202601 = [m for m in datos.materias if m.clave == "DP0194" and m.periodo == "202601"]
if dp0194_202601:
    m = dp0194_202601[0]
    print(f"DP0194 (202601):")
    print(f"  Estatus: {m.estatus}")
    print(f"  Créditos: {m.creditos}")
    print(f"  Calificación: {m.calificacion}")
    print(f"  ✓ Debe ser EN_CURSO" if m.estatus == "EN_CURSO" else f"  ✗ ERROR: debería ser EN_CURSO")
