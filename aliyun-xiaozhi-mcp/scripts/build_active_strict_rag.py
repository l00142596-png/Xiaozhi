#!/usr/bin/env python3
"""Build rag_strict_active from approved sources in rag_strict/source_registry.json."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

BASE = Path('/opt/xiaozhi-mcp')
SRC = BASE / 'rag_strict'
OUT = BASE / 'rag_strict_active'


def main() -> int:
    chunks = json.loads((SRC / 'chunks.json').read_text(encoding='utf-8'))
    embeddings = np.load(SRC / 'embeddings.npz')['embeddings']
    if len(chunks) != len(embeddings):
        raise RuntimeError(f'rag_strict mismatch: chunks={len(chunks)} embeddings={len(embeddings)}')

    registry = json.loads((SRC / 'source_registry.json').read_text(encoding='utf-8'))
    approved_registry = [r for r in registry if r.get('status') == 'approved']
    approved = {r['filename'] for r in approved_registry}
    keep = [i for i, c in enumerate(chunks) if c.get('filename') in approved]

    OUT.mkdir(parents=True, exist_ok=True)
    active_chunks = [chunks[i] for i in keep]
    (OUT / 'chunks.json').write_text(json.dumps(active_chunks, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    np.savez_compressed(OUT / 'embeddings.npz', embeddings=embeddings[keep].astype(np.float32))
    (OUT / 'source_registry.json').write_text(json.dumps(approved_registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    sources = {}
    for c in active_chunks:
        fn = c.get('filename', 'UNKNOWN')
        sources[fn] = sources.get(fn, 0) + 1
    (OUT / 'sources.txt').write_text('\n'.join(f'{n}\t{s}' for s, n in sorted(sources.items())) + '\n', encoding='utf-8')

    print(json.dumps({
        'source_chunks': len(chunks),
        'source_embeddings': list(embeddings.shape),
        'active_chunks': len(active_chunks),
        'active_sources': len(sources),
        'disabled_sources': len(registry) - len(approved_registry),
        'out': str(OUT),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
