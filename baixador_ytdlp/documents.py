"""Conversão de documentos com o Qt que o app já empacota (sem LibreOffice, Pandoc ou rede).

Lê TXT, Markdown, HTML, DOCX e ODT (texto, títulos, negrito/itálico, listas simples e
tabelas) e grava PDF, DOCX, HTML, TXT ou Markdown. Imagens viram PDF de uma página: o
FFmpeg do app decodifica qualquer formato para PNG e o Qt monta a página.

Roda só no worker (``MediaToolWorker``), nunca na thread da interface.
"""
from __future__ import annotations

import html
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtCore import QMarginsF, QSizeF, QUrl
from PySide6.QtGui import (QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter,
                           QTextCharFormat, QTextDocument)

from .media_tools import CONVERT_FORMATS, DOCUMENT_SOURCES
from .processes import CREATE_NO_WINDOW
from .tools import Toolchain

DOCUMENT_FORMATS = CONVERT_FORMATS["document"]

# Limites contra arquivos montados para travar o app (zip bomb, XML gigante).
MAX_TEXT_BYTES = 20 * 1024 * 1024
MAX_XML_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ODF_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
ODF_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"


class DocumentError(RuntimeError):
    """Documento que não dá para ler ou gravar; a mensagem vai direto para a pessoa."""


class _LocalDocument(QTextDocument):
    """QTextDocument que só carrega imagens da pasta do próprio documento.

    Sem isso, um HTML/Markdown baixado com ``<img src="file:///C:/Users/…">`` ou
    ``../../`` copiaria arquivos locais para dentro do PDF que a pessoa vai compartilhar.
    O Qt não acessa a rede aqui, mas negamos qualquer esquema que não seja arquivo."""

    def __init__(self, folder: Path):
        super().__init__()
        self._folder = folder.resolve()

    def loadResource(self, kind: int, url: QUrl):  # noqa: N802 - assinatura do Qt
        if kind != QTextDocument.ResourceType.ImageResource.value:
            return None
        if url.scheme() not in {"", "file"}:
            return None
        relative = url.toLocalFile() if url.isLocalFile() else url.path()
        try:
            target = (self._folder / relative).resolve()
        except (OSError, ValueError):
            return None
        if not target.is_relative_to(self._folder) or not target.is_file():
            return None
        image = QImage(str(target))
        return None if image.isNull() else image


def is_document(path: Path) -> bool:
    return path.suffix.casefold() in DOCUMENT_SOURCES


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise DocumentError("O documento passa de 20 MB de texto.")
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _zip_xml(path: Path, member: str) -> ElementTree.Element:
    """Lê um XML de dentro do DOCX/ODT com teto de tamanho (o ZIP pode mentir)."""
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(member)
            if info.file_size > MAX_XML_BYTES:
                raise DocumentError("O documento é grande demais para converter.")
            with archive.open(info) as handle:
                data = handle.read(MAX_XML_BYTES + 1)
    except KeyError as exc:
        raise DocumentError("O arquivo não parece um documento válido.") from exc
    except zipfile.BadZipFile as exc:
        raise DocumentError("O arquivo está corrompido ou não é um documento.") from exc
    if len(data) > MAX_XML_BYTES:
        raise DocumentError("O documento é grande demais para converter.")
    if b"<!DOCTYPE" in data[:4096] or b"<!ENTITY" in data:
        # DOCX/ODT nunca usam DTD; entidades só serviriam para ataques (billion laughs/XXE).
        raise DocumentError("O documento tem conteúdo XML não suportado.")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise DocumentError("O documento está corrompido.") from exc


