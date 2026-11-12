import base64
import binascii
import hmac
import io
import os
from typing import Optional

import modal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "pillow")
)

app = modal.App("probador-virtual-api", image=image)


class TryOnRequest(BaseModel):
    person_image_base64: str = Field(min_length=1, max_length=14_000_000)
    garment_image_base64: str = Field(min_length=1, max_length=14_000_000)
    category: str = Field(
        default="upper_body",
        pattern="^(upper_body|lower_body|dresses)$",
    )


def _decode_image(image_base64: str, field_name: str):
    from PIL import Image, UnidentifiedImageError

    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(422, f"{field_name} no contiene Base64 válido.") from error

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, f"{field_name} supera el límite de 10 MB.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            source.load()
            return source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise HTTPException(422, f"{field_name} no es una imagen válida.") from error


web_app = FastAPI()


@web_app.post("/try-on")
async def try_on_endpoint(
    req: TryOnRequest,
    authorization: Optional[str] = Header(default=None),
):
    expected_token = os.environ.get("VTON_API_TOKEN")
    supplied_token = (
        authorization.removeprefix("Bearer ").strip()
        if authorization and authorization.startswith("Bearer ")
        else ""
    )
    if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
        raise HTTPException(401, "Se requiere un token Bearer válido.")

    person_image = _decode_image(req.person_image_base64, "person_image_base64")
    _decode_image(req.garment_image_base64, "garment_image_base64")

    buffered = io.BytesIO()
    person_image.save(buffered, format="JPEG", quality=90)
    return {
        "status": "simulation",
        "detail": "La inferencia VTON aún no está integrada; se devuelve la foto original.",
        "result_image_base64": base64.b64encode(buffered.getvalue()).decode("utf-8"),
    }


@app.function(secrets=[modal.Secret.from_name("vton-api-auth")])
@modal.asgi_app()
def fastapi_app():
    return web_app