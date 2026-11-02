from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProductoVestua:
    id: str
    titulo: str
    categorias_catalogo: str
    tipo_prenda: str
    marca: str
    categoria_referencia: Optional[str]
    talla: str
    precio_clp: Optional[int]
    url: str
    fecha_consulta: str

