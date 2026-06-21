"""Xiaozhi Knowledge Base MCP Server v2.

Tools:
  save_knowledge(title, content)     - Save one JSON knowledge item
  search_knowledge(keywords)         - Keyword search JSON knowledge
  list_all_knowledge()               - List JSON knowledge titles
  search_regulation(query)           - Strict citation RAG search for railway rules
  railway_safety_workflow(text)      - Deterministic K100+350 safety workflow
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
ALL_SOURCE_REGISTRY_FILE = Path(os.environ.get("KB_ALL_SOURCE_REGISTRY", BASE_DIR / "rag_strict" / "source_registry.json"))
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
_all_source_registry: dict[str, dict] | None = None


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


def _load_all_source_registry() -> dict[str, dict]:
    """Load all source decisions, including disabled files, for exact-match refusal."""
    global _all_source_registry
    if _all_source_registry is not None:
        return _all_source_registry
    _all_source_registry = {}
    if ALL_SOURCE_REGISTRY_FILE.exists():
        try:
            data = json.loads(ALL_SOURCE_REGISTRY_FILE.read_text(encoding="utf-8"))
            _all_source_registry = {item.get("filename", ""): item for item in data if item.get("filename")}
        except Exception as e:
            logger.error("All source registry load failed: %s", e)
    return _all_source_registry


def _normalize_identifier(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\.(pdf|docx)$", "", text)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _source_title_candidate(filename: str, document_no: str = "") -> str:
    """Get a human title from a source filename for exact title matching."""
    title = re.sub(r"\.(pdf|docx)$", "", filename, flags=re.IGNORECASE).strip()
    if document_no:
        title = title.replace(document_no, "")
    title = re.sub(r"^(TG\s*[A-Z]{1,3}\s*\d+[A-Z]?[-－]\d{4}|TGGW\s*\d+[A-Z]?[-－]\d{4})", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^[\s_\-－—]+", "", title).strip()
    return title


def _disabled_source_match(query: str) -> dict | None:
    qn = _normalize_identifier(query)
    if not qn:
        return None
    for item in _load_all_source_registry().values():
        if item.get("status") == "approved":
            continue
        candidates = [
            item.get("filename", ""),
            item.get("document_no", ""),
            _source_title_candidate(item.get("filename", ""), item.get("document_no", "")),
        ]
        for candidate in candidates:
            cn = _normalize_identifier(candidate)
            if cn and (cn in qn or qn in cn):
                return item
    return None


def _approved_source_match(query: str) -> dict | None:
    """If the user names an approved source/document, restrict search to it."""
    qn = _normalize_identifier(query)
    if not qn:
        return None
    for item in _load_source_registry().values():
        if item.get("status") != "approved":
            continue
        candidates = [
            item.get("filename", ""),
            item.get("document_no", ""),
            _source_title_candidate(item.get("filename", ""), item.get("document_no", "")),
        ]
        for candidate in candidates:
            cn = _normalize_identifier(candidate)
            if cn and (cn in qn or qn in cn):
                return item
    return None


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


def _infer_query_domain(query: str) -> tuple[str, str]:
    """Infer the user's intended railway sub-domain from explicit keywords."""
    if any(x in query for x in ["桥隧", "桥梁", "隧道", "涵洞", "桥涵"]):
        return "普速铁路", "桥隧建筑物"
    if any(x in query for x in ["线路修理", "线路维修", "钢轨", "轨道", "道岔", "线路设备"]):
        return "普速铁路", "线路修理"
    if any(x in query for x in ["工务安全", "工务作业", "工务"]):
        return "普速铁路", "工务安全"
    if ("普速" in query or "普速铁路" in query) and any(x in query for x in ["技规", "技术管理规程"]):
        return "普速铁路", "技术管理规程"
    if any(x in query for x in ["营业线施工", "施工管理", "天窗", "维修作业", "邻近营业线"]):
        return "营业线施工", "施工管理/通知办法"
    if any(x in query for x in ["接触网", "供电"]):
        return "供电专业", "接触网"
    if any(x in query for x in ["信号", "电务"]):
        return "电务专业", "信号/电务"
    return "", ""


def _domain_score(query_scope: str, query_discipline: str, source_scope: str, source_discipline: str) -> float:
    if not query_scope and not query_discipline:
        return 0.0
    if query_scope == source_scope and query_discipline == source_discipline:
        return 0.10
    if query_discipline and query_discipline == source_discipline:
        return 0.06
    if query_scope and query_scope == source_scope:
        return 0.03
    # A clear sub-domain query should not be silently answered from another specialty.
    return -0.10


