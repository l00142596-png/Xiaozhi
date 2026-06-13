"""知识库 MCP Server — 提供知识的保存、搜索和列表功能。

通过 SSE 为 xiaozhi-client 提供本地知识管理能力。
所有工具返回 JSON 字符串，result 字段不超过 1024 字节。
"""

import json
import os
import logging

from fastmcp import FastMCP

DATA_FILE = "/opt/xiaozhi-mcp/knowledge.json"
MAX_RESULT_LENGTH = 1000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [KB] %(levelname)s %(message)s",
)
logger = logging.getLogger("kb_server")

mcp = FastMCP("知识库")


def _load() -> dict:
    """从 JSON 文件加载知识库数据。"""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    """将知识库数据持久化到 JSON 文件。"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _truncate(text: str, max_bytes: int = MAX_RESULT_LENGTH) -> str:
    """截断文本到指定字节数以内（按 UTF-8 字节计算）。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # 逐字符缩减直到字节数达标
    result = text
    while len(result.encode("utf-8")) > max_bytes:
        result = result[:-1]
    return result.rstrip() + "…"


@mcp.tool()
def save_knowledge(title: str, content: str) -> str:
    """保存一条知识到本地知识库。

何时使用：当用户明确要求"记住"、"保存"、"记录"某个信息时调用。
例如"帮我把事故分析存起来"、"记下这个知识点"。

参数：
- title: 知识的标题，用于后续查找和列表展示
- content: 知识的完整内容，可以是多行文本

返回：JSON 格式，result 字段包含保存确认信息。
"""
    logger.info("save_knowledge called: title=%s", title)
    data = _load()
    data[title] = content
    _save(data)
    logger.info("Knowledge saved, total entries: %d", len(data))
    return json.dumps({"result": f"已保存知识「{title}」"}, ensure_ascii=False)


@mcp.tool()
def search_knowledge(keywords: str) -> str:
    """在知识库中按关键词搜索匹配的内容。

何时使用：当用户问"XX 是什么"、"关于 XX 有什么记录"、"帮我查一下 XX"时调用。
同时搜索标题和正文，只要任意一者包含关键词即命中。

参数：
- keywords: 搜索关键词，支持中英文，大小写不敏感

返回：JSON 格式，result 字段包含匹配的完整知识内容。
如果没有匹配项，result 会说明未找到。
"""
    logger.info("search_knowledge called: keywords=%s", keywords)
    data = _load()
    results: list[str] = []
    for title, content in data.items():
        if keywords.lower() in title.lower() or keywords.lower() in content.lower():
            results.append(f"【{title}】\n{content}")

    if not results:
        return json.dumps(
            {"result": f"知识库中未找到与「{keywords}」相关的内容"}, ensure_ascii=False
        )

    combined = "\n\n---\n\n".join(results)
    truncated = _truncate(combined)
    logger.info("Search matched %d entries, output %d bytes", len(results), len(truncated.encode("utf-8")))
    return json.dumps({"result": truncated}, ensure_ascii=False)


@mcp.tool()
def list_all_knowledge() -> str:
    """列出知识库中所有知识的标题。

何时使用：当用户问"知识库里有什么"、"有哪些知识"、"列出所有条目"时调用。
仅返回标题列表，不包含正文内容，方便快速浏览。

返回：JSON 格式，result 字段包含编号的标题列表。
"""
    logger.info("list_all_knowledge called")
    data = _load()
    if not data:
        return json.dumps({"result": "知识库目前为空，还没有保存任何知识。在对话中说需要记录的内容，我会帮你保存。"}, ensure_ascii=False)

    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(data.keys(), 1))
    result = f"知识库共有 {len(data)} 条知识：\n{titles}"
    logger.info("Listed %d entries", len(data))
    return json.dumps({"result": result}, ensure_ascii=False)


if __name__ == "__main__":
    logger.info("Starting Knowledge Base MCP Server on 127.0.0.1:8766")
    mcp.run(transport="sse", host="127.0.0.1", port=8766)
