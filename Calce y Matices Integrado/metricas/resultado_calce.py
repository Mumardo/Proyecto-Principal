from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class MedidaComparada:
    nombre: str
    prenda: float
    cuerpo: Optional[float]
    holgura: Optional[float]


@dataclass(frozen=True)
class DiagnosticoCalce:
    etiqueta: str
    clase_css: str


@dataclass(frozen=True)
class ResultadoCalce:
    """Resultado calculado, listo para presentar en la interfaz."""

    medidas: Tuple[MedidaComparada, ...]
    puntuacion: float
    diagnostico: DiagnosticoCalce
    diferencia_largo: Optional[float]
