# NAS 准备清单

## 必做项

1. 进入 DSM `存储管理器`，确认系统警告来源。
2. 检查存储池、卷、硬盘、容量和文件系统状态。
3. 加装官方兼容 `4GB DDR4 non-ECC SO-DIMM`，总内存提升到 `6GB`。
4. 安装 `Container Manager`，但第一阶段只运行轻量工具。
5. 创建 `/volume1/docker/enterprise-rag/` 目录：

```text
/volume1/docker/enterprise-rag/
  compose/
  data/
  inventory/
  samples/
  eval/
  logs/
```

## 不在 NAS 上运行

```text
RAGFlow 全套
本地大模型
大规模 OCR
大规模 embedding
Elasticsearch/OpenSearch
Milvus
```

## 账号和权限

创建专用只读账号：

```text
rag_reader
```

授权范围：

```text
PUR-SHR：只读
SALES-SHR：只读
产品设计成果(2021年起)：只读
其他目录：无权限
```

## 网络原则

后续外部服务器通过局域网读取 NAS：

```text
NAS IP: 192.168.1.153
协议：SMB 或 NFS
权限：只读挂载
```

不要使用 QuickConnect 作为索引数据通道。
