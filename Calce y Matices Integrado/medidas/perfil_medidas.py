from dataclasses import dataclass
from math import isfinite
from typing import Dict, Optional


@dataclass(frozen=True)
class PerfilMedidas:
    """Medidas corporales en centímetros; las medidas no ingresadas son None."""

    busto: Optional[float] = None
    cintura: Optional[float] = None
    cadera: Optional[float] = None
    largo: Optional[float] = None

    @classmethod
    def desde_formulario(cls, valores: Dict[str, Optional[str]]) -> "PerfilMedidas":
        return cls(
            busto=cls._leer_valor(valores.get("bust")),
            cintura=cls._leer_valor(valores.get("waist")),
            cadera=cls._leer_valor(valores.get("hip")),
            largo=cls._leer_valor(valores.get("length")),
        )

    def como_diccionario(self) -> Dict[str, Optional[float]]:
        return {
            "busto": self.busto,
            "cintura": self.cintura,
            "cadera": self.cadera,
            "largo": self.largo,
        }

    @staticmethod
    def _leer_valor(valor: Optional[str]) -> Optional[float]:
        if valor is None or not valor.strip():
            return None
        try:
            numero = float(valor.replace(",", "."))
        except ValueError:
            return None
        return numero if isfinite(numero) and numero > 0 else None
