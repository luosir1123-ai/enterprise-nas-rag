# 企业 NAS 三目录 RAG 试点

本项目用于把 Synology NAS 上的三个业务目录整理成企业 RAG 的可靠数据源。当前阶段不在 NAS 上跑完整 RAGFlow、本地大模型、OCR、embedding 或 reranker，只做只读扫描、文件清单、目录治理、权限规划和后续外部服务器接入准备。

## 试点范围

| NAS 目录 | 知识库名称 | 第一版用途 |
|---|---|---|
| `PUR-SHR` | 采购知识库 | 供应商、采购流程、报价、合同、物料资料 |
| `SALES-SHR` | 销售知识库 | 客户资料、报价方案、销售合同、项目记录 |
| `产品设计成果(2021年起)` | 产品设计知识库 | 产品方案、设计文档、BOM、评审材料、技术资料 |

已确认 NAS 环境：

- 型号：Synology `DS224+`
- CPU：`Intel Celeron J4125`，4 核
- 当前内存：`2GB`
- DSM：`7.2.1-69057 Update 11`
- 局域网 IP：`192.168.1.153`
- `Container Manager` 可安装，但当前未安装
- DSM 当前有存储警告，部署前必须先确认原因

## 当前阶段目标

1. 处理 NAS 存储警告，确认卷和硬盘状态不会影响试点。
2. 创建 RAG 专用只读账号 `rag_reader`。
3. 只读扫描三个目录，生成文件清单。
4. 统计目录大小、文件数量、文件类型、候选文件和排除文件。
5. 为后续外部服务器 RAG 部署准备固定挂载路径和评估集模板。

## 目录结构

```text
enterprise-nas-rag/
  configs/
    knowledge_bases.yaml
    exclude_patterns.yaml
    permissions.yaml
  scripts/
    scan_nas.py
  data/
    inventory/
    samples/
    eval/
  docs/
  compose/
  README.md
  requirements.txt
```

## 安装依赖

```powershell
cd D:\letouch\enterprise-nas-rag
python -m pip install -r .\requirements.txt
```

## 配置扫描路径

编辑 `configs/knowledge_bases.yaml`。

如果是在外部 Linux 服务器上扫描，推荐把 NAS 目录只读挂载到：

```text
/mnt/nas/PUR-SHR
/mnt/nas/SALES-SHR
/mnt/nas/product-design
```

如果是在 Windows 临时测试，可以把 `local_scan_path` 改成实际映射盘路径，例如：

```yaml
local_scan_path: "Z:/PUR-SHR"
```

默认脚本不会修改 NAS 文件。

## 运行只读扫描

首次试跑建议限制数量：

```powershell
python .\scripts\scan_nas.py --max-files 100
```

正式扫描使用快速 hash：

```powershell
python .\scripts\scan_nas.py
```

如果数据量较小且需要完整文件指纹，可使用完整 SHA256：

```powershell
python .\scripts\scan_nas.py --sha256
```

输出文件：

```text
data/inventory/file_inventory.csv
data/inventory/file_inventory.sqlite3
data/inventory/summary.md
```

## 生成样本计划

扫描清单生成后，可以从候选文件里抽样：

```powershell
python .\scripts\sample_files.py --per-kb 100
```

输出文件：

```text
data/samples/sample_plan.csv
data/samples/sample_plan.md
```

## 运行测试

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## 清单字段

```text
knowledge_base
knowledge_base_id
nas_path
scan_path
relative_path
filename
extension
file_size_bytes
modified_time
sha256_or_fast_hash
is_candidate
exclude_reason
parse_status
permission_group
```

## 第一版纳入和排除规则

优先纳入：

```text
.docx
.xlsx
.pptx
.pdf
.txt
.md
.csv
```

默认排除：

```text
~$*
*.tmp
*.bak
*.exe
*.dll
*.zip
*.rar
*.7z
__MACOSX/
回收站/
临时/
草稿/
```

## NAS 上允许和禁止运行的内容

允许在 NAS 上运行：

- 文件清单查看页
- 扫描任务触发器
- 日志查看
- 小规模样本测试

第一阶段不在 NAS 上运行：

- RAGFlow 全套
- 本地大模型
- 大规模 OCR
- 大规模 embedding
- Elasticsearch / OpenSearch
- Milvus

## 后续外部服务器默认架构

NAS 只作为资料源，外部服务器负责重计算：

```text
NAS 只读挂载
  -> 文档解析
  -> OCR
  -> embedding
  -> reranker
  -> 向量库
  -> 全文索引
  -> LLM 调用
  -> RAG Web/API
```

推荐最低服务器：

```text
CPU: 8 核以上
RAM: 32GB
Disk: 1TB NVMe
OS: Ubuntu Server
```

推荐正式服务器：

```text
CPU: 12-16 核
RAM: 64GB
Disk: 2TB NVMe
GPU: 可选，取决于是否本地跑 OCR/embedding/LLM
```

## 验收标准

1. `rag_reader` 只能读取三个知识库目录，不能访问其他目录。
2. 外部机器可通过 SMB/NFS 只读挂载三个目录。
3. 扫描不修改任何 NAS 原文件。
4. `file_inventory.csv`、`file_inventory.sqlite3`、`summary.md` 正常生成。
5. `summary.md` 使用中文列出目录大小、文件数量、文件类型分布、候选文件、排除文件和最大文件。
6. 每个知识库至少抽样 100 个候选文件。
7. 每个知识库至少准备 20 条评估问题。

## 下一步

1. 在 DSM 存储管理器中确认存储警告原因。
2. 加装官方兼容 4GB 内存，把 NAS 提升到 6GB。
3. 安装 Container Manager，仅用于轻量工具。
4. 创建 `rag_reader` 只读账号。
5. 配置 SMB/NFS，并让外部服务器只读挂载三个目录。
6. 运行 `scripts/scan_nas.py` 生成第一版文件清单。
