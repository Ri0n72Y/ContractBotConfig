# WorkBuddy Host Spec

## 1. Purpose

定义办公室 WorkBuddy 以及微信远程 WorkBuddy Host 的安装、运行与验收要求。

## 2. Office WorkBuddy

### WB-OFF-01 Skill

必须安装指定版本 `opencontracts-contract` Skill。

### WB-OFF-02 MCP

必须配置认证 OpenContracts MCP。优先项目级配置；需要跨项目复用时再使用用户级配置。

配置样例不得包含真实 token。

### WB-OFF-03 Local files

用户显式选择的工作目录是本地文件权限边界。Skill 不应自行扫描无关用户目录寻找合同。

### WB-OFF-04 Model ownership

WorkBuddy 使用客户自己的登录/模型配置；ContractBot 服务端不代管该模型 token。

## 3. WeChat Host

### WB-WX-01 Platform

Host 使用官方支持的 macOS/Windows WorkBuddy，并满足当前微信客服号/微信助理最低版本要求。

### WB-WX-02 Always-on

Host 必须：

```text
powered on
network connected
WorkBuddy logged in
assistant/channel enabled
sleep disabled during service window
```

健康检查不能把“进程存在”当成“微信通道可用”。

### WB-WX-03 Dedicated identity

首版每个客户/客服入口使用独立 WorkBuddy 绑定和独立 OpenContracts 凭证。不得把一个本地助理会话当成天然多租户隔离容器。

### WB-WX-04 OS isolation

建议每个 Host 使用：

- 非管理员 OS 账户；
- 专属工作目录；
- 不挂载无关个人文件；
- 最小 OpenContracts 权限；
- 日志与临时文件独立目录。

### WB-WX-05 Workspace

远程任务固定使用助理专属工作目录时，合同 Skill 进一步约定：

```text
inbox/
work/
output/
metadata/
```

不同任务产物必须可区分，不依赖“最后一个文件”隐式指针。

## 4. Channel behavior

根据当前 WorkBuddy 官方文档，微信远程通道可以：

- 发起/继续远程任务；
- 发送后续指令；
- 批准需要确认的执行；
- 查看输出和通知；
- 在桌面助理查看完整记录和生成文件。

首版 spec 不假设 DOCX/PDF 一定能作为微信聊天附件直接发送。PoC 必须记录：

```text
text response support
incoming file support
outgoing artifact support
maximum file size
multi-user conversation behavior
approval UX
```

## 5. MCP configuration

WorkBuddy adapter 至少支持：

```text
server URL
authentication configuration
server enable/disable
tool enable/disable if available
```

若使用 OAuth，测试 token refresh/reconnect；若使用静态 token，必须有轮换步骤。

## 6. Failure behavior

### Host offline

不得返回合同处理成功。渠道恢复后不自动重放可能产生写副作用的任务。

### MCP unavailable

- 纯本地分析/修改可在明确不需要企业资料时继续；
- 依赖企业模板/历史的任务必须标记企业数据不可用；
- 归档任务不得伪装成功。

### Upload commit unknown

返回人工核查，不由 WorkBuddy 自动重跑写入 helper。

## 7. Operational checks

建议提供 host smoke test：

```text
check WorkBuddy version
check Skill version
check OpenContracts MCP auth
check target corpus visibility
check output directory writable
check renderer
check upload helper config (without writing)
```

## 8. Acceptance criteria

- [ ] WorkBuddy 安装 Skill 成功；
- [ ] MCP 认证连接成功；
- [ ] 本地合同分析成功；
- [ ] 本地合同修改输出 DOCX；
- [ ] 微信发起分析成功；
- [ ] 微信发起修改成功；
- [ ] 宿主机离线行为已验证；
- [ ] MCP 权限越权被拒绝；
- [ ] 微信产物回传真实能力被记录；
- [ ] Host 重启后 Skill/MCP/channel 可恢复。
