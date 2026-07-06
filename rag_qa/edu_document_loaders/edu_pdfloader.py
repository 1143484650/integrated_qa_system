import os
import cv2
import fitz  # pyMuPDF里面的fitz包，不要与pip install fitz混淆
import numpy as np
from PIL import Image
from tqdm import tqdm
from typing import Iterator
from edu_ocr import get_ocr, extract_text_and_score, parse_array_with_ocr_service
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader
from langchain.text_splitter import CharacterTextSplitter
# PDF OCR 控制：只对宽高超过页面一定比例（图片宽/页面宽，图片高/页面高）的图片进行 OCR。
# 这样可以避免 PDF 中一些小图片的干扰，提高非扫描版 PDF 处理速度
PDF_OCR_THRESHOLD = (0.6, 0.6)
PDF_TEXT_THRESHOLD = 30


class OCRPDFLoader(BaseLoader):
    """An example document loader that reads a file line by line."""

    def __init__(self, file_path: str) -> None:
        """Initialize the loader with a file path.

        Args:
            file_path: The path to the file to load.
        """
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        # <-- Does not take any arguments
        """A lazy loader that reads a file line by line.

        When you're implementing lazy load methods, you should use a generator
        to yield documents one by one.
        """

        line, metadata = self.pdf2text()
        yield Document(page_content=line, metadata=metadata)



    def pdf2text(self):
        rapid_ocr = get_ocr()
        structure_ocr = None
        # 打开pdf文件
        doc = fitz.open(self.file_path)
        resp = []
        scores = []
        parse_methods = set()
        b_unit = tqdm(total=doc.page_count, desc="OCRPDFLoader context page index: 0")
        for i, page in enumerate(doc):
            b_unit.set_description("OCRPDFLoader context page index: {}".format(i))
            b_unit.refresh()
            text = page.get_text("text").strip()
            img_list = page.get_image_info(xrefs=True)

            if self._should_use_ppstructure(text, img_list, page):
                if structure_ocr is None:
                    structure_ocr = get_ocr(backend="ppstructure")
                page_text, page_score, parse_method = self._extract_page_with_ppstructure(page, structure_ocr)
                if page_text:
                    resp.append(page_text)
                if page_score is not None:
                    scores.append(page_score)
                parse_methods.add(parse_method)
                b_unit.update(1)
                continue

            if text:
                resp.append(text)
                parse_methods.add("text")

            for img in img_list:
                if xref := img.get("xref"):
                    bbox = img["bbox"]
                    if ((bbox[2] - bbox[0]) / (page.rect.width) < PDF_OCR_THRESHOLD[0]
                            or (bbox[3] - bbox[1]) / (page.rect.height) < PDF_OCR_THRESHOLD[1]):
                        continue
                    pix = fitz.Pixmap(doc, xref)
                    if int(page.rotation) != 0:
                        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
                        tmp_img = Image.fromarray(img_array)
                        ori_img = cv2.cvtColor(np.array(tmp_img), cv2.COLOR_RGB2BGR)
                        rot_img = self.rotate_img(img=ori_img, angle=360 - page.rotation)
                        img_array = cv2.cvtColor(rot_img, cv2.COLOR_RGB2BGR)
                    else:
                        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)

                    result, _ = rapid_ocr(img_array)
                    image_text, image_score = extract_text_and_score(result)
                    if image_text:
                        resp.append(image_text)
                        parse_methods.add("rapidocr")
                    if image_score is not None:
                        scores.append(image_score)
            b_unit.update(1)

        metadata = {"source": self.file_path, "parse_method": "+".join(sorted(parse_methods or {"text"}))}
        if scores:
            metadata["ocr_confidence"] = round(sum(scores) / len(scores), 4)
        return "\n".join(resp), metadata

    def _should_use_ppstructure(self, text, img_list, page):
        if len(text) < PDF_TEXT_THRESHOLD:
            return True
        for img in img_list:
            bbox = img.get("bbox")
            if not bbox:
                continue
            width_ratio = (bbox[2] - bbox[0]) / page.rect.width
            height_ratio = (bbox[3] - bbox[1]) / page.rect.height
            if width_ratio >= PDF_OCR_THRESHOLD[0] and height_ratio >= PDF_OCR_THRESHOLD[1]:
                return True
        return False

    def _extract_page_with_ppstructure(self, page, ocr):
        img = self._render_page_image(page)
        service_result = parse_array_with_ocr_service(img)
        if service_result:
            return (
                service_result.get("text", ""),
                service_result.get("ocr_confidence"),
                service_result.get("parse_method", "ppstructure-service"),
            )

        result = ocr(img)
        parse_method = "ppstructure"
        if isinstance(result, tuple):
            result = result[0]
            parse_method = "rapidocr"
        text, score = extract_text_and_score(result)
        return text, score, parse_method

    def _render_page_image(self, page):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        if pix.width > 2000 or pix.height > 2000:
            pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def rotate_img(self, img, angle):
        '''
        img   --image
        angle --rotation angle
        return--rotated img
        '''

        h, w = img.shape[:2]
        rotate_center = (w / 2, h / 2)
        # 获取旋转矩阵
        # 参数1为旋转中心点;
        # 参数2为旋转角度,正值-逆时针旋转;负值-顺时针旋转
        # 参数3为各向同性的比例因子,1.0原图，2.0变成原来的2倍，0.5变成原来的0.5倍
        M = cv2.getRotationMatrix2D(rotate_center, angle, 1.0)
        # 计算图像新边界
        new_w = int(h * np.abs(M[0, 1]) + w * np.abs(M[0, 0]))
        new_h = int(h * np.abs(M[0, 0]) + w * np.abs(M[0, 1]))
        # 调整旋转矩阵以考虑平移
        M[0, 2] += (new_w - w) / 2
        M[1, 2] += (new_h - h) / 2

        rotated_img = cv2.warpAffine(img, M, (new_w, new_h))
        return rotated_img

if __name__ == '__main__':
    samples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'samples')
    # pdf_loader = OCRPDFLoader(file_path=os.path.join(samples_dir, 'ocr_03.pdf'))
    pdf_loader = OCRPDFLoader(file_path=os.path.join(samples_dir, 'AI大模型开发（Python）就业学习大纲.pdf'))
    doc = pdf_loader.load()

    print(type(doc))
    print(doc)
    text_spliter = CharacterTextSplitter(chunk_size=300, chunk_overlap=20)
    result = text_spliter.split_documents(doc)
    print('>>>'*20)
    print(len(result))
    print(result[0])
