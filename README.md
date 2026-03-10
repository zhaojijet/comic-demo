# Comic Demo — AI 漫剧创作助手

基于 AI Agent 驱动的自动化漫剧（漫画短剧）创作系统。从剧本构思到音视频成片，通过对话式交互与 MCP (Model Context Protocol) 架构一站式完成。

## ✨ 核心功能

- **双服务架构** — FastAPI 提供 WebSocket 网关与前端托管，FastMCP 驱动底层工作流引擎
- **对话式流式创作** — 通过 WebSocket 实时交互，支持前端节点状态可视化反馈
- **多模态生成模式** — 支持 5 种高级视频生成模式（纯文本、首帧图生视频、首尾帧生视频、多参考图生视频、样片生视频）
- **六大核心创作节点** — 剧本 (Script) → 画风 (Style) → 角色 (Character) → 分镜 (Storyboard) → 生图 (Image) → 图转视频 (Image2Video)

## 📁 项目结构

```
comic-demo/
├── main.py              # FastAPI 核心网关与前端托管 (Port 8002)
├── config.toml          # 项目全量配置 (LLM/MCP/节点等参数)
├── requirements.txt     # Python 核心依赖
├── start_dev.sh         # 双服务一键启停脚本 (start/stop/status/restart)
├── frontend/            # 前端应用 (Minimalist Lux 风格)
│   ├── index.html       # SPA 页面结构
│   ├── styles.css       # 玻璃拟态高级样式
│   └── app.js           # 核心交互逻辑与 WebSocket 客户端
├── src/                 # 后端源码
│   ├── agent.py         # 顶层 Agent 构建与编排
│   ├── config.py        # 静态配置解析
│   ├── nodes/           # 创作流水线节点定义
│   ├── mcp_custom/      # MCP 服务 (Port 8001)、工具注册与请求拦截
│   ├── storage/         # 历史记录、伪持久化会话与产物管理
│   └── utils/           # 各类工具组件
└── outputs/             # (运行时生成) 存放视频、图片素材与中间产物
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.12+

### 2. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装底层依赖
pip install -r requirements.txt
```

### 3. 配置 API Key

根据预设需要在 `config.toml` 中填写对应的大模型厂商秘钥（例如由于多模态生成，我们深度集成并依赖了 Volcengine Ark API）。

```toml
[llm]
model = "deepseek-chat"
base_url = "https://api.deepseek.com"
api_key = "你的 DeepSeek API Key"

[image_llm.providers.seedream-5-0]
model = "doubao-seedream-5-0-260128"
base_url = "https://ark.cn-beijing.volces.com/api/v3"
api_key = "你的 火山 Ark API Key"

[video_llm.providers.seedance-1-5-pro]
model = "doubao-seedance-1-5-pro-251215"
base_url = "https://ark.cn-beijing.volces.com/api/v3"
api_key = "你的 火山 Ark API Key"
```

### 4. 启动服务

本系统采用了 **双进程** 架构运行，推荐使用内置的启动脚本来自动管理 MCP Server 与 Main Service。

```bash
# 赋予执行权限
chmod +x start_dev.sh

# 一键启动所有服务并在后台保持守护
./start_dev.sh start

# 状态健康检查
./start_dev.sh status

# 停止全部服务
./start_dev.sh stop
```

服务就绪后，后端 API 与前端资源托管网关将在 `http://localhost:8002` 提供。

### 5. 访问界面

本地开发时，打开浏览器访问：**[http://localhost:8002/](http://localhost:8002/)**

> **🌐 局域网与广域网访问支持**：  
> 后端网关原生绑定了 `0.0.0.0` 并配置了完全放行的 CORS 策略，**只需确保您的机器/云服务器防火墙开启了 8002 端口**，在同一个局域网下的手机，或者互联网上的任何人都可以直接使用机器的 IP 访问（例如：`http://192.168.x.x:8002/`），无需修改任何代码。

## 🔌 通信接口规范

### WebSocket 实时交互网关 (Main)

应用通过单一全双工长链接与大模型交互。WebSocket 客户端会根据当前访问页面的 `Host` 动态寻址连接（兼容局域网/公网 IP 访问）。

```json
// 下发指令 (客户端 -> 服务端)
{"type": "chat", "content": "帮我生成一个古代武侠短片", "mode": "text-only"}

// 接收进度 (服务端 -> 客户端)
{"type": "node_start", "node": "ComicScriptNode", "content": "正在生成剧本..."}
{"type": "node_complete", "node": "ComicScriptNode", "content": "剧本生成完成"}
{"type": "complete", "content": "漫剧创作完成！", "result": "剧情文字详情...", "media_type": "video", "media_urls": ["/outputs/demo.mp4"]}
```

## ⚠️ 注意事项

- 创作流水线极大依赖外部 AI 生成服务，请确保国内/国外网络环境通畅。
- 视频生成为异步长耗时作业，单次完整执行可能需要若干分钟，请通过前端弹提醒关注生成状态。
- 生成的历史会话数据保存在 `./data/history.json`。
- **关于生成模式兼容性 (✨ 新功能)**：不同的视频模型提供商（如 Seedance 1.5 Pro 与 1.0 Lite）支持的“生成模式”存在差异（如只有 1.5 Pro 支持“样片图参考生视频”）。**目前前端 UI 已实现了双向响应绑定交互：当您选择不兼容的模型时，不支持的生成模式会智能置灰并禁用点击，极大提升了使用体验。**
