# 剪映 AI 剪辑技能 — 扣子 (Coze) 插件包

通过豆包 AI 驱动剪映专业版自动剪辑视频的 REST API 插件。

## 功能列表

| 工具名称 | 说明 |
|---------|------|
| 检查服务状态 | 检查剪映、FFmpeg、豆包 API 是否就绪 |
| 上传视频文件 | 上传视频到服务器，获取时长、大小等信息 |
| AI 分析视频 | 分析视频内容，获取 AI 剪辑建议 |
| 生成字幕 | 提取音频并生成字幕 |
| 智能剪辑 | AI 生成剪辑方案（自动/精彩/紧凑） |
| 长视频转短片 | 从长视频提取精彩片段生成短视频 |
| 全自动流水线 | 一键完成 分析→字幕→剪辑→导出 |
| 打开剪映 | 启动剪映专业版 |
| 查看草稿 | 列出剪映中的所有草稿 |
| 打开草稿 | 在剪映中打开指定草稿 |

## 上传到扣子平台

### 第一步：部署 API 服务

插件需要一个公网可访问的 API 地址。你可以选择：

**方案 A：云服务器部署（推荐）**

1. 准备一台有公网 IP 的服务器（Windows/Linux 均可）
2. 安装 Python 3.10+ 和 FFmpeg
3. 上传整个 `doubao_skill` 目录到服务器
4. 安装依赖并启动：

```bash
pip install -r requirements.txt
set DOUBAO_API_KEY=你的豆包API Key
python server.py
```

5. 使用 Nginx 反向代理，配置 HTTPS：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:9800;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**方案 B：内网穿透（测试用）**

使用 ngrok 或 frp 将本地 9800 端口暴露到公网：

```bash
# ngrok 方式
ngrok http 9800

# 得到类似 https://xxxx.ngrok.io 的地址
```

### 第二步：在扣子平台创建插件

1. 打开 [扣子平台](https://www.coze.cn/) 并登录
2. 进入「工作台」→ 选择或创建一个 Bot
3. 点击「插件」→「添加插件」→「创建自定义插件」
4. 填写插件信息：
   - **插件名称**: 剪映 AI 剪辑
   - **插件描述**: 通过豆包 AI 驱动剪映专业版自动剪辑视频，支持视频分析、字幕生成、智能剪辑、长转短等功能
   - **插件图标**: 选择一个视频/剪辑相关的图标

### 第三步：配置 API

1. 在插件配置页面，选择「导入 OpenAPI Schema」
2. 上传本目录下的 `openapi.json` 文件
3. 扣子会自动解析出所有接口
4. 修改 **API 地址** 为你部署后的公网地址（如 `https://your-domain.com`）
5. 点击「验证」确认所有接口可访问

### 第四步：配置鉴权（可选）

如果你的 API 需要鉴权，在扣子平台配置：
- **鉴权方式**: 自定义 Header
- **Header 名称**: `Authorization`
- **Header 值**: `Bearer your-secret-token`

（需要在 server.py 中添加对应的鉴权中间件）

### 第五步：配置 Bot 提示词

在 Bot 的「人设与回复逻辑」中添加：

```
你是剪映 AI 剪辑助手，可以通过工具帮用户完成视频剪辑任务。

## 能力
1. 分析视频内容和结构
2. 自动生成字幕
3. 智能剪辑（去废话、提取精彩片段）
4. 长视频转短视频
5. 一键全自动剪辑并导出到剪映

## 工作流程
- 当用户提到视频剪辑需求时，先调用「检查服务状态」确认就绪
- 然后调用「上传视频」获取视频文件
- 根据用户需求选择对应的剪辑工具
- 最后可以调用「打开剪映」让用户查看和微调结果

## 注意事项
- 视频路径需要使用服务器上的实际路径
- 如果服务不可用，提示用户检查服务状态
```

## 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `DOUBAO_API_KEY` | 火山引擎方舟平台 API Key | 是 |
| `JIANYING_PATH` | 剪映安装路径 | 否（自动检测） |
| `FFMPEG_PATH` | FFmpeg 路径 | 否（自动检测） |

## 目录结构

```
doubao_skill/
├── openapi.json        # OpenAPI Schema（上传到扣子的文件）
├── server.py           # API 服务源码
├── requirements.txt    # Python 依赖
├── start_server.bat    # Windows 启动脚本
├── skill.json          # 技能元数据（备用）
└── README.md           # 本文件
```

## 本地测试

```bash
# 安装依赖
pip install -r requirements.txt

# 设置 API Key
set DOUBAO_API_KEY=ark-xxxxx

# 启动服务
python server.py

# 访问文档
# http://localhost:9800/docs
```
