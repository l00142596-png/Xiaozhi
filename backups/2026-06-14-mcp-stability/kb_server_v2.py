"""知识库 MCP Server v2 — 支持 RAG 语义检索

工具:
  save_knowledge(title, content)     — 保存知识到本地 JSON 知识库
  search_knowledge(keywords)         — 关键词搜索 JSON 知识库
  list_all_knowledge()              — 列出 JSON 知识库所有标题
  search_regulation(query)          — RAG 语义搜索铁路法规（跨78个文件）
"""

import json
import os
import logging
from pathlib import Path

import numpy as np

from fastmcp import FastMCP

# ── 配置 ──
BASE_DIR = Path(os.environ.get("KB_BASE_DIR", "/opt/xiaozhi-mcp"))
DATA_FILE = Path(os.environ.get("KB_DATA_FILE", BASE_DIR / "knowledge.json"))
RAG_DIR = Path(os.environ.get("KB_RAG_DIR", BASE_DIR / "rag"))
CHUNKS_FILE = Path(os.environ.get("KB_CHUNKS_FILE", RAG_DIR / "chunks.json"))
EMB_FILE = Path(os.environ.get("KB_EMB_FILE", RAG_DIR / "embeddings.npz"))
MAX_RESULT = int(os.environ.get("KB_MAX_RESULT_BYTES", "1000"))
RAG_TOP_K = int(os.environ.get("KB_RAG_TOP_K", "5"))
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
HOST = os.environ.get("KB_HOST", "127.0.0.1")
PORT = int(os.environ.get("KB_PORT", "8766"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [KB] %(levelname)s %(message)s")
logger = logging.getLogger("kb_server")

mcp = FastMCP("知识库")

# ── RAG 数据（懒加载）──
_rag_chunks: list[dict] | None = None
_rag_embeddings: np.ndarray | None = None


def _load_rag():
    """懒加载 RAG 向量库"""
    global _rag_chunks, _rag_embeddings
    if _rag_chunks is not None:
        return
    if not CHUNKS_FILE.exists() or not EMB_FILE.exists():
        logger.warning("RAG 数据不存在: %s / %s", CHUNKS_FILE, EMB_FILE)
        return
    with CHUNKS_FILE.open("r", encoding="utf-8") as f:
        _rag_chunks = json.load(f)
    data = np.load(EMB_FILE)
    _rag_embeddings = data["embeddings"]
    logger.info("RAG 已加载: %d 块, 嵌入维度 %d", len(_rag_chunks), _rag_embeddings.shape[1])


def _embed_query(text: str) -> np.ndarray | None:
    """调用 DashScope API 生成查询向量"""
    import urllib.request

    if not DASHSCOPE_API_KEY:
        logger.error("DASHSCOPE_API_KEY is not set")
        return None

    url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    payload = json.dumps({
        "model": "text-embedding-v4",
        "input": {"texts": [text]},
        "parameters": {"text_type": "query"}
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            r = json.loads(resp.read())
            return np.array(r["output"]["embeddings"][0]["embedding"], dtype=np.float32)
    except Exception as e:
        logger.error("Embedding API 失败: %s", e)
        return None


def _cosine_search(query_vec: np.ndarray, top_k: int = RAG_TOP_K) -> list[dict]:
    """余弦相似度搜索"""
    q_norm_value = np.linalg.norm(query_vec)
    if q_norm_value == 0:
        return []
    embedding_norms = np.linalg.norm(_rag_embeddings, axis=1, keepdims=True)
    embedding_norms[embedding_norms == 0] = 1
    q_norm = query_vec / q_norm_value
    e_norm = _rag_embeddings / embedding_norms
    sims = np.dot(e_norm, q_norm)
    top_idx = np.argsort(sims)[::-1][:top_k]

    results = []
    for rank, idx in enumerate(top_idx):
        c = _rag_chunks[int(idx)]
        results.append({
            "rank": rank + 1,
            "similarity": round(float(sims[idx]), 4),
            "source": c["filename"],
            "title": c["title"],
            "text": c["text"]
        })
    return results


def _truncate(text: str, max_bytes: int = MAX_RESULT) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    result = text
    while len(result.encode("utf-8")) > max_bytes:
        result = result[:-1]
    return result.rstrip() + "…"


# ── JSON 知识库 ──
def _load_kb() -> dict:
    if not DATA_FILE.exists():
        return {}
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_kb(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════ MCP 工具 ═══════════════

@mcp.tool()
def save_knowledge(title: str, content: str) -> str:
    """保存一条知识到本地知识库。

何时使用：当用户明确要求"记住"、"保存"、"记录"某个信息时调用。
例如"帮我把这个规定存起来"、"记下这个知识点"。

参数：
- title: 知识的标题，用于后续查找和列表展示
- content: 知识的完整内容，可以是多行文本

返回：JSON 格式，result 字段包含保存确认信息。
"""
    logger.info("save_knowledge: title=%s", title)
    data = _load_kb()
    data[title] = content
    _save_kb(data)
    return json.dumps({"result": f"已保存知识「{title}」"}, ensure_ascii=False)


@mcp.tool()
def search_knowledge(keywords: str) -> str:
    """在知识库中按关键词搜索匹配的内容。

何时使用：当用户问"XX 是什么"、"关于 XX 有什么记录"、"帮我查一下 XX"时调用。
同时搜索标题和正文，只要任意一者包含关键词即命中。

参数：
- keywords: 搜索关键词，支持中英文，大小写不敏感

返回：JSON 格式，result 字段包含匹配的知识内容。
"""
    logger.info("search_knowledge: keywords=%s", keywords)
    data = _load_kb()
    results = []
    for title, content in data.items():
        if keywords.lower() in title.lower() or keywords.lower() in content.lower():
            results.append(f"【{title}】\n{content}")
    if not results:
        return json.dumps({"result": f"知识库中未找到与「{keywords}」相关的内容"}, ensure_ascii=False)
    combined = "\n\n---\n\n".join(results)
    return json.dumps({"result": _truncate(combined)}, ensure_ascii=False)


@mcp.tool()
def list_all_knowledge() -> str:
    """列出知识库中所有知识的标题。

何时使用：当用户问"知识库里有什么"、"有哪些知识"、"列出所有条目"时调用。
仅返回标题列表，方便快速浏览。

返回：JSON 格式，result 字段包含编号的标题列表。
"""
    logger.info("list_all_knowledge called")
    data = _load_kb()
    if not data:
        return json.dumps({"result": "知识库目前为空"}, ensure_ascii=False)
    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(data.keys(), 1))
    return json.dumps({"result": f"知识库共有 {len(data)} 条知识：\n{titles}"}, ensure_ascii=False)


@mcp.tool()
def search_regulation(query: str) -> str:
    """RAG 语义搜索铁路法规知识库（覆盖铁路技术管理规程、施工管理办法、安全管理条例等78个文件）。

何时使用：
- 当用户询问铁路施工、安全、技术标准等专业问题时调用
- 当 search_knowledge 搜不到内容时调用此工具补充
- 例如："隧道施工有什么安全要求"、"高速铁路线路维修标准是什么"、"接触网作业有什么规定"

参数：
- query: 完整的查询问题，越具体越好。例如"既有线施工安全防护要求"比"安全"更好

返回：JSON 格式，result 字段包含 top-5 个最相关的法规条文及来源文件。
"""
    logger.info("search_regulation: query=%s", query)
    _load_rag()

    if _rag_chunks is None or _rag_embeddings is None:
        return json.dumps({"result": "RAG 法规知识库尚未加载，请联系管理员上传"}, ensure_ascii=False)

    q_vec = _embed_query(query)
    if q_vec is None:
        return json.dumps({"result": "语义搜索服务暂时不可用（API故障），请改用 search_knowledge 试试"}, ensure_ascii=False)

    results = _cosine_search(q_vec)

    output_parts = []
    for r in results:
        output_parts.append(
            f"【{r['title'] or '相关条文'}】(来源: {r['source'][:50]}, 相关度: {r['similarity']})\n{r['text']}"
        )

    combined = "\n\n---\n\n".join(output_parts)
    logger.info("RAG 搜索完成: %d 条结果, %d 字节", len(results), len(combined.encode("utf-8")))
    return json.dumps({"result": _truncate(combined)}, ensure_ascii=False)


if __name__ == "__main__":
    _load_rag()
    logger.info("Starting KB Server v2 on %s:%d (4 tools)", HOST, PORT)
    mcp.run(transport="sse", host=HOST, port=PORT)
