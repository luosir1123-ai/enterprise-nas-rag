# RAGFlow问答链路诊断记录

记录时间：2026-06-30

## 当前结论

当前 RAGFlow 问答链路已经跑通。

测试问题：

```text
LT-G20大理石 单价多少？
```

后端测试返回：

```text
LT-G20大理石的单价为￥26.00 [ID:0]。
```

前端页面测试返回：

```text
型号为LT-G20大理石的充电器，其单价（不含包装未税）为￥26.00。
```

引用来源：

```text
20W饼干超薄充电器报价单.xlsx
```

## 已完成

1. NAS 三目录已经作为资料源接入 Ubuntu 服务器。
2. RAGFlow 已部署在 Ubuntu 服务器 `172.21.238.68`。
3. RAGFlow 容器、MySQL、Elasticsearch、MinIO、Redis 均处于运行状态。
4. 已创建三个知识库：
   - 采购知识库
   - 销售知识库
   - 产品设计知识库
5. 已导入部分样本文档。
6. 检索链路已验证成功，能够从 `20W饼干超薄充电器报价单.xlsx` 命中 `LT-G20大理石` 的价格信息。
7. 当前 Chat 已绑定：
   - 销售知识库
   - 产品设计知识库
8. 当前 Chat 已切换为本地模型：
   - LLM：`qwen3.6:27b@local-ollama@Ollama`
   - Embedding：`bge-m3:latest@local-ollama@Ollama`
9. 已修复本地 Qwen3 模型在 RAGFlow 中不返回正文的问题。

## 问题原因

这次“提问题不回答”不是 NAS、挂载、知识库或检索的问题。

实际原因有两个：

1. DeepSeek API 返回 `402 Payment Required / Insufficient Balance`，表示账号余额或额度不足。RAGFlow 已经检索到答案，但在调用 DeepSeek 生成回答时失败，所以前端表现为卡住或不回答。
2. 本地 `qwen3.6:27b` 默认会输出到 Ollama 的 `thinking` 字段，而不是正常的 `content` 字段。RAGFlow 前端主要读取 `content`，所以看起来像模型没有回答。

## 本次修复

已备份 RAGFlow 原文件：

```text
/data/home/lxd2/ragflow-tools/backups/chat_model.py.bak-20260630-ollama-think
```

已修改容器内文件：

```text
/ragflow/rag/llm/chat_model.py
```

本地保留补丁文件：

```text
D:\workspace\enterprise-nas-rag\patches\chat_model.py
```

修改逻辑：

1. 当 provider 是 `Ollama` 且模型名包含 `qwen3` 时，向请求里加入：

```text
think: false
enable_thinking: false
```

2. 同时给 Ollama 请求加入输出长度上限：

```text
options.num_predict = 512
```

这样做的原因：

1. `think:false` 让 Qwen3 不再只输出思考内容，而是把最终答案放到 `content` 字段。
2. `num_predict=512` 防止模型无限续写，避免前端长期显示 Running。
3. 这个修改只针对 Ollama + Qwen3，不影响 DeepSeek、OpenAI 或其他模型。

## 验证结果

后端 smoke test 已通过：

```text
Generate answer: 1784.5ms
Generated tokens approximately: 21
Token speed: 11/s
```

页面端也已通过：

1. 打开 `http://172.21.238.68/chat/5dc6373c746011f1b4e439a2bb3fe40b`
2. 输入 `LT-G20大理石 单价多少？`
3. 页面正常返回价格，并显示来源文件。

## 当前仍未完成

1. 采购知识库目前还没有导入样本文档。
2. 销售知识库和产品设计知识库只导入了少量样本文档，还不是完整企业知识库。
3. 尚未建立每个知识库 20-50 条黄金评估问题。
4. 尚未做批量导入自动化。
5. 尚未做严格的权限过滤验证。
6. 当前补丁是在运行容器内修改的，如果未来重建 RAGFlow 镜像或重新拉取容器，需要重新应用补丁或做成正式镜像。

## 下一步

下一步不继续调模型，而是继续补数据和评估。

推荐顺序：

1. 给采购知识库导入第一批 10-30 个样本文档。
2. 给销售知识库、产品设计知识库继续补充样本文档。
3. 每个知识库准备 20 条真实业务问题。
4. 用这些问题测试：
   - 是否能找到正确来源
   - 是否能正确引用文件
   - 没有证据时是否拒答
5. 根据测试结果再调检索参数，例如 `top_n`、相似度阈值、知识库范围。
6. 等三类知识库样本验证稳定后，再做批量导入和企业权限策略。

## 当前可用测试问题

```text
LT-G20大理石 单价多少？
```

预期答案：

```text
LT-G20大理石的单价（不含包装未税）为 ￥26.00。
```

预期来源：

```text
20W饼干超薄充电器报价单.xlsx
```
