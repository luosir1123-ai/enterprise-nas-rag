# RAGFlow 首批文件上传与检索验证记录

记录时间：2026-07-01

## 1. 本次目标

本次目标是把 NAS 三个目录中的一批真实文件上传到服务器上的 RAGFlow，并确认它们可以被解析、切片、embedding 和检索。

这一步属于 RAG 项目的“数据接入与索引验证”阶段，不是最终大规模全量上线。它验证的是：

```text
NAS 只读挂载
-> 选择一批可解析文件
-> 上传到 RAGFlow 对象存储
-> 触发 RAGFlow 文档解析
-> 生成切片和向量
-> 在对应知识库中检索命中
```

## 2. 当前部署环境

RAGFlow 部署在 Ubuntu 服务器：

```text
服务器 IP: 172.21.238.68
RAGFlow 地址: http://172.21.238.68/
RAGFlow 容器: docker-ragflow-cpu-1
RAGFlow 项目路径: /data/home/lxd2/ragflow
```

NAS 在服务器和容器中的挂载位置：

```text
服务器宿主机: /mnt/nas/LE_TOUCH_SHR
RAGFlow 容器: /ragflow/nas/LE_TOUCH_SHR
```

本次只处理三个业务目录：

```text
/ragflow/nas/LE_TOUCH_SHR/PUR-SHR
/ragflow/nas/LE_TOUCH_SHR/SALES-SHR
/ragflow/nas/LE_TOUCH_SHR/产品设计成果(2021年起)
```

## 3. 已完成的事情

### 3.1 生成上传清单

新增脚本：

```text
scripts/ragflow_make_upload_manifest.py
```

作用：

```text
从三个 NAS 目录中选择一批适合第一轮导入的文件
跳过已成功上传且对象存储正常的同名文件
跳过超大文件、图片、CAD、压缩包、系统临时文件
生成 /tmp/ragflow_upload_manifest.txt
```

本次生成的 manifest 共 18 个文件：

```text
采购知识库: 9 个
销售知识库: 5 个
产品设计知识库: 4 个
```

生成报告已经保存到：

```text
data/inventory/ragflow_upload_manifest_make_report.json
```

### 3.2 上传 manifest 文件并触发解析

新增脚本：

```text
scripts/ragflow_upload_manifest_batch.py
```

作用：

```text
读取 /tmp/ragflow_upload_manifest.txt
按路径判断文件属于哪个知识库
上传文件到 RAGFlow/MinIO 对象存储
触发 RAGFlow 文档解析任务
输出上传和解析触发报告
```

本次上传结果：

```text
manifest 文件总数: 18
成功上传并触发解析: 18
上传错误: 0
```

上传报告已经保存到：

```text
data/inventory/ragflow_upload_manifest_report.json
```

### 3.3 清理采购知识库中的坏记录

之前有一批采购文档在 RAGFlow 中创建了文档记录，但对象存储里找不到对应文件。这类记录的表现是：

```text
RAGFlow 页面能看到文件名
解析时报 Can not find file from minio
检索不到内容
```

原因是早期脚本把中文 NAS 相对路径拼到了对象存储路径中，经过 Windows、SSH、Docker 多层传输后路径出现乱码或空路径段，导致 RAGFlow 解析时找不到 MinIO 对象。

本次脚本已清理 8 个这类坏记录，并用稳定方式重新上传：

```text
報價單CBATB5005-100A  20260225  RMB.pdf
Acon Type-C 1m EPR TBT4 Cable Report 2022-05-05证书.pdf
Thunderbolt E-Marker Cable_ACON_CBATB5005-100A_Rev 1.0.pdf
SW09无线充报价单260127.pdf
SW09产品规格书.pdf
20250310更新 FM01  FM03-ASR UI操作(LET).xlsx
LT-T43-X-MARK CARD THREE-产品规格书20260121.docx
LT-T43-X-MARK CARD THREE-产品规格书20260121.pdf
```

这次修复的关键原则是：

```text
NAS 真实路径只写入报告
RAGFlow 对象存储路径只使用稳定英文批次目录
不要把中文长路径直接作为 MinIO 存储路径
```

## 4. 当前知识库状态

截至 2026-07-01 15:07 左右，三个知识库状态如下：

