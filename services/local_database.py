"""
Servicio de base de datos usando PostgreSQL
Conecta a la BD local creada en pgAdmin
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, Estudiante, Materia, HistorialAcademico, Alerta, RequisitoAdicional
from typing import List, Dict, Optional
from pathlib import Path
import json
from config import settings


class DatabaseService:
    """Servicio de base de datos usando PostgreSQL"""
    
    def __init__(self):
        """Inicializa la conexión a PostgreSQL"""
        # Usar DATABASE_URL del .env
        database_url = settings.DATABASE_URL
        
        if not database_url:
            raise ValueError("DATABASE_URL no está configurada en .env")
        
        # Crear engine con encoding explícito y search_path al schema proyecto_pt
        self.engine = create_engine(
            database_url,
            echo=False,
            connect_args={
                "client_encoding": "utf8",
                "options": "-c search_path=proyecto_pt"
            }
        )
        
        # Crear todas las tablas (si no existen)
        Base.metadata.create_all(self.engine)
        
        # Crear sesión
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        """Obtiene una nueva sesión"""
        return self.Session()
    
    # ======== ESTUDIANTES ========
    def crear_estudiante(self, matricula: str, datos: Dict) -> Dict:
        """Crea o actualiza un registro de estudiante (upsert)"""
        try:
            session = self.get_session()
            estudiante = session.query(Estudiante).filter_by(id=matricula).first()
            if estudiante:
                # Actualizar datos existentes
                estudiante.nombre = datos.get("nombre", estudiante.nombre)
                estudiante.plan_estudios = datos.get("plan_estudios", estudiante.plan_estudios)
                estudiante.situacion = datos.get("situacion", estudiante.situacion)
                estudiante.total_creditos = datos.get("total_creditos", estudiante.total_creditos)
                estudiante.promedio_general = datos.get("promedio_general", estudiante.promedio_general)
            else:
                estudiante = Estudiante(
                    id=matricula,
                    nombre=datos.get("nombre"),
                    plan_estudios=datos.get("plan_estudios"),
                    situacion=datos.get("situacion"),
                    total_creditos=datos.get("total_creditos", 0),
                    promedio_general=datos.get("promedio_general", 0.0)
                )
                session.add(estudiante)
            session.commit()
            result = {"id": estudiante.id, "nombre": estudiante.nombre, "plan_estudios": estudiante.plan_estudios}
            session.close()
            return result
        except Exception as e:
            print(f"Error creando estudiante: {e}")
            session.rollback()
            session.close()
            return {}
    
    def obtener_estudiante(self, matricula: str) -> Optional[Dict]:
        """Obtiene información de un estudiante"""
        try:
            session = self.get_session()
            est = session.query(Estudiante).filter_by(id=matricula).first()
            if est:
                result = {
                    "id": est.id,
                    "nombre": est.nombre,
                    "plan_estudios": est.plan_estudios,
                    "situacion": est.situacion,
                    "total_creditos": est.total_creditos,
                    "promedio_general": est.promedio_general
                }
            else:
                result = None
            session.close()
            return result
        except Exception as e:
            print(f"Error obteniendo estudiante: {e}")
            return None
    
    # ======== MATERIAS ========
    def crear_materias(self, materias: List[Dict]) -> List[Dict]:
        """Inserta múltiples materias"""
        try:
            session = self.get_session()
            resultado = []
            for mat_data in materias:
                mat = Materia(
                    clave=mat_data.get("clave"),
                    nombre=mat_data.get("nombre"),
                    creditos=mat_data.get("creditos", 0),
                    ciclo=mat_data.get("ciclo", 0),
                    categoria=mat_data.get("categoria", "")
                )
                session.add(mat)
                resultado.append({
                    "clave": mat.clave,
                    "nombre": mat.nombre
                })
            session.commit()
            session.close()
            return resultado
        except Exception as e:
            print(f"Error creando materias: {e}")
            return []
    
    def obtener_todas_materias(self) -> List[Dict]:
        """Obtiene todas las materias"""
        try:
            session = self.get_session()
            materias = session.query(Materia).all()
            resultado = [
                {
                    "clave": m.clave,
                    "nombre": m.nombre,
                    "creditos": m.creditos,
                    "ciclo": m.ciclo,
                    "categoria": m.categoria
                }
                for m in materias
            ]
            session.close()
            return resultado
        except Exception as e:
            print(f"Error obteniendo materias: {e}")
            return []
    
    # ======== HISTORIAL ACADÉMICO ========
    def crear_registro_historial(self, matricula: str, registros: List[Dict]) -> List[Dict]:
        """Inserta registros de historial académico, reemplazando los anteriores del mismo estudiante"""
        try:
            session = self.get_session()
            # Borrar historial previo del estudiante para evitar duplicados
            session.query(HistorialAcademico).filter_by(estudiante_id=matricula).delete()
            resultado = []
            for reg in registros:
                clave = reg.get("clave")
                # Upsert de la materia en el catálogo (por si no existe)
                materia_existente = session.query(Materia).filter_by(clave=clave).first()
                if not materia_existente:
                    materia = Materia(
                        clave=clave,
                        nombre=reg.get("nombre", clave),
                        creditos=reg.get("creditos", 0),
                        ciclo=0,
                        categoria="DESCONOCIDA"
                    )
                    session.add(materia)
                
                hist = HistorialAcademico(
                    estudiante_id=matricula,
                    materia_clave=clave,
                    periodo=reg.get("periodo"),
                    calificacion=reg.get("calificacion"),
                    creditos_obtenidos=reg.get("creditos", 0) if reg.get("estatus") == "APROBADA" else 0,
                    estatus=reg.get("estatus")
                )
                session.add(hist)
                resultado.append({"clave": clave, "periodo": reg.get("periodo")})
            session.commit()
            session.close()
            return resultado
        except Exception as e:
            print(f"Error creando historial: {e}")
            session.rollback()
            session.close()
            return []
    
    def obtener_historial_estudiante(self, matricula: str) -> List[Dict]:
        """Obtiene historial académico de un estudiante"""
        try:
            session = self.get_session()
            registros = session.query(HistorialAcademico).filter_by(estudiante_id=matricula).all()
            resultado = [
                {
                    "materia_clave": r.materia_clave,
                    "periodo": r.periodo,
                    "calificacion": r.calificacion,
                    "creditos_obtenidos": r.creditos_obtenidos,
                    "estatus": r.estatus
                }
                for r in registros
            ]
            session.close()
            return resultado
        except Exception as e:
            print(f"Error obteniendo historial: {e}")
            return []
    
    # ======== ALERTAS ========
    def crear_alerta(self, matricula: str, alerta: Dict) -> Dict:
        """Crea una alerta académica"""
        try:
            session = self.get_session()
            alert = Alerta(
                estudiante_id=matricula,
                tipo=alerta.get("tipo"),
                descripcion=alerta.get("descripcion"),
                severidad=alerta.get("severidad", "INFO"),
                activa=True
            )
            session.add(alert)
            session.commit()
            result = {
                "id": alert.id,
                "tipo": alert.tipo,
                "descripcion": alert.descripcion
            }
            session.close()
            return result
        except Exception as e:
            print(f"Error creando alerta: {e}")
            return {}
    
    def obtener_alertas_estudiante(self, matricula: str) -> List[Dict]:
        """Obtiene alertas activas de un estudiante"""
        try:
            session = self.get_session()
            alertas = session.query(Alerta).filter_by(estudiante_id=matricula, activa=True).all()
            resultado = [
                {
                    "id": a.id,
                    "tipo": a.tipo,
                    "descripcion": a.descripcion,
                    "severidad": a.severidad
                }
                for a in alertas
            ]
            session.close()
            return resultado
        except Exception as e:
            print(f"Error obteniendo alertas: {e}")
            return []
    
    # ======== REQUISITOS ADICIONALES ========
    def crear_requisitos(self, matricula: str, requisitos: List[str]) -> List[Dict]:
        """Crea registros de requisitos adicionales"""
        try:
            session = self.get_session()
            resultado = []
            for req in requisitos:
                req_obj = RequisitoAdicional(
                    estudiante_id=matricula,
                    requisito=req,
                    completado=False
                )
                session.add(req_obj)
                resultado.append({"requisito": req, "completado": False})
            session.commit()
            session.close()
            return resultado
        except Exception as e:
            print(f"Error creando requisitos: {e}")
            return []
    
    def obtener_requisitos_estudiante(self, matricula: str) -> List[Dict]:
        """Obtiene requisitos adicionales de un estudiante"""
        try:
            session = self.get_session()
            reqs = session.query(RequisitoAdicional).filter_by(estudiante_id=matricula).all()
            resultado = [
                {
                    "id": r.id,
                    "requisito": r.requisito,
                    "completado": r.completado
                }
                for r in reqs
            ]
            session.close()
            return resultado
        except Exception as e:
            print(f"Error obteniendo requisitos: {e}")
            return []


# Mantener nombres legados para compatibilidad
LocalDatabaseService = DatabaseService
