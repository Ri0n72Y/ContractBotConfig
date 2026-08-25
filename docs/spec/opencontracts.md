# OpenContracts Spec

## 1. Purpose

定义 OpenContracts 在新架构中的公网 MCP、认证、文件导入、租户隔离和 patch 约束。

## 2. Endpoint requirements

### OC-01 HTTPS only

生产 MCP/API 只能通过 HTTPS 暴露。

### OC-02 Authenticated private MCP

企业私有合同默认使用认证 MCP，例如上游 `/mcp/me/` 或等价的受认证 corpus-scoped endpoint。

匿名 `/mcp/`：

- 只能访问明确公开数据；
- 企业私有部署可以由 reverse proxy 禁用；
- Skill 不得默认连接匿名入口。

### OC-03 Discovery first

Skill/adapter 运行前应通过 MCP discovery 确认工具，不把某一 OpenContracts 版本的工具全集写死为永久事实。

## 3. Authorization requirements

- request principal 必须可映射为 OpenContracts 用户/服务身份；
- MCP 工具必须通过上游 service layer；
- patch 新增工具不得直接 ORM 绕过 `visible_to_user` / permission service；
- corpus slug/ID 参数不能赋予额外权限；
- 私有文档即使位于公开/共享 corpus 中，也必须遵守文档级可见性。

## 4. Client credential modes

支持按部署选择：

```text
interactive user auth / OAuth / JWT
service credential
corpus-scoped WorkerKey（仅适合受限导入）
```

WorkerKey 不能被当成通用 MCP 读取凭证，也不能放入通用 Skill 包。

## 5. File ingestion

### OC-UP-01

大文件上传使用 HTTPS multipart / OpenContracts 官方导入面，不使用 base64 MCP JSON 作为默认方案。

### OC-UP-02

上传 helper 输入：

```text
file path
sha256
logical target corpus
contract identity
intent: create | version
```

### OC-UP-03

已存在合同的 version/update 必须有显式用户确认或已配置的确定性无人值守策略；默认是要求确认。

### OC-UP-04

上传后必须通过 MCP 读取事实核验：至少确认文档身份和正文可读；需要语义检索场景时再确认 search 命中。

## 6. Write status contract

所有写 helper/扩展工具统一返回：

```json
{
  "status": "complete|processing|blocked|manual_review|failed",
  "retry_safe": true,
  "request_id": null,
  "document_id": null,
  "version_id": null,
  "source_sha256": "...",
  "reason": null
}
```

规则：

- `blocked` 必须确定尚未提交；
- `manual_review` 一律 `retry_safe=false`；
- timeout/cancel/connection reset after request body send 视为 commit unknown；
- `failed` 只能用于已知未提交或远端明确拒绝。

## 7. Patch policy

目录目标：

```text
patches/opencontracts/
scripts/opencontracts/
```

每个 patch 必须带：

```text
target upstream tag/commit
reason
files changed
apply command
verify command
rollback note
```

禁止：

- vendor 整个 OpenContracts fork 到本仓库；
- 复制上游已有 MCP tool；
- 在 patch 中写客户 token/corpus id；
- 直接修改数据库跳过 migration/service layer。

## 8. Required scripts

### `check_version.py`

- 输出当前 OpenContracts version/commit；
- 与支持矩阵比较；
- 不匹配时非零退出。

### `configure_public_mcp.py`

- 检查公网 base URL、allowed hosts、proxy headers、MCP route；
- 检查匿名入口策略；
- 支持 dry-run；
- 不生成真实 TLS private key。

### `bootstrap_tenant.py`

- 创建/验证客户用户或服务身份；
- 创建/验证逻辑 corpuses；
- 设置权限；
- 可选 mint WorkerKey；
- 重复执行不创建重复对象。

### `apply_patch.py`

- 版本检查；
- 检测 patch 已应用；
- 原子或 fail-before-write；
- 输出变更清单。

### `verify.py`

至少测试：

```text
authenticated MCP handshake
discovery
allowed corpus read/search
denied corpus isolation
file upload
post-upload verification
```

## 9. Acceptance criteria

- [ ] WorkBuddy 使用非匿名凭证连接成功；
- [ ] 无凭证不能读取私有合同；
- [ ] 客户 A 凭证不能读客户 B corpus；
- [ ] 文件上传后能通过 MCP 找到并读取；
- [ ] 写入 timeout 测试不自动重试；
- [ ] patch 在支持版本可重复应用/检测；
- [ ] 上游升级不匹配时脚本 fail-closed。
