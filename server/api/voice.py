"""voice.py — speech-to-text for the composer mic button.

The browser records audio -> POST /api/transcribe (multipart) -> Whisper via a provider
(config-driven) -> {text}. Provider-agnostic: the model comes from STT_MODEL, or is picked
from whichever provider key is present. No model string is hardcoded (project invariant); the
actual model call goes through core.llm.transcribe (the single call point).
"""
import os
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException

from core.llm import transcribe, Budget

router = APIRouter(prefix="/api", tags=["voice"])


def stt_model() -> str:
    """The speech-to-text model. STT_MODEL wins; otherwise the first provider whose key is
    present (Groq's free Whisper preferred for accuracy + speed)."""
    forced = os.environ.get("STT_MODEL", "").strip()
    if forced:
        return forced
    if os.environ.get("GROQ_API_KEY"):
        return "groq/whisper-large-v3"
    if os.environ.get("DEEPINFRA_API_KEY"):
        return "deepinfra/openai/whisper-large-v3"
    if os.environ.get("OPENAI_API_KEY"):
        return "whisper-1"
    return ""


@router.get("/transcribe/available")
def available():
    """So the UI can show/hide the mic button based on whether STT is configured."""
    m = stt_model()
    return {"available": bool(m), "model": m}


@router.post("/transcribe")
async def do_transcribe(file: UploadFile = File(...)):
    model = stt_model()
    if not model:
        raise HTTPException(
            status_code=400,
            detail="No speech-to-text model configured. Add GROQ_API_KEY (free Whisper) or "
                   "STT_MODEL to .env.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio")
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        text = transcribe(tmp.name, model, budget=Budget(max_usd=0.05, max_iterations=2))
        return {"text": text, "model": model}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"transcription failed ({type(e).__name__}): {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
