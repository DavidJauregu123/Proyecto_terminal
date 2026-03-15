"""
Sistema Experto de Seriación Curricular (NATIVO)
Plan 2021 - IDeIO (Ingeniería en Datos e Inteligencia Organizacional)

Implementación nativa de sistema experto (sin dependencias externas)
para seriación adaptativa basada en progreso académico.
"""

import json
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# TIPOS Y ENUMERACIONES
# ============================================================================

class TipoAlerta(Enum):
    """Tipos de alertas que puede generar el sistema"""
    BLOQUEO = "BLOQUEO"           # Prerequisito no cumplido
    LIGADURA = "LIGADURA"         # Materia bloqueada por ligadura
    REZAGO = "REZAGO"             # Materia rezagada (de ciclo anterior)


@dataclass
class Materia:
    """Representación de una materia del currículo"""
    clave: str
    nombre: str
    ciclo: int
    categoria: str
    creditos: int
    requisitos: List[str] = None
    
    def __post_init__(self):
        if self.requisitos is None:
            self.requisitos = []


@dataclass
class EstudianteInfo:
    """Información del estudiante"""
    id: str
    nombre: str
    promedio: float = 0.0
    total_creditos: int = 0


@dataclass
class MateriaAprobada:
    """Registro de materia aprobada"""
    clave: str
    calificacion: float
    creditos_obtenidos: int


@dataclass
class Alerta:
    """Alerta académica generada"""
    tipo: TipoAlerta
    materia: Optional[str] = None
    descripcion: str = ""


# ============================================================================
# MOTOR DE INFERENCIA NATIVO
# ============================================================================

