# SeedanceMini v2 - Windows 使用说明

## 你只需要做 5 件事（不需要懂电脑）

### 第 1 步：安装 Python（如果还没装过）

打开这个网址：
```
https://www.python.org/downloads/release/python-31011/
```
下载 **Windows installer (64-bit)** 并双击安装。

**安装时请务必勾选** 第一个画面最下方的：
- ☑ `Add Python 3.10 to PATH`
其他全部默认下一步即可。

### 第 2 步：准备项目文件夹

把整个项目文件夹（`Seedanceminiv2`）复制到桌面。**不要放在 C 盘根目录、不要放在中文路径下**。

### 第 3 步：准备 FFmpeg（快剪功能需要）

从下面这个地址下载 `ffmpeg-release-essentials.zip`：
```
https://www.gyan.dev/ffmpeg/builds/
```

下载完成后：
1. 解压 zip
2. 打开里面的 `bin` 文件夹
3. 找到 `ffmpeg.exe`
4. 在项目根目录下新建 `tools` 文件夹，把 `ffmpeg.exe` 复制进去

最终路径应该是：
```
C:\Users\你的名字\Desktop\Seedanceminiv2\tools\ffmpeg.exe
```

### 第 4 步：运行安装脚本

在项目文件夹里**双击** `setup.bat`。
- 第一次运行需要几分钟（会自动下载依赖包）
- 看到 `安装完成！` 后按任意键关闭窗口

### 第 5 步：启动和停止项目

启动服务：在项目文件夹里**双击** `start.bat`。
- 浏览器会自动打开 http://127.0.0.1:8000
- 看到左侧的"项目"列表就开始使用了

停止服务：在项目文件夹里**双击** `stop.bat`。
- 看到 `Stopped SeedanceMini v2 server` 表示停止成功
- 如果提示服务没有运行，不需要处理
- 停止后，自己和局域网同事都将无法继续访问

也可以直接关闭运行 `start.bat` 的黑色窗口，并在窗口中按 `Ctrl + C` 后确认退出。

### 同一 Wi-Fi 下让同事访问

项目启动后，同事不需要安装项目环境，直接在浏览器访问运行项目电脑的局域网地址即可。

macOS 查询局域网 IP：
```bash
ipconfig getifaddr en0
```

假设查询结果是 `192.168.1.131`，同事访问：
```text
http://192.168.1.131:8000
```

注意：
- 两台电脑需要连接同一个可互通的 Wi-Fi。
- 运行项目的电脑必须保持开机，服务不能关闭，电脑不能休眠。
- 防火墙需要允许 Python 接收网络连接。
- 局域网 IP 可能变化，无法访问时重新查询。
- 所有人访问同一套项目数据，当前没有用户权限隔离，不建议多人同时编辑同一个项目。
- 公共或公司 Wi-Fi 如果开启客户端隔离，设备之间可能无法访问。

## 遇到问题怎么办？

### 启动时弹出黑窗口然后关闭
- 看 `start.bat` 窗口里最后的英文提示
- 90% 是 Python 没装好，重新装一次并勾选 `Add to PATH`

### 快剪按钮点了没反应
- 确认 `tools\ffmpeg.exe` 存在
- 重新双击 `setup.bat`

### 浏览器没自动打开
- 自己手动打开浏览器，访问 http://127.0.0.1:8000

## 常见操作

| 想要做的事 | 操作 |
|------------|------|
| 新建项目 | 左侧"+ 新建项目"，输入名称 |
| 上传剧本 | 进入项目 → "剧本" → 上传 docx |
| 拆分片段 | "片段" → AI 拆分 |
| 生成 Seedance 提示词 | "片段" → 每条卡片点"生成" |
| 裁剪视频 | "Seedance 视频生成" → "快剪" |
| 编辑提示词 | "Seedance 视频生成" → 中间输入框 |
| 启动服务 | 双击 `start.bat` |
| 停止服务 | 双击 `stop.bat` |

## 联系开发者

如果遇到无法解决的问题，把下面信息发给开发者：
- `start.bat` 窗口里显示的英文提示截图
- Windows 版本（开始菜单 → 运行 → 输入 `winver` → 回车）

---

## 给开发者看的

```bash
# 项目结构
Seedanceminiv2/
├── start.bat           # 双击启动
├── setup.bat           # 双击安装
├── tools/              # 把 ffmpeg.exe 放这里
├── web/                # FastAPI 后端
├── src/                # 业务逻辑
├── projects/           # 用户项目数据
├── config.yaml         # 模型配置
└── requirements.txt    # 依赖清单（已锁定版本）
```

启动命令：
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn web.app:app --host 0.0.0.0 --port 8000
```