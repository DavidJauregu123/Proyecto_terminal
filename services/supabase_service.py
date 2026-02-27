from supabase import create_client
from config import settings
from typing import List, Dict, Optional
import json


class SupabaseService:
    """Servicio para interactuar con Supabase"""
    
    def __init__(self):
        """Inicializa la conexión con Supabase"""
        self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    
    # ======== ESTUDIANTES ========
    def crear_estudiante(self, matricula: str, datos: Dict) -> Dict:
        """Crea un nuevo registro de estudiante"""
        try:
            response = self.client.table("estudiantes").insert(
                {
                    "id": matricula,
                    "nombre": datos.get("nombre"),
                    "plan_estudios": datos.get("plan_estudios"),
                    "situacion": datos.get("situacion"),
                    "total_creditos": datos.get("total_creditos", 0),
                    "promedio_general": datos.get("promedio_general", 0.0)
                }
            ).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"Error creando estudiante: {e}")
            return {}
    
    def obtener_estudiante(self, matricula: str) -> Optional[Dict]:
        """Obtiene información de un estudiante"""
        try:
            response = self.client.table("estudiantes").select("*").eq("id", matricula).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error obteniendo estudiante: {e}")
            return None
    
    def actualizar_estudiante(self, matricula: str, datos: Dict) -> Dict:
        """Actualiza información de un estudiante"""
        try:
            response = self.client.table("estudiantes").update(datos).eq("id", matricula).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"Error actualizando estudiante: {e}")
            return {}
    
    # ======== MATERIAS ========
    def crear_materias(self, materias: List[Dict]) -> List[Dict]:
        """Inserta múltiples materias"""
        try:
            response = self.client.table("materias").insert(materias).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error creando materias: {e}")
            return []
    
    def obtener_materia(self, clave: str) -> Optional[Dict]:
        """Obtiene información de una materia"""
        try:
            response = self.client.table("materias").select("*").eq("clave", clave).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error obteniendo materia: {e}")
            return None
    
    def obtener_todas_materias(self) -> List[Dict]:
        """Obtiene todas las materias"""
        try:
            response = self.client.table("materias").select("*").execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error obteniendo materias: {e}")
            return []
    
    # ======== HISTORIAL ACADÉMICO ========
    def crear_registro_historial(self, matricula: str, registros: List[Dict]) -> List[Dict]:
        """Inserta registros de historial académico"""
        try:
            datos_para_insertar = []
            for reg in registros:
                datos_para_insertar.append({
                    "estudiante_id": matricula,
                    "materia_clave": reg.get("clave"),
                    "periodo": reg.get("periodo"),
                    "calificacion": reg.get("calificacion"),
                    "creditos_obtenidos": reg.get("creditos", 0) if reg.get("estatus") == "APROBADA" else 0,
                    "estatus": reg.get("estatus")
                })
            
            response = self.client.table("historial_academico").insert(datos_para_insertar).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error creando historial: {e}")
            return []
    
    def obtener_historial_estudiante(self, matricula: str) -> List[Dict]:
        """Obtiene historial académico de un estudiante"""
        try:
            response = self.client.table("historial_academico").select("*").eq("estudiante_id", matricula).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error obteniendo historial: {e}")
            return []
    
    # ======== ALERTAS ========
    def crear_alerta(self, matricula: str, alerta: Dict) -> Dict:
        """Crea una alerta académica"""
        try:
            response = self.client.table("alertas").insert(
                {
                    "estudiante_id": matricula,
                    "tipo": alerta.get("tipo"),
                    "descripcion": alerta.get("descripcion"),
                    "severidad": alerta.get("severidad", "INFO"),
                    "activa": True
                }
            ).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"Error creando alerta: {e}")
            return {}
    
    def obtener_alertas_estudiante(self, matricula: str) -> List[Dict]:
        """Obtiene alertas activas de un estudiante"""
        try:
            response = self.client.table("alertas").select("*").eq("estudiante_id", matricula).eq("activa", True).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error obteniendo alertas: {e}")
            return []
    
    # ======== REQUISITOS ADICIONALES ========
    def crear_requisitos(self, matricula: str, requisitos: List[str]) -> List[Dict]:
        """Crea registros de requisitos adicionales"""
        try:
            datos = [
                {
                    "estudiante_id": matricula,
                    "requisito": req,
                    "completado": False
                }
                for req in requisitos
            ]
            response = self.client.table("requisitos_adicionales").insert(datos).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error creando requisitos: {e}")
            return []
    
    def obtener_requisitos_estudiante(self, matricula: str) -> List[Dict]:
        """Obtiene requisitos adicionales de un estudiante"""
        try:
            response = self.client.table("requisitos_adicionales").select("*").eq("estudiante_id", matricula).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error obteniendo requisitos: {e}")
            return []
    
    def actualizar_requisito(self, requisito_id: int, completado: bool) -> Dict:
        """Marca un requisito como completado"""
        try:
            response = self.client.table("requisitos_adicionales").update(
                {"completado": completado}
            ).eq("id", requisito_id).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"Error actualizando requisito: {e}")
            return {}
