import html
import os
import re
import tempfile

import requests

'''
paddleocr：解析图片中的文字，也可以进行表格识别
rapidocr_paddle 和 rapidocr_onnxruntime 两种导入方式
主要区别在于它们所使用的推理引擎和硬件支持
选择哪种方式最合适取决于你的硬件环境和性能需求。
当你有 GPU 且追求速度时：使用 rapidocr_paddle。PaddlePaddle 原生支持在 GPU 上推理 PaddleOCR 模型，速度更快。
当只有 CPU 且需要高效推理时：使用 rapidocr_onnxruntime。它在 CPU 上进行了优化，资源占用较低。
'''


def get_rapid_ocr(use_cuda: bool = True):
    try:
        from rapidocr_paddle import RapidOCR
        return RapidOCR(det_use_cuda=use_cuda, cls_use_cuda=use_cuda, rec_use_cuda=use_cuda)
    except ImportError:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()


def get_pp_structure(use_cuda: bool = True):
    from paddleocr import PPStructure
    return PPStructure(
        table=False,
        ocr=True,
        layout=True,
        formula=False,
        show_log=False,
        image_orientation=False,
        use_gpu=use_cuda,
    )


def get_ocr(use_cuda: bool = True, backend: str = "rapidocr"):
    if backend == "ppstructure":
        try:
            return get_pp_structure(use_cuda=use_cuda)
        except ImportError:
            return get_rapid_ocr(use_cuda=use_cuda)
    return get_rapid_ocr(use_cuda=use_cuda)


def parse_with_ocr_service(image_path: str):
    service_url = os.getenv("OCR_SERVICE_URL")
    if not service_url:
        return None

    try:
        with open(image_path, "rb") as file:
            response = requests.post(
                f"{service_url.rstrip('/')}/parse/image",
                files={"file": (os.path.basename(image_path), file)},
                timeout=120,
            )
        response.raise_for_status()
        return response.json()
    except (OSError, requests.RequestException):
        return None


def parse_array_with_ocr_service(image):
    service_url = os.getenv("OCR_SERVICE_URL")
    if not service_url:
        return None

    import cv2

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp_path = tmp.name

    try:
        cv2.imwrite(tmp_path, image)
        return parse_with_ocr_service(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def extract_text_and_score(result):
    texts, scores = _collect_text_and_scores(result)
    text = "\n".join(texts)
    if not scores:
        return text, None
    return text, sum(scores) / len(scores)


def _collect_text_and_scores(result):
    texts = []
    scores = []
    if not result:
        return texts, scores

    if isinstance(result, list) and result and isinstance(result[0], dict):
        for block in sorted(result, key=_structure_sort_key):
            block_texts, block_scores = _extract_structure_block(block)
            texts.extend(block_texts)
            scores.extend(block_scores)
        return texts, scores

    for line in result:
        if not isinstance(line, (list, tuple)) or len(line) < 2:
            continue
        text = _clean_text(line[1])
        if text:
            texts.append(text)
        if len(line) > 2 and isinstance(line[2], (int, float)):
            scores.append(float(line[2]))
    return texts, scores


def _extract_structure_block(block):
    res = block.get("res")
    if isinstance(res, dict):
        rec_res = res.get("rec_res") or []
        if rec_res:
            return _extract_recognition_items(rec_res)
        html_text = _html_to_text(res.get("html", ""))
        if html_text:
            return [html_text], []
        return [], []

    if isinstance(res, tuple) and len(res) >= 2:
        return _extract_recognition_items(res[1])

    if isinstance(res, list):
        return _extract_recognition_items(res)

    return [], []


def _extract_recognition_items(items):
    texts = []
    scores = []
    for item in items:
        if isinstance(item, dict):
            text = _clean_text(item.get("text"))
            if text:
                texts.append(text)
            confidence = item.get("confidence")
            if isinstance(confidence, (int, float)):
                scores.append(float(confidence))
            continue

        if not isinstance(item, (list, tuple)) or not item:
            continue
        text = _clean_text(item[0])
        if text:
            texts.append(text)
        if len(item) > 1 and isinstance(item[1], (int, float)):
            scores.append(float(item[1]))
    return texts, scores


def _structure_sort_key(block):
    bbox = block.get("bbox") or [0, 0, 0, 0]
    if len(bbox) < 2:
        return 0, 0
    return bbox[1], bbox[0]


def _html_to_text(content):
    if not content:
        return ""
    text = re.sub(r"<[^>]+>", " ", content)
    text = html.unescape(text)
    return _clean_text(text)


def _clean_text(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip()