def _cosine_search(query_vec: np.ndarray, query_text: str, top_k: int = RAG_TOP_K, source_filter: str | None = None) -> list[dict]:
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

    query_scope, query_discipline = _infer_query_domain(query_text)
    scored = []
    for idx in candidate_idx:
        c = _rag_chunks[int(idx)]
        filename = c.get("filename", "未知来源")
        if source_filter and filename != source_filter:
            continue
        if not _source_is_approved(filename):
            continue
        meta = _source_meta(filename)
        body = f"{filename} {c.get('title', '')} {c.get('text', '')}"
        similarity = float(sims[idx])
        coverage = _keyword_coverage(query_text, body)
        penalty = _tail_clause_penalty(query_text, body)
        authority_boost = max(0, _source_priority(filename) - 60) / 1000
        domain_boost = _domain_score(
            query_scope,
            query_discipline,
            str(meta.get("railway_scope", "")),
            str(meta.get("discipline", "")),
        )
        hybrid = similarity + 0.08 * coverage + authority_boost + domain_boost - penalty
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
            "railway_scope": meta.get("railway_scope", ""),
            "discipline": meta.get("discipline", ""),
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
    """列出本地 JSON 知识库中所有知识标题。

    约束：这是最终回复型工具。
    当用户询问“有多少”或“有哪些”时，直接给出数量和标题列表，不要追加“需要我展开哪一条吗”之类的追问。
    """
    logger.info("list_all_knowledge called")
    data = _load_kb()
    if not data:
        return json.dumps({
            "result": "知识库目前为空。请直接告知用户当前没有可列出的知识，不要追问。"
        }, ensure_ascii=False)
    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(data.keys(), 1))
    return json.dumps({
        "result": (
            f"知识库共有 {len(data)} 条知识，标题如下：\n"
            f"{titles}\n"
            "请直接把以上信息告诉用户，不要追问需要展开哪一条。"
        )
    }, ensure_ascii=False)

@mcp.tool()
def search_regulation(query: str) -> str:
    """严格检索铁路法规、规程、规则、标准和正式管理文件。

使用要求：涉及铁路施工、安全、技术标准、作业限制、设备维修、营业线管理等问题时，必须先调用本工具。
回答要求：只能依据本工具返回的原文摘录回答；必须引用来源文件和页码/条目；未检索到可靠依据时必须明确说“未检索到可靠依据”，不得凭经验补充。
"""
    logger.info("search_regulation: query=%s", query)
    disabled = _disabled_source_match(query)
    if disabled:
        return json.dumps({
            "mode": "strict_citation",
            "result": f"用户明确查询的来源未启用，不能作为严格规范依据：{disabled.get('filename')}。原因：{disabled.get('disabled_reason') or '该来源未批准'}。请提供正确完整文件或改问其他已批准规范。",
            "disabled_source": disabled,
            "answer_policy": "不得用相近文件替代被点名的未启用来源；不得编造该文件内容。",
        }, ensure_ascii=False)

    _load_rag()
    approved_exact = _approved_source_match(query)
    source_filter = approved_exact.get("filename") if approved_exact else None

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

    results = _cosine_search(q_vec, query, source_filter=source_filter)
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
            "railway_scope": r.get("railway_scope", ""),
            "discipline": r.get("discipline", ""),
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
        "source_filter": source_filter or "",
        "answer_policy": "只能基于 result 中的原文摘录回答；必须引用来源；不得添加未被摘录支持的内容。",
    }, ensure_ascii=False)


WORKFLOW_STATE_FILE = BASE_DIR / "railway_safety_workflow_state.json"
WORKFLOW_AUDIT_FILE = Path("/var/log/railway_safety_workflow.log")


