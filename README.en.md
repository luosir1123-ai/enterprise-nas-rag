<div align="center">
  <img src="assets/enterprise-nas-rag-banner.svg" alt="Enterprise NAS RAG" width="100%">
</div>

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776ab.svg)](requirements.txt)
[![RAGFlow](https://img.shields.io/badge/RAGFlow-Knowledge%20Engine-0f766e.svg)](docs/RAGFlow部署与NAS接入记录.md)
[![NAS](https://img.shields.io/badge/NAS-Read--only%20Source-475569.svg)](docs/挂载方式决策说明.md)
[![Evaluation](https://img.shields.io/badge/RAG-Regression%20Evaluation-7c3aed.svg)](docs/评估集说明.md)

**Incremental NAS ingestion, structured retrieval, evaluation, and an internal knowledge portal.**

[中文完整指南](README.md)

</div>

---

## Overview

Enterprise NAS RAG turns purchasing, sales, and product-design documents on a read-only NAS into a governed RAG pipeline. It started as a three-directory inventory pilot and now includes idempotent synchronization, business metadata, Excel row retrieval, RAGFlow operations, regression evaluation, and a React/FastAPI internal portal.

This is an environment-specific engineering reference rather than a turnkey SaaS product. New deployments must supply their own mounts, datasets, access model, secrets, assistants, and evaluation ground truth.

## Capability map

| Layer | Responsibility |
|---|---|
| Inventory | read-only scanning, include/exclude policy, CSV/SQLite inventory, sampling |
| Synchronization | added/modified/historical/missing/duplicate state and idempotent updates |
| Structured retrieval | business metadata and SQLite FTS indexing for Excel rows |
| Knowledge engine | RAGFlow parsing, chunks, vector/full-text retrieval, evidence references |
| Evaluation | source-recall coverage, business-answer accuracy, refusal behavior |
| Portal | purchasing, sales, and product assistants plus read-only operations status |

## Data flow

```text
Read-only NAS mounts
        -> inventory and fingerprints
        -> incremental synchronization and metadata
        -> Excel row index + RAGFlow retrieval
        -> evidence-backed answers / refusal
        -> regression evaluation
        -> internal knowledge portal
```

## Start with an inventory

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/scan_nas.py --max-files 100
python scripts/sample_files.py --per-kb 100
```

Configure read-only mount paths in [configs/knowledge_bases.yaml](configs/knowledge_bases.yaml). The scanner writes inventory and summary artifacts under `data/inventory/`; it does not modify source files.

## Operations

- `scripts/run_incremental_sync.sh`: synchronize current NAS changes into RAGFlow.
- `scripts/run_excel_row_index_refresh.sh`: refresh structured Excel-row retrieval.
- `scripts/run_automated_evaluation.sh`: run source-coverage and business-accuracy suites.
- `launchd/com.waimao.*.plist`: macOS scheduler templates; replace account-path placeholders before installation.
- [apps/internal-portal](apps/internal-portal/): React portal and FastAPI read-only proxy.

## Checks

```bash
python3 -m unittest discover -s tests -p "test_*.py"
npm --prefix apps/internal-portal install
npm --prefix apps/internal-portal run build
```

## Security boundaries

- Keep RAGFlow tokens, identity secrets, and session keys out of Git.
- Filter authorization before retrieval; hiding unauthorized results after retrieval is not sufficient.
- Treat NAS documents as immutable sources and indexes as disposable derived data.
- Reconfigure all example paths, addresses, dataset IDs, and assistant bindings for each environment.
- A trusted-LAN deployment is not equivalent to strong user authentication.

## Limitations

- Parsing, OCR, embedding, reranking, and generation quality depend on external RAGFlow and model configuration.
- Excel row indexing does not model every formula or cross-workbook business rule.
- Fixed regression suites measure their covered questions, not universal answer correctness.
- The repository currently declares no open-source license; do not assume redistribution or commercial-use rights.
