"""
Script para inicializar la BD PostgreSQL
Carga las materias iniciales desde el mapa curricular
"""

import sys
from pathlib import Path
import json

# Agregar proyecto a path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.local_database import DatabaseService


def cargar_materias_iniciales():
    """Carga las materias iniciales en la BD local"""
    db = DatabaseService()
    
    # Cargar mapa curricular
    mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_ejemplo.json"
    
    if not mapa_path.exists():
        print(f"❌ Archivo no encontrado: {mapa_path}")
        return
    
    with open(mapa_path, "r", encoding="utf-8") as f:
        mapa = json.load(f)
    
    # Preparar datos
    materias = []
    for clave, info in mapa.items():
        materias.append({
            "clave": clave,
            "nombre": info.get("nombre", ""),
            "creditos": info.get("creditos", 0),
            "ciclo": info.get("ciclo", 0),
            "categoria": info.get("categoria", "")
        })
    
    # Insertar
    print("\n📚 Cargando materias en PostgreSQL...")
    resultado = db.crear_materias(materias)
    
    if resultado:
        print(f"✅ {len(resultado)} materias cargadas correctamente")
    else:
        print("⚠️  Error al cargar materias")


def main():
    """Función principal"""
    print("🔧 Inicializador de Base de Datos PostgreSQL")
    print("=" * 80)
    
    # Crear tablas
    print("\n[Paso 1] Creando tablas en PostgreSQL...")
    try:
        db = DatabaseService()
        print("✅ Tablas creadas/verificadas")
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Cargar materias
    print("\n[Paso 2] Cargando materias...")
    cargar_materias_iniciales()
    
    print("\n✅ Inicialización completada")
    print("\n📊 Base de datos: PostgreSQL (proyecto_ideio)")
    print("\n📖 Próximos pasos:")
    print("  1. Ejecuta: streamlit run dashboard/app.py")
    print("  2. Sube un kardex en PDF para probar")
    print("  3. Los datos se guardarán en PostgreSQL")


if __name__ == "__main__":
    main()