class SistemaExpertoSeriacion:
    """
    Motor de inferencia nativo para cálculo de seriación.
    
    Algoritmo:
    1. Detectar ciclo actual (>=75% de créditos completados)
    2. Generar candidatas temporales (materias del ciclo actual + rezagadas)
    3. Filtrar por requisitos (solo si todos los prerequisitos aprobados)
    4. Aplicar regla de ligaduras (eliminar dependientes si ambas candidatas)
    """
    
    def __init__(self, mapa_curricular: Dict[str, dict]):
        """
        Inicializa el sistema con el mapa curricular.
        
        Args:
            mapa_curricular: {clave: {nombre, ciclo, categoria, creditos, requisitos}}
        """
        self.mapa_curricular = {
            clave: Materia(
                clave=clave,
                nombre=datos.get("nombre", ""),
                ciclo=datos.get("ciclo", 1),
                categoria=datos.get("categoria", ""),
                creditos=datos.get("creditos", 0),
                requisitos=datos.get("requisitos", [])
            )
            for clave, datos in mapa_curricular.items()
        }
        
        self.diagrama_ligaduras = self._construir_ligaduras()
        self.alertas = []

        # Cadena de Inglés ordenada (para diagnóstico de nivel)
        self.cadena_ingles = ["ID0107", "ID0207", "ID0307", "ID0406", "ID0507", "ID0606"]
    
    def _construir_ligaduras(self) -> Dict[str, str]:
        """
        Construye diagrama de ligaduras: {materia_dependiente: materia_requisito}
        
        Ligadura: si una materia tiene un único prerequisito obligatorio directo
        y ambas son candidatas, la dependiente se elimina (regla del profesor).
        """
        ligaduras = {}
        
        for clave, materia in self.mapa_curricular.items():
            # Una materia tiene ligadura si tiene exactamente 1 prerequisito
            # y están en ciclos consecutivos o mismo ciclo
            if len(materia.requisitos) == 1:
                req = materia.requisitos[0]
                if req in self.mapa_curricular:
                    ciclo_req = self.mapa_curricular[req].ciclo
                    ciclo_mat = materia.ciclo
                    
                    # Ligadura si ciclos son consecutivos o mismos
                    if 0 <= ciclo_mat - ciclo_req <= 1:
                        ligaduras[clave] = req
        
        return ligaduras
    
    def detectar_ciclo_actual(
        self,
        historial: List[MateriaAprobada]
    ) -> int:
        """
        Detecta el ciclo actual basándose en créditos completados por ciclo.
        
        Un ciclo se considera "completado" cuando tiene >=75% de sus créditos.
        """
        # Agrupar creditos por ciclo
        creditos_aprobados = {}
        creditos_totales = {}
        
        for materia in self.mapa_curricular.values():
            ciclo = materia.ciclo
            
            if ciclo not in creditos_totales:
                creditos_totales[ciclo] = 0
                creditos_aprobados[ciclo] = 0
            
            creditos_totales[ciclo] += materia.creditos
            
            # Buscar en historial si está aprobada
            for h in historial:
                if h.clave == materia.clave:
                    creditos_aprobados[ciclo] += h.creditos_obtenidos
                    break
        
        # Encontrar primer ciclo no completado
        ciclo_actual = 1
        for ciclo in sorted(creditos_totales.keys()):
            porcentaje = (creditos_aprobados[ciclo] / creditos_totales[ciclo] * 100)
            
            print(f"[CICLO {ciclo}] {porcentaje:.1f}% "
                  f"({creditos_aprobados[ciclo]}/{creditos_totales[ciclo]} creditos)")
            
            if porcentaje >= 75:
                ciclo_actual = ciclo + 1
            else:
                break
        
        return ciclo_actual
    
    def generar_candidatas_temporales(
        self,
        ciclo_actual: int,
        historial: List[MateriaAprobada]
    ) -> List[str]:
        """
        Genera lista de materias candidatas (no cursadas) del ciclo actual
        y ciclos anteriores (rezagadas).
        """
        materias_aprobadas = {h.clave for h in historial}
        candidatas = []
        
        for clave, materia in self.mapa_curricular.items():
            # Candidata si: (1) no aprobada, (2) del ciclo actual o anterior
            if clave not in materias_aprobadas and materia.ciclo <= ciclo_actual:
                candidatas.append(clave)
        
        print(f"[CANDIDATAS] {len(candidatas)} materias")
        
        return candidatas
    
    def filtrar_por_requisitos(
        self,
        candidatas: List[str],
        historial: List[MateriaAprobada]
    ) -> List[str]:
        """
        Filtra candidatas verificando que todos los requisitos estén aprobados.
        """
        materias_aprobadas = {h.clave for h in historial}
        candidatas_validas = []
        
        for clave in candidatas:
            materia = self.mapa_curricular[clave]
            tiene_requisitos = True
            
            for requisito in materia.requisitos:
                if requisito not in materias_aprobadas:
                    tiene_requisitos = False
                    
                    self.alertas.append(Alerta(
                        tipo=TipoAlerta.BLOQUEO,
                        materia=clave,
                        descripcion=f"Requiere {requisito}"
                    ))
                    break
            
            if tiene_requisitos:
                candidatas_validas.append(clave)
        
        print(f"[VALIDAS] {len(candidatas_validas)} materias (despues requisitos)")
        
        return candidatas_validas
    
    def aplicar_regla_ligaduras(
        self,
        candidatas: List[str]
    ) -> List[str]:
        """
        Aplicaregla de ligaduras:
        Si ambas materias (requisito y dependiente) son candidatas,
        elimina la dependiente hasta que se complete la requisito.
        """
        candidatas_set = set(candidatas)
        materias_eliminar = set()
        
        for materia_dep, materia_req in self.diagrama_ligaduras.items():
            # Si ambas son candidatas, eliminar la dependiente
            if materia_dep in candidatas_set and materia_req in candidatas_set:
                materias_eliminar.add(materia_dep)
                
                self.alertas.append(Alerta(
                    tipo=TipoAlerta.LIGADURA,
                    materia=materia_dep,
                    descripcion=f"Suspendida hasta completar {materia_req}"
                ))
        
        if materias_eliminar:
            print(f"[LIGADURAS] Eliminadas {len(materias_eliminar)} materias")
            candidatas = [c for c in candidatas if c not in materias_eliminar]
        
        return candidatas

    def filtrar_por_oferta_academica(
        self,
        candidatas: List[str],
        oferta_claves: Optional[Set[str]]
    ) -> List[str]:
        """
        Filtra candidatas por oferta académica del periodo vigente.
        Si no se proporciona oferta, no aplica filtro.
        """
        if not oferta_claves:
            return candidatas

        candidatas_filtradas = [c for c in candidatas if c in oferta_claves]
        print(
            f"[OFERTA] {len(candidatas_filtradas)} materias "
            f"(de {len(candidatas)} candidatas)"
        )
        return candidatas_filtradas
    
    def _resolver_nivel_ingles(self, historial: List[MateriaAprobada]) -> List[MateriaAprobada]:
        """
        Regla especial: alumnos que ingresan con nivel de inglés avanzado
        por examen diagnóstico. Si el historial contiene un nivel de inglés
        sin tener los niveles previos, se completan automáticamente los
        niveles anteriores como si estuvieran acreditados (créditos 0,
        calificación 10 — acreditado por diagnóstico).
        """
        claves_aprobadas = {h.clave for h in historial}
        historial_extra = list(historial)

        # Encontrar el nivel más alto de inglés registrado en el historial
        nivel_maximo = -1
        for i, clave in enumerate(self.cadena_ingles):
            if clave in claves_aprobadas:
                nivel_maximo = i

        if nivel_maximo <= 0:
            return historial  # Sin nivel avanzado, no hay nada que resolver

        # Agregar virtualmente todos los niveles previos no registrados
        for i in range(nivel_maximo):
            clave_previa = self.cadena_ingles[i]
            if clave_previa not in claves_aprobadas:
                materia = self.mapa_curricular.get(clave_previa)
                creditos = materia.creditos if materia else 0
                historial_extra.append(MateriaAprobada(
                    clave=clave_previa,
                    calificacion=10.0,  # Acreditado por diagnóstico
                    creditos_obtenidos=creditos
                ))
                print(f"[INGLÉS] {clave_previa} agregado virtualmente por examen diagnóstico")

        return historial_extra

    def ejecutar(
        self,
        historial: List[MateriaAprobada],
        materias_en_curso: Optional[List[str]] = None,
        oferta_claves: Optional[Set[str]] = None
    ) -> Dict:
        """
        Ejecuta el sistema completo y retorna materias recomendadas.
        
        Returns:
            {
                "ciclo_actual": int,
                "ciclo_recomendado": int,
                "materias_recomendadas": [...],
                "alertas": [...],
                "diagrama_ligaduras": {...}
            }
        """
        self.alertas = []

        # Regla especial: nivel de inglés por examen diagnóstico
        historial = self._resolver_nivel_ingles(historial)

        # PASO 1: Detectar ciclo actual
        ciclo_actual = self.detectar_ciclo_actual(historial)
        ciclo_recomendado = ciclo_actual
        
        print(f"[INFO] Ciclo actual: {ciclo_actual}")
        
        # PASO 2: Generar candidatas temporales
        candidatas = self.generar_candidatas_temporales(ciclo_actual, historial)
        
        # PASO 3: Filtrar por requisitos
        candidatas = self.filtrar_por_requisitos(candidatas, historial)
        
        # PASO 4: Aplicar regla de ligaduras
        candidatas = self.aplicar_regla_ligaduras(candidatas)

        # PASO 5: Filtrar por oferta académica (si existe)
        candidatas = self.filtrar_por_oferta_academica(candidatas, oferta_claves)

        # PASO 6: Excluir materias actualmente en curso
        if materias_en_curso:
            en_curso_set = set(materias_en_curso)
            candidatas = [c for c in candidatas if c not in en_curso_set]
            print(f"[EN_CURSO] Excluidas materias en curso; quedan {len(candidatas)}")
        
        # PASO 7: Generar detalles de materias recomendadas
        materias_recomendadas = []
        for clave in candidatas:
            materia = self.mapa_curricular[clave]
            materias_recomendadas.append({
                "clave": materia.clave,
                "nombre": materia.nombre,
                "ciclo": materia.ciclo,
                "categoria": materia.categoria,
                "creditos": materia.creditos
            })
        
        print(f"[RECOMENDACIONES] {len(materias_recomendadas)} materias\n")
        
        # Retornar resultado
        return {
            "ciclo_actual": ciclo_actual,
            "ciclo_recomendado": ciclo_recomendado,
            "materias_recomendadas": materias_recomendadas,
            "total_materias_recomendadas": len(materias_recomendadas),
            "alertas": [
                {
                    "tipo": a.tipo.value,
                    "materia": a.materia,
                    "descripcion": a.descripcion
                }
                for a in self.alertas
            ],
            "diagrama_ligaduras": self.diagrama_ligaduras
        }


