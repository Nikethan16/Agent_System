"""
vision.py — let an agent LOOK at an image in the workspace (C1 multimodal).

A `see_image` tool: sends a workspace image + a question to a VISION model and returns
its description, so screenshots / diagrams / charts / photos become usable input without
changing the agent loop's message format. The vision model comes from VISION_MODEL, else
a fleet multimodal model (routing task_type 'vision'). Best-effort: if the chosen model
doesn't support image input, it returns a clear error rather than crashing the run.
"""
import os
import base64
import mimetypes

from core import toolbelt
from core.tools import _safe
from core.llm import complete, Budget
from core.registry import registry


def _vision_model() -> str:
    return os.environ.get("VISION_MODEL") or registry.model_chain("tier2", task_type="vision")[0]


def see_image(path: str, question: str = "Describe this image in detail.") -> str:
    try:
        full = _safe(path)
    except Exception as e:
        return f"ERROR: {e}"
    if not os.path.isfile(full):
        return f"ERROR: no such image: {path}"
    try:
        mime = mimetypes.guess_type(full)[0] or "image/png"
        with open(full, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        model = _vision_model()
        resp, _ = complete(
            model,
            [{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}],
            max_tokens=700, budget=Budget(max_usd=0.25, max_iterations=2),
        )
        return resp.choices[0].message.content or "(no description returned)"
    except Exception as e:
        return (f"ERROR analyzing image (the selected vision model may not support image "
                f"input — set VISION_MODEL): {type(e).__name__}: {e}")


toolbelt.register_fn(
    "see_image",
    lambda path, question="Describe this image in detail.": see_image(path, question),
    {"type": "object",
     "properties": {"path": {"type": "string"}, "question": {"type": "string"}},
     "required": ["path"]},
    "Look at an image in the workspace (screenshot, diagram, chart, photo) and answer a "
    "question about it.", toolbelt.RISK_SAFE,
)
