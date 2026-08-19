# 历史对对碰

面向 1920×1200 横屏学练机的历史记忆配对游戏，以及独立教师演示后台。

## 本地数据闭环

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:DEMO_ADMIN_KEY="local-demo-reset"
.venv\Scripts\python app.py
```

启动后访问：

- 学生端：<http://127.0.0.1:5000/student?demoStudent=demo-s2101>
- 教师端：<http://127.0.0.1:5000/teacher>
- 健康检查：<http://127.0.0.1:5000/api/health>

学生端在 HTTP 环境自动启用同步，直接打开 `memory_station.html` 时保持离线单文件模式。教师端在 HTTP 环境读取真实 API，直接打开 `teacher_dashboard.html` 时使用匿名模拟数据。

## 演示流程

1. 打开学生端，用 `demo-s2101` 完成一局 4×4。
2. 在设置中确认“等待上传”为 0，状态为“已同步”。
3. 打开教师端并选择高二年级、高二（1）班。
4. 查看新增对局、板块掌握度以及学生详情中的有效错误与首次翻牌豁免。
5. 断开或停止后端后继续游戏，事件会保留在本地；恢复服务后点击“立即同步”。

重置演示学习数据：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/v1/demo/reset -Headers @{"X-Demo-Admin-Key"="local-demo-reset"}
```

## 自动化测试

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

测试覆盖健康检查、事件幂等、教师接口、重置鉴权，以及“首次未知错配保留原始记录但不扣独立判断正确率”。

## Render 部署

仓库根目录的 `render.yaml` 会创建一个 Python Web Service 和一个 PostgreSQL 数据库。连接字符串与演示重置密钥通过 Render 环境变量提供，不写入 HTML 或仓库。

部署完成后使用：

- `https://你的服务地址/student?demoStudent=demo-s2101`
- `https://你的服务地址/teacher`
- `https://你的服务地址/api/health`

演示前提前访问健康检查地址完成免费实例预热。本项目的 HTML 文件仍可作为断网备用。
