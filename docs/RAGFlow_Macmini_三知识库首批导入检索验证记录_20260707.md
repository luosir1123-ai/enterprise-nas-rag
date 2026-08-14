# RAGFlow Mac mini 三知识库首批导入与检索验证记录

记录时间：2026-07-07

## 1. 本次目标

本次执行的是计划里的第一轮 Mac mini 小批量链路验证：

```text
NFS 只读挂载
-> RAGFlow 三知识库
-> 样本文档上传
-> 限速解析
-> text-embedding-v4 embedding
-> Elasticsearch 索引
-> 按知识库限定检索
```

本次没有做全量导入，也没有修改 NAS 原始文件。

## 2. 环境确认

- NAS 宿主机挂载路径：`/Users/Shared/nas/LE_TOUCH_SHR`
- 挂载属性：NFS 只读
- RAGFlow 容器内路径：`/ragflow/nas/LE_TOUCH_SHR`
- RAGFlow 当前用户空间：`Dong‘s Kingdom`
- 默认 embedding：`text-embedding-v4@dashscope-text-embedding-v4@Tongyi-Qianwen`

注意：当前默认 LLM 字段显示为 `deepseek-v4-flash@dashscope-text-embedding-v4@Tongyi-Qianwen`，看起来像模型名和 provider instance 组合不一致。它不影响本次文档解析和检索，但问答验证前需要单独核对 DeepSeek 聊天模型是否可用。

## 3. 已创建知识库

| 知识库 | RAGFlow ID | Embedding | Parser |
|---|---|---|---|
| 采购知识库 | `<redacted-id>` | `text-embedding-v4@dashscope-text-embedding-v4@Tongyi-Qianwen` | `naive` |
| 销售知识库 | `<redacted-id>` | `text-embedding-v4@dashscope-text-embedding-v4@Tongyi-Qianwen` | `naive` |
| 产品设计知识库 | `<redacted-id>` | `text-embedding-v4@dashscope-text-embedding-v4@Tongyi-Qianwen` | `naive` |

## 4. 上传与解析结果

首批 manifest 共 36 个文件，每个知识库 12 个，单文件上限 8MB。

上传结果：

- 上传文件数：36
- 上传错误：0
- 对象存储检查：已通过
- NAS 原文件：未修改

解析采用限速方式触发，先每库解析约 5 个文件。最终状态：

| 知识库 | 文档数 | DONE 文档 | 未解析文档 | Chunk 数 | Token 数 |
|---|---:|---:|---:|---:|---:|
| 采购知识库 | 12 | 5 | 7 | 36 | 9523 |
| 销售知识库 | 12 | 5 | 7 | 52 | 16716 |
| 产品设计知识库 | 12 | 6 | 6 | 27 | 3654 |

观察：

- `text-embedding-v4` 已完成实际 embedding 调用和索引写入。
- PDF OCR/版面分析是主要耗时点，尤其是证书、审厂报告、带水印 PDF。
- 产品设计的水印 PDF `(水印)Design Concept of Find My Cable.pdf` 本轮能够切出 chunk，但后续仍建议归入 OCR/特殊 PDF 队列单独统计。

## 5. 检索烟测结果

检索测试均按单个知识库 ID 限定范围执行，不做跨库全量检索。

| 知识库 | 检索词 | 预期来源 | 结果 |
|---|---|---|---|
| 采购知识库 | `ISO9001` | `ISO9001中文證書2027.1.26.pdf` | 通过 |
| 采购知识库 | `CBATB5005` | `CBATB5005` 相关报价/规格/报告 | 通过 |
| 销售知识库 | `BEPI` | `LeTouch- 2024-2026 BEPI.pdf` | 通过 |
| 销售知识库 | `BSCI` | `LeTouch -2024-2025 BSCI.pdf` | 通过 |
| 产品设计知识库 | `Find My Cable` | `Design Concept of Find My Cable.pdf` | 通过 |
| 产品设计知识库 | `20W` | `20W饼干超薄充电器报价单.xlsx` / `Super slim type c charger LeTouch 202208.pdf` | 通过 |

检索烟测结论：

```text
6 个检索问题全部命中预期来源。
三知识库均已完成：上传 -> 解析 -> chunk -> embedding -> 索引 -> 按知识库检索命中。
```

## 6. 本次归档文件

本次运行证据保存在：

```text
data/ragflow_runs/20260707_175728/
```

关键文件：

- `ragflow_upload_manifest.txt`
- `ragflow_upload_manifest_make_report.json`
- `ragflow_upload_manifest_report.json`
- `ragflow_queue_unparsed_batch_report.json`
- `ragflow_check_status_final.json`
- `ragflow_retrieval_smoke_report.json`

## 7. 本次新增和调整脚本

新增：

- `scripts/ragflow_env.py`
- `scripts/ragflow_ensure_kbs.py`

已更新为自动识别 Mac mini 当前 RAGFlow tenant：

- `scripts/ragflow_check_status.py`
- `scripts/ragflow_make_upload_manifest.py`
- `scripts/ragflow_upload_manifest_batch.py`
- `scripts/ragflow_queue_unparsed_batch.py`
- `scripts/ragflow_retrieval_smoke.py`
- `scripts/ragflow_list_model_config.py`

注意：以下旧脚本仍保留旧 Ubuntu 环境的固定 tenant ID，后续如要继续使用，需要先改为 `ragflow_env.py` 的自动识别方式：

- `scripts/ragflow_import_samples.py`
- `scripts/ragflow_controlled_batch_import.py`
- `scripts/ragflow_diagnose_chat.py`
- `scripts/ragflow_switch_chat_to_deepseek.py`
- `scripts/ragflow_switch_chat_to_ollama_model.py`

## 8. 还没完成

- 还没有完成黄金评估集：每个知识库 20 条真实业务问题仍需业务侧补齐。
- 还没有做最终问答验证：引用来源、拒答、答案准确性仍未验收。
- 还没有做权限过滤验证：当前只验证了按知识库过滤，尚未验证 `permission_group` 级别过滤。
- 首批 36 个文档中仍有 20 个未解析，需后续限速分批继续。
- DeepSeek 聊天模型默认配置需要在问答前单独验证或修正。

## 9. 建议下一步

1. 先修正并验证 DeepSeek LLM 默认模型，确认 RAGFlow 问答能正常调用。
2. 将剩余 20 个已上传未解析文档继续按每库 3-5 个限速解析。
3. 建立三库黄金评估集，每库先补 20 条真实问题。
4. 创建或配置 RAGFlow Chat，要求回答显示来源文件。
5. 在检索入口实现并验证 `knowledge_base + permission_group` 前置过滤。
