import html
import re


def parse_structure_result(result):
    texts = []
    scores = []
    blocks = []

    for index, block in enumerate(sorted(result or [], key=_sort_key)):
        block_text, block_scores = _extract_block(block)
        if not block_text:
            continue

        scores.extend(block_scores)
        texts.append(block_text)
        blocks.append({
            "index": index,
            "type": block.get("type"),
            "bbox": block.get("bbox"),
            "text": block_text,
            "confidence": _avg(block_scores),
        })

    return "\n".join(texts), _avg(scores), blocks


def _extract_block(block):
    res = block.get("res")
    if isinstance(res, dict):
        rec_res = res.get("rec_res") or []
        if rec_res:
            text_list, scores = _extract_recognition_items(rec_res)
            return "\n".join(text_list), scores
        return _html_to_text(res.get("html", "")), []

    if isinstance(res, tuple) and len(res) >= 2:
        text_list, scores = _extract_recognition_items(res[1])
        return "\n".join(text_list), scores

    if isinstance(res, list):
        text_list, scores = _extract_recognition_items(res)
        return "\n".join(text_list), scores

    return "", []


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


def _sort_key(block):
    bbox = block.get("bbox") or [0, 0, 0, 0]
    if len(bbox) < 2:
        return 0, 0
    return bbox[1], bbox[0]


def _html_to_text(content):
    if not content:
        return ""
    text = re.sub(r"<[^>]+>", " ", content)
    return _clean_text(html.unescape(text))


def _clean_text(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _avg(values):
    if not values:
        return None
    return round(sum(values) / len(values), 4)
