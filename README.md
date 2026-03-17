# 极文造物 (ApexProse Novel Engine) v1.0

这是一个基于 FastAPI + React 构建的工业级 AI 长篇小说自动化写作与生产控制台。

<div align="center">
  <a href="#zh" style="color:#1e8a7a;text-decoration:underline;font-weight:700;font-size:16px;">中文</a>
  <span style="margin: 0 10px;"> / </span>
  <a href="#en" style="color:#1e8a7a;text-decoration:underline;font-weight:700;font-size:16px;">English</a>
</div>

<br/>

<a id="zh"></a>

## 📖 项目介绍

**极文造物 (ApexProse)** 是一款专为高规格长篇网文生产打造的 AI 引擎。它颠覆了传统的碎片化对话式 AI 写作模式，构建了从“世界观架构 -> 数值体系 -> 事件链编排 -> 章节生成”的**全闭环自动化工作流**。系统旨在为创作者提供工程级的保障，确保千万字级连载的逻辑严密性与质量收敛。

## ✨ 核心产品力

- 🚀 **工业级全链路生产线**：告别零散 Prompt。一键贯通从初始设定到正文落地的端到端生成，大幅降低心智负担。
- 🧠 **智能事件流驱动**：内置结构化情节拆解算法，实现对叙事节奏、目标字数与生成成本的精准可控。
- 🌍 **动态上下文与设定收敛**：全局状态管理，自动追踪角色成长与伏笔回收，有效杜绝长篇连载中的“战力崩坏”与“设定遗忘”。
- 🗄️ **隔离式轻量级数据引擎**：采用 `Per-Novel SQLite` 架构，每本小说数据独立存储于 `backend/data/`，保障核心创意资产的绝对隐私与极速无缝迁移。
- 💻 **现代化生产控制台**：前后端一体化协作，在同一视界内完成大纲统筹、正文质检与系统重写。

## 📂 架构概览

- `backend/`: FastAPI 核心逻辑引擎与大模型通信网关
- `frontend/`: 现代化的 React 沉浸式 UI 工作站
- `start.py`: 全自动化环境构建与一键启动脚本

## 🚀 快速上手

**第一步：克隆项目**
将代码库拉取到本地环境。

**第二步：配置 API 网关**
打开 `backend/config.json`，在对应配置项中将 `YOUR_API_KEY` 替换为您的大模型密钥。

**第三步：一键点火**
在终端运行以下命令：
```bash
python start.py
```
*(系统将自动接管底层环境：创建虚拟环境、安装前后端依赖库，并在可用端口同时启动后台引擎与可视控制台。)*

## 💬 联系与交流

- **Telegram**：[@dandan9977](https://t.me/dandan9977)
- **微信 (WeChat)**：扫描下方二维码（添加时请备注 **GitHub ApexProse**）

<div align="left">
  <img src="assets/wechat-qr.png" width="200" alt="WeChat QR Code">
</div>

## ⚠️ 免责声明

本项目及核心算法仅用于技术交流、架构探讨与生产力探索。作者不对任何因 API 消耗、模型生成内容合规性或因操作不当导致的数据丢失承担法律与经济责任。建议定期备份您的 `backend/data/` 目录。

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。您可以自由地使用、商业化、修改和分发代码，但请保留原作者版权声明。

---

<br/>

<a id="en"></a>

## 📖 Overview

**ApexProse Novel Engine** is an enterprise-grade AI automated writing platform designed for massive, long-form fiction production. It revolutionizes the fragmented AI chatbot writing process by providing a closed-loop workflow—from worldbuilding and character progression to event mapping and full-chapter drafting. The system is built to ensure logical consistency and quality convergence across serials spanning millions of words.

## ✨ Core Highlights

- 🚀 **Industrial-Grade Pipeline**: From blueprint to full text. Say goodbye to scattered prompts and manual context feeding.
- 🧠 **Event-Driven Narrative Engine**: Built-in algorithmic plot structuring for precise pacing, word count targeting, and API cost control.
- 🌍 **Dynamic Context & Lore Consistency**: Global state management automatically tracks character arcs and foreshadowing, preventing plot holes and "power creep" in long-running serials.
- 🗄️ **Isolated Lightweight Storage**: Employs a `Per-Novel SQLite` architecture. Data is stored independently in `backend/data/`, ensuring absolute asset privacy and seamless portability.
- 💻 **Modern Immersive Console**: Integrated React frontend and FastAPI backend for a unified management, generation, and quality-control experience.

## 📂 Project Structure

- `backend/`: FastAPI core logic engine and LLM communication gateway.
- `frontend/`: Modern React immersive UI workstation.
- `start.py`: Fully automated environment builder and bootstrap script.

## 🚀 Quick Start

**Step 1: Clone the repository.**
Pull the source code to your local machine.

**Step 2: API Configuration.**
Open `backend/config.json` and replace `YOUR_API_KEY` with your actual LLM provider key.

**Step 3: Ignition.**
Run the following command in your terminal:
```bash
python start.py
```
*(The system will automatically handle the environment: creating a venv, installing all dependencies, and launching both the backend engine and frontend console.)*

## 💬 Contact

- **Telegram**: [@dandan9977](https://t.me/dandan9977)
- **WeChat**: Scan the QR code below (Please note **GitHub ApexProse** when adding)

<div align="left">
  <img src="assets/wechat-qr.png" width="200" alt="WeChat QR Code">
</div>

## ⚠️ Disclaimer

This project and its core algorithms are for technical exchange, architectural discussion, and productivity exploration only. The author assumes no legal or financial responsibility for API costs, the compliance of AI-generated content, or data loss caused by improper operation. It is highly recommended to regularly back up your `backend/data/` directory.

## 📄 License

This project is licensed under the [MIT License](LICENSE). You are free to use, commercialize, modify, and distribute the code, provided that attribution to the original author is maintained.
