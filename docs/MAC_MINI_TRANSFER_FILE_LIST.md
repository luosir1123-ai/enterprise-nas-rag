# Mac mini 可直接迁移文件清单

本文档说明当前 Windows 项目中哪些内容可以直接复制到 Mac mini，哪些只能作为参考，哪些不建议迁移。

## 1. 必须复制

这些文件是 Mac mini 第一阶段接手项目所必需的。

```text
README.md
requirements.txt
configs/knowledge_bases.macmini.yaml
configs/exclude_patterns.yaml
configs/permissions.yaml
scripts/scan_nas.py
scripts/sample_files.py
scripts/macmini_nfs_check.sh
docs/MAC_MINI_HANDOFF.md
docs/MAC_MINI_TRANSFER_FILE_LIST.md
data/eval/eval_questions_template.csv
```

用途：

- `knowledge_bases.macmini.yaml`：Mac mini NFS 路径版三知识库配置。
- `macmini_nfs_check.sh`：检查 Mac mini 是否能通过 NFS 只读挂载 NAS。
- `scan_nas.py`：重新扫描 NAS 三目录，生成真实文件清单。
- `sample_files.py`：从真实清单里抽样，形成第一版样本计划。
- `eval_questions_template.csv`：后续人工评估问题模板。

## 2. 建议复制

这些文件不是运行必需，但能帮助 Mac mini 上的 Codex 理解项目历史和当前决策。

```text
docs/项目阶段说明.md
docs/下一步计划.md
docs/NAS准备清单.md
docs/RAGFlow部署与NAS接入记录.md
docs/RAGFlow上传与解析解耦方案.md
docs/RAGFlow首批文件上传与检索验证记录.md
docs/RAGFlow三知识库小样本导入与检索验证记录.md
docs/RAGFlow问答链路诊断记录.md
output/企业NAS_RAG项目Macmini采购与NFS提速方案_20260703.docx
output/企业NAS_RAG项目Macmini采购与NFS提速方案_20260703.pdf
```

用途：

- 说明为什么从旧 Ubuntu 服务器迁移到 Mac mini。
- 说明为什么要通过 NFS 解决 SMB 慢的问题。
- 保留 RAGFlow 旧服务器验证过程，便于后续对照。

## 3. 可参考但需要重新生成

这些文件可以带过去做历史参考，但不能代表 Mac mini 当前真实状态。

```text
data/inventory/file_inventory.csv
data/inventory/file_inventory.sqlite3
data/inventory/summary.md
data/samples/sample_plan.csv
data/samples/sample_plan.md
```

原因：

- 旧清单来自旧环境或旧挂载路径。
- Mac mini 通过 NFS 挂载后，必须重新扫描。
- 新的真实结果应覆盖输出到 `data/inventory/`。

## 4. 不建议复制

这些内容不应放入 Mac mini 交接包。

```text
__pycache__/
.pytest_cache/
output/boss_report_render_*/
scripts/_tmp_status_counts*.py
docs/Ollama本地模型接入记录.md
docs/NAS到Ubuntu真实接入记录.md
```

原因：

- 缓存和临时文件没有价值。
- 渲染图片体积较大，不影响部署。
- 部分历史文档包含账号邮箱、DSM 用户名或旧服务器临时操作记录，不适合做迁移包。

## 5. 旧 RAGFlow 知识库不能直接复制的原因

旧服务器上的 RAGFlow 知识库不是一个普通目录，而是分散在：

```text
MySQL
MinIO
Elasticsearch
RAGFlow 配置与日志目录
```

因此不能只复制 `enterprise-nas-rag` 项目目录就得到旧服务器上的知识库状态。Mac mini 第一阶段应该：

```text
NFS 只读挂载 NAS
-> 重新扫描三目录
-> 生成新的 file_inventory.csv / sqlite3 / summary.md
-> 选择小批量文件导入 RAG 服务
```

旧服务器继续作为参考环境和回退环境。

## 6. Mac mini 第一阶段验收

Mac mini 上第一阶段只验收以下内容：

```text
1. 有线接入公司内网
2. 能 ping 通 NAS 192.0.2.153
3. 能 showmount 查看 NAS NFS 导出
4. 能只读挂载 /Users/Shared/nas/LE_TOUCH_SHR
5. 能看到 PUR-SHR、SALES-SHR、产品设计成果(2021年起)
6. 能运行 scan_nas.py 生成真实文件清单
7. 能运行 sample_files.py 生成样本计划
```

如果 NFS 不通，必须先停止，不要继续部署 RAGFlow 或导入文件。
