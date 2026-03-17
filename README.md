极文造物 (Novel Engine) v1.0
这是一个基于 FastAPI + React 构建的 AI 长篇小说自动化写作与管理平台。

<div>
<a href="#zh" style="color:#1e8a7a;text-decoration:underline;font-weight:700;">中文</a>
<span> / </span>
<a href="#en" style="color:#1e8a7a;text-decoration:underline;font-weight:700;">English</a>
</div>

<a id="zh"></a>

项目介绍
极文造物是一套面向长篇网文生产的 AI 自动化引擎，强调“全流程、可持续、可进化”。它把从世界观设定、阶段规划、人物卡、事件链到正文生产的流程打通，并为长篇连载的稳定性和可维护性提供工程级保障。

核心亮点
- 端到端长篇生产链路：从设定到正文，一键贯通
- 结构化事件驱动：可控节奏、可控成本、可控质量
- 统一的故事系统与成长体系：持续连载不崩盘
- 前后端一体化协作：管理与生成同屏完成

目录结构
backend/: FastAPI 核心逻辑与 API 服务
frontend/: React UI 界面
start.py: 自动化启动脚本

快速上手
第一步：克隆项目。
第二步：API 配置：请修改 backend/config.json 中的 YOUR_API_KEY。
第三步：运行脚本：

Bash
python start.py
脚本会自动创建虚拟环境、安装依赖并同时启动前后端服务。

联系方式
Telegram：@dandan9977

微信（WeChat）：扫描下方二维码（请备注 GitHub RPA）
![WeChat QR](assets/wechat-qr.png)
💡微信扫码时请务必备注来自 GitHub

免责声明
本项目仅用于技术交流与架构思考探讨。作者不对任何因操作不当或微信版本更新导致的账号限制、数据损失负责。

许可证
本项目采用 MIT 许可证。您可以自由地使用、修改和分发代码，但请保留原作者版权声明。

<a id="en"></a>

Overview
Novel Engine is a production-grade AI platform for long-form fiction. It connects worldbuilding, stage planning, character design, event chains, and chapter drafting into a single, maintainable workflow—built for continuity, scalability, and delivery speed.

Highlights
- End-to-end long-form pipeline from planning to full text
- Structured, event-driven storytelling for controllable quality and cost
- Unified story system for stable, long-running serialization
- Integrated UI for management and generation in one place

Project Structure
backend/: FastAPI core logic and API service
frontend/: React UI
start.py: Automated bootstrap script

Quick Start
Step 1: Clone the repository.
Step 2: API config: update YOUR_API_KEY in backend/config.json.
Step 3: Run the script:

Bash
python start.py
The script automatically creates a virtual environment, installs dependencies, and starts both backend and frontend.

Contact
Telegram: @dandan9977

WeChat: scan the QR code below (please note GitHub RPA)
![WeChat QR](assets/wechat-qr.png)
💡Please mention you are from GitHub when adding WeChat.

Disclaimer
This project is for technical exchange and architectural discussion only. The author is not responsible for any account restrictions or data loss caused by improper use or WeChat version changes.

License
This project is licensed under the MIT License. You are free to use, modify, and distribute the code with attribution.


数据存储：
系统使用轻量级 SQLite，每本小说的数据独立存储在 backend/data/ 下。
