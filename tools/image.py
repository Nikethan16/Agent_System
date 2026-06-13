"""
image.py — generate_image tool (provider-backed; lives outside core).

Calls core.llm.generate_image (the single provider call point, budget-capped), then
saves the result into the current session workspace as an artifact. The image MODEL
is read from config/models.yaml (`image_model:`), never hardcoded. Until a provider
key + model are configured it returns a clear PLACEHOLDER instead of failing.
"""
import os
import base64
import urllib.request

from core import toolbelt
from core.tools import current_workspace
from core.registry import registry
from core.llm import generate_image as _gen, Budget, current_budget


def _image_model():
    # config-driven; falls back to a common default name if unset.
    return registry.cfg.get("image_model") or os.environ.get("IMAGE_MODEL")


def generate_image(prompt: str, filename: str = "image.png") -> str:
    model = _image_model()
    if not model:
        return (
            "PLACEHOLDER: image generation needs an image model + provider key. Set "
            "`image_model:` in config/models.yaml (e.g. a DALL·E/Imagen/SD model "
            "string) and the provider key in .env, then retry."
        )
    try:
        # Image generation can be a PAID call — charge the run's budget (+ daily cap)
        # instead of running uncapped. A child bounds this single generation.
        parent = current_budget()
        b = parent.child(max_usd=0.50) if parent else Budget(max_usd=0.50)
        resp, _cost = _gen(prompt, model, budget=b)
        item = resp.data[0]
        out = os.path.join(current_workspace(), filename)
        if getattr(item, "b64_json", None):
            with open(out, "wb") as f:
                f.write(base64.b64decode(item.b64_json))
        elif getattr(item, "url", None):
            urllib.request.urlretrieve(item.url, out)
        else:
            return f"ERROR: image provider returned no url/b64 ({item!r})"
        return f"Saved generated image to {filename}"
    except Exception as e:
        return f"ERROR generating image: {type(e).__name__}: {e}"


toolbelt.register_fn(
    "generate_image", generate_image,
    {"type": "object",
     "properties": {"prompt": {"type": "string"}, "filename": {"type": "string"}},
     "required": ["prompt"]},
    "Generate an image from a text prompt and save it to the workspace.",
    toolbelt.RISK_WRITE,
)
