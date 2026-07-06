import os
import tempfile
from threading import Lock

import cv2
from fastapi import FastAPI, File, HTTPException, UploadFile
from paddleocr import PPStructure

from parser import parse_structure_result


USE_GPU = os.getenv("OCR_USE_GPU", "false").lower() == "true"
_engine = None
_engine_lock = Lock()

app = FastAPI(title="OCR Structure Service", description="PP-Structure OCR service")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "engine": "ppstructure",
        "engine_loaded": _engine is not None,
        "use_gpu": USE_GPU,
    }


@app.post("/warmup")
async def warmup():
    try:
        _get_engine()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OCR engine initialization failed: {exc}") from exc
    return {"status": "ready", "engine": "ppstructure", "use_gpu": USE_GPU}


@app.post("/parse/image")
async def parse_image(file: UploadFile = File(...)):
    content = await file.read()
    suffix = os.path.splitext(file.filename or "")[1] or ".png"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        image = cv2.imread(tmp_path)
        if image is None:
            raise HTTPException(status_code=400, detail="Unsupported image file")

        try:
            result = _get_engine()(image)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"OCR engine unavailable: {exc}") from exc
        text, score, blocks = parse_structure_result(result)
        return {
            "text": text,
            "ocr_confidence": score,
            "parse_method": "ppstructure",
            "blocks": blocks,
        }
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _get_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = PPStructure(
                    table=False,
                    ocr=True,
                    layout=True,
                    formula=False,
                    show_log=False,
                    image_orientation=False,
                    use_gpu=USE_GPU,
                )
    return _engine
