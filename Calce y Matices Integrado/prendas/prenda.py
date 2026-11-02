from dataclasses import dataclass


@dataclass(frozen=True)
class Prenda:
    """Referencia de medidas y atributos de una prenda del catálogo."""

    categoria: str
    calce: str
    tela: str
    elasticidad: float
    holgura_diseno: float
    origen: str
    busto: float
    cintura: float
    cadera: float
    largo: float
    marca: str
    linea: str
    tolerancia: float
    fuente: str

    @property
    def nombre(self) -> str:
        return self.categoria
