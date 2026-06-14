# Xiaozhi MCP strict RAG mode

This backup records the Aliyun `/opt/xiaozhi-mcp` strict citation setup.

Runtime paths:
- Mixed RAG backup on server: `/opt/xiaozhi-mcp/backups/rag_mixed_20260614_155202`
- Full strict candidate RAG: `/opt/xiaozhi-mcp/rag_strict`
- Active approved strict RAG: `/opt/xiaozhi-mcp/rag_strict_active`
- Active service: `xiaozhi-kb.service`
- Client bridge: `xiaozhi-client.service`

Current active strict RAG:
- Sources: 36
- Chunks: 15637
- `TG GD 115-2017 普速铁路接触网安全工作规则.pdf` is approved and included with 41 OCR chunks.

Strict behavior:
- `search_regulation` reads `rag_strict_active` by default.
- Only sources marked `approved` in `source_registry_active.json` are loaded into the active RAG.
- Duplicate, incomplete, rejected, or reference-only sources stay outside the active RAG.
- If the user explicitly names a disabled source/document number, the tool refuses to answer from similar files.
- If the user explicitly names an approved source/document number/title, the tool restricts search to that source.
- Low confidence results are refused with “未检索到足够可靠的标准规范依据”.
- Returned results include source file, authority level, priority, issuer, document number, year, page/article hint, similarity, keyword coverage, railway scope, and discipline.
- Domain-aware ranking keeps explicit sub-domain queries inside the right norm family where possible.

Important:
- Do not commit real API keys or Xiaozhi endpoint tokens. Use `/etc/xiaozhi-mcp.env` on the server.
- Reference materials such as textbooks, Q&A books, and work guides remain in the mixed backup, not the default strict RAG.
