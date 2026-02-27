from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Estudiante(Base):
    """Modelo de Estudiante"""
    __tablename__ = "estudiantes"
    
    id = Column(String, primary_key=True)  # Matrícula
    nombre = Column(String, nullable=False)
    plan_estudios = Column(String, nullable=False)  # ej: 2021ID
    situacion = Column(String, nullable=False)  # Regular, etc
    total_creditos = Column(Integer, default=0)
    promedio_general = Column(Float, default=0.0)
    fecha_carga = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Estudiante(id={self.id}, nombre={self.nombre})>"


class Materia(Base):
    """Modelo de Materia"""
    __tablename__ = "materias"
    
    clave = Column(String, primary_key=True)  # ej: ID0101
    nombre = Column(String, nullable=False)
    creditos = Column(Integer, default=0)
    ciclo = Column(Integer, default=0)  # 1, 2, 3, 4 (0 = desconocido)
    categoria = Column(String, default="DESCONOCIDA")  # BASICA, ELECCIÓN LIBRE, PRE-ESPECIALIDAD
    
    def __repr__(self):
        return f"<Materia(clave={self.clave}, nombre={self.nombre})>"


class HistorialAcademico(Base):
    """Modelo de Historial Académico del Estudiante"""
    __tablename__ = "historial_academico"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    estudiante_id = Column(String, ForeignKey("estudiantes.id"), nullable=False)
    materia_clave = Column(String, nullable=False)  # Clave de la materia (sin FK para permitir materias no catalogadas)
    periodo = Column(String, nullable=False)  # YYYYMM
    calificacion = Column(Float, nullable=True)  # 0-10 o NULL si no cursó
    creditos_obtenidos = Column(Integer, default=0)
    estatus = Column(String, nullable=False)  # APROBADA, REPROBADA, EN_CURSO, SIN_REGISTRAR
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<HistorialAcademico(estudiante={self.estudiante_id}, materia={self.materia_clave})>"


class Alerta(Base):
    """Modelo de Alertas Académicas"""
    __tablename__ = "alertas"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    estudiante_id = Column(String, ForeignKey("estudiantes.id"), nullable=False)
    tipo = Column(String, nullable=False)  # TERCERA_OPORTUNIDAD, ALUMNO_IRREGULAR, etc
    descripcion = Column(Text, nullable=False)
    severidad = Column(String, nullable=False)  # CRITICA, ADVERTENCIA, INFO
    activa = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Alerta(estudiante={self.estudiante_id}, tipo={self.tipo})>"


class RequisitoAdicional(Base):
    """Modelo de Requisitos Adicionales"""
    __tablename__ = "requisitos_adicionales"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    estudiante_id = Column(String, ForeignKey("estudiantes.id"), nullable=False)
    requisito = Column(String, nullable=False)  # ACTIVIDAD_DEPORTIVA, ACTIVIDAD_CULTURAL, INGLES
    completado = Column(Boolean, default=False)
    fecha_completado = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<RequisitoAdicional(estudiante={self.estudiante_id}, requisito={self.requisito})>"
