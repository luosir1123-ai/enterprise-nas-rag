# RAGFlow 部署与 NAS 接入记录

记录时间：2026-06-29

## 本阶段目标

本阶段做的是 RAGFlow 项目的第二步：在 Ubuntu 服务器上把 RAGFlow 服务跑起来，并把 NAS 已经挂载好的企业资料目录以只读方式暴露给 RAGFlow 容器。

这一步的定位是“检索系统运行环境准备 + 数据源可见性验证”，还不是正式知识库导入，也不是文档解析、切片、embedding 或问答检索。

## 已完成内容

### 1. Ubuntu 服务器可用

服务器地址：

```text
192.0.2.68
```

已经确认可以通过 SSH 密钥登录 `root@192.0.2.68`。

### 2. NAS 目录已经接入服务器

NAS 共享通过 SMB over Tailscale 挂载到 Ubuntu：

```text
/mnt/nas/LE_TOUCH_SHR
```

挂载属性为只读：

```text
//100.113.180.91/LE TOUCH SHR on /mnt/nas/LE_TOUCH_SHR type cifs (ro,...)
```

当前 RAG 试点只使用这个共享下面的三个目录：

```text
/mnt/nas/LE_TOUCH_SHR/PUR-SHR
/mnt/nas/LE_TOUCH_SHR/SALES-SHR
/mnt/nas/LE_TOUCH_SHR/产品设计成果(2021年起)
```

### 3. Docker 与 Compose 已安装

服务器已安装 Docker 和 Docker Compose：

```text
Docker version 29.1.3
Docker Compose version 2.40.3
```

并设置了 Elasticsearch 需要的内核参数：

```text
vm.max_map_count=262144
```

### 4. RAGFlow 已部署

RAGFlow 官方项目已放在服务器：

```text
/data/home/lxd2/ragflow
```

RAGFlow Docker 配置目录：

```text
/data/home/lxd2/ragflow/docker
```

当前使用 CPU 版 RAGFlow：

```text
swr.cn-north-4.myhuaweicloud.com/infiniflow/ragflow:v0.26.2
```

### 5. 已解决 Docker Hub 超时问题

服务器直接拉 Docker Hub 镜像时出现超时：

```text
failed to resolve reference "docker.io/valkey/valkey:8"
dial tcp ...:443: i/o timeout
```

处理方式：新增 Compose override 文件，不修改官方 `docker-compose.yml` 主文件。

新增文件：

```text
/data/home/lxd2/ragflow/docker/docker-compose.cn-images.yml
```

这个文件把 RAGFlow 依赖镜像切换到华为云镜像源：

```text
Elasticsearch: swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/elasticsearch:8.11.3
MySQL:         swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/mysql:8.0.39
MinIO:         swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/pgsty/minio:RELEASE.2026-03-25T00-00-00Z
Redis/Valkey:  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/valkey/valkey:8
```

这样做的原因是：保留官方配置，另外用 override 覆盖镜像地址，后续升级或回退更容易。

### 6. NAS 已挂进 RAGFlow 容器

新增 Compose override 文件：

```text
/data/home/lxd2/ragflow/docker/docker-compose.nas.yml
```

作用是把宿主机 NAS 挂载路径只读映射进 RAGFlow 容器：

```yaml
services:
  ragflow-cpu:
    volumes:
      - /mnt/nas/LE_TOUCH_SHR:/ragflow/nas/LE_TOUCH_SHR:ro
```

容器内可见路径：

```text
/ragflow/nas/LE_TOUCH_SHR
```

容器内已确认能看到三个目录：

```text
/ragflow/nas/LE_TOUCH_SHR/PUR-SHR
/ragflow/nas/LE_TOUCH_SHR/SALES-SHR
/ragflow/nas/LE_TOUCH_SHR/产品设计成果(2021年起)
```

写入测试结果：

```text
WRITE_BLOCKED
touch: cannot touch '/ragflow/nas/LE_TOUCH_SHR/.codex_write_test': Read-only file system
```

这说明 RAGFlow 容器可以读取 NAS 资料，但不能修改 NAS 原文件，符合企业知识库的安全要求。

### 7. RAGFlow 服务已启动

启动命令：

```bash
cd /data/home/lxd2/ragflow/docker
COMPOSE_PROFILES=elasticsearch,cpu docker compose \
  -f docker-compose.yml \
  -f docker-compose.nas.yml \
  -f docker-compose.cn-images.yml \
  up -d
```

当前核心容器：

```text
docker-es01-1
docker-minio-1
docker-mysql-1
docker-redis-1
docker-ragflow-cpu-1
```

当前状态：

```text
Elasticsearch: healthy
MinIO: healthy
MySQL: healthy
Redis/Valkey: healthy
RAGFlow CPU: up
```

RAGFlow Web 端口：

```text
80
```

RAGFlow API 端口：

```text
9380
```

本机到服务器端口连通性已经验证：

```text
192.0.2.68:80   TcpTestSucceeded=True
192.0.2.68:9380 TcpTestSucceeded=True
```

服务器本机访问 RAGFlow 首页返回：

```text
HTTP/1.1 200 OK
```

访问地址：

```text
http://192.0.2.68/
```

## 当前还没完成的内容

### 1. 还没有在 RAGFlow 里创建正式知识库