# ============================================================================
# FUNCIONES PÚBLICAS
# ============================================================================

def cargar_mapa_curricular(ruta_json: str) -> Dict:
    """Carga el mapa curricular desde JSON"""
    with open(ruta_json, 'r', encoding='utf-8') as f:
        return json.load(f)


def cargar_oferta_academica_vigente(
    ruta_oferta: Path,
    plan_estudios: str = "2021ID",
    periodo_objetivo: Optional[str] = None
) -> Tuple[Set[str], Optional[str]]:
    """
    Carga las claves ofertadas del periodo más reciente (o uno específico)
    para un plan de estudios.
    """
    if not ruta_oferta.exists() or not ruta_oferta.is_dir():
        return set(), None

    archivos = sorted(list(ruta_oferta.glob("*.xls")) + list(ruta_oferta.glob("*.xlsx")))
    if not archivos:
        return set(), None

    try:
        import pandas as pd
    except Exception:
        return set(), None

    bloques = []
    for archivo in archivos:
        try:
            # Los IRSecciones usan encabezado en la fila 2
            df = pd.read_excel(archivo, header=1)
            columnas = {str(c).strip() for c in df.columns}
            if not {"Plan Estudio", "Clave", "Periodo"}.issubset(columnas):
                continue

            sub = df[df["Plan Estudio"].astype(str).str.strip().eq(plan_estudios)].copy()
            if sub.empty:
                continue

            sub = sub[["Periodo", "Clave"]].dropna(subset=["Periodo", "Clave"])
            bloques.append(sub)
        except Exception:
            continue

    if not bloques:
        return set(), None

    oferta = pd.concat(bloques, ignore_index=True)
    oferta["Periodo"] = oferta["Periodo"].astype(str).str.strip()
    oferta["Clave"] = oferta["Clave"].astype(str).str.strip()

    if periodo_objetivo is None:
        periodos = sorted(p for p in oferta["Periodo"].unique().tolist() if p.isdigit())
        if not periodos:
            return set(), None
        periodo_objetivo = periodos[-1]

    oferta_periodo = oferta[oferta["Periodo"] == str(periodo_objetivo)]
    claves = set(oferta_periodo["Clave"].unique().tolist())
    return claves, str(periodo_objetivo)


