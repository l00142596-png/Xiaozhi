#!/usr/bin/env python3
"""Build strict-RAG source registry with manual overrides and domain taxonomy."""
import json
import re
from pathlib import Path

BASE = Path('/opt/xiaozhi-mcp')
RAG = BASE / 'rag_strict'
CHUNKS = RAG / 'chunks.json'
REGISTRY = RAG / 'source_registry.json'
APPROVED = RAG / 'approved_sources.txt'
TODO = RAG / 'source_review_todo.txt'
OVERRIDES = RAG / 'source_overrides.json'


def norm_name(name: str) -> str:
    stem = re.sub(r'\.(pdf|docx)$', '', name, flags=re.I)
    stem = re.sub(r'\(1\)$', '', stem).strip()
    stem = re.sub(r'[-－]?\d+$', '', stem) if '桥隧建筑物修理规则' in stem else stem
    stem = re.sub(r'\s+', '', stem)
    return stem


def infer_domain(name: str) -> tuple[str, str]:
    if any(x in name for x in ['桥隧', '桥梁', '隧']):
        return '普速铁路', '桥隧建筑物'
    if any(x in name for x in ['线路修理', '线路维修', '线路']):
        return '普速铁路' if '普速' in name or 'TGGW' in name else '线路专业', '线路修理'
    if any(x in name for x in ['工务安全']):
        return '普速铁路', '工务安全'
    if any(x in name for x in ['技术管理规程-普速', '技规普速']):
        return '普速铁路', '技术管理规程'
    if any(x in name for x in ['技术管理规程-高速', '技规高速', '高速铁路']):
        return '高速铁路', '技术管理规程/高速'
    if any(x in name for x in ['营业线施工', '施工安全管理', '施工管理实施细则', '施工管理办法', '施工[', '铁调[2021]160', '国铁运输监[2021]31']):
        return '营业线施工', '施工管理/通知办法'
    if any(x in name for x in ['接触网', '供电']):
        return '供电专业', '接触网'
    if any(x in name for x in ['信号', '电务']):
        return '电务专业', '信号/电务'
    if any(x in name for x in ['机车', '机务']):
        return '机务专业', '机车操作'
    if any(x in name for x in ['铁路法', '条例', '运输安全保护']):
        return '综合法规', '法律法规/行政法规'
    if any(x in name for x in ['建设项目', '工程建设', '标准设计', '变更设计', '联调联试']):
        return '铁路建设', '建设管理'
    if any(x in name for x in ['给水']):
        return '给水专业', '给水管理'
    if any(x in name for x in ['环境保护']):
        return '环保专业', '环境保护'
    if any(x in name for x in ['统计']):
        return '综合管理', '行业统计'
    return '综合管理', '其他规范资料'


def infer_doc_type(name: str) -> str:
    if any(x in name for x in ['铁路法', '条例']):
        return 'law_or_regulation'
    if any(x in name for x in ['技术管理规程', '技规', '规则', '规程']):
        return 'technical_rule'
    if any(x in name for x in ['管理办法', '实施细则', '指导意见', '规定', '通知']):
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
        r'(铁道部铁计\[[0-9]{4}\]\d+\s*号)',
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
    if name.startswith('TG ') or name.startswith('TGGW') or name.startswith('TGXH'):
        return '铁路行业技术规章发布单位待核'
    if '技规' in name or '铁路技术管理规程' in name:
        return '铁路技术管理规程发布单位待核'
    if '中华人民共和国铁路法' in name:
        return '全国人民代表大会常务委员会'
    if '铁路安全管理条例' in name or '铁路运输安全保护条例' in name:
        return '国务院'
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
    overrides = json.loads(OVERRIDES.read_text(encoding='utf-8')) if OVERRIDES.exists() else {}
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
        railway_scope, discipline = infer_domain(name)
        review = []
        if not infer_doc_no(name) and not any(x in name for x in ['铁路法', '条例', '技规']):
            review.append('文号待人工补录')
        if not infer_issuer(name):
            review.append('发布单位待人工补录')
        if year is None:
            review.append('年份/生效日期待人工补录')
        if count < 20 and status == 'approved':
            review.append('切片数较少，请核对完整性')
        item = {
            'filename': name,
            'status': status,
            'disabled_reason': disabled_reason,
            'chunk_count': count,
            'authority_level': authority,
            'priority': priority,
            'railway_scope': railway_scope,
            'discipline': discipline,
            'document_type': infer_doc_type(name),
            'issuer': infer_issuer(name),
            'document_no': infer_doc_no(name),
            'effective_year': year,
            'effective_date': '',
            'scope': '',
            'review_notes': review,
        }
        override = overrides.get(name, {})
        for key, value in override.items():
            if key == 'review_notes_add':
                for note in value:
                    if note not in item['review_notes']:
                        item['review_notes'].append(note)
            else:
                item[key] = value
        registry.append(item)

    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    APPROVED.write_text('\n'.join(r['filename'] for r in registry if r['status'] == 'approved') + '\n', encoding='utf-8')
    TODO.write_text('\n'.join(
        f"[{r['status']}] {r['railway_scope']}/{r['discipline']} | {r['filename']} | chunks={r['chunk_count']} | no={r['document_no'] or '-'} | issuer={r['issuer'] or '-'} | notes={'; '.join(r['review_notes']) or r['disabled_reason'] or '-'}"
        for r in registry
        if r['status'] != 'approved' or r['review_notes']
    ) + '\n', encoding='utf-8')
    print('registry', REGISTRY)
    print('sources', len(registry))
    print('approved', sum(1 for r in registry if r['status'] == 'approved'))
    print('disabled', sum(1 for r in registry if r['status'] == 'disabled'))
    domains = {}
    for r in registry:
        if r['status'] == 'approved':
            key = f"{r['railway_scope']}/{r['discipline']}"
            domains[key] = domains.get(key, 0) + 1
    for key, count in sorted(domains.items()):
        print(count, key)

if __name__ == '__main__':
    main()