def _docx_run_text(run: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in run:
        if node.tag == f"{W}t":
            parts.append(html.escape(node.text or ""))
        elif node.tag == f"{W}tab":
            parts.append("&emsp;")
        elif node.tag in {f"{W}br", f"{W}cr"}:
            parts.append("<br>")
    text = "".join(parts)
    props = run.find(f"{W}rPr")
    if props is not None and text:
        if _on(props.find(f"{W}b")):
            text = f"<b>{text}</b>"
        if _on(props.find(f"{W}i")):
            text = f"<i>{text}</i>"
        if _on(props.find(f"{W}u")):
            text = f"<u>{text}</u>"
    return text


def _on(node: ElementTree.Element | None) -> bool:
    return node is not None and node.get(f"{W}val", "true") not in {"0", "false", "none"}


def _docx_paragraph(paragraph: ElementTree.Element) -> str:
    text = "".join(_docx_run_text(run) for run in paragraph.iter(f"{W}r"))
    style = paragraph.find(f"{W}pPr/{W}pStyle")
    name = (style.get(f"{W}val", "") if style is not None else "").casefold()
    level = re.search(r"(?:heading|título|titulo|ttulo)\s*(\d)", name)
    if name == "title":
        return f"<h1>{text}</h1>"
    if level:
        tag = f"h{min(6, int(level[1]))}"
        return f"<{tag}>{text}</{tag}>"
    if paragraph.find(f"{W}pPr/{W}numPr") is not None:
        return f"<ul><li>{text}</li></ul>"
    return f"<p>{text or '&nbsp;'}</p>"


def _docx_html(path: Path) -> str:
    body = _zip_xml(path, "word/document.xml").find(f"{W}body")
    if body is None:
        raise DocumentError("O documento Word está vazio.")
    parts: list[str] = []
    for block in body:
        if block.tag == f"{W}p":
            parts.append(_docx_paragraph(block))
        elif block.tag == f"{W}tbl":
            rows = []
            for row in block.iter(f"{W}tr"):
                cells = ["<td>" + "".join(_docx_paragraph(p) for p in cell.iter(f"{W}p")) + "</td>"
                         for cell in row.iter(f"{W}tc")]
                rows.append("<tr>" + "".join(cells) + "</tr>")
            parts.append('<table border="1" cellspacing="0" cellpadding="4">'
                         + "".join(rows) + "</table>")
    return "<html><body>" + "".join(parts) + "</body></html>"


def _odt_inline(node: ElementTree.Element) -> str:
    parts = [html.escape(node.text or "")]
    for child in node:
        if child.tag == f"{ODF_TEXT}s":
            parts.append("&nbsp;" * int(child.get(f"{ODF_TEXT}c", "1") or 1))
        elif child.tag == f"{ODF_TEXT}tab":
            parts.append("&emsp;")
        elif child.tag == f"{ODF_TEXT}line-break":
            parts.append("<br>")
        else:
            parts.append(_odt_inline(child))
        parts.append(html.escape(child.tail or ""))
    return "".join(parts)


def _odt_blocks(node: ElementTree.Element) -> list[str]:
    parts: list[str] = []
    for child in node:
        if child.tag == f"{ODF_TEXT}h":
            level = min(6, max(1, int(child.get(f"{ODF_TEXT}outline-level", "1") or 1)))
            parts.append(f"<h{level}>{_odt_inline(child)}</h{level}>")
        elif child.tag == f"{ODF_TEXT}p":
            parts.append(f"<p>{_odt_inline(child) or '&nbsp;'}</p>")
        elif child.tag == f"{ODF_TEXT}list":
            items = ["<li>" + "".join(_odt_blocks(item)) + "</li>"
                     for item in child.iter(f"{ODF_TEXT}list-item")]
            parts.append("<ul>" + "".join(items) + "</ul>")
        elif child.tag == f"{ODF_TABLE}table":
            rows = []
            for row in child.iter(f"{ODF_TABLE}table-row"):
                cells = ["<td>" + "".join(_odt_blocks(cell)) + "</td>"
                         for cell in row.iter(f"{ODF_TABLE}table-cell")]
                rows.append("<tr>" + "".join(cells) + "</tr>")
            parts.append('<table border="1" cellspacing="0" cellpadding="4">'
                         + "".join(rows) + "</table>")
        elif child.tag == f"{ODF_TEXT}section":
            parts.extend(_odt_blocks(child))
    return parts


def _odt_html(path: Path) -> str:
    root = _zip_xml(path, "content.xml")
    text = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:office:1.0}text")
    if text is None:
        raise DocumentError("O documento ODT está vazio.")
    return "<html><body>" + "".join(_odt_blocks(text)) + "</body></html>"


def load_document(path: Path) -> QTextDocument:
    """Abre o documento num QTextDocument que nunca lê nada fora da pasta dele."""
    document = _LocalDocument(path.parent)
    font = document.defaultFont()
    font.setPointSize(11)
    document.setDefaultFont(font)
    document.setBaseUrl(QUrl.fromLocalFile(str(path.parent.resolve()) + "/"))
    suffix = path.suffix.casefold()
    if suffix == ".txt":
        document.setPlainText(_read_text(path))
    elif suffix in {".md", ".markdown"}:
        document.setMarkdown(_read_text(path))
    elif suffix in {".html", ".htm"}:
        document.setHtml(_read_text(path))
    elif suffix == ".docx":
        document.setHtml(_docx_html(path))
    elif suffix == ".odt":
        document.setHtml(_odt_html(path))
    else:
        raise DocumentError("Formato de documento não suportado.")
    return document


def _pdf_writer(destination: Path) -> QPdfWriter:
    writer = QPdfWriter(str(destination))
    writer.setCreator("Baixador-YTDLP")
    writer.setResolution(300)
    return writer


def _write_pdf(document: QTextDocument, destination: Path) -> None:
    writer = _pdf_writer(destination)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                     QPageLayout.Orientation.Portrait,
                                     QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter))
    document.print_(writer)


def _docx_xml_text(text: str) -> str:
    return html.escape(text, quote=False)