现在只是让 RAGFlow 能看到 NAS 文件路径，还没有在 RAGFlow UI 中创建：

```text
采购知识库
销售知识库
产品设计知识库
```

### 2. 还没有把 NAS 文件导入 RAGFlow

RAGFlow 默认更偏向“上传文件到知识库”的工作流。虽然容器内已经能看到 NAS 文件路径，但还需要确认 RAGFlow UI 或 API 是否支持直接从容器本地路径批量导入。

如果 UI 不支持直接选择容器路径，就需要做一个“批量导入脚本”：

```text
NAS 只读路径 -> 按知识库筛选候选文件 -> 调用 RAGFlow API 上传 -> RAGFlow 解析和建索引
```

### 3. 还没有完成文档解析、切片和向量化

以下步骤还没开始：

```text
PDF/Office 文档解析
OCR
chunk 切片
embedding
向量索引
rerank
引用回答
低置信度拒答
```

### 4. 还没有配置企业级模型

RAGFlow 已经启动，但还需要配置：

```text
LLM
embedding 模型
reranker 模型
OCR 或文档解析策略
```

第一版建议优先用外部 API 或外部 embedding 服务，避免在 NAS 或初期环境里堆太多重计算。

### 5. 还没有解决深层目录批量枚举性能

已经观察到：通过 SMB over Tailscale 读取某些深层目录时可能比较慢。尤其是 `SALES-SHR` 或大量文件目录，不适合一次性全量深度枚举。

后续导入必须做分批策略：

```text
按知识库分批
按年份分批
按目录深度分批
按文件类型分批
失败可重试
记录导入状态
```

## 当前阶段的原理解释

### 1. 为什么先部署 RAGFlow

RAGFlow 是完整 RAG 系统的一部分，它负责：

```text
知识库管理
文档上传
文档解析
文本切片
向量化
检索
问答
引用来源
```

但它不能凭空访问 NAS 文件。必须先把 NAS 数据通过服务器挂载和 Docker volume 映射暴露给它。

### 2. 为什么 NAS 要只读挂载

企业资料是原始数据源，RAG 系统不应该直接修改原文件。

只读挂载的好处：

```text
防止误删
防止误改
防止程序异常写入
保留 NAS 作为权威资料源
降低试点风险
```

### 3. 为什么不用 QuickConnect 做索引通道

QuickConnect 适合网页访问 DSM，不适合大规模文档扫描和索引。

当前实际使用的是：

```text
NAS -> Tailscale -> SMB -> Ubuntu -> Docker volume -> RAGFlow
```

这样比 QuickConnect 更适合服务器长期读取文件。

### 4. 为什么用 SMB 而不是 NFS

之前测试 NFS 时出现：

```text
access denied by server
```

SMB 已经确认可用，所以当前优先用 SMB 推进项目。企业项目第一原则是先跑通可验证链路，再优化协议。

后续如果需要更高性能，可以重新调 NFS，但不应该卡住当前试点。

### 5. 为什么要用 Docker Compose override

官方 `docker-compose.yml` 不直接改，原因是：

```text
保留官方默认配置
降低升级冲突
方便定位我们自己改过什么
可以按需启用 NAS 挂载和国内镜像源
```

当前额外使用两个 override：

```text
docker-compose.nas.yml        # NAS 只读挂载
docker-compose.cn-images.yml  # 国内镜像源
```

## 下一步建议

### 第一步：打开 RAGFlow 页面

浏览器访问：

```text
http://192.0.2.68/
```

先完成账号注册或登录。

### 第二步：配置模型

至少需要配置：

```text
LLM
embedding 模型
```

如果不配置 embedding，文档即使上传，也无法正常完成向量索引。

### 第三步：创建三个知识库

建议按业务目录建立三个知识库：

```text
采购知识库
销售知识库
产品设计知识库
```

### 第四步：做小样本导入

不要一开始导入 300GB。

建议第一批每个知识库只导入：

```text
10-30 个文件
```

文件类型优先：

```text
.pdf
.docx
.xlsx
.pptx
.txt
.md
.csv
```

第一批目标不是覆盖全部资料，而是验证：

```text
能否上传
能否解析
能否切片
能否 embedding
能否检索
回答是否带来源
没有证据时是否拒答
```

### 第五步：如果 UI 不能直接导入 NAS 路径，就开发导入脚本

脚本逻辑：

```text
读取 data/inventory/file_inventory.csv
按 knowledge_base 过滤
按文件类型过滤
按样本数量过滤
调用 RAGFlow API 上传文件
记录 upload_status / parse_status / dataset_id / document_id
失败文件单独记录
```

这是下一阶段最可能需要开发的内容。

## 当前结论

本阶段已经完成：

```text
NAS 三目录只读接入 Ubuntu
RAGFlow CPU 版部署成功
RAGFlow 依赖服务启动成功
NAS 目录在 RAGFlow 容器内可见
NAS 写入被阻止
RAGFlow Web 页面可访问
```

本阶段还没有完成：

```text
RAGFlow 知识库创建
NAS 文件正式导入
文档解析
向量索引
问答检索
评估集验证
```

下一步的核心任务不是继续改 NAS，而是进入 RAGFlow：

```text
配置模型 -> 创建三个知识库 -> 小样本导入 -> 验证检索效果
```
