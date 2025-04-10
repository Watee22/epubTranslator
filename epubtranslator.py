import sys
import openai
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup,NavigableString
import threading
from queue import Queue
import traceback
import time
from collections import deque
import re
import os
from dotenv import load_dotenv
import json
import pickle
import argparse

# 加载环境变量
load_dotenv()

# 设置OpenAI的API密钥
# 通过环境变量读取配置信息


openai.api_key = os.getenv('API_KEY')
openai.api_base = os.getenv('BASE_URL')
model_name = os.getenv('MODEL_NAME', 'gpt-3.5-turbo')

# 用于保存翻译进度的文件名模板
CHECKPOINT_FILE = "{}_translation_checkpoint.pkl"
# 保存专有名词词典的文件名
GLOSSARY_FILE = "{}_glossary.json"

def load_common_words(file_path='./commonwords/google-10000-english.txt'):
    """从文件中加载常用词列表"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            words = set()
            for line in f:
                # 忽略注释行和空行
                line = line.strip()
                if line and not line.startswith('#'):
                    words.add(line.lower())
            print(f"已加载 {len(words)} 个常用词")
            return words
    except FileNotFoundError:
        print(f"警告: 找不到常用词文件 {file_path}，将使用空列表")
        return set()
    except Exception as e:
        print(f"加载常用词列表出错: {e}")
        return set()

# 加载常用词列表
COMMON_WORDS = load_common_words()

class TranslationResult:
    def __init__(self, result, errorcode, data):
        self.result = result
        self.errorcode = errorcode
        self.data = data

def check_string(s):
    # 检查字符串是否只包含英文单词、句子、适量的标点和空格
    # 允许字符串中有数字和其他字符，但不能只有这些字符
    # 这个正则表达式匹配包含至少一个英文字母的字符串，并允许空格、标点符号和数字
    match = re.search(r'[A-Za-z]', s)
    
    # 如果match不是None，则字符串是有效的
    return match is not None

def is_valid_term(term):
    """
    判断一个词组是否可能是一个有效的专有名词，主要基于Google常用词表
    """
    # 如果是空或只有一个字符，不是有效术语
    if not term or len(term) <= 1:
        return False
        
    # 分割成单词
    words = term.split()
    
    # 如果只有一个单词
    if len(words) == 1:
        # 如果是常见单词（不区分大小写），排除
        if words[0].lower() in COMMON_WORDS:
            return False
        
        # 如果只有一个单词且长度小于4，可能不够特殊，除非它可能是缩写（全大写）
        if len(words[0]) < 4 and not words[0].isupper():
            return False
    
    # 检查多词组合是否全是常用词
    all_common = all(word.lower() in COMMON_WORDS for word in words)
    if all_common:
        return False
    
    # 可能是有意义的专有名词
    return True

def extract_terms(input_epub):
    """从EPUB文件中提取可能的专有名词、人名、地名等"""
    print("开始提取专有名词...")
    book = epub.read_epub(input_epub)
    terms = set()
    
    # 正则表达式用于匹配可能的专有名词（首字母大写的词组，允许1-3个词）
    term_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b')
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            content = item.get_content().decode('utf-8')
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text()
            
            # 提取匹配的词组
            matches = term_pattern.findall(text)
            for term in matches:
                # 使用增强的过滤规则
                if is_valid_term(term):
                    terms.add(term)
    
    print(f"提取了 {len(terms)} 个可能的专有名词")
    return sorted(list(terms))

def translate_text(text, glossary=None):
    # 先检查词汇表中是否有对应的翻译
    if glossary and text in glossary:
        print(f"使用词汇表翻译: {text} -> {glossary[text]}")
        return TranslationResult(True, 0, glossary[text])
    
    # 调用OpenAI的API进行翻译
    try:
        if (check_string(text)==False):
            print("不需要翻译！")
            return TranslationResult(True, 0, text)
        
        # 根据API类型选择不同的请求方式
        if os.getenv('API_TYPE') == 'azure':
            response = openai.ChatCompletion.create(
                deployment_id=deployment_id,
                messages=[
                    {
                        "role":"system",
                        "content":"Starting now, you are an English translator. You will not engage in any conversation with me; you will only translate my words from English to Chinese. You will return a pure translation result, without adding anything else, including Chinese pinyin."},
                    {
                        "role": "user", 
                        "content": f"{text}"
                    }
                ],
                max_tokens=256,
                temperature=0.0,
                request_timeout = 10            
            )
        else:
            response = openai.ChatCompletion.create(
                model=model_name,
                messages=[
                    {
                        "role":"system",
                        "content":"Starting now, you are an English translator. You will not engage in any conversation with me; you will only translate my words from English to Chinese. You will return a pure translation result, without adding anything else, including Chinese pinyin."},
                    {
                        "role": "user", 
                        "content": f"{text}"
                    }
                ],
                max_tokens=256,
                temperature=0.0,
                request_timeout = 10            
            )
            
        if (response==None):
            print("翻译失败！")
            return text
        translated_text = response.choices[0].message['content']
        return TranslationResult(True, 0, translated_text)
    except Exception as e:
        print("发生异常：", e)
        traceback.print_exc()
        return TranslationResult(False, 1001, None)
    
def translate_html(text, glossary=None):
    # 先检查词汇表中是否有对应的翻译
    if glossary and text in glossary:
        print(f"使用词汇表翻译HTML: {text} -> {glossary[text]}")
        return TranslationResult(True, 0, glossary[text])
    
    # 调用OpenAI的API进行翻译
    try:
        if (check_string(text)==False):
            print("不需要翻译！")
            return TranslationResult(True, 0, text)
        response = openai.ChatCompletion.create(
            messages=[
                {
                    "role":"system",
                    "content":"我将发一段HTML代码给你，其中包含了英文文本，请根据具体情况翻译英文文本到中文，维持原有HTML格式。如果翻译会破坏原有格式，请不做任何处理原样发回。"},
                {
                    "role": "user", 
                    "content": f"{text}"
                }
            ],
            max_tokens=256,
            temperature=0.0,
            request_timeout = 10            
        )
        response = openai.ChatCompletion.create(
            model=model_name,
            messages=[
                {
                    "role":"system",
                    "content":"我将发一段HTML代码给你，其中包含了英文文本，请根据具体情况翻译英文文本到中文，维持原有HTML格式。如果翻译会破坏原有格式，请不做任何处理原样发回。"},
                {
                    "role": "user", 
                    "content": f"{text}"
                }
            ],
            max_tokens=256,
            temperature=0.0,
            request_timeout = 10            
        )
        
        if (response==None):
            print("翻译失败！")
            return text
        translated_text = response.choices[0].message['content']
        return TranslationResult(True, 0, translated_text)
    except Exception as e:
        print("发生异常：", e)
        traceback.print_exc()
        return TranslationResult(False, 1001, None)

def update_epub_title(epub_path, new_title):
    # 读取epub文件
    book = epub.read_epub(epub_path)
    print("当前标题:", book.get_metadata('DC', 'title')[0][0])
    
    # 更新标题
    book.title = new_title
    book.set_unique_metadata('DC', 'title', new_title)
    # 保存修改
    epub.write_epub(epub_path, book, {})
    
    # 重新读取文件查看更新后的标题
    updated_book = epub.read_epub(epub_path)
    print("更新后的标题:", updated_book.get_metadata('DC', 'title')[0][0])

stop_event = threading.Event()

def worker(queue, output_epub, new_book, lock, glossary=None):
    try:
        while True:
            if stop_event.is_set():
                break
            item = queue.get()
            if item is None:
                break
            current_thread = threading.current_thread()
            if item.get_type() == 4 or item.get_type() == 9:
                print(f"{current_thread.name} 正在处理 {item.file_name}")
            translate_and_save_item(item, output_epub, new_book, lock, glossary)
            queue.task_done()
    except Exception as e:
        print(f"{current_thread.name}发生异常")
        traceback.print_exc()
        queue.task_done()
        quit()

def translate_and_save_item(item, output_epub, new_book, lock, glossary=None):
    if item.get_type() == 9:
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        p_list = soup.findAll("p")
        if len(p_list) == 0:
            new_book.add_item(item)
            return
        for p in p_list:
            if stop_event.is_set():
                break
            print("翻前HTML：",p)
            tresult = translate_html(str(p), glossary)
            if (tresult.result):
                translated_text = tresult.data
                newtag = BeautifulSoup(translated_text,'html.parser').p
                p.replace_with(newtag)
                print(f"翻后HTML：{newtag}")
        item.set_content(str(soup).encode('utf-8'))
    new_book.add_item(item)
    with lock:
        epub_options = {'ignore_ncx': False}
        epub.write_epub(output_epub, new_book,epub_options)

def modify_links(item, glossary=None):
    if isinstance(item, epub.Link):
        # Modify the title of the link
        print(f"开始翻译LINK： {item.title}")
        tresult = translate_text(item.title, glossary)
        if (tresult.result == False):
            return epub.Link(item.href, item.title, item.uid)
        else:
            translated_text = tresult.data
            new_title = translated_text
            print(f"翻译完成： {new_title}")
            return epub.Link(item.href, new_title, item.uid)
    elif isinstance(item, tuple):
        # 解包
        toc_section, toc_links = item  # 解包元组
        print ("Section Title:",toc_section.title)
        new_title = toc_section.title
        tresult = translate_text(toc_section.title, glossary)
        if (tresult.result):
            translated_text = tresult.data
            new_title = translated_text
            print(f"翻译完成： {new_title}")
        new_links = [modify_links(link, glossary) for link in toc_links]
        # Return a tuple with the modified section and links
        return (epub.Section(new_title, toc_section.href), new_links)
    else:
        # Return the item unmodified if it's not a link or a section
        print("****啥也不是!****",type(item),item)
        # 如果 TOC 有不同类型的对象，可以在这里处理
        return item

def load_glossary(input_file, user_glossary=None):
    """加载或创建专有名词词典"""
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    glossary_file = GLOSSARY_FILE.format(base_name)
    
    glossary = {}
    # 如果存在词汇表文件，加载它
    if os.path.exists(glossary_file):
        with open(glossary_file, 'r', encoding='utf-8') as f:
            glossary = json.load(f)
        print(f"已加载词汇表，包含 {len(glossary)} 个词条")
    
    # 如果提供了用户自定义词汇表，合并它
    if user_glossary:
        glossary.update(user_glossary)
        print(f"已合并用户词汇表，现在共有 {len(glossary)} 个词条")
        
    # 保存合并后的词汇表
    with open(glossary_file, 'w', encoding='utf-8') as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2)
        
    return glossary

def load_checkpoint(input_file, output_file):
    """加载翻译进度检查点"""
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    checkpoint_file = CHECKPOINT_FILE.format(base_name)
    
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'rb') as f:
                checkpoint_data = pickle.load(f)
                print(f"已加载断点，已完成项 {checkpoint_data['completed_items']} 个")
                return checkpoint_data
        except Exception as e:
            print(f"加载断点出错: {e}")
    
    return {
        'completed_items': 0,
        'processed_ids': set(),
        'book_data': None
    }

def save_checkpoint(checkpoint_data, input_file):
    """保存翻译进度检查点"""
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    checkpoint_file = CHECKPOINT_FILE.format(base_name)
    
    with open(checkpoint_file, 'wb') as f:
        pickle.dump(checkpoint_data, f)
    print(f"已保存断点，已完成项 {checkpoint_data['completed_items']} 个")

def translate_epub(input_epub, output_epub, num_threads=5, user_glossary=None, resume=True):
    try:
        # 加载或创建词汇表
        glossary = load_glossary(input_epub, user_glossary)
        
        # 加载断点
        checkpoint = None
        if resume:
            checkpoint = load_checkpoint(input_epub, output_epub)
        
        # 如果没有断点或不需要恢复，重新开始
        if not checkpoint or not resume or not checkpoint['book_data']:
            print("从头开始翻译...")
            epub_options = {'ignore_ncx': False}
            book = epub.read_epub(input_epub, epub_options)
            new_book = epub.EpubBook()
            new_book.metadata = book.metadata
            new_book.spine = book.spine
            
            # 遍历现有的 TOC并翻译
            print(f"开始翻译目录")
            new_toc = [modify_links(link, glossary) for link in book.toc]
            # 更新书籍的 TOC
            new_book.toc = tuple(new_toc)
            new_book.set_language('zh-cn')
            
            # 创建新的断点数据
            checkpoint = {
                'completed_items': 0,
                'processed_ids': set(),
                'book_data': {
                    'items': list(book.get_items()),
                    'total_items': len(list(book.get_items()))
                }
            }
            
            # 保存初始断点
            save_checkpoint(checkpoint, input_epub)
        else:
            print(f"从断点恢复翻译，已完成 {checkpoint['completed_items']}/{checkpoint['book_data']['total_items']} 项...")
            new_book = epub.read_epub(output_epub)
        
        queue = Queue()
        lock = threading.Lock()
        threads = []
        
        # 创建工作线程
        for _index in range(num_threads):
            thread = threading.Thread(target=worker, args=(queue, output_epub, new_book, lock, glossary), name="Thread-"+_index.__str__())
            thread.start()
            threads.append(thread)

        # 添加未处理的项目到队列
        for item in checkpoint['book_data']['items']:
            if item.id not in checkpoint['processed_ids']:
                queue.put(item)
            
        # 检查是否所有任务已完成
        checkpoint_save_interval = 5  # 每5秒保存一次断点
        last_checkpoint_save = time.time()
        
        all_tasks_completed = False
        while not all_tasks_completed:
            try:
                time.sleep(1)  # 短暂睡眠，允许主线程检查 KeyboardInterrupt
                
                # 定期保存断点
                if time.time() - last_checkpoint_save > checkpoint_save_interval:
                    checkpoint['completed_items'] = checkpoint['book_data']['total_items'] - queue.unfinished_tasks
                    save_checkpoint(checkpoint, input_epub)
                    last_checkpoint_save = time.time()
                
                all_tasks_completed = queue.unfinished_tasks == 0
            except KeyboardInterrupt:
                print("侦测到Ctrl+C，正在保存断点并退出...")
                checkpoint['completed_items'] = checkpoint['book_data']['total_items'] - queue.unfinished_tasks
                save_checkpoint(checkpoint, input_epub)
                # 通知终止所有子线程的操作
                stop_event.set()
                break
                
        print("进入退出程序...")
        # 最终保存断点
        if not all_tasks_completed:
            checkpoint['completed_items'] = checkpoint['book_data']['total_items'] - queue.unfinished_tasks
            save_checkpoint(checkpoint, input_epub)
            
        for _ in threads:
            queue.put(None)
        for thread in threads:
            thread.join()
        print("退出程序执行完毕...")
        
        # 如果全部完成，可以删除断点文件
        if all_tasks_completed:
            base_name = os.path.splitext(os.path.basename(input_epub))[0]
            checkpoint_file = CHECKPOINT_FILE.format(base_name)
            if os.path.exists(checkpoint_file):
                os.remove(checkpoint_file)
                print("翻译完成，已删除断点文件")
                
    except KeyboardInterrupt:
        print("主线程侦测到Ctrl+C，正在退出...")
        checkpoint['completed_items'] = checkpoint['book_data']['total_items'] - queue.unfinished_tasks
        save_checkpoint(checkpoint, input_epub)
        for _ in threads:
            queue.put(None)
        for thread in threads:
            thread.join()

if __name__ == '__main__':
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='翻译 EPUB 文件从英文到中文')
    parser.add_argument('input_file', help='输入的 EPUB 文件路径')
    parser.add_argument('--output', '-o', help='输出的 EPUB 文件路径 (默认为输入文件名_cn.epub)')
    parser.add_argument('--threads', '-t', type=int, default=5, help='使用的线程数 (默认: 5)')
    parser.add_argument('--glossary', '-g', help='使用的词汇表文件路径 (JSON 格式)')
    parser.add_argument('--no-resume', action='store_true', help='禁用断点续传')
    parser.add_argument('--extract-terms', action='store_true', help='仅提取专有名词并保存')
    
    args = parser.parse_args()
    
    input_file = args.input_file
    if not input_file.endswith('.epub'):
        print("输入文件必须是 EPUB 文件。")
        sys.exit(1)
    
    # 设置输出文件路径
    output_file = args.output if args.output else input_file.replace('.epub', '_cn.epub')
    
    # 如果只是提取专有名词
    if args.extract_terms:
        terms = extract_terms(input_file)
        # 保存为 JSON 文件
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        terms_file = f"{base_name}_terms.json"
        with open(terms_file, 'w', encoding='utf-8') as f:
            json.dump(terms, f, ensure_ascii=False, indent=2)
        print(f"已提取 {len(terms)} 个可能的专有名词并保存到 {terms_file}")
        sys.exit(0)
    
    # 加载词汇表（如果提供）
    user_glossary = None
    if args.glossary:
        try:
            with open(args.glossary, 'r', encoding='utf-8') as f:
                user_glossary = json.load(f)
            print(f"已加载词汇表，包含 {len(user_glossary)} 个词条")
        except Exception as e:
            print(f"加载词汇表出错: {e}")
            sys.exit(1)
    
    print("开始翻译...")
    translate_epub(input_file, output_file, num_threads=args.threads, 
                  user_glossary=user_glossary, resume=not args.no_resume)
