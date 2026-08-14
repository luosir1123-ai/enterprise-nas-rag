# Mac mini 接手企业 NAS RAG 项目说明

本文档给 Mac mini 上的 Codex 使用。目标是在新买的 Mac mini 上接手当前企业 NAS RAG 项目，先完成公司内网接入、NFS 只读挂载、文件清单扫描，再决定是否在 Mac 上部署 RAGFlow 或采用更适合 Apple Silicon 的轻量 RAG 服务。

## 1. 当前项目已经完成了什么

当前 Windows 工作区项目路径：

```text
D:\workspace\enterprise-nas-rag
```

当前已完成内容：

- 已建立企业 RAG 项目骨架。
- 已明确三个知识库：
  - `PUR-SHR` -> `采购知识库`
  - `SALES-SHR` -> `销售知识库`
  - `产品设计成果(2021年起)` -> `产品设计知识库`
- 已完成 NAS 三目录配置、排除规则、权限规划。
- 已写好只读扫描脚本 `scripts/scan_nas.py`。
- 已写好样本抽取脚本 `scripts/sample_files.py`。
- 已在旧 Ubuntu 服务器部署并验证过 RAGFlow。
- 旧服务器已通过 SMB 只读挂载过 NAS，并上传过首批真实文件。
- 已确认旧服务器无法直连 NAS 内网 IP，NFS 不通，因此采购 Mac mini 的核心目的就是接入公司内网后通过 NFS 只读读取 NAS。

## 2. 当前旧服务器上的 RAGFlow 状态

旧服务器：

```text
172.21.238.68
```

旧服务器上 RAGFlow 相关服务：

| 服务 | 容器名 | 作用 |
|---|---|---|
| RAGFlow 主服务 | `docker-ragflow-cpu-1` | Web、API、知识库管理、上传和解析入口 |
| Elasticsearch | `docker-es01-1` | 全文检索和索引 |
| MinIO | `docker-minio-1` | 上传文件对象存储 |
| MySQL | `docker-mysql-1` | 用户、知识库、文档、任务、配置 |
| Redis/Valkey | `docker-redis-1` | 缓存和任务状态 |

旧服务器上的三个知识库统计快照：

| 知识库 | 文档数 | 切片数 | Token 数 |
|---|---:|---:|---:|
| 采购知识库 | 24 | 328 | 118,227 |
| 销售知识库 | 63 | 305 | 126,955 |
| 产品设计知识库 | 87 | 206 | 73,229 |

注意：这些知识库状态存储在旧服务器的 MySQL、MinIO、Elasticsearch 和 RAGFlow 数据目录里，不是一个普通文件夹。不能简单复制项目目录就得到同样的 RAGFlow 知识库。Mac mini 上第一阶段应优先重新从 NAS 扫描和导入。

## 3. 可以直接迁移到 Mac mini 的内容

建议把整个迁移包复制到 Mac mini：

```text
enterprise-nas-rag-macmini-handoff.zip
```

里面最重要的是：

```text
README.md
requirements.txt
configs/
scripts/
docs/
data/eval/
data/samples/
data/inventory/
output/企业NAS_RAG项目Macmini采购与NFS提速方案_20260703.docx
output/企业NAS_RAG项目Macmini采购与NFS提速方案_20260703.pdf
```

### 直接可用

| 内容 | 是否直接可用 | 用途 |
|---|---|---|
| `configs/knowledge_bases.macmini.yaml` | 是 | Mac mini NFS 路径版三知识库配置 |
| `configs/exclude_patterns.yaml` | 是 | 扫描排除规则 |
| `configs/permissions.yaml` | 是 | 权限分组设计 |
| `scripts/scan_nas.py` | 是 | 只读扫描 NAS，生成 CSV/SQLite/summary |
| `scripts/sample_files.py` | 是 | 根据扫描结果抽样 |
| `scripts/macmini_nfs_check.sh` | 是 | 检查 Mac mini 网络、NFS 和只读挂载 |
| `data/eval/eval_questions_template.csv` | 是 | 评估问题模板 |
| `data/samples/sample_plan.*` | 可参考 | 旧样本计划，Mac 上重新扫描后应重新生成 |
| `data/inventory/*` | 可参考 | 旧服务器/旧扫描结果，不作为 Mac 当前真实结果 |
| `docs/*.md` | 是 | 项目说明、历史记录、排查记录 |

