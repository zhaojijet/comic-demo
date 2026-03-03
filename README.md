# Comic Demo — AI 漫剧创作助手

基于 AI Agent 驱动的自动化漫剧（漫画短剧）创作系统。从剧本构思到视频成片，通过对话式交互一站式完成。

## ✨ 核心功能

- **对话式创作** — 通过 WebSocket 实时对话界面描述你的漫剧构思
- **10 节点流水线** — 剧本 → 风格 → 角色 → 分镜 → 生图 → 精修 → 高清 → 视频 → 后期 → 超分
- **实时流式反馈** — WebSocket Gateway 实时推送各节点执行进度
- **快捷模板** — 预设赛博朋克、古风武侠等场景一键启动创作

## 📁 项目结构

```
comic-demo/
├── main.py              # FastAPI 服务入口 (REST + WebSocket Gateway)
├── config.toml          # 项目配置 (LLM/VLM/MCP/节点)
├── requirements.txt     # Python 依赖
├── start_dev.sh         # 一键启动脚本 (支持 start/stop/status/restart)
├── frontend/            # 前端界面
│   ├── index.html       # Chat UI 页面
│   ├── styles.css       # Minimalist Lux 样式
│   └── app.js           # WebSocket 客户端
├── src/                 # 后端源码
│   ├── agent.py         # Agent 构建与编排
│   ├── config.py        # 配置加载
│   ├── nodes/           # 漫剧创作节点
│   │   ├── comic_nodes/ # 10 个漫剧节点实现
│   │   └── core_nodes/  # 核心基础节点
│   ├── mcp_custom/      # MCP 服务器与工具注册
│   ├── storage/         # 会话与产物存储
│   ├── skills/          # 技能模块
│   └── utils/           # 工具函数
├── prompts/tasks/       # 各节点 Prompt 模板
└── resource/bgms/       # 背景音乐资源
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.12+
- FFmpeg（视频处理需要）

### 2. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置 API Key

编辑 `config.toml`，填入你的 LLM（DeepSeek）和图/生视频模型（火山引擎）API Key：

```toml
[llm]
model = "deepseek-chat"
base_url = "https://api.deepseek.com"
api_key = "你的 DeepSeek API Key"

[image_llm]
model = "doubao-seedream-5-0-260128"
base_url = "https://ark.cn-beijing.volces.com/api/v3"
api_key = "你的 火山 Ark API Key"

[video_llm]
model = "doubao-seedance-1-5-pro-251215"
base_url = "https://ark.cn-beijing.volces.com/api/v3"
api_key = "你的 火山 Ark API Key"
```

### 4. 启动服务

```bash
# 推荐使用一键启动脚本 (会自动管理后台进程)
chmod +x start_dev.sh
./start_dev.sh start

# 其他服务管理命令
./start_dev.sh status   # 查看运行状态和健康检查
./start_dev.sh stop     # 停止服务
./start_dev.sh restart  # 重启服务

# 手动启动 (调试模式)
export PYTHONPATH=$(pwd)/src:$PYTHONPATH
./.venv/bin/python main.py
```

服务将在 `http://localhost:8002` 启动。

### 5. 访问界面

打开浏览器访问：**http://localhost:8002/web**

## 🔌 API 接口

### WebSocket 实时对话（推荐）

连接 `ws://localhost:8002/ws`，通过 JSON 消息交互：

```json
// 发送消息
{"type": "chat", "content": "帮我创作一个赛博朋克漫画"}

// 接收事件
{"type": "node_start", "node": "ComicScriptNode", "content": "正在生成剧本..."}
{"type": "node_complete", "node": "ComicScriptNode", "content": "剧本生成完成"}
{"type": "complete", "content": "漫剧创作完成！", "result": "..."}
```

### REST API（备用）

```bash
curl -X POST http://localhost:8002/create_comic \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-001", "user_prompt": "赛博朋克风格短篇漫画"}'
```

## 🎨 创作流水线节点

| 节点 | 功能 |
|------|------|
| ComicScriptNode | 剧本生成 |
| ComicStyleNode | 画风定义 |
| ComicCharacterNode | 角色设计 |
| ComicStoryboardNode | 分镜脚本 |
| ComicStoryboardImageNode | 分镜图生成 |
| ComicRefineImageNode | 图片精修 |
| ComicHighresImageNode | 高清放大 |
| ComicImage2VideoNode | 图转视频 |
| ComicPostProductionNode | 后期合成 |
| ComicSuperResolutionNode | 超分辨率 |

## ⚠️ 注意事项

- 创作过程需要调用外部 AI 服务，请确保网络通畅
- 单次完整创作可能需要数分钟
- 生成的产物保存在 `./outputs/` 目录下
- `resource/bgms/` 可放置背景音乐素材供后期使用
