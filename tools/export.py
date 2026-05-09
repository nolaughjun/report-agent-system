# tools/export.py — 报告导出工具
"""报告导出工具模块"""
from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("outputs")


def _ensure_pandoc_in_path():
    """确保 pandoc 在 PATH 中"""
    # 常见的 pandoc 安装路径
    possible_paths = [
        # WinGet 安装路径
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        # 用户目录
        Path(os.environ.get("LOCALAPPDATA", "")) / "Pandoc",
        # 系统目录
        Path("C:/Program Files/Pandoc"),
    ]

    for base_path in possible_paths:
        if base_path.exists():
            # 查找 pandoc.exe
            for p in base_path.rglob("pandoc.exe"):
                pandoc_dir = str(p.parent)
                if pandoc_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = pandoc_dir + os.pathsep + os.environ.get("PATH", "")
                    logger.info("[export] 添加 pandoc 到 PATH: %s", pandoc_dir)
                    return True

    # 尝试从注册表或标准位置查找
    try:
        import subprocess
        result = subprocess.run(["where", "pandoc"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            pandoc_path = result.stdout.strip().split("\n")[0]
            pandoc_dir = str(Path(pandoc_path).parent)
            if pandoc_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = pandoc_dir + os.pathsep + os.environ.get("PATH", "")
                return True
    except Exception:
        pass

    return False


def _ensure_latex_in_path():
    """确保 MiKTeX (xelatex/pdflatex) 在 PATH 中"""
    # MiKTeX 常见安装路径
    miktex_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin",
        Path("C:/Program Files/MiKTeX/miktex/bin/x64"),
        Path("C:/Program Files/MiKTeX/miktex/bin"),
    ]

    for miktex_bin in miktex_paths:
        if miktex_bin.exists():
            # 检查是否有 xelatex 或 pdflatex
            has_xelatex = (miktex_bin / "xelatex.exe").exists()
            has_pdflatex = (miktex_bin / "pdflatex.exe").exists()

            if has_xelatex or has_pdflatex:
                miktex_dir = str(miktex_bin)
                if miktex_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = miktex_dir + os.pathsep + os.environ.get("PATH", "")
                    logger.info("[export] 添加 MiKTeX 到 PATH: %s", miktex_dir)
                    return True

    return False


def _ensure_output_dir(output_dir: str | Path) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def _safe_filename(name: str) -> str:
    """生成安全的文件名"""
    if not name:
        return "report"
    safe_name = re.sub(r'[^\w一-鿿\-]', '_', name)
    safe_name = re.sub(r'_+', '_', safe_name)
    safe_name = safe_name.strip('_')
    return safe_name[:100] if safe_name else "report"


def export_markdown(
    content: str,
    topic: str = "",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    filename: str | None = None,
) -> str:
    """导出 Markdown 文件"""
    output_path = _ensure_output_dir(output_dir)

    if filename:
        safe_name = _safe_filename(filename)
    elif topic:
        safe_name = _safe_filename(topic)
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_name = f"report_{timestamp}"

    md_path = output_path / f"{safe_name}.md"

    if topic and not content.startswith("#"):
        full_content = f"# {topic}\n\n{content}"
    else:
        full_content = content

    md_path.write_text(full_content, encoding="utf-8")
    logger.info("[export_markdown] 导出成功: %s", md_path)

    return str(md_path.resolve())


def export_pdf(
    markdown_path: str | Path,
    output_dir: str | Path | None = None,
) -> str | None:
    """将 Markdown 转换为 PDF

    使用 pypandoc + xelatex（支持中文）
    """
    md_path = Path(markdown_path)

    if not md_path.exists():
        logger.error("[export_pdf] 文件不存在: %s", md_path)
        return None

    if output_dir:
        pdf_dir = _ensure_output_dir(output_dir)
    else:
        pdf_dir = md_path.parent

    pdf_path = pdf_dir / f"{md_path.stem}.pdf"

    # 确保 pandoc 和 MiKTeX 在 PATH 中
    _ensure_pandoc_in_path()
    _ensure_latex_in_path()

    # 直接使用简化方案，更稳定
    return _export_pdf_simple(md_path, pdf_path)


def _export_pdf_simple(md_path: Path, pdf_path: Path) -> str | None:
    """简化的 PDF 转换

    支持：
    - 中文显示
    - 段落缩进（两个字符）
    - 完整内容（不截断）
    """
    try:
        import pypandoc

        # 创建临时 LaTeX header 文件
        header_content = r"""
\usepackage{indentfirst}
\setlength{\parindent}{2em}
\setlength{\parskip}{0.3em}
"""
        header_path = md_path.parent / "_latex_header.tex"
        header_path.write_text(header_content, encoding="utf-8")

        try:
            # 带段落缩进的转换
            pypandoc.convert_file(
                str(md_path),
                "pdf",
                format="md",
                outputfile=str(pdf_path),
                extra_args=[
                    "--pdf-engine=xelatex",
                    "-V",
                    "mainfont=Microsoft YaHei",
                    "-V",
                    "CJKmainfont=Microsoft YaHei",
                    "-V",
                    "geometry:margin=2.5cm",
                    "-V",
                    "documentclass=article",
                    "-V",
                    "classoption=12pt,a4paper",
                    # 不换行，保持完整内容
                    "--wrap=none",
                    # 段落缩进 header
                    "--include-in-header=" + str(header_path),
                ],
            )
            logger.info("[export_pdf] 转换成功: %s", pdf_path)
            return str(pdf_path.resolve())
        finally:
            # 清理临时文件
            if header_path.exists():
                header_path.unlink()

    except Exception as e:
        logger.warning("[export_pdf] 带缩进转换失败: %s，尝试基础转换", e)

        # 尝试最基础的转换
        try:
            import pypandoc
            pypandoc.convert_file(
                str(md_path),
                "pdf",
                format="md",
                outputfile=str(pdf_path),
                extra_args=[
                    "--pdf-engine=xelatex",
                    "-V",
                    "mainfont=Microsoft YaHei",
                    "-V",
                    "geometry:margin=2.5cm",
                ],
            )
            logger.info("[export_pdf] 基础转换成功: %s", pdf_path)
            return str(pdf_path.resolve())
        except Exception as e2:
            logger.error("[export_pdf] 基础转换也失败: %s", e2)
            return None


def export_report(
    content: str,
    topic: str = "",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    filename: str | None = None,
) -> dict[str, str | None]:
    """导出报告（Markdown + PDF）"""
    md_path = export_markdown(content, topic, output_dir, filename)
    pdf_path = export_pdf(md_path, output_dir)

    return {
        "markdown": md_path,
        "pdf": pdf_path,
    }
