# Xiaozhi MCP strict RAG mode

This backup records the Aliyun `/opt/xiaozhi-mcp` strict citation setup.

Runtime paths:
- Mixed RAG backup on server: `/opt/xiaozhi-mcp/backups/rag_mixed_20260614_155202`
- Full strict candidate RAG: `/opt/xiaozhi-mcp/rag_strict`
- Active approved strict RAG: `/opt/xiaozhi-mcp/rag_strict_active`
- Active service: `xiaozhi-kb.service`
- Client bridge: `xiaozhi-client.service`

Strict behavior:
- `search_regulation` reads `rag_strict_active` by default.
- Only sources marked `approved` in `source_registry_active.json` are loaded into the active RAG.
- Duplicate, incomplete, or reference-only sources stay outside the active RAG.
- Low confidence results are refused with “未检索到足够可靠的标准规范依据”.
- Returned results include source file, authority level, priority, issuer, document number, year, page/article hint, similarity, and keyword coverage.
- The answer policy requires citation and forbids unsupported additions.

Governance files:
- `source_registry_all.json`: all strict-candidate sources with status and metadata.
- `source_registry_active.json`: approved sources currently loaded by the service.
- `source_review_todo.txt`: metadata gaps and disabled-source reasons.
- `scripts/build_source_registry.py`: regenerates the registry from `rag_strict`.

Important:
- Do not commit real API keys or Xiaozhi endpoint tokens. Use `/etc/xiaozhi-mcp.env` on the server.
- Reference materials such as textbooks, Q&A books, and work guides remain in the mixed backup, not the default strict RAG.
- If a disabled source is actually required, upload a complete authoritative copy and regenerate the registry.
