极文造物 (Novel Engine) v1.0
这是一个基于 FastAPI + React 构建的 AI 长篇小说自动化写作与管理平台。

目录结构
backend/: FastAPI 核心逻辑与 API 服务
frontend/: React UI 界面
start.py: 自动化启动脚本

部署指南
环境要求：Python 3.10+，Node.js 18+。

快速启动：
直接运行根目录下的启动脚本：

Bash
python start.py
脚本会自动创建虚拟环境、安装依赖并同时启动前后端服务。

配置 API：
启动后，请在“控制台 -> API设置”中配置你的 API Key。默认配置文件位于 backend/config.json。

数据存储：
系统使用轻量级 SQLite，每本小说的数据独立存储在 backend/data/ 下。
