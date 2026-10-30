"""Conversão de documentos (1.16): DOCX, ODT, TXT, Markdown e HTML com o Qt do app.

Inclui as proteções: XML com DTD/entidades recusado, ZIP que mente o tamanho, imagens só
da pasta do documento e saída que nunca sobrescreve um arquivo existente.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QApplication

from baixador_ytdlp import documents
from baixador_ytdlp.documents import DocumentError, convert_document, image_to_pdf, load_document
from baixador_ytdlp.media_tools import (CONVERT_FORMATS, MediaToolError, MediaToolOptions,
                                        build_command, is_document_job, source_kind)
from baixador_ytdlp.tools import Toolchain

FFMPEG = shutil.which("ffmpeg")
W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(path: Path, body: str, prolog: str = "") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml",
                         f'<?xml version="1.0"?>{prolog}<w:document {W_NS}><w:body>{body}'
                         "</w:body></w:document>")
    return path


DOCX_BODY = (
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Relatório</w:t></w:r></w:p>'
    '<w:p><w:r><w:t xml:space="preserve">Texto </w:t></w:r>'
    '<w:r><w:rPr><w:b/></w:rPr><w:t>forte</w:t></w:r>'
    '<w:r><w:rPr><w:i/></w:rPr><w:t> e inclinado</w:t></w:r></w:p>'
    '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A1</w:t></w:r></w:p></w:tc>'
    '<w:tc><w:p><w:r><w:t>B1</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
)


class DocumentosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_tipo_e_formatos(self) -> None:
        for name in ("a.docx", "a.ODT", "a.txt", "a.md", "a.markdown", "a.html", "a.htm"):
            self.assertEqual(source_kind(Path(name)), "document", name)
        self.assertEqual(CONVERT_FORMATS["document"], ("pdf", "docx", "html", "txt", "md"))
        self.assertIn("pdf", CONVERT_FORMATS["image"])
        self.assertTrue(is_document_job(MediaToolOptions(Path("a.png"), Path("a.pdf"), "convert")))
        self.assertTrue(is_document_job(MediaToolOptions(Path("a.docx"), Path("a.txt"), "convert")))
        self.assertFalse(is_document_job(MediaToolOptions(Path("a.png"), Path("a.jpg"), "convert")))
        self.assertFalse(is_document_job(MediaToolOptions(Path("a.docx"), Path("a.pdf"), "trim")))

    def test_ffmpeg_nunca_recebe_documento(self) -> None:
        source = self.root / "a.docx"
        source.write_bytes(b"x")
        tc = Toolchain(self.root / "y", self.root / "ffmpeg", self.root / "ffprobe", self.root)
        with self.assertRaises(MediaToolError):
            build_command(MediaToolOptions(source, self.root / "a.pdf", "convert"), tc)

    def test_docx_para_cada_formato(self) -> None:
        source = _docx(self.root / "rel.docx", DOCX_BODY)
        for target in ("pdf", "docx", "html", "txt", "md"):
            convert_document(source, self.root / f"saida.{target}")
        self.assertTrue((self.root / "saida.pdf").read_bytes().startswith(b"%PDF"))
        text = (self.root / "saida.txt").read_text(encoding="utf-8")
        for piece in ("Relatório", "Texto forte e inclinado", "A1", "B1"):
            self.assertIn(piece, text)
        markdown = (self.root / "saida.md").read_text(encoding="utf-8")
        self.assertIn("# Relatório", markdown)
        self.assertIn("**forte**", markdown)
        # O DOCX gerado abre de novo (ida e volta) e mantém título e negrito.
        again = load_document(self.root / "saida.docx")
        self.assertIn("Texto forte e inclinado", again.toPlainText())
        with zipfile.ZipFile(self.root / "saida.docx") as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn('w:val="Heading1"', xml)
        self.assertIn("<w:b/>", xml)

    def test_markdown_e_texto_com_acentos_do_windows(self) -> None:
        markdown = self.root / "nota.md"
        markdown.write_text("# Título\n\n- item *um*\n- item dois\n", encoding="utf-8")
        convert_document(markdown, self.root / "nota.docx")
        self.assertIn("Título", load_document(self.root / "nota.docx").toPlainText())
        legacy = self.root / "antigo.txt"
        legacy.write_bytes("Ação & coração <b>".encode("cp1252"))
        convert_document(legacy, self.root / "antigo.html")
        convert_document(legacy, self.root / "antigo2.txt")
        self.assertEqual((self.root / "antigo2.txt").read_text(encoding="utf-8"),
                         "Ação & coração <b>")   # texto puro não vira marcação

    def test_odt(self) -> None:
        source = self.root / "doc.odt"
        office = 'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        text = 'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("content.xml", (
                f'<?xml version="1.0"?><office:document-content {office} {text}>'
                "<office:body><office:text>"
                '<text:h text:outline-level="2">Capítulo</text:h>'
                "<text:p>Olá<text:s text:c=\"2\"/>mundo<text:line-break/>fim</text:p>"
                "<text:list><text:list-item><text:p>ponto</text:p></text:list-item></text:list>"
                "</office:text></office:body></office:document-content>"))
        convert_document(source, self.root / "doc.md")
        markdown = (self.root / "doc.md").read_text(encoding="utf-8")
        self.assertIn("## Capítulo", markdown)
        self.assertIn("ponto", markdown)
        self.assertIn("mundo", markdown)

    def test_xml_com_entidades_e_recusado(self) -> None:
        """Billion laughs / XXE: DOCX legítimo nunca traz DTD."""
        prolog = ('<!DOCTYPE w:document [<!ENTITY a "aaaaaaaaaa">'
                  '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>')
        source = _docx(self.root / "bomba.docx", "<w:p><w:r><w:t>&b;</w:t></w:r></w:p>", prolog)
        with self.assertRaisesRegex(DocumentError, "XML"):
            convert_document(source, self.root / "x.txt")
        self.assertFalse((self.root / "x.txt").exists())

    def test_zip_grande_demais_e_recusado(self) -> None:
        source = _docx(self.root / "grande.docx", "<w:p><w:r><w:t>" + "a" * 5000 + "</w:t></w:r></w:p>")
        with patch.object(documents, "MAX_XML_BYTES", 1000):
            with self.assertRaisesRegex(DocumentError, "grande demais"):
                convert_document(source, self.root / "x.txt")

    def test_arquivo_que_nao_e_docx(self) -> None:
        fake = self.root / "falso.docx"
        fake.write_text("não sou zip", encoding="utf-8")
        with self.assertRaisesRegex(DocumentError, "corrompido"):
            convert_document(fake, self.root / "x.pdf")

    def test_nunca_sobrescreve(self) -> None:
        source = self.root / "a.txt"
        source.write_text("novo", encoding="utf-8")
        existing = self.root / "b.txt"
        existing.write_text("antigo", encoding="utf-8")
        with self.assertRaises(DocumentError):
            convert_document(source, existing)
        self.assertEqual(existing.read_text(encoding="utf-8"), "antigo")

    def test_imagens_so_da_pasta_do_documento(self) -> None:
        """Um HTML baixado não pode copiar arquivos do computador para o PDF."""
        folder = self.root / "doc"
        (folder / "img").mkdir(parents=True)
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(0xFF0000)
        image.save(str(folder / "img" / "ok.png"))
        image.save(str(self.root / "segredo.png"))
        page = folder / "pagina.html"
        page.write_text("<p>x</p>", encoding="utf-8")
        document = load_document(page)
        kind = QTextDocument.ResourceType.ImageResource.value
        self.assertIsNotNone(document.loadResource(kind, QUrl("img/ok.png")))
        for url in ("../segredo.png", QUrl.fromLocalFile(str(self.root / "segredo.png")).toString(),
                    "http://127.0.0.1:9/x.png", "img/../../segredo.png"):
            self.assertIsNone(document.loadResource(kind, QUrl(url)), url)

    @unittest.skipUnless(FFMPEG, "FFmpeg ausente")
    def test_imagem_vira_pdf_do_tamanho_dela(self) -> None:
        source = self.root / "foto%d.webp"
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=300x150",
                        "-frames:v", "1", "-update", "1", str(source)], check=True)
        tc = Toolchain(self.root / "y", Path(FFMPEG), Path(FFMPEG), self.root)
        destination = self.root / "foto.pdf"
        image_to_pdf(source, destination, tc)
        data = destination.read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        box = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", data)
        self.assertIsNotNone(box)
        assert box is not None
        # 300x150 px a 150 dpi = 2x1 polegadas = 144x72 pontos.
        self.assertEqual((float(box[1]), float(box[2])), (144.0, 72.0))

    def test_worker_converte_documento_sem_ffmpeg(self) -> None:
        from baixador_ytdlp.workers import MediaToolWorker

        source = self.root / "nota.txt"
        source.write_text("linha", encoding="utf-8")
        destination = self.root / "nota.pdf"
        tc = Toolchain(self.root / "y", self.root / "ffmpeg-inexistente", self.root / "p", self.root)
        worker = MediaToolWorker(MediaToolOptions(source, destination, "convert"), tc)
        outcome: dict[str, str] = {}
        worker.finished_ok.connect(lambda path: outcome.update(ok=path))
        worker.failed.connect(lambda message: outcome.update(failed=message))
        worker.run()
        self.assertEqual(outcome, {"ok": str(destination)})
        self.assertTrue(destination.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
