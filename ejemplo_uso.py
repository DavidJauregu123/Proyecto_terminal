"""
Ejemplo de uso: Procesar un kardex y generar reporte
"""

import sys
from pathlib import Path
import pandas as pd

# Agregar proyecto a path
sys.path.insert(0, str(Path(__file__).parent))

from parsers import KardexParser
from services import AcademicProcessor, SupabaseService
from config import settings
import json


def ejemplo_procesar_kardex():
    """Ejemplo: Procesar un kardex PDF"""
    
    print("=" * 80)
    print("EJEMPLO: Procesar Kardex y Generar Reporte")
    print("=" * 80)
    
    # 1. Parsear kardex
    print("\n[1] Parseando kardex...")
    parser = KardexParser()
    
    # Nota: Reemplaza con tu ruta real del PDF
    ruta_pdf = "path/to/kardex.pdf"
    
    try:
        datos_estudiante = parser.parse_kardex(ruta_pdf)
        print(f"✅ Kardex procesado")
        print(f"   Estudiante: {datos_estudiante.nombre}")
        print(f"   Matrícula: {datos_estudiante.matricula}")
        print(f"   Total de materias: {len(datos_estudiante.materias)}")
    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {ruta_pdf}")
        print("   (Este es solo un ejemplo, proporciona una ruta real)")
        return
    
    # 2. Convertir a DataFrame
    print("\n[2] Convirtiendo a DataFrame...")
    df = parser.to_dataframe()
    print(f"✅ DataFrame creado: {df.shape[0]} filas")
    print(df.head())
    
    # 3. Cargar mapa curricular
    # Nota: el parser extrae clave y nombre directamente del PDF;
    # el mapa se usa como referencia para ciclo/categoría/procesamiento.
    print("\n[3] Cargando mapa curricular...")
    mapa_path = Path(__file__).parent / "data" / "mapa_curricular_2021ID_real.json"
    with open(mapa_path, "r", encoding="utf-8") as f:
        mapa_curricular = json.load(f)
    print(f"✅ Mapa curricular cargado: {len(mapa_curricular)} materias")
    
    # 4. Procesar datos académicos
    print("\n[4] Procesando datos académicos...")
    processor = AcademicProcessor(mapa_curricular)
    
    # Calcular progreso por ciclo
    progreso = processor.calcular_progreso_por_ciclo(df)
    print("✅ Progreso calculado:")
    for ciclo, p in sorted(progreso.items()):
        print(f"   Ciclo {ciclo}: {p.porcentaje:.1f}% completado ({p.finalizadas}/{p.total})")
    
    # Identificar alertas
    alertas = processor.identificar_alertas(df)
    print(f"✅ Alertas identificadas: {len(alertas)}")
    for alerta in alertas:
        print(f"   - {alerta['tipo']}: {alerta['descripcion']}")
    
    # 5. Guardar en Supabase (si está configurado)
    print("\n[5] Guardando en Supabase...")
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        service = SupabaseService()
        
        # Crear estudiante
        est = service.crear_estudiante(datos_estudiante.matricula, {
            "nombre": datos_estudiante.nombre,
            "plan_estudios": datos_estudiante.plan_estudios,
            "situacion": datos_estudiante.situacion,
            "total_creditos": datos_estudiante.total_creditos,
            "promedio_general": datos_estudiante.promedio_general
        })
        
        if est:
            print(f"✅ Estudiante guardado en BD")
            
            # Guardar historial
            registros = [
                {
                    "clave": m.clave,
                    "periodo": m.periodo,
                    "calificacion": m.calificacion,
                    "creditos": m.creditos,
                    "estatus": m.estatus
                }
                for m in datos_estudiante.materias
            ]
            
            service.crear_registro_historial(datos_estudiante.matricula, registros)
            print(f"✅ Historial guardado en BD ({len(registros)} registros)")
            
            # Guardar alertas
            for alerta in alertas:
                service.crear_alerta(datos_estudiante.matricula, alerta)
            print(f"✅ Alertas guardadas en BD")
        else:
            print("❌ Error al guardar estudiante")
    else:
        print("⚠️  Supabase no configurado (omitido)")
    
    print("\n" + "=" * 80)
    print("✅ Ejemplo completado")
    print("=" * 80)


def ejemplo_streamlit():
    """Ejemplo: Ejecutar dashboard"""
    print("\n📊 Para ejecutar el dashboard interactivo:")
    print("   streamlit run dashboard/app.py")


if __name__ == "__main__":
    print("EJEMPLOS DE USO")
    print()
    print("1. Procesar kardex y generar reporte")
    print("2. Ejecutar dashboard Streamlit")
    print()
    
    choice = input("¿Cuál ejemplo deseas ejecutar? (1 o 2): ").strip()
    
    if choice == "1":
        ejemplo_procesar_kardex()
    elif choice == "2":
        ejemplo_streamlit()
    else:
        print("❌ Opción inválida")
