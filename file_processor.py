import re
from collections import Counter
import importlib


class FileProcessor:
    """Handle text extraction and top-keyword extraction."""

    STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "can", "did", "do",
        "does", "for", "from", "had", "has", "have", "he", "her", "hers", "him", "his", "i", "if", "in",
        "into", "is", "it", "its", "itself", "me", "my", "myself", "no", "not", "of", "on", "or", "our",
        "ours", "ourselves", "she", "so", "than", "that", "the", "their", "theirs", "them", "themselves",
        "then", "there", "these", "they", "this", "those", "to", "too", "up", "us", "very", "was", "we",
        "were", "what", "when", "where", "which", "who", "whom", "why", "will", "with", "you", "your",
        "yours", "yourself", "yourselves",
    }

    @staticmethod
    def extract_text(file_path):
        lower_path = file_path.lower()
        if lower_path.endswith(".pdf"):
            try:
                text = FileProcessor._extract_pdf_text(file_path)
            except Exception:
                text = FileProcessor._extract_doc_text(file_path)
        elif lower_path.endswith(".docx"):
            try:
                text = FileProcessor._extract_docx_text(file_path)
            except Exception:
                text = FileProcessor._extract_doc_text(file_path)
        elif lower_path.endswith(".doc"):
            text = FileProcessor._extract_doc_text(file_path)
        else:
            try:
                text = FileProcessor._extract_txt_text(file_path)
            except Exception:
                text = FileProcessor._extract_doc_text(file_path)
        return text.lower()

    @staticmethod
    def _extract_pdf_text(file_path):
        pypdf2 = importlib.import_module("PyPDF2")

        text = []
        with open(file_path, "rb") as file:
            pdf_reader = pypdf2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text() or ""
                text.append(page_text)
        return "\n".join(text)

    @staticmethod
    def _extract_docx_text(file_path):
        docx_module = importlib.import_module("docx")
        document = docx_module.Document(file_path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    @staticmethod
    def _extract_doc_text(file_path):
        # Legacy .doc parsing support: try readable-text fallback from binary bytes.
        with open(file_path, "rb") as file:
            raw = file.read()
        return raw.decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_txt_text(file_path):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            return file.read()

    @staticmethod
    def extract_keywords(text, top_k=5):
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        filtered = [word for word in words if word not in FileProcessor.STOPWORDS]
        frequency = Counter(filtered)
        keywords = [word for word, _ in frequency.most_common(top_k)]

        if keywords:
            return keywords
        return ["document"]
