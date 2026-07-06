import os
from typing import Iterator
from edu_ocr import get_ocr, extract_text_and_score, parse_with_ocr_service
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader


class OCRIMGLoader(BaseLoader):
    """An example document loader that reads a file line by line."""

    def __init__(self, img_path: str) -> None:
        """Initialize the loader with a file path.

        Args:
            img_path: The path to the img to load.
        """
        self.img_path = img_path

    def lazy_load(self) -> Iterator[Document]:
        # <-- Does not take any arguments
        """A lazy loader that reads a file line by line.

        When you're implementing lazy load methods, you should use a generator
        to yield documents one by one.
        """
        line, score, parse_method = self.img2text()
        metadata = {"source": self.img_path, "parse_method": parse_method}
        if score is not None:
            metadata["ocr_confidence"] = round(score, 4)
        yield Document(page_content=line, metadata=metadata)

    def img2text(self):
        service_result = parse_with_ocr_service(self.img_path)
        if service_result:
            return (
                service_result.get("text", ""),
                service_result.get("ocr_confidence"),
                service_result.get("parse_method", "ppstructure-service"),
            )

        import cv2

        img = cv2.imread(self.img_path)
        if img is None:
            return "", None, "ppstructure"

        ocr = get_ocr(backend="ppstructure")
        result = ocr(img)
        parse_method = "ppstructure"
        if isinstance(result, tuple):
            result = result[0]
            parse_method = "rapidocr"
        text, score = extract_text_and_score(result)
        return text, score, parse_method


if __name__ == '__main__':
    samples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'samples')
    img_loader = OCRIMGLoader(img_path=os.path.join(samples_dir, 'ocr_04.png'))
    doc = img_loader.load()
    print(doc)