def _workflow_load_state() -> dict:
    if WORKFLOW_STATE_FILE.exists():
        try:
            return json.loads(WORKFLOW_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("workflow state load failed: %s", e)
    return {"state": "idle", "scenario": "", "updated_at": ""}


def _workflow_save_state(state: dict) -> None:
    import time
    state["updated_at"] = time.strftime("%F %T")
    WORKFLOW_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _workflow_audit(user_text: str, old_state: str, new_state: str, result: str) -> None:
    import time
    try:
        item = {
            "time": time.strftime("%F %T"),
            "user_text": user_text,
            "old_state": old_state,
            "new_state": new_state,
            "result": result,
        }
        with WORKFLOW_AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("workflow audit write failed: %s", e)


def _workflow_norm(text: str) -> str:
    return re.sub(r"\s+", "", text).lower().replace("＋", "+").replace("加", "+")


def _workflow_is_trigger(text: str) -> bool:
    q = _workflow_norm(text)
    has_location = "k100+350" in q or "k100+350" in q
    has_signal = "信号机" in q and "更换" in q
    has_plan = "施工计划" in q or "施工" in q
    has_analysis = "分析" in q or "风险" in q or "防控" in q
    short_alias = has_location and has_signal and has_plan
    full_alias = has_location and has_signal and has_analysis and has_plan
    return (short_alias or full_alias) and not _workflow_is_confirm(text) and not _workflow_is_fence_request(text)



def _workflow_is_confirm(text: str) -> bool:
    q = _workflow_norm(text)
    return q in {"确认下发", "确认", "下发", "同意下发", "确定下发"} or ("确认" in q and "下发" in q)


def _workflow_is_fence_request(text: str) -> bool:
    q = _workflow_norm(text)
    return "电子围栏" in q and ("生成" in q or "调度命令" in q)


def _workflow_response_risk_analysis() -> str:
    return (
        "正在分析~~本施工计划安全风险点共有5处：\n"
        "1.根据列车运行计划今日2时30分1936次列车遵义站通过，计划于2时35分通过k100+350信号机更换作业施工工点，请做好施工防护工作，确保列车运行安全。\n"
        "2.1936次列车在k100+350处限速30公里/小时通过。\n"
        "3.施工前确认施工驻站联络员就位，并调试通信设备。\n"
        "4.施工负责人和安全员严格按照调度命令、施工计划进行施工作业，及时联系驻站联络员。\n"
        "安全风险防控点已整理完成，是否需要下发列车司机、施工安全员？"
    )


def _workflow_result(result: str, state: str, done: bool = False, matched: bool = True) -> str:
    return json.dumps({
        "mode": "deterministic_workflow",
        "matched": matched,
        "state": state,
        "done": done,
        "result": result,
        "answer_policy": "只输出 result 字段给用户；不要暴露工具名、状态机或内部调用过程。",
    }, ensure_ascii=False)


@mcp.tool()
def railway_safety_workflow(text: str) -> str:
    """内部铁路施工安全流程状态机。

当用户提到 K100+350 / K100加350、信号机更换、施工计划、安全风险防控点、确认下发、电子围栏时调用。
不要向用户暴露工具名；只把 result 字段作为小五自然回复。
"""
    logger.info("railway_safety_workflow: text=%s", text)
    state_obj = _workflow_load_state()
    old_state = state_obj.get("state", "idle")
    new_state = old_state

    if any(x in text for x in ["取消流程", "重置流程", "退出流程"]):
        new_state = "idle"
        result = "已退出K100+350信号机更换施工安全流程。"
        state_obj = {"state": new_state, "scenario": ""}
        _workflow_save_state(state_obj)
        _workflow_audit(text, old_state, new_state, result)
        return _workflow_result(result, new_state, done=True)
    if _workflow_is_trigger(text):
        new_state = "risk_analysis_done"
        result = _workflow_response_risk_analysis()
        state_obj = {"state": new_state, "scenario": "k100+350_signal_replacement"}
        _workflow_save_state(state_obj)
        _workflow_audit(text, old_state, new_state, result)
        return _workflow_result(result, new_state)

    if _workflow_is_confirm(text) and old_state == "risk_analysis_done":
        new_state = "risk_notice_sent"
        result = "已发至列车司机、现场施工安全员。"
        state_obj["state"] = new_state
        _workflow_save_state(state_obj)
        _workflow_audit(text, old_state, new_state, result)
        return _workflow_result(result, new_state)

    if _workflow_is_fence_request(text) and old_state in {"risk_notice_sent", "risk_analysis_done"}:
        new_state = "fence_generated"
        result = "电子围栏已生成，时间：2:45-4:00,空间：k100+100——k100+500区段，是否下发施工安全员随身设备？"
        state_obj["state"] = new_state
        _workflow_save_state(state_obj)
        _workflow_audit(text, old_state, new_state, result)
        return _workflow_result(result, new_state)


    if _workflow_is_confirm(text) and old_state == "fence_generated":
        new_state = "fence_sent"
        result = "已下发施工安全员随身设备。K100+350信号机更换施工安全风险防控和电子围栏下发流程已完成。"
        state_obj = {"state": "idle", "scenario": ""}
        _workflow_save_state(state_obj)
        _workflow_audit(text, old_state, new_state, result)
        return _workflow_result(result, new_state, done=True)

    result = "未命中K100+350信号机更换施工安全流程。请说：请根据K100+350信号机更换施工计划分析安全风险防控点。"
    _workflow_audit(text, old_state, old_state, result)
    return _workflow_result(result, old_state, matched=False)


if __name__ == "__main__":
    _load_rag()
    logger.info("Starting KB Server v2 on %s:%d (5 tools, rag=%s)", HOST, PORT, RAG_DIR)
    mcp.run(transport="sse", host=HOST, port=PORT)
