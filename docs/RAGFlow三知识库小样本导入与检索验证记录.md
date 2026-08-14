# RAGFlow 三知识库小样本导入与检索验证记录

记录时间：2026-06-30

## 1. 本阶段目标

本阶段的目标不是全量导入 NAS 的 300GB 企业资料，而是先验证一条最小可用链路：

```text
NAS 只读目录
-> RAGFlow 知识库
-> 文档上传
-> 文档解析
-> 切片
-> bge-m3 embedding
-> Elasticsearch 索引
-> 按知识库检索
```

这一步对应 RAGFlow 里的“知识库数据接入、解析和检索验证”阶段，还不是最终的企业问答系统上线。

## 2. 已完成的实际操作

### 2.1 清理错误知识库

之前由于 Windows、SSH、Linux shell 多层传输时中文编码被破坏，RAGFlow 中出现过两个乱码知识库：

```text
<redacted-id>
<redacted-id>
```

本次已经通过 RAGFlow 服务层删除，结果：

```text
success_count: 2
```

为什么要删除：  
这两个知识库没有文档，名字也无法识别。继续保留会干扰后续判断，也容易让用户在 RAGFlow 页面里误选错误知识库。

### 2.2 创建三个中文知识库

已在 RAGFlow 中创建三个知识库：

| 逻辑目录 | RAGFlow 知识库 | 知识库 ID | 当前状态 |
|---|---|---|---|
| `PUR-SHR` | 采购知识库 | `<redacted-id>` | 已创建，当前无样本文档 |
| `SALES-SHR` | 销售知识库 | `<redacted-id>` | 已创建，已导入样本 |
| `产品设计成果(2021年起)` | 产品设计知识库 | `<redacted-id>` | 已创建，已导入样本 |

三个知识库统一使用：

```text
Embedding: bge-m3:latest@local-ollama@Ollama
Parser: naive
LLM: qwen3.6:27b@local-ollama@Ollama
```

为什么这样做：  
知识库先按企业业务权限和业务场景拆开。后续用户问答时，可以先按知识库和权限过滤，再检索内容，避免“先搜全公司资料，再隐藏无权限结果”的安全问题。

### 2.3 导入第一批 NAS 小样本

本次只读读取 NAS 文件，不修改、不移动、不重命名 NAS 原始资料。

NAS 在 RAGFlow 容器内的路径为：

```text
/ragflow/nas/LE_TOUCH_SHR
```

本次导入 7 个样本文件：

| 知识库 | 文件名 | 结果 |
|---|---|---|
| 销售知识库 | `LeTouch- 2024-2026 BEPI.pdf` | 上传成功 |
| 销售知识库 | `LeTouch- BEPI_level.pdf` | 上传成功 |
| 销售知识库 | `107 LT - Sitecom Factory Audit Checklist -V1.3--for Factory-240701.docx` | 上传成功 |
| 产品设计知识库 | `Non-Disclosure Agreement.docx` | 上传成功 |
| 产品设计知识库 | `(水印)Design Concept of Find My Cable.pdf` | 上传成功 |
| 产品设计知识库 | `Design Concept of Find My Cable.pdf` | 上传成功 |
| 产品设计知识库 | `20W饼干超薄充电器报价单.xlsx` | 上传成功 |

采购知识库当前没有导入样本。原因是前一次扫描结果中 `PUR-SHR` 只发现少量非候选文件，暂时没有适合第一批验证的 Office/PDF/TXT 等候选文档。

## 3. 解析与切片结果

截至本次验证，7 个样本文档都已经结束解析任务。

### 3.1 销售知识库

销售知识库当前统计：

```text
文档数: 3
切片数: 23
Token 数: 8754
```

文档明细：

| 文件 | 解析状态 | 切片数 | Token 数 | 说明 |
|---|---:|---:|---:|---|
| `LeTouch- 2024-2026 BEPI.pdf` | DONE | 5 | 2382 | 已解析、已 embedding、已入索引 |
| `LeTouch- BEPI_level.pdf` | DONE | 1 | 313 | 已解析、已 embedding、已入索引 |
| `107 LT - Sitecom Factory Audit Checklist -V1.3--for Factory-240701.docx` | DONE | 17 | 6059 | 已解析、已 embedding、已入索引 |

### 3.2 产品设计知识库

产品设计知识库当前统计：

```text
文档数: 4
切片数: 4
Token 数: 2105
```

文档明细：

| 文件 | 解析状态 | 切片数 | Token 数 | 说明 |
|---|---:|---:|---:|---|
| `Non-Disclosure Agreement.docx` | DONE | 2 | 1243 | 已解析、已 embedding、已入索引 |
| `(水印)Design Concept of Find My Cable.pdf` | DONE | 0 | 0 | 上传成功，但没有切出文本内容 |
| `Design Concept of Find My Cable.pdf` | DONE | 1 | 450 | 已解析、已 embedding、已入索引 |
| `20W饼干超薄充电器报价单.xlsx` | DONE | 1 | 412 | 已解析、已 embedding、已入索引 |

带水印 PDF 的结果很重要：  
它上传成功，但 RAGFlow 没有切出 chunk。这通常说明文件可能是图片型 PDF、扫描件、内容被水印或版面影响，或者普通文本解析器无法提取有效文本。后续如果这类文件很多，需要加 OCR 或换解析策略。

## 4. 检索验证结果

本次做的是 retrieval smoke test，也就是只验证“能不能搜到正确来源文件”，不是最终问答质量评估。

检索使用 RAGFlow 的索引层，按 `kb_id` 过滤对应知识库。这个机制符合企业权限设计：先限定知识库范围，再检索。

### 4.1 销售知识库检索

检索词：

```text
BEPI
```

