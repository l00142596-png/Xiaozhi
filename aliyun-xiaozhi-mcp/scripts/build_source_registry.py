import json
import re
from pathlib import Path

BASE = Path('/opt/xiaozhi-mcp')
RAG = BASE / 'rag_strict'
CHUNKS = RAG / 'chunks.json'
REGISTRY = RAG / 'source_registry.json'
APPROVED = RAG / 'approved_sources.txt'
TODO = RAG / 'source_review_todo.txt'


def norm_name(name: str) -> str:
    stem = re.sub(r'\.(pdf|docx)$', '', name, flags=re.I)
    stem = re.sub(r'\(1\)$', '', stem).strip()
    stem = re.sub(r'\s+', '', stem)
    return stem


def infer_doc_type(name: str) -> str:
    if any(x in name for x in ['铁路法', '条例']):
        return 'law_or_regulation'
    if any(x in name for x in ['技术管理规程', '技规', '规则', '规程']):
        return 'technical_rule'
    if any(x in name for x in ['管理办法', '实施细则', '指导意见', '规定']):
        return 'management_rule'
    return 'official_reference'


def infer_authority(name: str) -> tuple[str, int]:
    if '中华人民共和国' in name or '国务院' in name or '条例' in name or '铁路法' in name:
        return '法律法规/行政法规', 100
    if any(x in name for x in ['国家铁路局', '国铁', '中国铁路总公司', '铁总', '铁调']):
        return '国家铁路/国铁集团文件', 90
    if any(x in name for x in ['TG ', 'TGGW', 'TGXH', 'TG XH', 'TG GW', 'TG GD', 'TG JW', '规则', '规程', '技规']):
        return '技术规章/行业规则', 80
    if any(x in name for x in ['上铁', '成铁', '局集团']):
        return '局集团实施细则', 70
    return '规范资料', 60


def infer_year(name: str):
    years = re.findall(r'(19\d{2}|20\d{2})', name)
    return max(map(int, years)) if years else None


def infer_doc_no(name: str) -> str:
    patterns = [
        r'(TG\s*[A-Z]{1,3}\s*\d+[A-Z]?[-－]\d{4})',
        r'(TGGW\s*\d+[A-Z]?[-－]\d{4})',
        r'([\u4e00-\u9fa5]{1,4}\[[0-9]{4}\]\d+号)',
        r'([\u4e00-\u9fa5]{1,4}〔[0-9]{4}〕\d+号)',
    ]
    for pat in patterns:
        m = re.search(pat, name, flags=re.I)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).strip()
    return ''


def infer_issuer(name: str) -> str:
    if '国务院' in name:
        return '国务院/国务院办公厅'
    if '国家铁路局' in name:
        return '国家铁路局'
    if '国铁集团' in name:
        return '中国国家铁路集团有限公司'
    if '中国铁路总公司' in name or '铁总' in name:
        return '中国铁路总公司'
    if '成铁' in name or '成都局' in name:
        return '中国铁路成都局集团有限公司'
    if '上铁' in name or '上海局' in name:
        return '中国铁路上海局集团有限公司'
    if '铁道部' in name:
        return '原铁道部'
    return ''


def reason_for_disabled(name: str, chunks: int, names_by_norm: dict[str, list[str]]) -> str:
    if chunks <= 2:
        return '切片数过少，疑似文件不完整，暂不作为严格引用依据'
    if '(1)' in name:
        return '疑似重复文件，保留原始文件作为引用来源'
    if name.lower().endswith('.docx'):
        same = names_by_norm.get(norm_name(name), [])
        if any(x.lower().endswith('.pdf') for x in same):
            return '与 PDF 来源重复，严格引用优先使用 PDF'
    return ''


def main():
    chunks = json.loads(CHUNKS.read_text(encoding='utf-8'))
    counts = {}
    for c in chunks:
        fn = c.get('filename', 'UNKNOWN')
        counts[fn] = counts.get(fn, 0) + 1
    names_by_norm = {}
    for name in counts:
        names_by_norm.setdefault(norm_name(name), []).append(name)

    registry = []
    for name, count in sorted(counts.items()):
        authority, priority = infer_authority(name)
        year = infer_year(name)
        disabled_reason = reason_for_disabled(name, count, names_by_norm)
        status = 'disabled' if disabled_reason else 'approved'
        review = []
        if not infer_doc_no(name):
            review.append('文号待人工补录')
        if not infer_issuer(name):
            review.append('发布单位待人工补录')
        if year is None:
            review.append('年份/生效日期待人工补录')
        if count < 20 and status == 'approved':
            review.append('切片数较少，请核对完整性')
        registry.append({
            'filename': name,
            'status': status,
            'disabled_reason': disabled_reason,
            'chunk_count': count,
            'authority_level': authority,
            'priority': priority,
            'document_type': infer_doc_type(name),
            'issuer': infer_issuer(name),
            'document_no': infer_doc_no(name),
            'effective_year': year,
            'effective_date': '',
            'scope': '',
            'review_notes': review,
        })

    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    APPROVED.write_text('\n'.join(r['filename'] for r in registry if r['status'] == 'approved') + '\n', encoding='utf-8')
    TODO.write_text('\n'.join(
        f"[{r['status']}] {r['filename']} | chunks={r['chunk_count']} | no={r['document_no'] or '-'} | issuer={r['issuer'] or '-'} | notes={'; '.join(r['review_notes']) or r['disabled_reason'] or '-'}"
        for r in registry
        if r['status'] != 'approved' or r['review_notes']
    ) + '\n', encoding='utf-8')
    print('registry', REGISTRY)
    print('sources', len(registry))
    print('approved', sum(1 for r in registry if r['status'] == 'approved'))
    print('disabled', sum(1 for r in registry if r['status'] == 'disabled'))

if __name__ == '__main__':
    main()
