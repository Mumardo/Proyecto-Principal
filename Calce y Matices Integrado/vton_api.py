import base64
import binascii
import hmac
import io
import os
from pathlib import Path
from typing import Optional

import modal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


MODEL_DIRECTORY = Path("/models/fashn-vton-1.5")
HF_HOME = Path("/models/fashn-hf-home")
MODEL_REVISION = "7720683168567eb5a2a4c67f15116c6e29c83ded"
DWPOSE_REVISION = "548b5df25b84d9f4aac0611dfa1c2a7a12f15571"
MODEL_CATEGORIES = {
    "upper_body": "tops",
    "lower_body": "bottoms",
    "dresses": "one-pieces",
}

api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "pillow")
)

model_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "fastapi",
        "git+https://github.com/fashn-AI/fashn-vton-1.5.git"
        "@7c0f10af3f91ad4048fe9729c470a13ef905d25a",
        "onnxruntime-gpu[cuda,cudnn]==1.31.1",
    )
    .env(
        {
            "HF_HOME": str(HF_HOME),
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
    )
)

app = modal.App("probador-virtual-api")
model_volume = modal.Volume.from_name("vton-weights", create_if_missing=True)


class TryOnRequest(BaseModel):
    person_image_base64: str = Field(min_length=1, max_length=14_000_000)
    garment_image_base64: str = Field(min_length=1, max_length=14_000_000)
    category: str = Field(
        default="upper_body",
        pattern="^(upper_body|lower_body|dresses)$",
    )


def _decode_image(image_base64: str, field_name: str):
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(422, f"{field_name} no contiene Base64 válido.") from error

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, f"{field_name} supera el límite de 10 MB.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.width * source.height > 30_000_000:
                raise HTTPException(413, f"{field_name} supera el límite de 30 megapíxeles.")
            source.load()
            return ImageOps.exif_transpose(source).convert("RGB")
    except Image.DecompressionBombError as error:
        raise HTTPException(413, f"{field_name} supera el límite de tamaño de imagen.") from error
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise HTTPException(422, f"{field_name} no es una imagen válida.") from error


def _ensure_model_weights() -> None:
    from fashn_human_parser import FashnHumanParser
    from huggingface_hub import hf_hub_download

    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    model_weights = MODEL_DIRECTORY / "model.safetensors"
    if not model_weights.is_file():
        hf_hub_download(
            repo_id="fashn-ai/fashn-vton-1.5",
            filename="model.safetensors",
            revision=MODEL_REVISION,
            local_dir=str(MODEL_DIRECTORY),
        )

    dwpose_directory = MODEL_DIRECTORY / "dwpose"
    dwpose_directory.mkdir(parents=True, exist_ok=True)
    for filename in ("yolox_l.onnx", "dw-ll_ucoco_384.onnx"):
        if not (dwpose_directory / filename).is_file():
            hf_hub_download(
                repo_id="fashn-ai/DWPose",
                filename=filename,
                revision=DWPOSE_REVISION,
                local_dir=str(dwpose_directory),
            )

    parser_cache = HF_HOME / "hub" / "models--fashn-ai--fashn-human-parser"
    if not list(parser_cache.glob("snapshots/*/model.safetensors")):
        FashnHumanParser(device="cpu")

    model_volume.commit()


@app.function(
    image=model_image,
    volumes={"/models": model_volume},
    cpu=4,
    memory=16_384,
    timeout=1800,
    startup_timeout=600,
)
def prepare_weights():
    _ensure_model_weights()
    return {"status": "ready"}


@app.cls(
    image=model_image,
    gpu="L4",
    volumes={"/models": model_volume},
    cpu=4,
    memory=16_384,
    timeout=600,
    startup_timeout=600,
    scaledown_window=60,
    max_containers=1,
)
class VirtualTryOnModel:
    @modal.enter()
    def load_model(self):
        import onnxruntime
        from fashn_vton import TryOnPipeline

        onnxruntime.preload_dlls(directory="")
        _ensure_model_weights()
        self.pipeline = TryOnPipeline(
            weights_dir=str(MODEL_DIRECTORY),
            device="cuda",
        )

    @modal.method()
    def generate(
        self,
        person_image_base64: str,
        garment_image_base64: str,
        category: str,
    ) -> str:
        result = self.pipeline(
            person_image=_decode_image(person_image_base64, "person_image_base64"),
            garment_image=_decode_image(garment_image_base64, "garment_image_base64"),
            category=MODEL_CATEGORIES[category],
            garment_photo_type="model",
            num_timesteps=20,
            segmentation_free=True,
        )
        if not result.images:
            raise RuntimeError("FASHN VTON no generó ninguna imagen.")

        buffered = io.BytesIO()
        result.images[0].save(buffered, format="JPEG", quality=90)
        return base64.b64encode(buffered.getvalue()).decode("ascii")


model = VirtualTryOnModel()
web_app = FastAPI()


@web_app.post("/try-on")
def try_on_endpoint(
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

    _decode_image(req.person_image_base64, "person_image_base64")
    _decode_image(req.garment_image_base64, "garment_image_base64")

    output_b64 = model.generate.remote(
        req.person_image_base64,
        req.garment_image_base64,
        req.category,
    )
    return {
        "status": "success",
        "detail": "Imagen generada con FASHN VTON 1.5.",
        "result_image_base64": output_b64,
    }


@app.function(
    image=api_image,
    secrets=[modal.Secret.from_name("vton-api-auth")],
    timeout=600,
    startup_timeout=600,
)
@modal.asgi_app()
def fastapi_app():
    return web_app
