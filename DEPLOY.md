# 在线演示部署

发布入口是 **demo_app.py**。`app.py` 是本地完整版本，不应直接作为匿名公开服务部署。

## Streamlit Community Cloud

1. 访问 https://share.streamlit.io ，使用自己的GitHub账号登录并授权仓库访问。
2. 点击 **Create app** → **Yup, I have an app**。
3. 填入以下部署参数：

| 设置 | 值 |
| --- | --- |
| Repository | `fhanlong/ai-market-insight-copilot` |
| Branch | `online-demo` |
| Main file path | `demo_app.py` |
| Advanced settings / Python | `3.12` |
| Secrets | 留空，不需要API密钥 |
| App URL | 可选，自定义域名前缀由平台检查是否可用 |

4. 点击 **Deploy**，等待平台构建并展示实际的 `*.streamlit.app` 地址。
5. 用独立浏览器会话验证：加载演示→提取→对比→文案→修改并确认→导出。另一会话不应看到第一会话的项目或审核内容。

部署账号登录及授权必须由账号持有人完成。本文中的步骤不表示云端已部署成功，实际地址以平台成功结果为准。

`online-demo` 分支的服务器监听地址为 `0.0.0.0`，适合云平台接入；`main` 分支保留本地默认 `127.0.0.1`。后续更新在线版时，将main的新代码合入online-demo，再由云平台重新部署；不要把云端监听配置覆盖回本地默认配置。

官方操作说明：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## 演示模式的边界

- 每个Streamlit访客会话拥有独立的内存SQLite，无全局数据库缓存，不读取磁盘中的本地项目。
- 模型模式与模型API预算入口均关闭，即使环境中误配置API密钥，也不能通过公开演示发起模型调用。
- 文件上传不可用；访客加载内置模拟资料后可以修改需求、生成结果、审核和导出。
- 会话是临时体验，不提供跨刷新、重连、服务重启的数据持久化承诺。需要保留内容请立即导出。
- 每会话最多3个项目，每项目最多40个生成批次与100条审核记录；可点击“重置我的演示”释放当前会话数据。
- 不应输入个人、客户或企业敏感信息。公开演示不是具备账号隔离、持久存储和运营保障的生产服务。

## 本地验证在线入口

```powershell
python -m streamlit run demo_app.py --server.address 127.0.0.1
python -m pytest -q
```

其他Python托管服务应以 `python -m streamlit run demo_app.py --server.address 0.0.0.0 --server.port <平台分配端口>` 启动，网络暴露仅限这个演示入口。本地版本仍保持回环地址默认配置。
