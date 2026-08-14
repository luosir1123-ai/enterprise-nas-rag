<div align="center">
  <img src="assets/enterprise-nas-rag-banner.svg" alt="Enterprise NAS RAG" width="100%">
</div>

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776ab.svg)](requirements.txt)
[![RAGFlow](https://img.shields.io/badge/RAGFlow-Knowledge%20Engine-0f766e.svg)](docs/RAGFlow部署与NAS接入记录.md)
[![NAS](https://img.shields.io/badge/NAS-Read--only%20Source-475569.svg)](docs/挂载方式决策说明.md)
[![Evaluation](https://img.shields.io/badge/RAG-Regression%20Evaluation-7c3aed.svg)](docs/评估集说明.md)
[![Portal](https://img.shields.io/badge/Portal-React%20%2B%20FastAPI-149eca.svg)](apps/internal-portal/)

**面向企业 NAS 文档的增量同步、结构化检索、质量评测与内部知识门户。**

[English](README.en.md)

</div>

---

## 项目定位

`enterprise-nas-rag` 把企业 NAS 中的采购、销售和产品设计资料组织成可治理、可评测、可追溯的 RAG 数据链路。NAS 始终作为权威只读资料源；扫描、解析、索引、检索、评测和问答运行在外部计算节点。

项目最初从“三目录只读扫描试点”开始，仓库现在还包含增量同步、业务元数据、Excel 行级索引、RAGFlow 运维脚本、回归评测和内部知识门户。历史文档保留了试点演进过程，当前能力以可执行脚本、门户代码和测试为准。

> [!IMPORTANT]
> 本仓库是面向特定企业环境形成的工程参考，不是开箱即用的通用 SaaS。真实部署必须重新配置 NAS 路径、RAGFlow 数据集、身份认证、权限组、密钥和评估答案。

## 能力地图

| 模块 | 作用 | 主要产物 |
|---|---|---|
| NAS 扫描与抽样 | 只读盘点文件、执行纳入/排除规则、生成样本计划 | CSV/SQLite 清单、统计报告、样本计划 |
| 幂等增量同步 | 识别新增、修改、历史、缺失和重复副本 | 同步变更、RAGFlow 文档、运行报告 |
| 业务元数据 | 从路径和文件名提取年份、型号、文档类型与权威性 | 检索过滤与业务重排字段 |
| Excel 行级索引 | 为表格的型号、报价、MOQ、供应商等字段建立精查入口 | SQLite FTS 行索引与来源定位 |
| 自动评测 | 分离来源召回与业务答案准确性 | 评测报告、失败清单、回归基线 |
| 内部知识门户 | 提供采购、销售、产品助手和只读运维状态 | 带引用问答、历史会话、同步/评测看板 |

## 数据链路

```text
Synology NAS：采购 / 销售 / 产品设计
                │ 只读挂载
                ▼
文件扫描与内容指纹
                │
                ├────▶ 清单、样本、权限与排除规则
                │
                ▼
幂等增量同步与业务元数据
                │
                ├────▶ Excel 行级 FTS 精查
                │
                ▼
RAGFlow：解析、切片、向量与全文检索
                │
                ▼
检索过滤 / 重排 / 有证据回答 / 无证据拒答
                │
                ├────▶ 自动回归评测
                ▼
Waimao 内部知识门户
```

## 设计原则

- **源数据只读**：索引和解析都是派生数据，不写回 NAS 原文件。
- **权限先于检索**：先按知识库和权限组过滤，再进行召回与生成。
- **内容变更优先**：新增和修改优先于历史元数据迁移。
- **历史不自动删除**：来源中消失的文档标记状态，等待人工确认。
- **证据优先**：回答必须附来源；没有足够证据时拒答。
- **评测驱动**：失败进入检索优化清单，不通过修改标准答案“提高”结果。

## 快速开始：只读扫描

创建环境并安装基础依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

编辑 [configs/knowledge_bases.yaml](configs/knowledge_bases.yaml)，将每个 `local_scan_path` 指向只读挂载目录。先进行限制数量的试跑：

```bash
python scripts/scan_nas.py --max-files 100
python scripts/sample_files.py --per-kb 100
```

正式扫描可以使用快速内容指纹；需要完整指纹时增加 `--sha256`：

```bash
python scripts/scan_nas.py
python scripts/scan_nas.py --sha256
```

典型输出：

```text
data/inventory/file_inventory.csv
data/inventory/file_inventory.sqlite3
data/inventory/summary.md
data/samples/sample_plan.csv
data/samples/sample_plan.md
```

## 增量同步与评测

Mac 外部计算节点的任务入口包括：

- `scripts/run_incremental_sync.sh`：执行当前 NAS 到 RAGFlow 的增量同步；
- `scripts/run_excel_row_index_refresh.sh`：刷新 Excel 行级索引；
- `scripts/run_automated_evaluation.sh`：运行来源覆盖和业务准确性评测；
- `launchd/com.letouch.*.plist`：定时任务模板，安装前必须替换示例账号路径。

完整状态模型、保留策略、批次限制和日志位置见[知识库同步与自动评测运维说明](docs/知识库同步与自动评测运维说明.md)。

## 内部知识门户

[内部知识门户](apps/internal-portal/) 使用 React + FastAPI 构建，浏览器不保存 RAGFlow API Key。门户提供：

- 采购、销售和产品设计三个固定业务入口；
- 带来源引用的问答与用户隔离的历史会话；
- 当前增量同步状态、知识库计数和自动评测结果；
- `trusted_lan` 与企业微信认证适配路径；
- 不暴露 RAGFlow 管理后台，也不能从门户执行 Docker 或修改知识库。

```bash
cd apps/internal-portal
npm install
npm run build
```

正式部署步骤与代理 Token 生成见[门户说明](apps/internal-portal/README.md)。

## 仓库结构

```text
configs/                 知识库、排除、权限、Excel 索引配置
scripts/                 扫描、同步、检索、诊断、评测与运维脚本
apps/internal-portal/    React 门户与 FastAPI 只读代理
data/eval/               来源覆盖与业务准确性评测集
launchd/                 macOS 定时任务模板
docs/                    设计决策、部署记录、验证记录与运维说明
tests/                   扫描、索引、同步策略、门户和运维测试
```

## 验证

```bash
python3 -m unittest discover -s tests -p "test_*.py"
npm --prefix apps/internal-portal install
npm --prefix apps/internal-portal run build
```

## 安全与隐私边界

- RAGFlow Token、企业微信 Secret 和会话密钥必须放在未跟踪的 Secret 文件中。
- 示例 IP、路径、数据集 ID 和助手 ID 不能直接用于新的生产环境。
- 内网信任模式依赖网络隔离和主机防火墙，不能等同于完整身份认证。
- 真实文档名可能包含业务品牌或历史证据，不应通过机械替换破坏评测来源。
- 门户和脚本不能替代 NAS 权限、备份、审计、密钥轮换和灾难恢复。

## 局限

- 解析、OCR、Embedding、Reranker 和模型质量由外部 RAGFlow 与模型配置决定。
- Excel 行级检索解决结构化精查问题，但不能覆盖所有复杂公式和跨表业务逻辑。
- 仓库包含特定环境的演进记录，新部署需要重新做容量、权限与评估设计。
- 评测通过率只代表当前固定用例，不代表所有企业问题都能正确回答。

## License

仓库当前未声明开源许可证。未获得权利人明确许可前，请不要假设可以复制、分发或用于商业部署。
