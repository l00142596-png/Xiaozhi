"""Xiaozhi Knowledge Base MCP Server v2.

Tools:
  save_knowledge(title, content)     - Save one JSON knowledge item
  search_knowledge(keywords)         - Keyword search JSON knowledge
  list_all_knowledge()               - List JSON knowledge titles
  search_regulation(query)           - Strict citation RAG search for railway rules
"""

import json
import logging
import os
import re
from pathlib import Path

import numpy as np
from fastmcp import FastMCP

BASE_DIR = Path(os.environ.get("KB_BASE_DIR", "/opt/xiaozhi-mcp"))
DATA_FILE = Path(os.environ.get("KB_DATA_FILE", BASE_DIR / "knowledge.json"))
DEFAULT_RAG_DIR = BASE_DIR / "rag_strict"
if not DEFAULT_RAG_DIR.exists():
    DEFAULT_RAG_DIR = BASE_DIR / "rag"
RAG_DIR = Path(os.environ.get("KB_RAG_DIR", DEFAULT_RAG_DIR))
CHUNKS_FILE = Path(os.environ.get("KB_CHUNKS_FILE", RAG_DIR / "chunks.json"))
EMB_FILE = Path(os.environ.get("KB_EMB_FILE", RAG_DIR / "embeddings.npz"))
SOURCE_REGISTRY_FILE = Path(os.environ.get("KB_SOURCE_REGISTRY", RAG_DIR / "source_registry.json"))
MAX_RESULT = int(os.environ.get("KB_MAX_RESULT_BYTES", "2400"))
RAG_TOP_K = int(os.environ.get("KB_RAG_TOP_K", "6"))
STRICT_MIN_SIMILARITY = float(os.environ.get("KB_STRICT_MIN_SIMILARITY", "0.60"))
RESULT_MIN_SIMILARITY = float(os.environ.get("KB_RESULT_MIN_SIMILARITY", "0.52"))
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
HOST = os.environ.get("KB_HOST", "127.0.0.1")
PORT = int(os.environ.get("KB_PORT", "8766"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [KB] %(levelname)s %(message)s")
logger = logging.getLogger("kb_server")

mcp = FastMCP("知识库")

_rag_chunks: list[dict] | None = None
_rag_embeddings: np.ndarray | None = None
_source_registry: dict[str, dict] | None = None


def _load_rag():
    """Lazy-load RAG chunks and embeddings."""
    global _rag_chunks, _rag_embeddings
    if _rag_chunks is not None:
        return
    if not CHUNKS_FILE.exists() or not EMB_FILE.exists():
        logger.warning("RAG data missing: %s / %s", CHUNKS_FILE, EMB_FILE)
        return
    with CHUNKS_FILE.open("r", encoding="utf-8") as f:
        _rag_chunks = json.load(f)
    data = np.load(EMB_FILE)
    _rag_embeddings = data["embeddings"]
    if len(_rag_chunks) != len(_rag_embeddings):
        logger.error("RAG mismatch: chunks=%d embeddings=%d", len(_rag_chunks), len(_rag_embeddings))
        _rag_chunks = None
        _rag_embeddings = None
        return
    _load_source_registry()
    logger.info(
        "RAG loaded: dir=%s chunks=%d dim=%d strict_min=%.2f result_min=%.2f",
        RAG_DIR,
        len(_rag_chunks),
        _rag_embeddings.shape[1],
        STRICT_MIN_SIMILARITY,
        RESULT_MIN_SIMILARITY,
    )


def _embed_query(text: str) -> np.ndarray | None:
    """Call DashScope embedding API."""
    import urllib.request

    if not DASHSCOPE_API_KEY:
        logger.error("DASHSCOPE_API_KEY is not set")
        return None

    url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    payload = json.dumps({
        "model": "text-embedding-v4",
        "input": {"texts": [text]},
        "parameters": {"text_type": "query"},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            r = json.loads(resp.read())
            return np.array(r["output"]["embeddings"][0]["embedding"], dtype=np.float32)
    except Exception as e:
        logger.error("Embedding API failed: %s", e)
        return None


def _load_source_registry() -> dict[str, dict]:
    """Load approved-source metadata for strict citation governance."""
    global _source_registry
    if _source_registry is not None:
        return _source_registry
    _source_registry = {}
    if SOURCE_REGISTRY_FILE.exists():
        try:
            data = json.loads(SOURCE_REGISTRY_FILE.read_text(encoding="utf-8"))
            _source_registry = {item.get("filename", ""): item for item in data if item.get("filename")}
            logger.info("Source registry loaded: %d sources from %s", len(_source_registry), SOURCE_REGISTRY_FILE)
        except Exception as e:
            logger.error("Source registry load failed: %s", e)
    else:
        logger.warning("Source registry missing: %s; fallback allows all loaded sources", SOURCE_REGISTRY_FILE)
    return _source_registry


def _source_meta(filename: str) -> dict:
    registry = _load_source_registry()
    meta = registry.get(filename)
    if meta:
        return meta
    level, priority = _infer_source_level(filename)
    return {
        "filename": filename,
        "status": "approved",
        "authority_level": level,
        "priority": priority,
        "document_type": "unregistered",
        "issuer": "",
        "document_no": "",
        "effective_year": None,
        "effective_date": "",
        "scope": "",
        "review_notes": ["未登记来源，建议补录元数据"],
    }


def _source_is_approved(filename: str) -> bool:
    meta = _source_meta(filename)
    return meta.get("status", "approved") == "approved"


def _source_priority(filename: str) -> int:
    return int(_source_meta(filename).get("priority", 60) or 60)


def _infer_source_level(filename: str) -> tuple[str, int]:
    if any(x in filename for x in ["中华人民共和国", "国务院", "铁路安全管理条例", "铁路法"]):
        return "法律法规/行政法规", 100
    if any(x in filename for x in ["国铁", "国家铁路局", "中国铁路总公司", "铁总", "铁调"]):
        return "国家铁路/国铁集团文件", 90
    if any(x in filename for x in ["TG ", "TGGW", "规则", "规程", "技规"]):
        return "技术规章/行业规则", 80
    if any(x in filename for x in ["上铁", "成铁", "局集团"]):
        return "局集团实施细则", 70
    return "规范资料", 60


def _source_level(filename: str) -> str:
    return str(_source_meta(filename).get("authority_level") or _infer_source_level(filename)[0])


def _extract_page(chunk: dict) -> str:
    title = str(chunk.get("title", ""))
    text = " ".join(str(chunk.get(k, "")) for k in ("id", "title", "filename"))
    article = re.search(r"(第[一二三四五六七八九十百千万零〇两0-9]+[条章节款项])", title)
    if article:
        return article.group(1)
    m = re.search(r"第\s*(\d+)\s*页", text)
    if m:
        return f"第{m.group(1)}页"
    m = re.search(r"[_-]p(?:age)?[_-]?(\d+)", text, re.IGNORECASE)
    if m:
        return f"第{m.group(1)}页"
    return "页码/条目未识别"

def _keyword_coverage(query: str, body: str) -> float:
    chars = re.findall(r"[\u4e00-\u9fff]", query)
    bigrams = {"".join(chars[i:i + 2]) for i in range(max(0, len(chars) - 1))}
    stop = {"什么", "如何", "是否", "有关", "规定", "要求", "标准", "铁路"}
    terms = {x for x in bigrams if x not in stop}
    terms.update(re.findall(r"[A-Za-z0-9]{2,}", query.lower()))
    if not terms:
        return 0.0
    body_l = body.lower()
    hits = sum(1 for t in terms if t in body_l)
    return hits / len(terms)


def _tail_clause_penalty(query: str, body: str) -> float:
    query_l = query.lower()
    if any(x in query for x in ["废止", "施行", "生效", "附件", "格式"]):
        return 0.0
    head = body[:700]
    if any(x in head for x in ["同时废止", "本办法自", "附件:", "附件：", "格式"]):
        return 0.08
    return 0.0


def _cosine_search(query_vec: np.ndarray, query_text: str, top_k: int = RAG_TOP_K) -> list[dict]:
    """Hybrid search: semantic candidates reranked by keyword coverage."""
    if _rag_chunks is None or _rag_embeddings is None:
        return []
    q_norm_value = np.linalg.norm(query_vec)
    if q_norm_value == 0:
        return []
    embedding_norms = np.linalg.norm(_rag_embeddings, axis=1, keepdims=True)
    embedding_norms[embedding_norms == 0] = 1
    q_norm = query_vec / q_norm_value
    e_norm = _rag_embeddings / embedding_norms
    sims = np.dot(e_norm, q_norm)
    pool_size = min(len(sims), max(top_k * 10, 50))
    candidate_idx = np.argsort(sims)[::-1][:pool_size]

    scored = []
    for idx in candidate_idx:
        c = _rag_chunks[int(idx)]
        filename = c.get("filename", "未知来源")
        if not _source_is_approved(filename):
            continue
        body = f"{filename} {c.get('title', '')} {c.get('text', '')}"
        similarity = float(sims[idx])
        coverage = _keyword_coverage(query_text, body)
        penalty = _tail_clause_penalty(query_text, body)
        authority_boost = max(0, _source_priority(filename) - 60) / 1000
        hybrid = similarity + 0.08 * coverage + authority_boost - penalty
        scored.append((hybrid, similarity, coverage, penalty, idx))
    scored.sort(reverse=True, key=lambda x: x[0])

    results = []
    for rank, (hybrid, similarity, coverage, penalty, idx) in enumerate(scored[:top_k]):
        c = _rag_chunks[int(idx)]
        filename = c.get("filename", "未知来源")
        meta = _source_meta(filename)
        results.append({
            "rank": rank + 1,
            "similarity": round(similarity, 4),
            "hybrid_score": round(float(hybrid), 4),
            "keyword_coverage": round(float(coverage), 4),
            "source": filename,
            "source_status": meta.get("status", "approved"),
            "source_priority": meta.get("priority", _source_priority(filename)),
            "document_no": meta.get("document_no", ""),
            "issuer": meta.get("issuer", ""),
            "effective_year": meta.get("effective_year"),
            "source_level": _source_level(filename),
            "page": _extract_page(c),
            "title": c.get("title") or "相关条文",
            "text": c.get("text", ""),
        })
    return results


def _truncate(text: str, max_bytes: int = MAX_RESULT) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    result = text
    while len(result.encode("utf-8")) > max_bytes:
        result = result[:-1]
    return result.rstrip() + "..."


def _load_kb() -> dict:
    if not DATA_FILE.exists():
        return {}
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_kb(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@mcp.tool()
def save_knowledge(title: str, content: str) -> str:
    """保存一条知识到本地知识库。"""
    logger.info("save_knowledge: title=%s", title)
    data = _load_kb()
    data[title] = content
    _save_kb(data)
    return json.dumps({"result": f"已保存知识《{title}》"}, ensure_ascii=False)


@mcp.tool()
def search_knowledge(keywords: str) -> str:
    """在本地 JSON 知识库中按关键词搜索。"""
    logger.info("search_knowledge: keywords=%s", keywords)
    data = _load_kb()
    results = []
    for title, content in data.items():
        if keywords.lower() in title.lower() or keywords.lower() in content.lower():
            results.append(f"【{title}】\n{content}")
    if not results:
        return json.dumps({"result": f"知识库中未找到与《{keywords}》相关的内容"}, ensure_ascii=False)
    combined = "\n\n---\n\n".join(results)
    return json.dumps({"result": _truncate(combined)}, ensure_ascii=False)


@mcp.tool()
def list_all_knowledge() -> str:
    """列出本地 JSON 知识库中所有知识标题。"""
    logger.info("list_all_knowledge called")
    data = _load_kb()
    if not data:
        return json.dumps({"result": "知识库目前为空"}, ensure_ascii=False)
    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(data.keys(), 1))
    return json.dumps({"result": f"知识库共有 {len(data)} 条知识：\n{titles}"}, ensure_ascii=False)


@mcp.tool()
def search_regulation(query: str) -> str:
    """严格检索铁路法规、规程、规则、标准和正式管理文件。

使用要求：涉及铁路施工、安全、技术标准、作业限制、设备维修、营业线管理等问题时，必须先调用本工具。
回答要求：只能依据本工具返回的原文摘录回答；必须引用来源文件和页码/条目；未检索到可靠依据时必须明确说“未检索到可靠依据”，不得凭经验补充。
"""
    logger.info("search_regulation: query=%s", query)
    _load_rag()

    if _rag_chunks is None or _rag_embeddings is None:
        return json.dumps({
            "mode": "strict_citation",
            "result": "严格法规知识库尚未加载或数据不一致，请联系管理员。",
            "answer_policy": "不得凭经验回答。",
        }, ensure_ascii=False)

    q_vec = _embed_query(query)
    if q_vec is None:
        return json.dumps({
            "mode": "strict_citation",
            "result": "语义检索服务暂时不可用，未取得可靠法规依据。",
            "answer_policy": "不得凭经验回答；请稍后重试或要求管理员检查 DASHSCOPE_API_KEY。",
        }, ensure_ascii=False)

    results = _cosine_search(q_vec, query)
    top_similarity = results[0]["similarity"] if results else 0.0
    if not results or top_similarity < STRICT_MIN_SIMILARITY:
        logger.info("RAG strict refusal: top_similarity=%.4f query=%s", top_similarity, query)
        return json.dumps({
            "mode": "strict_citation",
            "result": "未检索到足够可靠的标准规范依据。请缩小问题范围，或指定文件名、条款号、专业方向后重新查询。",
            "top_similarity": top_similarity,
            "threshold": STRICT_MIN_SIMILARITY,
            "answer_policy": "必须回答：未检索到可靠依据。不得编造条款、数值、流程或出处。",
        }, ensure_ascii=False)

    filtered = [r for r in results if r["similarity"] >= RESULT_MIN_SIMILARITY]
    output_parts = [
        "严格引用模式：只能依据以下检索结果回答；必须引用[编号]、来源文件和页码/条目；未覆盖的内容必须说明未检索到可靠依据。"
    ]
    citations = []
    for i, r in enumerate(filtered, 1):
        snippet = _truncate(r["text"], 650)
        output_parts.append(
            f"[{i}] 来源文件：{r['source']}\n"
            f"资料级别：{r['source_level']}，优先级：{r.get('source_priority', '')}\n"
            f"发布单位：{r.get('issuer') or '待补录'}；文号：{r.get('document_no') or '待补录'}；年份：{r.get('effective_year') or '待补录'}\n"
            f"位置：{r['page']}\n"
            f"标题：{r['title']}\n"
            f"相关度：{r['similarity']}，关键词覆盖：{r.get('keyword_coverage', 0)}\n"
            f"原文摘录：{snippet}"
        )
        citations.append({
            "ref": i,
            "source": r["source"],
            "source_level": r["source_level"],
            "source_priority": r.get("source_priority"),
            "document_no": r.get("document_no", ""),
            "issuer": r.get("issuer", ""),
            "effective_year": r.get("effective_year"),
            "page": r["page"],
            "title": r["title"],
            "similarity": r["similarity"],
            "keyword_coverage": r.get("keyword_coverage", 0),
        })

    combined = "\n\n---\n\n".join(output_parts)
    logger.info("RAG strict search: results=%d top=%.4f bytes=%d", len(filtered), top_similarity, len(combined.encode("utf-8")))
    return json.dumps({
        "mode": "strict_citation",
        "result": _truncate(combined),
        "top_similarity": top_similarity,
        "threshold": STRICT_MIN_SIMILARITY,
        "citations": citations,
        "answer_policy": "只能基于 result 中的原文摘录回答；必须引用来源；不得添加未被摘录支持的内容。",
    }, ensure_ascii=False)


if __name__ == "__main__":
    _load_rag()
    logger.info("Starting KB Server v2 on %s:%d (4 tools, rag=%s)", HOST, PORT, RAG_DIR)
    mcp.run(transport="sse", host=HOST, port=PORT)
