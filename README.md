# Sistema Experto de Asesoría Curricular - IDeIO

## 📋 Descripción

Sistema Experto basado en Agentes para automatizar y optimizar la planeación académica de estudiantes de Ingeniería en Datos e Inteligencia Organizacional (IDeIO) Plan 2021.

## 🏗️ Arquitectura

### 1. **Sistema Experto** (Base de Conocimientos)
- Mapa curricular con 86 materias
- Reglas de seriación (uso de NetworkX)
- 8 reglas de oro academic

### 2. **Motor de Inferencia y Optimización**
- Validación de seriación
- Filtrado de conflictos de horarios
- Optimización con Pandas

### 3. **Agente Inteligente** (Interfaz)
- Interfaz conversacional con Gemini
- Usuario: "David, analicé tu kárdex..."

### 4. **Orquestador** (LangGraph)
- Gestión de flujo de trabajo
- Memoria de conversación
- Estados y transiciones

## 📁 Estructura del Proyecto

```
proyecto terminal/
├── config/                 # Configuración
│   ├── __init__.py
│   └── settings.py
├── db/                     # Base de datos (modelos SQLAlchemy)
│   ├── __init__.py
│   └── models.py
├── parsers/                # Extracción de PDFs
│   ├── __init__.py
│   └── kardex_parser.py
├── services/               # Lógica de negocio
│   ├── __init__.py
│   ├── processor.py        # Procesamiento académico
│   └── local_database.py   # Servicio de base de datos PostgreSQL
├── dashboard/              # Interfaz Streamlit
│   ├── __init__.py
│   └── app.py
├── agents/                 # Agentes LangGraph + Gemini
│   └── __init__.py
├── data/                   # Datos estáticos
│   └── mapa_curricular_ejemplo.json
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Instalación

### 1. Clonar repositorio
```bash
cd proyecto terminal
```

### 2. Crear entorno virtual
```bash
python -m venv venv
source venv/Scripts/activate  # Windows
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno
```bash
cp .env.example .env
```

Edita `.env` con:
- `DB_USER`: Usuario de PostgreSQL
- `DB_PASSWORD`: Contraseña de PostgreSQL
- `DB_HOST`: Host de PostgreSQL (localhost por defecto)
- `DB_PORT`: Puerto de PostgreSQL (5432 por defecto)
- `DB_NAME`: Nombre de la base de datos
- `GEMINI_API_KEY`: Tu API key de Google Gemini

### 5. Inicializar Base de Datos
```bash
python scripts/init_local.py
```

Esto creará las tablas en PostgreSQL.

## 📊 Ejecutar Dashboard

```bash
streamlit run dashboard/app.py
```

El dashboard se abrirá en `http://localhost:8501`

## �️ Estructura de Base de Datos

### Tablas Principales

#### `estudiantes`
Almacena información de los estudiantes
- `id` (STRING, PK): Matrícula
- `nombre` (STRING): Nombre completo
- `plan_estudios` (STRING): Plan de estudios (ej: 2021ID)
- `situacion` (STRING): Situación académica (Regular, etc)
- `total_creditos` (INTEGER): Total de créditos cursados
- `promedio_general` (FLOAT): Promedio académico
- `fecha_carga` (TIMESTAMP): Fecha de registro

#### `materias`
Catálogo de materias disponibles
- `clave` (STRING, PK): Código de materia (ej: ID0101)
- `nombre` (STRING): Nombre de la materia
- `creditos` (INTEGER): Créditos de la materia
- `ciclo` (INTEGER): Ciclo/Semestre (1-4)
- `categoria` (STRING): Categoría (BASICA, ELECCIÓN LIBRE, PRE-ESPECIALIDAD)

#### `historial_academico`
Registro de calificaciones y estatus de cada estudiante
- `id` (INTEGER, PK): Identificador único
- `estudiante_id` (STRING, FK): Referencia a estudiante
- `materia_clave` (STRING): Clave de la materia
- `periodo` (STRING): Período (YYYYMM)
- `calificacion` (FLOAT): Calificación obtenida
- `creditos_obtenidos` (INTEGER): Créditos ganados
- `estatus` (STRING): APROBADA, REPROBADA, EN_CURSO, SIN_REGISTRAR
- `fecha_registro` (TIMESTAMP): Fecha de registro

#### `alertas`
Alertas académicas generadas por el sistema
- `id` (INTEGER, PK): Identificador único
- `estudiante_id` (STRING, FK): Referencia a estudiante
- `tipo` (STRING): Tipo de alerta
- `descripcion` (TEXT): Descripción detallada
- `severidad` (STRING): CRITICA, ADVERTENCIA, INFO
- `activa` (BOOLEAN): Estado de la alerta
- `fecha_creacion` (TIMESTAMP): Fecha de creación

#### `requisitos_adicionales`
Requisitos adicionales para graduación
- `id` (INTEGER, PK): Identificador único
- `estudiante_id` (STRING, FK): Referencia a estudiante
- `requisito` (STRING): Tipo de requisito (ACTIVIDAD_DEPORTIVA, ACTIVIDAD_CULTURAL, INGLES)
- `completado` (BOOLEAN): Si fue completado
- `fecha_completado` (TIMESTAMP): Fecha de cumplimiento

## �🔄 Flujo de Trabajo

1. **Cargar PDF**: Sube kardex e historia académica
2. **Parser**: Extrae datos estructurados
3. **Procesamiento**: Valida seriación y calcula progreso
4. **Visualización**: Muestra reportes y alertas
5. **Agente**: Consulta en lenguaje natural (próximo)

## 📄 Tecnologías para Análisis de PDFs

El sistema utiliza tres bibliotecas especializadas para extraer y analizar la información de los archivos PDF:

| Biblioteca | Versión | Función |
|------------|---------|---------|
| **pdfplumber** | 0.10.3 | Extracción de texto e información estructurada (tablas, posiciones) de PDFs digitales con texto seleccionable. Es la herramienta principal usada en `KardexParser` e `HistorialParser`. |
| **pdf2image** | 1.16.0 | Convierte páginas de un PDF en imágenes (formato PIL/Pillow). Se utiliza como paso previo al OCR cuando el PDF es un documento escaneado. |
| **pytesseract** | 0.3.10 | Motor de Reconocimiento Óptico de Caracteres (OCR) que extrae texto a partir de imágenes. Se aplica sobre los PDFs escaneados convertidos con `pdf2image`. |

### Flujo de extracción

```
PDF digital (texto seleccionable)
    └──► pdfplumber → texto estructurado → parser (regex + pandas)

PDF escaneado (imagen)
    └──► pdf2image → imágenes por página → pytesseract (OCR) → texto → parser
```

> **Resumen**: Se usa **pdfplumber** como motor principal para PDFs digitales,
> y la combinación **pdf2image + pytesseract** como respaldo para PDFs escaneados.

## 📊 Componentes Implementados

- ✅ Parser de Kardex (pdfplumber)
- ✅ Modelos de base de datos (SQLAlchemy)
- ✅ Processor académico (Pandas)
- ✅ Dashboard Streamlit
- ✅ Servicio de base de datos PostgreSQL
- ⏳ Agentes LangGraph + Gemini (próximo)

## 🤖 Agentes (Próximo)

- **Agente Conversacional**: Responde en lenguaje natural
- **Agente de Optimización**: Sugiere mejores horarios
- **Agente de Alertas**: Notificaciones proactivas

## 👨‍💻 Autor

David - Proyecto de Tesis

## 📄 Licencia

MIT