def nombre_temporada_periodo(periodo: Optional[str]) -> Optional[str]:
    """Convierte el sufijo de periodo (PP) a nombre de temporada."""
    if not periodo:
        return None
    sufijo = str(periodo).strip()[-2:]
    temporadas = {
        "01": "Primavera",
        "02": "Verano",
        "03": "Otoño",
        "04": "Invierno",
    }
    return temporadas.get(sufijo)


def ejecutar_sistema_experto(
    datos_estudiante: Dict,
    historial_academico: List[Dict],
    materias_en_curso: Optional[List[str]] = None,
    usar_oferta_academica: bool = True,
    periodo_oferta: Optional[str] = None,
    plan_estudios: str = "2021ID"
) -> Dict:
    """
    Ejecuta el sistema experto para un estudiante.
    
    Args:
        datos_estudiante: {id, nombre, promedio, total_creditos}
        historial_academico: [{clave_materia, calificacion, creditos_obtenidos}, ...]
        materias_en_curso: [clave_materia, ...]
    
    Returns:
        {
            ciclo_actual,
            ciclo_recomendado,
            materias_recomendadas: [{clave, nombre, ciclo, categoria, creditos}, ...],
            alertas: [{tipo, materia, descripcion}, ...],
            total_materias_recomendadas,
            diagrama_ligaduras
        }
    """
    # Cargar mapa curricular
    ruta_proyecto = Path(__file__).parent.parent
    ruta_mapa = ruta_proyecto / "data" / "mapa_curricular_2021ID_real_completo.json"
    
    if not ruta_mapa.exists():
        raise FileNotFoundError(f"Mapa curricular no encontrado en {ruta_mapa}")
    
    mapa_curricular = cargar_mapa_curricular(str(ruta_mapa))
    
    # Crear motor experto
    motor = SistemaExpertoSeriacion(mapa_curricular)

    # Cargar oferta académica vigente (opcional)
    oferta_claves = set()
    periodo_oferta_utilizado = None
    if usar_oferta_academica:
        ruta_oferta = ruta_proyecto / "agents" / "OfertaAcademica"
        oferta_claves, periodo_oferta_utilizado = cargar_oferta_academica_vigente(
            ruta_oferta=ruta_oferta,
            plan_estudios=plan_estudios,
            periodo_objetivo=periodo_oferta
        )
        if periodo_oferta_utilizado:
            print(
                f"[OFERTA] Periodo {periodo_oferta_utilizado}: "
                f"{len(oferta_claves)} materias ofertadas"
            )
    
    # Convertir historial a objetos
    historial = [
        MateriaAprobada(
            clave=h["clave_materia"],
            calificacion=h.get("calificacion", 0.0),
            creditos_obtenidos=h.get("creditos_obtenidos", 0)
        )
        for h in historial_academico
    ]
    
    # Ejecutar sistema
    resultado = motor.ejecutar(
        historial,
        materias_en_curso=materias_en_curso or [],
        oferta_claves=oferta_claves
    )

    resultado["periodo_oferta"] = periodo_oferta_utilizado
    resultado["temporada_oferta"] = nombre_temporada_periodo(periodo_oferta_utilizado)
    resultado["total_materias_ofertadas"] = len(oferta_claves)
    
    return resultado


