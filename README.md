# EPUB 翻译器

一个用于将英文 EPUB 电子书翻译成中文的工具，使用 OpenAI API 进行翻译。

## 特性

- 将英文 EPUB 书籍翻译成中文
- 支持 OpenAI API 和自定义代理服务器
- 专有名词词典功能：自动提取和使用自定义翻译
- 支持 Excel 和 JSON 格式的词汇表导入/导出
- 智能过滤提取专有名词，使用 Google 10000 常用词表
- 断点续传：可以在中断后继续翻译
- Streamlit 界面：易于使用的 Web 界面
- 多线程处理：加快翻译速度

## 安装

1. 克隆或下载此仓库
2. 安装依赖：
   ```
   pip install -r requirements.txt
   ```
3. 复制 `.env.example` 文件为 `.env` 并填写您的 API 信息
4. 确保 `./commonwords` 目录下有 `google-10000-english.txt` 文件

## 使用方法

### 命令行使用

```bash
# 基本用法
python epubtranslator.py your_book.epub

# 指定输出路径
python epubtranslator.py your_book.epub --output translated_book.epub

# 使用自定义词汇表
python epubtranslator.py your_book.epub --glossary glossary.json

# 使用更多线程 (默认: 5)
python epubtranslator.py your_book.epub --threads 8

# 禁用断点续传
python epubtranslator.py your_book.epub --no-resume

# 仅提取专有名词
python epubtranslator.py your_book.epub --extract-terms
```

### Web 界面

启动 Streamlit 界面：

```bash
streamlit run app.py
```

然后在浏览器中访问显示的链接（通常为 http://localhost:8501）。

## 词汇表格式

词汇表支持两种格式：

### JSON 格式

```json
{
  "English Term": "中文翻译",
  "Another Term": "另一个翻译"
}
```

### Excel 格式

Excel 文件需要包含两列，分别是"专有名词"和"中文翻译"，或者至少有两列且按此顺序排列。

## 常用词表

程序使用 Google 的 10000 个最常用英语单词列表来过滤常见词汇，提高专有名词提取质量：

- `./commonwords/google-10000-english.txt`：包含最常见的英语单词
- Source:`https://github.com/oprogramador/most-common-words-by-language`其他语种可参考

此列表用于过滤EPUB中的词汇，如果某个词或短语中的所有单词都出现在此列表中，则不会被视为专有名词。这有助于减少提取的噪音，使专有名词列表更加精确。

您可以替换或编辑此文件以自定义过滤行为，每行一个单词，以#开头的行会被当作注释。

## 环境变量配置

在 `.env` 文件中配置 API 信息：

```
API_KEY=your_api_key_here
MODEL_NAME=gpt-3.5-turbo
# 如果使用代理服务器
BASE_URL=https://your-proxy-server.com/v1
```

## 许可证

MIT

