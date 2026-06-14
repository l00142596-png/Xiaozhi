# RAG PDF ingest workflow

Created for adding scanned PDF railway documents into /opt/xiaozhi-mcp/rag.

Current PDF uploaded to Aliyun:
/opt/xiaozhi-mcp/source_pdfs/《工务系统普速铁路作业指导书》编委会编 --2015 -- 北京_中国铁道出版社 -- 9787113200701.pdf

Main script:
/opt/xiaozhi-mcp/scripts/ingest_pdf_to_rag.py

Run script:
/opt/xiaozhi-mcp/scripts/run_ingest_work_guide.sh

Runtime log:
/var/log/rag_ingest_work_guide.log

The script supports OCR cache and resumes already OCRed pages through /opt/xiaozhi-mcp/rag/ocr_cache.