if __name__ == "__main__":
    # Ejemplo de uso
    print("=" * 70)
    print("SISTEMA EXPERTO DE SERIACIÓN CURRICULAR - PLAN 2021 IDeIO")
    print("=" * 70)
    
    # Estudiante de prueba
    datos_est = {
        "id": "EST001",
        "nombre": "Juan Pérez",
        "promedio": 8.5,
        "total_creditos": 0
    }
    
    # Historial académico de prueba (ciclo 1 completado)
    historial = [
        {"clave_materia": "ID0001", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0101", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0102", "calificacion": 9.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0104", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0105", "calificacion": 7.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0106", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0107", "calificacion": 8.5, "creditos_obtenidos": 3},
    ]
    
    # Ejecutar
    resultado = ejecutar_sistema_experto(datos_est, historial)
    
    print("\n" + "=" * 70)
    print(f"CICLO RECOMENDADO: {resultado['ciclo_recomendado']}")
    print(f"MATERIAS RECOMENDADAS: {resultado['total_materias_recomendadas']}")
    print("=" * 70)
    
    for mat in resultado["materias_recomendadas"][:5]:
        print(f"  {mat['clave']} - {mat['nombre']}")
        print(f"    Ciclo: {mat['ciclo']} | Créditos: {mat['creditos']} | Categoría: {mat['categoria']}")
    
    if resultado["alertas"]:
        print("\n⚠️  ALERTAS:")
        for alerta in resultado["alertas"]:
            print(f"  [{alerta['tipo']}] {alerta['descripcion']}")
