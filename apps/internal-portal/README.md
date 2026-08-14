# Waimao 内部知识门户

这是 RAGFlow 之上的轻量业务前端。正式部署由内部代理服务调用 RAGFlow，浏览器不保存 RAGFlow 登录态或 API Key。

## 本地开发

```bash
npm install
npm run dev
```

开发地址：`http://127.0.0.1:4173/internal/`。开发时需要同时运行后端代理，或在 Vite 配置中指向正式 RAGFlow 服务。

## 构建

```bash
npm run build
```

构建产物位于 `dist/`，由 `docker/docker-compose.nas.yml` 只读挂载到 RAGFlow 容器的 `/ragflow/web/dist/internal`，正式入口为：

```text
http://127.0.0.1/internal/
```

办公室试用地址：`http://192.0.2.110/internal/`。当前默认只允许配置的办公室网段访问，三类助手均绑定固定知识库。

当前生产模式为 `trusted_lan`：企业微信工作台提供统一入口，办公室内网成员无需 RAGFlow 账号即可使用。企业微信应用和 SSO 后端已准备好，但示例域名 `company.example.com` 的备案主体尚未完成企业主体校验，因此暂不启用 `wecom` 模式；完成备案主体关联并配置企业可信 IP 后即可切换。

“工作台”展示小时级 NAS 增量同步和每周自动评测状态。同步报告从宿主机日志目录只读挂载，门户不能执行 Docker 命令或修改知识库。

- 当前 NAS 可见资料：标记为 `source_generation=current`、`effective_status=active`
- 旧 NAS 已解析资料：标记为 `source_generation=legacy`、`effective_status=historical`
- 当前 NAS 后来移除的资料：保留索引并标记 `sync_status=missing_from_source`
- 同名同大小的多路径文件：仅保留一个索引对象并统计为重复副本
- 自动评测：每周一 `04:10` 运行 60 条来源覆盖题和 12 条业务准确性题

认证模式：

- `trusted_lan`：办公室试用模式，不要求每位同事登录 RAGFlow；依赖局域网隔离和 Mac 防火墙。
- `wecom`：企业微信 SSO 模式；工作台内静默登录，普通浏览器扫码登录。当前办公室部署使用企业微信已接受的内网 IP 回调域 `192.0.2.110`，仅在办公室网络可达。

RAGFlow 服务密钥和企业微信 Secret 只存放在 `.secrets/internal-portal.env`，不能写入前端或提交到代码库。员工门户不显示 RAGFlow 管理后台入口，管理员仍可直接访问根路径进行运维。

首次启用代理：

```bash
cd /Users/your-account/Documents/ragflow/ragflow
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.nas.yml up -d --build ragflow-cpu internal-portal-api
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.nas.yml exec -T ragflow-cpu sh -lc 'cd /ragflow && PYTHONPATH=/ragflow/internal-scripts:/ragflow python /ragflow/internal-scripts/ragflow_create_internal_portal_token.py'
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.nas.yml up -d --force-recreate internal-portal-api
```

脚本只会为当前 RAGFlow 租户创建一次标记为 `internal-portal` 的专用 Token，并将它写到宿主机的 `.secrets/internal-portal.env`；该文件已加入忽略规则。不要把这个文件发给同事或提交到 Git。

## 助手绑定

| 入口 | RAGFlow 对话 |
| --- | --- |
| 采购知识助手 | `采购助手` |
| 销售知识助手 | `销售助理` |
| 产品资料助手 | `产品设计` |

助手 ID 当前由后端 `backend/app/main.py` 固定绑定，前端只传递 `purchase`、`sales`、`product` 三个业务标识。变更 RAGFlow 助手后需要更新后端并重建代理容器。