结果：

```text
召回到 LeTouch- BEPI_level.pdf
召回到 LeTouch- 2024-2026 BEPI.pdf
```

检索词：

```text
Factory Audit Checklist
```

结果：

```text
召回到 107 LT - Sitecom Factory Audit Checklist -V1.3--for Factory-240701.docx
```

结论：销售知识库样本已经可以被检索。

### 4.2 产品设计知识库检索

检索词：

```text
Non-Disclosure Agreement
```

结果：

```text
召回到 Non-Disclosure Agreement.docx
```

检索词：

```text
Find My Cable
```

结果：

```text
召回到 Design Concept of Find My Cable.pdf
```

检索词：

```text
20W
```

结果：

```text
召回到 20W饼干超薄充电器报价单.xlsx
```

结论：产品设计知识库样本已经可以被检索。

## 5. 本次新增脚本

本次新增了三个脚本，均在本地项目目录中：

```text
scripts/ragflow_import_samples.py
scripts/ragflow_check_status.py
scripts/ragflow_retrieval_smoke.py
```

### 5.1 `ragflow_import_samples.py`

用途：

```text
创建三个知识库
清理错误乱码知识库
从 NAS 只读读取第一批样本
上传样本到 RAGFlow
触发解析任务
```

这个脚本是幂等设计：重复执行时，会尽量复用已有知识库和已有文档，避免无意义重复导入。

### 5.2 `ragflow_check_status.py`

用途：

```text
查看三个知识库的文档数、切片数、token 数
查看每个文档的解析状态
查看每个文档是否 DONE、RUNNING、FAIL
```

后续如果导入更多样本，可以用它检查解析是否完成。

### 5.3 `ragflow_retrieval_smoke.py`

用途：

```text
按知识库做最小检索验证
确认关键词能否召回正确来源文件
确认切片已经进入 Elasticsearch 索引
```

这一步验证的是 RAG 的 R，也就是 Retrieval，不是最终生成回答。

## 6. 本阶段的技术原理

### 6.1 NAS 只读挂载的作用

NAS 是企业原始资料源，服务器和 RAGFlow 只能读取它，不应该修改它。

本次导入流程是：

```text
NAS 原始文件
-> RAGFlow 读取文件内容
-> RAGFlow 对象存储保存一份导入副本
-> RAGFlow 数据库记录文档元数据
-> RAGFlow 解析副本并建立索引
```

所以 RAGFlow 中的文档不是直接在 NAS 原文件上做修改。即使后续 RAGFlow 删除知识库，也不应该删除 NAS 原始文件。

### 6.2 为什么不直接全量导入 300GB

直接全量导入有几个风险：

```text
1. 文件类型复杂，很多文件可能无法解析
2. 扫描件和图片型 PDF 会导致大量 0 chunk
3. embedding 会占用 GPU 和时间
4. 索引膨胀后排查问题更难
5. 权限和业务边界没验证前，全量导入有数据泄露风险
```

所以第一阶段必须先用小样本验证解析、切片、检索和引用。

### 6.3 为什么要先检索验证，再做问答

RAG 的核心链路是：

```text
先检索证据
再基于证据生成答案
```

如果检索阶段找不到正确内容，LLM 生成再强也没有用，反而容易编造答案。  
所以本阶段先验证 retrieval smoke test，确认正确文件和片段能被召回。

### 6.4 为什么带水印 PDF 没有切片

`(水印)Design Concept of Find My Cable.pdf` 的解析结果是：

```text
DONE
chunk_num: 0
token_num: 0
```

这不是上传失败，而是“文件被处理了，但没有提取到可用文本”。常见原因：

```text
图片型 PDF
扫描件
文字被渲染成图片
水印或版式影响文本层提取
当前 naive parser 不适合该文件
```

解决方向：

```text
对这类文件加 OCR
或在 RAGFlow 中换更适合 PDF 版面识别的解析配置
或优先使用无水印、可复制文本的原始文件
```

## 7. 当前结论

本阶段已经跑通最小链路：

```text
NAS 三目录
-> RAGFlow 三知识库
-> 小样本文档上传
-> 文档解析
-> bge-m3 embedding
-> Elasticsearch 入索引
-> 按知识库检索召回正确来源文件
```

当前已经可以说：  
RAGFlow 在这台服务器上具备接入 NAS 企业资料并进行检索的基础能力。

但还不能说：  
企业级 RAG 问答系统已经完成。

还缺少：

```text
评估问题集
引用回答验证
无证据拒答验证
权限分组验证
更多文件类型测试
OCR 策略
增量更新策略
全量导入前的批处理方案
```

## 8. 下一步计划

下一步不要马上全量导入 300GB。建议只做三件事：

### 8.1 建立第一版评估问题

每个已导入样本先准备 3-5 个问题，例如：

```text
BEPI 报告的 monitored party 是谁？
BEPI 报告中的地址是什么？
Factory Audit Checklist 中产品月产能是多少？
Find My Cable 的适用场景是什么？
20W 充电器报价单里 LT-G20 的输出规格是什么？
```

每个问题必须绑定来源文件。

### 8.2 在 RAGFlow 里创建聊天应用做引用回答

目标不是让模型自由发挥，而是验证：

```text
回答是否来自检索片段
回答是否显示来源文件
找不到证据时是否拒答
中文问题能否检索英文文件
英文问题能否检索中文/中英混合文件
```

### 8.3 再扩大样本到每个知识库 30-100 个文件

第二批样本要覆盖：

```text
Word
Excel
PPT
PDF
中英文混合文件
扫描件或图片型 PDF
大文件
命名混乱文件
历史文件
最近一年文件
```

只有第二批样本稳定后，才考虑制定全量导入策略。

