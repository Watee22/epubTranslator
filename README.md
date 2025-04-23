# EPUB 翻译网页应用

一个基于 Streamlit 的网页应用，使用 OpenAI API 将 EPUB 文件从英语翻译成中文。

## 功能特点

- 上传并翻译 EPUB 文件
- 从 EPUB 文件中提取术语
- 管理自定义词汇表
- 从检查点恢复翻译
- 将术语和词汇表导出到 Excel
- 给模型提供背景知识，让其了解到自己在翻译什么

## 安装

1. 克隆此仓库
2. 安装所需的包：

```bash
pip install -r requirements.txt
```

## 使用方法

1. 运行 Streamlit 应用：

```bash
streamlit run app.py
```

2. 应用将在您的默认网络浏览器中打开，地址为 http://localhost:8501

3. 配置 API 设置：
   - 输入您的 OpenAI API 密钥
   - 可选择指定自定义 API 基础 URL
   - 选择用于翻译的模型

4. 上传您的 EPUB 文件并开始翻译

## 配置选项

- **线程数量**：控制并发翻译线程的数量
- **恢复翻译**：启用/禁用从检查点恢复
- **导出到 Excel**：将提取的术语或词汇表导出为 Excel 格式

## 目录结构

- `uploads/`：存储上传的 EPUB 文件
- `tmp/`：处理文件的临时存储
- `translated_files/`：翻译后的 EPUB 文件的永久存储

## 要求

- Python 3.7+
- DeepSeekAI API 密钥或其他API密钥
- 互联网连接

## 许可证

MIT

## 致谢

- 为 EPUB 文件处理和翻译修改了 EpubTranslator 模块。
- 使用了来自 `https://github.com/oprogramador/most-common-words-by-language` 的常用英语单词列表

## 待办事项
- 1.支持更多语言
- 2.Docker 部署