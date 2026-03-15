"""
Script para inicializar la base de datos en Supabase
Crea las tablas y carga datos iniciales
"""

import sys
from pathlib import Path
import json

# Agregar proyecto a path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import SupabaseService
from config import settings


def crear_tablas_supabase():
    """Crea las tablas en Supabase a través de SQL"""
    # Nota: Idealmente ejecutarías esto en el SQL editor de Supabase
    # o a través de una migración. Este es un recordatorio de las tablas.
    
    sql_tables = """
    -- Tabla: estudiantes
    CREATE TABLE IF NOT EXISTS estudiantes (
        id VARCHAR(20) PRIMARY KEY,
        nombre VARCHAR(255) NOT NULL,
        plan_estudios VARCHAR(50) NOT NULL,
        situacion VARCHAR(50) NOT NULL,
        total_creditos INTEGER DEFAULT 0,
        promedio_general NUMERIC(5, 2) DEFAULT 0.0,
        fecha_carga TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Tabla: materias
    CREATE TABLE IF NOT EXISTS materias (
        clave VARCHAR(10) PRIMARY KEY,
        nombre VARCHAR(255) NOT NULL,
        creditos INTEGER NOT NULL,
        ciclo INTEGER NOT NULL,
        categoria VARCHAR(50) NOT NULL
    );

    -- Tabla: historial_academico
    CREATE TABLE IF NOT EXISTS historial_academico (
        id BIGSERIAL PRIMARY KEY,
        estudiante_id VARCHAR(20) NOT NULL REFERENCES estudiantes(id) ON DELETE CASCADE,
        materia_clave VARCHAR(10) NOT NULL REFERENCES materias(clave),
        periodo VARCHAR(6) NOT NULL,
        calificacion NUMERIC(5, 2),
        creditos_obtenidos INTEGER DEFAULT 0,
        estatus VARCHAR(50) NOT NULL,
        fecha_registro TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(estudiante_id, materia_clave, periodo)
    );

    -- Tabla: alertas
    CREATE TABLE IF NOT EXISTS alertas (
        id BIGSERIAL PRIMARY KEY,
        estudiante_id VARCHAR(20) NOT NULL REFERENCES estudiantes(id) ON DELETE CASCADE,
        tipo VARCHAR(50) NOT NULL,
        descripcion TEXT NOT NULL,
        severidad VARCHAR(20) DEFAULT 'INFO',
        activa BOOLEAN DEFAULT TRUE,
        fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Tabla: requisitos_adicionales
    CREATE TABLE IF NOT EXISTS requisitos_adicionales (
        id BIGSERIAL PRIMARY KEY,
        estudiante_id VARCHAR(20) NOT NULL REFERENCES estudiantes(id) ON DELETE CASCADE,
        requisito VARCHAR(100) NOT NULL,
        completado BOOLEAN DEFAULT FALSE,
        fecha_completado TIMESTAMP WITH TIME ZONE,
        UNIQUE(estudiante_id, requisito)
    );

    -- Índices para optimizar búsquedas
    CREATE INDEX IF NOT EXISTS idx_historial_estudiante ON historial_academico(estudiante_id);
    CREATE INDEX IF NOT EXISTS idx_alertas_estudiante ON alertas(estudiante_id);
    CREATE INDEX IF NOT EXISTS idx_requisitos_estudiante ON requisitos_adicionales(estudiante_id);
    """
    
    print("SQL para crear las tablas:")
    print("=" * 80)
    print(sql_tables)
    print("=" * 80)
    print("\n⚠️  Copia y pega el SQL anterior en el SQL Editor de Supabase:")
    print("https://app.supabase.com -> Tu Proyecto -> SQL Editor")


def cargar_materias_iniciales():
    """Carga las materias iniciales en la base de datos"""
    service = SupabaseService()
    
    # Cargar mapa curricular de ejemplo
    mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID_real.json"
    
    if not mapa_path.exists():
        print(f"❌ Archivo no encontrado: {mapa_path}")
        return
    
    with open(mapa_path, "r", encoding="utf-8") as f:
        mapa = json.load(f)
    
    # Preparar datos para insertar
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
    print("\n📚 Cargando materias iniciales...")
    resultado = service.crear_materias(materias)
    
    if resultado:
        print(f"✅ {len(resultado)} materias cargadas correctamente")
    else:
        print("⚠️  Posible error al cargar materias (verifica Supabase)")


def main():
    """Función principal"""
    print("🔧 Inicializador de Supabase")
    print("=" * 80)
    
    # Verificar configuración
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        print("❌ Error: Variables de entorno no configuradas")
        print("   Configura SUPABASE_URL y SUPABASE_KEY en .env")
        return
    
    print(f"✅ Supabase URL: {settings.SUPABASE_URL[:50]}...")
    
    # Paso 1: Crear tablas (manual en SQL Editor)
    print("\n[Paso 1] Crear tablas")
    crear_tablas_supabase()
    
    # Paso 2: Cargar datos iniciales
    print("\n[Paso 2] Cargar materias iniciales")
    cargar_materias_iniciales()
    
    print("\n✅ Inicialización completada")
    print("\n📖 Próximos pasos:")
    print("  1. Verifica que las tablas se crearon en Supabase")
    print("  2. Ejecuta: streamlit run dashboard/app.py")
    print("  3. Sube un kardex en PDF para probar")


if __name__ == "__main__":
    main()
