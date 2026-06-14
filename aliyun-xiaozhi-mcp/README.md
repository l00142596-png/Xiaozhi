# Xiaozhi MCP strict RAG mode

This backup records the Aliyun `/opt/xiaozhi-mcp` strict citation setup.

Runtime paths:
- Mixed RAG backup on server: `/opt/xiaozhi-mcp/backups/rag_mixed_20260614_155202`
- Full strict candidate RAG: `/opt/xiaozhi-mcp/rag_strict`
- Active approved strict RAG: `/opt/xiaozhi-mcp/rag_strict_active`
- Rejected/manual-hold files: `/opt/xiaozhi-mcp/rejected_sources`
- Active service: `xiaozhi-kb.service`
- Client bridge: `xiaozhi-client.service`

Strict behavior:
- `search_regulation` reads `rag_strict_active` by default.
- Only sources marked `approved` in `source_registry_active.json` are loaded into the active RAG.
- Duplicate, incomplete, rejected, or reference-only sources stay outside the active RAG.
- If the user explicitly names a disabled source/document number, the tool refuses to answer from similar files.
- Low confidence results are refused with “未检索到足够可靠的标准规范依据”.
- Returned results include source file, authority level, priority, issuer, document number, year, page/article hint, similarity, and keyword coverage.
- The answer policy requires citation and forbids unsupported additions.

Governance files:
- `source_registry_all.json`: all strict-candidate sources with status and metadata.
- `source_registry_active.json`: approved sources currently loaded by the service.
- `source_overrides.json`: manual decisions that must survive registry regeneration.
- `source_review_todo.txt`: metadata gaps and disabled-source reasons.
- `scripts/build_source_registry.py`: regenerates the registry from `rag_strict` and applies overrides.
- `scripts/build_active_strict_rag.py`: regenerates `rag_strict_active` from approved sources.

Important:
- Do not commit real API keys or Xiaozhi endpoint tokens. Use `/etc/xiaozhi-mcp.env` on the server.
- Reference materials such as textbooks, Q&A books, and work guides remain in the mixed backup, not the default strict RAG.
- `TG GD 115-2017 普速铁路接触网安全工作规则.pdf` is explicitly disabled because the user confirmed it is not the same required norm. Provide the correct complete file before enabling it.
