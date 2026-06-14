#!/usr/bin/env python3
"""Ingest a PDF into the Xiaozhi RAG corpus.

Supports both text-layer PDFs and scanned PDFs via Tesseract OCR.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterable

import fitz
import numpy as np
import requests

BASE_DIR = Path(os.environ.get("KB_BASE_DIR", "/opt/xiaozhi-mcp"))
RAG_DIR = Path(os.environ.get("KB_RAG_DIR", BASE_DIR / "rag"))
CHUNKS_FILE = Path(os.environ.get("KB_CHUNKS_FILE", RAG_DIR / "chunks.json"))
EMB_FILE = Path(os.environ.get("KB_EMB_FILE", RAG_DIR / "embeddings.npz"))
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
EMBED_URL = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ocr_page(doc: fitz.Document, page_index: int, cache_file: Path, dpi: int, lang: str, psm: int) -> str:
    if cache_file.exists():
        return normalize_text(cache_file.read_text(encoding="utf-8", errors="ignore"))
    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        pix.save(str(tmp_path))
        cmd = ["tesseract", str(tmp_path), "stdout", "-l", lang, "--psm", str(psm)]
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(f"tesseract failed page={page_index + 1}: {proc.stderr[-500:]}")
        text = normalize_text(proc.stdout)
        cache_file.write_text(text, encoding="utf-8")
        return text
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def extract_pages(pdf_path: Path, start_page: int = 1, max_pages: int | None = None,
                  ocr: bool = False, ocr_cache_dir: Path | None = None,
                  ocr_dpi: int = 180, ocr_lang: str = "chi_sim+eng", ocr_psm: int = 6) -> list[tuple[int, str]]:
    doc = fitz.open(pdf_path)
    pages: list[tuple[int, str]] = []
    start_idx = max(start_page - 1, 0)
    end_idx = len(doc) if max_pages is None else min(len(doc), start_idx + max_pages)
    doc_hash = hashlib.sha1(str(pdf_path.resolve()).encode("utf-8") + str(pdf_path.stat().st_size).encode()).hexdigest()[:12]
    for i in range(start_idx, end_idx):
        page = doc.load_page(i)
        text = normalize_text(page.get_text("text"))
        if not text and ocr:
            cache_base = ocr_cache_dir or (RAG_DIR / "ocr_cache" / pdf_path.stem)
            cache_file = cache_base / f"{doc_hash}-page-{i + 1:04d}.txt"
            print(f"ocr page {i + 1}/{len(doc)}", flush=True)
            text = ocr_page(doc, i, cache_file, dpi=ocr_dpi, lang=ocr_lang, psm=ocr_psm)
        if text:
            pages.append((i + 1, text))
    return pages


def chunk_page_text(text: str, target_chars: int, overlap_chars: int) -> Iterable[str]:
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    buf = ""
    for para in paras:
        if len(para) > target_chars * 1.5:
            if buf:
                yield buf.strip()
                buf = ""
            step = max(target_chars - overlap_chars, 1)
            for start in range(0, len(para), step):
                piece = para[start:start + target_chars].strip()
                if piece:
                    yield piece
            continue
        candidate = (buf + "\n" + para).strip() if buf else para
        if len(candidate) <= target_chars:
            buf = candidate
        else:
            if buf:
                yield buf.strip()
            prefix = buf[-overlap_chars:] if overlap_chars and buf else ""
            buf = (prefix + "\n" + para).strip() if prefix else para
    if buf:
        yield buf.strip()


def build_chunks(pdf_path: Path, title: str, source_name: str, target_chars: int, overlap_chars: int,
                 start_page: int, max_pages: int | None, ocr: bool, ocr_dpi: int, ocr_lang: str, ocr_psm: int) -> list[dict]:
    digest = hashlib.sha1(pdf_path.read_bytes()).hexdigest()[:12]
    chunks: list[dict] = []
    pages = extract_pages(
        pdf_path,
        start_page=start_page,
        max_pages=max_pages,
        ocr=ocr,
        ocr_dpi=ocr_dpi,
        ocr_lang=ocr_lang,
        ocr_psm=ocr_psm,
    )
    for page_no, text in pages:
        for idx, chunk_text in enumerate(chunk_page_text(text, target_chars, overlap_chars), start=1):
            if len(chunk_text) < 30:
                continue
            chunks.append({
                "id": f"{digest}-p{page_no:04d}-{idx:03d}",
                "filename": source_name,
                "title": f"{title} 第{page_no}页",
                "text": chunk_text,
            })
    return chunks


def embed_batch(texts: list[str], retries: int = 4) -> np.ndarray:
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("DASHSCOPE_API_KEY is not set")
    payload = {
        "model": "text-embedding-v4",
        "input": {"texts": texts},
        "parameters": {"text_type": "document"},
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(EMBED_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            vectors = [item["embedding"] for item in data["output"]["embeddings"]]
            return np.asarray(vectors, dtype=np.float32)
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError("unreachable")


def load_existing() -> tuple[list[dict], np.ndarray]:
    chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8")) if CHUNKS_FILE.exists() else []
    if EMB_FILE.exists():
        embeddings = np.load(EMB_FILE)["embeddings"].astype(np.float32)
    else:
        embeddings = np.zeros((0, 1024), dtype=np.float32)
    return chunks, embeddings


def backup_files() -> None:
    stamp = time.strftime("%Y%m%d%H%M%S")
    for p in (CHUNKS_FILE, EMB_FILE):
        if p.exists():
            shutil.copy2(p, p.with_name(f"{p.name}.bak.{stamp}"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--source-name", default="")
    parser.add_argument("--chunk-chars", type=int, default=650)
    parser.add_argument("--overlap-chars", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--ocr-dpi", type=int, default=180)
    parser.add_argument("--ocr-lang", default="chi_sim+eng")
    parser.add_argument("--ocr-psm", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-source", action="store_true", help="Remove existing chunks with the same filename first.")
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    title = args.title or pdf_path.stem
    source_name = args.source_name or pdf_path.name

    new_chunks = build_chunks(
        pdf_path,
        title=title,
        source_name=source_name,
        target_chars=args.chunk_chars,
        overlap_chars=args.overlap_chars,
        start_page=args.start_page,
        max_pages=args.max_pages,
        ocr=args.ocr,
        ocr_dpi=args.ocr_dpi,
        ocr_lang=args.ocr_lang,
        ocr_psm=args.ocr_psm,
    )
    print(json.dumps({
        "pdf": str(pdf_path),
        "source_name": source_name,
        "new_chunks": len(new_chunks),
        "first_title": new_chunks[0]["title"] if new_chunks else None,
        "first_text": new_chunks[0]["text"][:260] if new_chunks else None,
    }, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0
    if not new_chunks:
        raise RuntimeError("No text chunks extracted from PDF. The PDF may need OCR or better preprocessing.")

    existing_chunks, existing_embeddings = load_existing()
    if len(existing_chunks) != len(existing_embeddings):
        raise RuntimeError(f"Existing chunks/embeddings mismatch: {len(existing_chunks)} vs {len(existing_embeddings)}")

    if args.replace_source:
        keep_idx = [i for i, c in enumerate(existing_chunks) if c.get("filename") != source_name]
        existing_chunks = [existing_chunks[i] for i in keep_idx]
        existing_embeddings = existing_embeddings[keep_idx] if len(keep_idx) else np.zeros((0, existing_embeddings.shape[1]), dtype=np.float32)

    vectors: list[np.ndarray] = []
    texts = [c["text"] for c in new_chunks]
    for i in range(0, len(texts), args.batch_size):
        batch = texts[i:i + args.batch_size]
        print(f"embedding {i + 1}-{i + len(batch)} / {len(texts)}", flush=True)
        vectors.append(embed_batch(batch))
        time.sleep(0.15)
    new_embeddings = np.vstack(vectors)
    if existing_embeddings.size and new_embeddings.shape[1] != existing_embeddings.shape[1]:
        raise RuntimeError(f"Embedding dim mismatch: new {new_embeddings.shape}, existing {existing_embeddings.shape}")

    backup_files()
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks = existing_chunks + new_chunks
    all_embeddings = np.vstack([existing_embeddings, new_embeddings]) if existing_embeddings.size else new_embeddings
    CHUNKS_FILE.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    np.savez_compressed(EMB_FILE, embeddings=all_embeddings.astype(np.float32))
    print(json.dumps({
        "old_chunks": len(existing_chunks),
        "added_chunks": len(new_chunks),
        "total_chunks": len(all_chunks),
        "embeddings_shape": list(all_embeddings.shape),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
