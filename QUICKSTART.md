# 🚀 Quick Start

## Paso 1: Configuración Inicial

### 1.1 Instalar PostgreSQL
1. Descarga PostgreSQL desde https://www.postgresql.org/download/
2. Durante la instalación, anota la contraseña del usuario `postgres`
3. Crea una base de datos llamada `proyecto_ideio`:
   ```sql
   CREATE DATABASE proyecto_ideio;
   ```

### 1.2 Configurar Variables de Entorno
```bash
cp .env.example .env
```

Edita `.env` con tus credenciales de PostgreSQL:
```
DB_USER=postgres
DB_PASSWORD=tu_contraseña
DB_HOST=localhost
DB_PORT=5432
DB_NAME=proyecto_ideio
GEMINI_API_KEY=tu_api_key_gemini
```

### 1.3 Crear Ambiente Virtual e Instalar Dependencias
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Paso 2: Inicializar Base de Datos

### 2.1 Crear Tablas en PostgreSQL
```bash
python scripts/init_local.py
```

Este script:
- Crea todas las tablas automáticamente
- Carga las materias desde `data/mapa_curricular_2021ID_real.json`
- Configura las relaciones entre tablas

### 2.2 Verificar Base de Datos (Opcional)
Puedes usar pgAdmin (http://localhost:5050) para verificar las tablas:
1. Servidor: localhost, puerto 5432
2. Usuario: postgres
3. Base de datos: proyecto_ideio

## Paso 3: Ejecutar Dashboard

Asegúrate que el ambiente virtual está activado:
```bash
.\venv\Scripts\Activate.ps1
streamlit run dashboard/app.py
```

Se abrirá en `http://localhost:8501`

### Usar el Dashboard:
1. Carga un PDF de kardex
2. Haz clic en "Procesar Kardex"
3. Visualiza el reporte académico
4. Consulta alertas y requisitos adicionales

## Paso 4: Próximos Pasos

- ✅ Parser de PDFs
- ✅ Dashboard básico
- ⏳ Integración con LangGraph
- ⏳ Agente Gemini conversacional
- ⏳ Sistema de notificaciones

## 📖 Estructura Importante

```
config/settings.py              →  Configuración centralizada
parsers/kardex_parser.py        →  Extrae PDFs
services/processor.py           →  Lógica académica
services/local_database.py      →  Acceso a BD PostgreSQL
db/models.py                    →  Modelos SQLAlchemy
scripts/init_local.py           →  Inicializador de BD
dashboard/app.py                →  Interfaz Streamlit
data/mapa_curricular_*.json     →  Datos estáticos
```

## 🗄️ Tablas de Base de Datos

- **estudiantes**: Información personal y académica
- **materias**: Catálogo de materias (86 materias del plan 2021)
- **historial_academico**: Calificaciones y estatus
- **alertas**: Alertas del sistema (tercera oportunidad, irregularidad, etc)
- **requisitos_adicionales**: Requisitos para graduación

## 🆘 Troubleshooting

**Error: "connection refused"**
- Verifica que PostgreSQL está ejecutándose
- En Windows: Services → PostgreSQL → Asegúrate que está "Running"

**Error: "Database proyecto_ideio does not exist"**
- Crea la base de datos:
  ```sql
  CREATE DATABASE proyecto_ideio;
  ```

**Error: "PDF parsing failed"**
- Verifica que el PDF es un Kardex válido
- Intenta con otro PDF

**Error: "Table estudiantes does not exist"**
- Ejecuta: `python scripts/init_local.py`
- Verifica credenciales en `.env`

## 💡 Tips

- Usa `python ejemplo_uso.py` para ver ejemplos de código
- Revisa los logs en la terminal de Streamlit
- El parser detecta automáticamente el formato

## 📞 Soporte

- Universidad del Caribe
- Proyecto: Sistema Experto IDeIO
