-- Script de configuración de PostgreSQL para IDeIO
-- Ejecutar este script en pgAdmin o psql

-- 1. Crear la base de datos (si no existe)
CREATE DATABASE proyecto_ideio
    WITH 
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'Spanish_Spain.1252'
    LC_CTYPE = 'Spanish_Spain.1252'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1;

-- 2. Conectarse a la base de datos
\c proyecto_ideio

-- 3. Crear el schema proyecto_pt
CREATE SCHEMA IF NOT EXISTS proyecto_pt;

-- 4. Dar permisos al usuario postgres
GRANT ALL ON SCHEMA proyecto_pt TO postgres;
GRANT ALL ON ALL TABLES IN SCHEMA proyecto_pt TO postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA proyecto_pt TO postgres;

-- 5. Verificar que todo está correcto
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'proyecto_pt';

-- ✅ Configuración completada
