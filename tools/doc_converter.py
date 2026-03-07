"""
DocConverter — Markdown to docx/pdf via pandoc.

Usage:
    converter = DocConverter()
    path = converter.to_docx(md_content, "HRS_MyProject", output_dir)
    path = converter.to_pdf(md_content, "HRS_MyProject", output_dir)
    path = converter.convert(md_content, "HRS_MyProject", output_dir, fmt="docx")

Requires pandoc installed and on PATH.
Falls back gracefully (returns None) if pandoc is unavailable.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, Optional

log = logging.getLogger(__name__)

OutputFormat = Literal["docx", "pdf", "html"]

_PANDOC_AVAILABLE: Optional[bool] = None  # lazy check


def _check_pandoc() -> bool:
    global _PANDOC_AVAILABLE
    if _PANDOC_AVAILABLE is None:
        _PANDOC_AVAILABLE = shutil.which("pandoc") is not None
        if not _PANDOC_AVAILABLE:
            log.warning("pandoc not found on PATH — doc conversion disabled")
    return _PANDOC_AVAILABLE


class DocConverter:
    """Converts markdown content to docx/pdf using pandoc."""

    def convert(
        self,
        markdown_content: str,
        stem: str,
        output_dir: Path | str,
        fmt: OutputFormat = "docx",
        reference_doc: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Convert markdown to the target format via pandoc.

        Args:
            markdown_content: Source markdown text.
            stem: Output filename without extension (e.g., "HRS_MyProject").
            output_dir: Directory to write the output file.
            fmt: "docx" | "pdf" | "html"
            reference_doc: Optional .docx reference template for styling.

        Returns:
            Path to the generated file, or None if pandoc is unavailable / fails.
        """
        if not _check_pandoc():
            return None

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{stem}.{fmt}"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(markdown_content)
            tmp_path = Path(tmp.name)

        try:
            cmd = [
                "pandoc",
                str(tmp_path),
                "-o", str(out_path),
                "--standalone",
                "--toc",
                "--toc-depth=3",
            ]

            if fmt == "docx" and reference_doc and reference_doc.exists():
                cmd += ["--reference-doc", str(reference_doc)]

            if fmt == "pdf":
                # Use xelatex for better Unicode support
                cmd += ["--pdf-engine=xelatex"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                log.error(
                    "pandoc failed (rc=%d): %s", result.returncode, result.stderr[:500]
                )
                return None

            log.info("doc_converter.ok fmt=%s path=%s", fmt, out_path)
            return out_path

        except subprocess.TimeoutExpired:
            log.error("pandoc timed out converting %s", stem)
            return None
        except Exception as exc:
            log.exception("doc_converter.error stem=%s fmt=%s: %s", stem, fmt, exc)
            return None
        finally:
            tmp_path.unlink(missing_ok=True)

    def to_docx(
        self,
        markdown_content: str,
        stem: str,
        output_dir: Path | str,
        reference_doc: Optional[Path] = None,
    ) -> Optional[Path]:
        return self.convert(markdown_content, stem, output_dir, "docx", reference_doc)

    def to_pdf(
        self,
        markdown_content: str,
        stem: str,
        output_dir: Path | str,
    ) -> Optional[Path]:
        return self.convert(markdown_content, stem, output_dir, "pdf")

    def to_html(
        self,
        markdown_content: str,
        stem: str,
        output_dir: Path | str,
    ) -> Optional[Path]:
        return self.convert(markdown_content, stem, output_dir, "html")

    def is_available(self) -> bool:
        return _check_pandoc()
