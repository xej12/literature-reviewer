# 文献梳理工具

一个面向个人科研使用的本地 Zotero 文献梳理工具。它读取本机 Zotero 文献库，以网页界面展示元数据和 PDF，并提供论文解读、专业术语提取和逐页图表解析。

## 特点

- 只读访问本机 Zotero SQLite 数据库和 PDF 附件；
- 模型地址、模型名称和 API Key 在网页中配置，保存在本机；
- 论文解读、术语和图表结果按文献缓存到本机，重复打开不会重复消耗 Token；
- 服务默认只监听 `127.0.0.1:8765`，不会自动暴露到局域网或公网。

## Windows 使用

1. 安装 Zotero，并确认 Zotero 数据目录中存在 `zotero.sqlite`。
2. 安装 Python 3.11 或更高版本，并安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. 安装 Poppler，并将包含 `pdftoppm.exe` 和 `pdfinfo.exe` 的目录加入 PATH。PDF 页面预览和图表解析需要它。
4. 启动服务：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
   ```

5. 打开 <http://127.0.0.1:8765>，点击右上角“模型设置”填写兼容 OpenAI Chat Completions API 的地址、模型和 Key。

如果 Zotero 数据目录不在默认位置，可以先设置环境变量：

```powershell
$env:ZOTERO_DATA_DIR = "D:\你的 Zotero 数据目录"
```

## 数据与隐私

`data/settings.json`、`data/analysis/` 和本机 Zotero 数据不会提交到 Git。`.gitignore` 已排除模型配置、分析缓存和 Python 缓存目录。使用外部模型时，只有发起解读或图表解析时，相关文本或页面图片才会发送到你配置的模型服务。

## 项目状态

这是一个逐步构建中的个人工具。接口和页面仍可能调整，欢迎通过 Issue 提交使用反馈。
