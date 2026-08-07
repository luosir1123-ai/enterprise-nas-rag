# RAGFlow 上传与解析解耦方案

记录时间：2026-07-01

## 1. 结论

可以先把文件上传到 RAGFlow，再由用户在页面里手动解析，或者后续用限速脚本分批触发解析。

这是当前更适合企业 NAS 大目录的方案：

```text
第一步：只上传文件，不解析
第二步：用户或脚本按批次解析
第三步：解析完成后再做检索和问答验证
```

不建议继续使用“上传一个文件马上解析一个文件”的方式，因为解析会调用 PDF/Office 解析、切片、embedding、索引写入，速度明显慢于单纯文件上传。

## 2. 为什么要解耦

RAGFlow 的数据进入知识库不是一个动作，而是三个动作：

```text
上传文件
-> 解析文件
-> 切片并写入向量/全文索引
```

文件上传只是把文件放进 RAGFlow 的对象存储，并在知识库里创建文档记录。解析才会真正消耗 CPU、内存、embedding 服务和索引服务资源。

对我们的 NAS 场景来说，解耦有几个好处：

1. 可以先快速把一批文件放进知识库，避免解析拖慢上传。
2. 用户可以在 RAGFlow 页面上按文件手动点解析。
3. 如果不想手动点，也可以每次只触发少量文件解析，避免队列堆积。
4. 文件上传失败和文件解析失败可以分开排查。
5. 对图片型 PDF、扫描件、CAD、压缩包等特殊文件，可以先上传或跳过，后续单独处理。

## 3. GitHub 和官方资料结论

我查了 RAGFlow 官方文档和 GitHub 相关问题，结论如下：

1. RAGFlow 官方 HTTP API 明确区分“上传文档”和“解析文档”：

```text
POST /api/v1/datasets/{dataset_id}/documents
POST /api/v1/datasets/{dataset_id}/chunks
```

前者负责上传，后者负责解析指定文档。

2. RAGFlow 页面工作流也是先 Add File，再点击绿色 Play 按钮开始解析。也就是说，先上传后解析本身就是 RAGFlow 的正常使用方式。

3. GitHub issue 里有人反馈批量上传和解析时，失败文档会混在成功文档中，重解析也需要额外处理。因此企业场景不要一次性把大量文件全部解析，而应该分批、可回滚、可观察。

## 4. 当前脚本调整

### 4.1 生成上传清单

脚本：

```text
scripts/ragflow_make_upload_manifest.py
```

作用：

```text
从 NAS 三个目录中生成待上传文件清单
跳过已上传且对象存储正常的同名文件
跳过超大文件和不支持格式
输出 /tmp/ragflow_upload_manifest.txt
```

现在这个脚本支持通过环境变量调整批量大小：

```text
RAGFLOW_MANIFEST_MAX_TOTAL_PER_KB
RAGFLOW_MANIFEST_MAX_BYTES
RAGFLOW_MANIFEST_MAX_SCAN_SECONDS_PER_KB
RAGFLOW_MANIFEST_MAX_SCAN_DIRS_PER_PRIORITY
RAGFLOW_MANIFEST_MAX_SCAN_FILES_PER_PRIORITY
RAGFLOW_MANIFEST_MAX_DEPTH
```

示例：

```bash
RAGFLOW_MANIFEST_MAX_TOTAL_PER_KB=50 \
RAGFLOW_MANIFEST_MAX_BYTES=52428800 \
python /tmp/ragflow_make_upload_manifest.py
```

含义：

```text
每个知识库最多选 50 个文件
单文件最大 50MB
```

### 4.2 只上传，不解析

脚本：

```text
scripts/ragflow_upload_manifest_batch.py
```

现在默认行为已经改为：

```text
只上传
不触发解析
```

也就是说，运行后文件会出现在 RAGFlow 知识库页面，但不会立刻开始解析。

如果以后想恢复“上传后自动解析”，需要显式设置：

```bash
RAGFLOW_PARSE_AFTER_UPLOAD=1 python /tmp/ragflow_upload_manifest_batch.py
```

默认不设置时：

```bash
python /tmp/ragflow_upload_manifest_batch.py
```

就是上传-only。

### 4.3 限速触发解析

新增脚本：

```text
scripts/ragflow_queue_unparsed_batch.py
```

作用：

```text
从已经上传但未解析的文件中，每个知识库只触发少量文件解析
不读取 NAS 文件
不修改 NAS 文件
只操作 RAGFlow 内已有文档记录
```

默认每个知识库触发 5 个未解析文档：

```bash
python /tmp/ragflow_queue_unparsed_batch.py
```

每个知识库触发 10 个：

```bash
RAGFLOW_PARSE_LIMIT_PER_KB=10 python /tmp/ragflow_queue_unparsed_batch.py
```

只解析采购知识库：

```bash
RAGFLOW_PARSE_KB_KEYS=purchase RAGFLOW_PARSE_LIMIT_PER_KB=10 python /tmp/ragflow_queue_unparsed_batch.py
```

可选知识库 key：

```text
purchase
sales
product_design
```

## 5. 推荐执行策略

### 方案 A：你手动解析

适合你想在 RAGFlow 页面里自己控制文件解析顺序。

流程：

```text
1. 我生成 manifest
2. 我运行上传-only 脚本
3. 你打开 RAGFlow 知识库页面
4. 你按文件或按批次点击绿色 Play 按钮解析
5. 我再检查解析结果和检索效果
```

优点：

```text
最直观
不会突然堆满解析队列
你能看到每个文件的状态
```

缺点：

```text
文件多时手动操作费时间
```

### 方案 B：脚本限速解析

适合文件数量变多后使用。

流程：

```text
1. 先上传-only
2. 每次触发每个知识库 5-10 个文件解析
3. 等待完成
4. 再触发下一批
```

优点：

```text
不用手工点很多文件
不会一次打爆 RAGFlow 队列
失败文件容易定位
```

缺点：

```text
仍然需要定期检查状态
```

### 方案 C：全自动解析

暂时不推荐。

原因：

```text
NAS 文件多
PDF 类型复杂
部分文件需要 OCR
失败文件会混在成功文件中
embedding 和索引服务压力不可控
```

## 6. 下一步建议

我建议下一步按以下方式推进：

```text
1. 第二批先只上传，不解析
2. 每个知识库扩大到 30-50 个文件
3. 文件大小限制先放宽到 50MB
4. 上传完成后，你在 RAGFlow 页面确认文件是否都出现
5. 再决定手动解析，还是用限速脚本解析
```

这个方式比“边上传边解析”更适合目前的企业 NAS 试点。

## 7. 注意事项

1. “上传完成”不等于“可以问答”。只有解析完成并生成切片后，RAGFlow 才能检索和回答。
2. 如果文件上传了但没有解析，知识库页面能看到文件，但 `chunk_num` 会是 0。
3. 图片型 PDF 即使解析完成，也可能没有切片，后续需要 OCR。
4. 不要一次性上传全 NAS，先按业务目录和文件类型分批推进。
5. 每批都要保留 manifest 和 report，方便失败后重跑和追溯。