### 不能直接当作 Mac 当前状态使用

| 内容 | 原因 |
|---|---|
| 旧 `file_inventory.csv/sqlite3` | 旧路径和旧时间快照，Mac 上 NFS 挂载后要重新扫描 |
| 旧 RAGFlow 上传报告 | 只说明旧服务器上传历史，不代表 Mac mini 当前知识库 |
| 旧服务器 Docker 容器和数据卷 | 存在服务器上，不能靠复制本项目目录迁移 |
| API key、NAS 密码、RAGFlow 登录态 | 不应放进迁移包，需要在 Mac 上重新安全配置 |
| `__pycache__`、`.pytest_cache`、渲染图片 | 不需要迁移 |

## 4. Mac mini 上建议目录

在 Mac mini 上建议使用：

```bash
mkdir -p ~/Projects
cd ~/Projects
unzip ~/Downloads/enterprise-nas-rag-macmini-handoff.zip
cd enterprise-nas-rag
```

NAS NFS 挂载点固定为：

```text
/Users/Shared/nas/LE_TOUCH_SHR
```

三个业务目录应该是：

```text
/Users/Shared/nas/LE_TOUCH_SHR/PUR-SHR
/Users/Shared/nas/LE_TOUCH_SHR/SALES-SHR
/Users/Shared/nas/LE_TOUCH_SHR/产品设计成果(2021年起)
```

## 5. Mac mini 初始安装命令

### 5.1 安装 Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

按安装完成后的提示把 brew 加入 shell 环境。

### 5.2 安装基础工具

```bash
brew install git python@3.12 node wget tree
brew install --cask docker
```

安装后打开 Docker Desktop，完成首次初始化。

### 5.3 安装 Codex

官方 Codex CLI 安装方式之一：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

也可以使用 Homebrew：

```bash
brew install --cask codex
```

安装后执行：

```bash
codex
```

按提示登录 ChatGPT 账号或配置 API key。

## 6. Mac mini NFS 验收命令

先确认 Mac mini 的有线网口 IP：

```bash
networksetup -listallhardwareports
ipconfig getifaddr en0
```

如果 Ethernet 不是 `en0`，按实际设备名替换。

确认能访问 NAS：

```bash
ping -c 4 192.168.1.153
```

确认 NAS 暴露 NFS：

```bash
showmount -e 192.168.1.153
```

运行项目自带检查脚本：

```bash
cd ~/Projects/enterprise-nas-rag
chmod +x scripts/macmini_nfs_check.sh
./scripts/macmini_nfs_check.sh
```

成功标准：

- Mac mini 拿到公司内网 IP。
- 能 ping 通 `192.168.1.153`。
- `showmount -e 192.168.1.153` 能看到 NAS 导出目录。
- `/Users/Shared/nas/LE_TOUCH_SHR` 能看到三个业务目录。
- 写入测试失败，说明挂载是只读。

## 7. 在 Mac mini 上重新扫描 NAS

创建 Python 环境：

```bash
cd ~/Projects/enterprise-nas-rag
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

先小规模测试扫描：

```bash
python scripts/scan_nas.py \
  --kb-config configs/knowledge_bases.macmini.yaml \
  --max-files 100
```

确认成功后正式扫描：

```bash
python scripts/scan_nas.py \
  --kb-config configs/knowledge_bases.macmini.yaml