| 知识库 | 文档数 | 切片数 | 当前状态 |
|---|---:|---:|---|
| 采购知识库 | 12 | 142 | 已有真实采购文件可检索 |
| 销售知识库 | 8 | 78 | 已有证书、验厂类文件可检索 |
| 产品设计知识库 | 8 | 23 | 已有产品设计、认证、报价类文件可检索 |

补充说明：

```text
采购知识库里早期遗留的 CBATB5005-100A01.pdf 已补触发解析。
部分产品设计 PDF 解析后没有生成切片，通常说明文件可能是图片型或扫描型 PDF，后续需要 OCR。
```

## 5. 检索验证结果

已在 RAGFlow 内部检索层做 6 个 smoke test，全部命中预期文件。

| 知识库 | 测试问题 | 命中文件 |
|---|---|---|
| 采购知识库 | `SW09无线充报价单` | `SW09无线充报价单260127.pdf` |
| 采购知识库 | `CBATB5005-100A 报价单` | `報價單CBATB5005-100A  20260225  RMB.pdf` |
| 销售知识库 | `BSCI` | `LeTouch -2024-2025 BSCI.pdf` 等 |
| 销售知识库 | `GRS` | `LeTouch-2024GRS.pdf` |
| 产品设计知识库 | `ETL报告` | `0930 ETL报告.pdf` |
| 产品设计知识库 | `Super slim type c charger` | `Super slim type c charger LeTouch 202208.pdf` |

这说明当前不是只“上传了文件名”，而是已经完成：

```text
文件上传
文档解析
切片生成
向量索引
按知识库检索命中
```

## 6. 为什么不直接上传全部 300GB

当前不能直接把 NAS 300GB 全部扔进 RAGFlow，原因有四个：

1. NAS 远程挂载目录遍历很慢，大目录全递归容易长时间无反馈。
2. RAGFlow 解析和 embedding 是计算密集任务，一次性导入太多会造成队列堆积。
3. 企业资料里有大量图片、CAD、压缩包、视频、系统文件，第一版不适合直接导入。
4. 部分 PDF 是图片型或扫描型 PDF，不做 OCR 就无法形成可检索文本切片。

所以当前采用的正确方式是：

```text
小批量 manifest
-> 上传
-> 解析
-> 检索验证
-> 扩大下一批
```

## 7. 后续继续导入的标准流程

后续继续导入时，按这个顺序执行：

```text
1. 生成上传清单
2. 检查清单文件数量和类型
3. 上传清单中的文件
4. 等待解析完成
5. 检查 doc_num、chunk_num、run 状态
6. 做检索 smoke test
7. 再进入下一批
```

对应脚本：

```text
scripts/ragflow_make_upload_manifest.py
scripts/ragflow_upload_manifest_batch.py
```

服务器容器内对应路径：

```text
/tmp/ragflow_make_upload_manifest.py
/tmp/ragflow_upload_manifest_batch.py
/tmp/ragflow_upload_manifest.txt
/tmp/ragflow_upload_manifest_make_report.json
/tmp/ragflow_upload_manifest_report.json
```

## 8. 下一步建议

下一步不要马上做全量导入，建议按业务优先级扩大第二批：

```text
采购知识库: 继续补 2025/2026 常用供应商报价、规格书、认证报告
销售知识库: 补客户资料、报价方案、合同、验厂/认证材料
产品设计知识库: 补 BOM、产品规格书、设计方案、认证报告
```

每批建议控制在：

```text
每个知识库 20-50 个文件
单文件优先小于 20MB
先处理 PDF/DOCX/XLSX/PPTX/TXT/CSV
图片型 PDF 单独归为 OCR 队列
CAD、视频、压缩包暂不进入第一版
```

验收标准：

```text
上传错误为 0
对象存储文件存在
解析 run 状态为 DONE
chunk_num 大于 0
检索测试能命中预期文件
问答回答时能引用来源文件
```

## 9. 当前遗留问题

1. NAS 遍历速度较慢，不能依赖一次性深度递归扫描。
2. 部分 PDF 解析后没有切片，后续需要 OCR。
3. RAGFlow 页面问答还需要继续验证 assistant 绑定、知识库选择、模型配置和引用回答效果。
4. 旧文档中有部分中文显示乱码，应后续单独整理，不影响本次 RAGFlow 入库结果。