def _write_docx(document: QTextDocument, destination: Path) -> None:
    """DOCX mínimo e válido: parágrafos, títulos (Heading1–6), negrito, itálico, sublinhado."""
    paragraphs: list[str] = []
    block = document.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        props = f'<w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr>' if 1 <= level <= 6 else ""
        runs: list[str] = []
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fmt: QTextCharFormat = fragment.charFormat()
                style = ""
                if fmt.fontWeight() >= QFont.Weight.Bold.value or level:
                    style += "<w:b/>"
                if fmt.fontItalic():
                    style += "<w:i/>"
                if fmt.fontUnderline():
                    style += '<w:u w:val="single"/>'
                pieces = fragment.text().replace("\u2028", "\n").split("\n")
                for index, piece in enumerate(pieces):
                    if index:
                        runs.append("<w:r><w:br/></w:r>")
                    if piece:
                        runs.append(f"<w:r>{f'<w:rPr>{style}</w:rPr>' if style else ''}"
                                    f'<w:t xml:space="preserve">{_docx_xml_text(piece)}</w:t></w:r>')
            iterator += 1
        paragraphs.append(f"<w:p>{props}{''.join(runs)}</w:p>")
        block = block.next()
    body = "".join(paragraphs)
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    headings = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/>'
        f'<w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="{n - 1}"/></w:pPr>'
        f'<w:rPr><w:b/><w:sz w:val="{max(24, 40 - 4 * n)}"/></w:rPr></w:style>'
        for n in range(1, 7))
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.styles+xml"/></Types>',
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/_rels/document.xml.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/></Relationships>',
        "word/styles.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{namespace}">'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
            f'<w:rPr><w:sz w:val="22"/></w:rPr></w:style>{headings}</w:styles>',
        "word/document.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{namespace}">'
            f'<w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1021" w:right="1021" w:bottom="1021" w:left="1021"/></w:sectPr>'
            '</w:body></w:document>',
    }
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def _write_text(destination: Path, text: str) -> None:
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def convert_document(source: Path, destination: Path) -> None:
    """Converte um documento; o destino nunca é sobrescrito (modo ``x``)."""
    target = destination.suffix.casefold().lstrip(".")
    if target == "htm":
        target = "html"
    if target == "markdown":
        target = "md"
    if target not in DOCUMENT_FORMATS:
        listed = ", ".join(f".{value}" for value in DOCUMENT_FORMATS)
        raise DocumentError(f"Use {listed} como extensão de saída para este documento.")
    if destination.exists():
        raise DocumentError("O arquivo de saída já existe. Escolha outro nome.")
    document = load_document(source)
    if target == "pdf":
        _write_pdf(document, destination)
    elif target == "docx":
        _write_docx(document, destination)
    elif target == "html":
        _write_text(destination, document.toHtml())
    elif target == "txt":
        _write_text(destination, document.toPlainText())
    else:
        _write_text(destination, document.toMarkdown())
    if not destination.is_file() or destination.stat().st_size == 0:
        raise DocumentError("Não foi possível gravar o documento convertido.")


def image_to_pdf(source: Path, destination: Path, toolchain: Toolchain) -> None:
    """Uma página do tamanho da imagem (150 dpi). O FFmpeg decodifica (WebP, TIFF, BMP…)."""
    if destination.exists():
        raise DocumentError("O arquivo de saída já existe. Escolha outro nome.")
    with tempfile.TemporaryDirectory(prefix="baixador-pdf-") as folder:
        png = Path(folder) / "pagina.png"
        result = subprocess.run(
            [str(toolchain.ffmpeg), "-hide_banner", "-v", "error", "-n",
             "-f", "image2", "-pattern_type", "none", "-protocol_whitelist", "file",
             "-i", str(source.absolute()), "-frames:v", "1", "-update", "1", str(png)],
            capture_output=True, text=True, timeout=120, check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not png.is_file():
            tail = (result.stderr or "").strip().splitlines()
            raise DocumentError(tail[-1] if tail else "Não foi possível ler a imagem.")
        image = QImage(str(png))
    if image.isNull():
        raise DocumentError("Não foi possível ler a imagem.")
    if image.width() * image.height() > MAX_IMAGE_PIXELS:
        raise DocumentError("A imagem é grande demais para virar PDF (mais de 100 megapixels).")
    dpi = 150
    writer = _pdf_writer(destination)
    writer.setResolution(dpi)
    writer.setPageSize(QPageSize(QSizeF(image.width() / dpi, image.height() / dpi),
                                 QPageSize.Unit.Inch))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    painter = QPainter(writer)
    try:
        page = writer.pageLayout().paintRectPixels(dpi)
        painter.drawImage(page, image)
    finally:
        painter.end()
    if not destination.is_file() or destination.stat().st_size == 0:
        raise DocumentError("Não foi possível gravar o PDF.")