```

输出文件：

```text
data/inventory/file_inventory.csv
data/inventory/file_inventory.sqlite3
data/inventory/summary.md
```

生成样本计划：

```bash
python scripts/sample_files.py --per-kb 100
```

## 8. RAGFlow 在 Mac mini 上的注意事项

旧服务器使用的 RAGFlow 镜像是 Linux x86_64 环境下的镜像。Mac mini 是 Apple Silicon ARM 架构。RAGFlow 官方文档曾明确说明 Apple Silicon/ARM 平台需要自行构建镜像，不能假设服务器上的镜像可直接搬到 Mac 上运行。

因此 Mac mini 上有两条路线：

### 路线 A：继续部署 RAGFlow

适合目标是尽量保持和旧服务器一致。

风险：

- Apple Silicon 可能需要自己构建 RAGFlow 镜像。
- Elasticsearch、MinIO、MySQL、Redis 等依赖需要重新部署。
- 旧服务器上的知识库状态不能简单复制，需要迁移数据库/对象存储/索引，复杂度较高。

建议让 Codex 在 Mac 上先检查官方最新 RAGFlow Apple Silicon 支持，再决定是否构建。

### 路线 B：先部署 Dify/轻量 RAG 服务

适合目标是尽快在 Mac mini 上跑通企业 RAG。

优点：

- 更适合 Mac Docker Desktop。
- DeepSeek API 负责回答，不需要本地大模型。
- 先验证 NFS、扫描、上传、问答和引用。

建议第一阶段优先保证数据链路：NFS -> 扫描 -> 小批量导入 -> 问答评估。

## 9. 给 Mac mini 上 Codex 的接手提示词

在 Mac mini 上打开终端：

```bash
cd ~/Projects/enterprise-nas-rag
codex
```

然后把下面这段发给 Codex：

```text
你现在接手一个企业 NAS RAG 项目。请先阅读 docs/MAC_MINI_HANDOFF.md、README.md、configs/knowledge_bases.macmini.yaml、scripts/scan_nas.py、scripts/macmini_nfs_check.sh。

目标：
1. 不修改 NAS 原始文件。
2. 先验证 Mac mini 是否通过有线内网访问 NAS 192.168.1.153。
3. 验证 NFS 只读挂载到 /Users/Shared/nas/LE_TOUCH_SHR。
4. 如果 NFS 未成功，停止并给出具体网络或 DSM 配置问题，不要继续部署 RAG。
5. 如果 NFS 成功，运行 scripts/scan_nas.py 使用 configs/knowledge_bases.macmini.yaml 先扫描 100 个文件。
6. 扫描成功后生成 data/inventory/file_inventory.csv、file_inventory.sqlite3、summary.md。
7. 然后运行 scripts/sample_files.py --per-kb 100 生成样本计划。
8. 再评估是否在 Mac mini 上部署 RAGFlow；注意 Mac mini 是 Apple Silicon，不能假设旧服务器 x86 RAGFlow 镜像可直接运行。

当前重要背景：
- NAS IP 是 192.168.1.153。
- NAS 共享目录是 LE TOUCH SHR。
- 三个业务目录是 PUR-SHR、SALES-SHR、产品设计成果(2021年起)。
- 旧 Ubuntu 服务器上 RAGFlow 已验证过，但 SMB 远程挂载慢；采购 Mac mini 的原因是通过公司内网 NFS 提速。
- 第一版模型推理使用 DeepSeek API，不在 Mac mini 上跑本地大模型。
- 所有 README 和说明文档默认中文。

请先只做环境检查和 NFS 挂载验证，不要上传文件，不要解析文件，不要安装重型服务，除非我确认。
```

## 10. 第一阶段终止条件

只要出现以下任一情况，就先停止，不要继续部署 RAGFlow：

- Mac mini 没有拿到公司内网 IP。
- Mac mini ping 不通 `192.168.1.153`。
- `showmount -e 192.168.1.153` 看不到 NAS 导出目录。
- NFS 挂载后看不到三个业务目录。
- 挂载不是只读。
- 扫描脚本无法读取三个目录。

第一阶段的验收不是“问答能用”，而是：

```text
Mac mini 有线接入公司内网
-> NFS 只读挂载 NAS
-> 重新生成真实文件清单
-> 生成样本计划
```
