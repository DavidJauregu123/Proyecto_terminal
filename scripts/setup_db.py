"""
Script para configurar la base de datos PostgreSQL
Crea la base de datos y el schema automáticamente
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sys

def setup_database():
    """Configura la base de datos PostgreSQL"""
    print("🔧 Configurador de Base de Datos PostgreSQL")
    print("=" * 80)
    
    # Solicitar credenciales
    print("\n📝 Ingresa las credenciales de PostgreSQL:")
    print("(Si instalaste PostgreSQL recientemente, el usuario por defecto es 'postgres')")
    
    host = input("Host [localhost]: ").strip() or "localhost"
    port = input("Puerto [5432]: ").strip() or "5432"
    user = input("Usuario [postgres]: ").strip() or "postgres"
    password = input("Contraseña: ").strip()
    
    if not password:
        print("❌ La contraseña es requerida")
        sys.exit(1)
    
    try:
        # Conectar a PostgreSQL (a la base de datos por defecto)
        print("\n🔌 Conectando a PostgreSQL...")
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="postgres"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Verificar si la base de datos existe
        print("🔍 Verificando base de datos 'proyecto_ideio'...")
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'proyecto_ideio'"
        )
        exists = cursor.fetchone()
        
        if not exists:
            # Crear la base de datos
            print("📦 Creando base de datos 'proyecto_ideio'...")
            cursor.execute("CREATE DATABASE proyecto_ideio")
            print("✅ Base de datos creada")
        else:
            print("✅ Base de datos ya existe")
        
        cursor.close()
        conn.close()
        
        # Conectar a la nueva base de datos y crear el schema
        print("\n🔌 Conectando a 'proyecto_ideio'...")
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="proyecto_ideio"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Crear el schema
        print("📋 Creando schema 'proyecto_pt'...")
        cursor.execute("CREATE SCHEMA IF NOT EXISTS proyecto_pt")
        
        # Dar permisos
        print("🔐 Configurando permisos...")
        cursor.execute(f"GRANT ALL ON SCHEMA proyecto_pt TO {user}")
        cursor.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA proyecto_pt TO {user}")
        cursor.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA proyecto_pt TO {user}")
        cursor.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA proyecto_pt GRANT ALL ON TABLES TO {user}")
        cursor.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA proyecto_pt GRANT ALL ON SEQUENCES TO {user}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ Configuración completada exitosamente!")
        print("\n📝 Actualiza tu archivo .env con esta línea:")
        print(f"\nDATABASE_URL=postgresql://{user}:{password}@{host}:{port}/proyecto_ideio")
        print("\n⚠️  IMPORTANTE: Guarda esta configuración en tu archivo .env")
        
    except psycopg2.OperationalError as e:
        print(f"\n❌ Error de conexión: {e}")
        print("\n💡 Posibles soluciones:")
        print("   1. Verifica que PostgreSQL esté corriendo")
        print("   2. Verifica que la contraseña sea correcta")
        print("   3. Verifica que el puerto 5432 esté disponible")
        print("   4. En Windows, ve a Servicios y busca 'postgresql' para iniciarlo")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    setup_database()
