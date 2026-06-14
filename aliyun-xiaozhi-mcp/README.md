# Xiaozhi MCP strict RAG mode

This backup records the Aliyun `/opt/xiaozhi-mcp` strict citation setup.

Runtime paths:
- Mixed RAG backup on server: `/opt/xiaozhi-mcp/backups/rag_mixed_20260614_155202`
- Active strict RAG: `/opt/xiaozhi-mcp/rag_strict`
- Active service: `xiaozhi-kb.service`
- Client bridge: `xiaozhi-client.service`

Strict behavior:
- `search_regulation` reads `rag_strict` by default.
- Low confidence results are refused with “未检索到足够可靠的标准规范依据”.
- Returned results include source file, source level, page/article hint, similarity, and keyword coverage.
- The answer policy requires citation and forbids unsupported additions.

Important:
- Do not commit real API keys. Use `/etc/xiaozhi-mcp.env` on the server.
- Reference materials such as textbooks, Q&A books, and work guides remain in the mixed backup, not the default strict RAG.
