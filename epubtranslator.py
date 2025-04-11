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
import tempfile
import shutil

# 加载环境变量
load_dotenv()

# 导入用于Excel处理的库
try:
    import pandas as pd
except ImportError:
    print("警告: pandas库未安装，无法导出Excel文件")
    pd = None

class TranslationResult:
    def __init__(self, result, errorcode, data):
        self.result = result
        self.errorcode = errorcode
        self.data = data

class EpubTranslator:
    # 用于保存翻译进度的文件名模板
    CHECKPOINT_FILE = "{}_translation_checkpoint.pkl"
    # 保存专有名词词典的文件名
    GLOSSARY_FILE = "{}_glossary.json"
    # 临时目录，用于存放导出的文件
    TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
    # 永久性存储目录，用于保存翻译后的文件
    TRANSLATED_FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translated_files")

    def __init__(self, api_key=None, api_base=None, model_name=None, common_words_path='./commonwords/google-10000-english.txt'):
        """初始化翻译器"""
        # 确保临时目录和永久性存储目录存在
        os.makedirs(self.TMP_DIR, exist_ok=True)
        os.makedirs(self.TRANSLATED_FILES_DIR, exist_ok=True)
        
        # 设置OpenAI API参数
        self.api_key = api_key or os.getenv('API_KEY')
        self.api_base = api_base or os.getenv('BASE_URL')
        self.model_name = model_name or os.getenv('MODEL_NAME')
        
        # 初始化OpenAI API
        openai.api_key = self.api_key
        if self.api_base:
            openai.api_base = self.api_base
            
        print(f"model_name: {self.model_name}")
        print(f"openai.api_key: {openai.api_key}")
        print(f"openai.api_base: {openai.api_base}")
        
        # 加载常用词列表
        self.common_words = self.load_common_words(common_words_path)
        
        # 初始化停止事件
        self.stop_event = threading.Event()

    def load_common_words(self, file_path):
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

    def check_string(self, s):
        """检查字符串是否只包含英文单词、句子、适量的标点和空格"""
        # 这个正则表达式匹配包含至少一个英文字母的字符串
        match = re.search(r'[A-Za-z]', s)
        # 如果match不是None，则字符串是有效的
        return match is not None

    def is_valid_term(self, term):
        """判断一个词组是否可能是一个有效的专有名词"""
        # 如果是空或只有一个字符，不是有效术语
        if not term or len(term) <= 1:
            return False
            
        # 分割成单词
        words = term.split()
        
        # 如果只有一个单词
        if len(words) == 1:
            # 如果是常见单词（不区分大小写），排除
            if words[0].lower() in self.common_words:
                return False
            
            # 如果只有一个单词且长度小于4，可能不够特殊，除非它可能是缩写（全大写）
            if len(words[0]) < 4 and not words[0].isupper():
                return False
        
        # 检查多词组合是否全是常用词
        all_common = all(word.lower() in self.common_words for word in words)
        if all_common:
            return False
        
        # 可能是有意义的专有名词
        return True

    def extract_terms(self, input_epub, export_excel=False):
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
                    if self.is_valid_term(term):
                        terms.add(term)
        
        sorted_terms = sorted(list(terms))
        print(f"提取了 {len(sorted_terms)} 个可能的专有名词")
        
        # 如果需要导出Excel，生成Excel文件并返回文件路径
        excel_path = None
        if export_excel and sorted_terms:
            base_name = os.path.splitext(os.path.basename(input_epub))[0]
            excel_path = self.export_terms_to_excel(sorted_terms, base_filename=base_name)
        
        return sorted_terms, excel_path

    def translate_text(self, text, glossary=None, max_retries=3):
        """翻译文本，支持重试和术语替换"""
        # 先检查词汇表中是否有对应的翻译
        if glossary and text in glossary:
            print(f"使用词汇表翻译: {text} -> {glossary[text]}")
            return TranslationResult(True, 0, glossary[text])
        
        # 预处理：在发送前替换文本中的术语
        preprocessed_text = text
        if glossary:
            # 按长度排序术语，优先替换长词，避免部分替换问题
            sorted_terms = sorted(glossary.items(), key=lambda x: len(x[0]), reverse=True)
            replaced_terms = []
            
            for term, translation in sorted_terms:
                if term in preprocessed_text:
                    # 简单字符串替换
                    preprocessed_text = preprocessed_text.replace(term, translation)
                    replaced_terms.append(f"{term} -> {translation}")
            
            if replaced_terms:
                print(f"预处理替换了 {len(replaced_terms)} 个术语: {', '.join(replaced_terms[:3])}")
                if len(replaced_terms) > 3:
                    print(f"...等共 {len(replaced_terms)} 个术语")
        
        # 调用OpenAI的API进行翻译，添加重试机制
        retries = 0
        while retries <= max_retries:
            try:
                if not self.check_string(preprocessed_text):
                    print("不需要翻译！")
                    return TranslationResult(True, 0, text)
                
                response = openai.ChatCompletion.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role":"system",
                            "content":"从现在开始，您是一名翻译。你不会与我进行任何对话;你只会将我的话从英语翻译成中文，无论或长或短都翻译。您将返回纯翻译结果，无需添加任何其他内容与解释，包括中文拼音。"
                        },  
                        {
                            "role": "user", 
                            "content": f"{preprocessed_text}"
                        }
                    ],
                    max_tokens=1024,
                    temperature=0.0,
                    request_timeout=30,  # 增加超时时间到30秒
                )
                    
                if response is None:
                    print("翻译失败！")
                    return text
                
                translated_text = response.choices[0].message['content']
                
                # 每个请求后休息3秒，避免请求过于频繁
                time.sleep(3)
                
                return TranslationResult(True, 0, translated_text)
                
            except Exception as e:
                print("发生异常：", e)
                error_msg = str(e).lower()
                # 判断是否为超时异常
                if "timeout" in error_msg or "timed out" in error_msg:
                    retries += 1
                    if retries <= max_retries:
                        wait_time = 5  # 超时后等待5秒
                        print(f"请求超时，等待{wait_time}秒后重试 ({retries}/{max_retries})...")
                        time.sleep(wait_time)
                        continue  # 继续下一次重试
                    else:
                        print(f"超过最大重试次数 ({max_retries})，放弃翻译")
                
                traceback.print_exc()
                return TranslationResult(False, 1001, None)

    def translate_html(self, text, glossary=None, max_retries=3):
        """翻译HTML内容，支持重试和术语替换"""
        # 先检查词汇表中是否有对应的翻译
        if glossary and text in glossary:
            print(f"使用词汇表翻译HTML: {text} -> {glossary[text]}")
            return TranslationResult(True, 0, glossary[text])
        
        # 预处理：替换HTML中的术语
        preprocessed_text = text
        if glossary:
            try:
                # 解析HTML
                soup = BeautifulSoup(text, 'html.parser')
                
                # 处理所有文本节点
                def process_text_nodes(node):
                    if isinstance(node, NavigableString):
                        text_content = str(node)
                        modified = False
                        
                        # 按长度排序术语，优先替换长词
                        sorted_terms = sorted(glossary.items(), key=lambda x: len(x[0]), reverse=True)
                        
                        for term, translation in sorted_terms:
                            if term in text_content:
                                text_content = text_content.replace(term, translation)
                                modified = True
                                print(f"在HTML中替换术语: {term} -> {translation}")
                        
                        if modified:
                            node.replace_with(text_content)
                    else:
                        # 递归处理子节点
                        for child in list(node.children):
                            process_text_nodes(child)
                
                # 处理HTML中的文本节点
                process_text_nodes(soup)
                
                # 将修改后的HTML转换回字符串
                preprocessed_text = str(soup)
            except Exception as e:
                print(f"处理HTML中的术语时出错: {e}")
                # 如果出错，继续使用原始的text
                preprocessed_text = text
        
        # 调用OpenAI的API进行翻译，添加重试机制
        retries = 0
        while retries <= max_retries:
            try:
                if not self.check_string(preprocessed_text):
                    print("不需要翻译！")
                    return TranslationResult(True, 0, text)
                
                response = openai.ChatCompletion.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role":"system",
                            "content":"我将发一段HTML代码给你，其中包含了英文文本，请根据具体情况翻译英文文本到中文，维持原有HTML格式。"
                        },
                        {
                            "role": "user", 
                            "content": f"{preprocessed_text}"
                        }
                    ],
                    max_tokens=1024,
                    temperature=0.0,
                    request_timeout=30  # 增加超时时间到30秒
                )
                
                if response is None:
                    print("翻译失败！")
                    return text
                    
                translated_text = response.choices[0].message['content']
                
                # 每个请求后休息3秒，避免请求过于频繁
                time.sleep(3)
                
                return TranslationResult(True, 0, translated_text)
                
            except Exception as e:
                print("发生异常：", e)
                error_msg = str(e).lower()
                # 判断是否为超时异常
                if "timeout" in error_msg or "timed out" in error_msg:
                    retries += 1
                    if retries <= max_retries:
                        wait_time = 5  # 超时后等待5秒
                        print(f"HTML请求超时，等待{wait_time}秒后重试 ({retries}/{max_retries})...")
                        time.sleep(wait_time)
                        continue  # 继续下一次重试
                    else:
                        print(f"HTML超过最大重试次数 ({max_retries})，放弃翻译")
                
                traceback.print_exc()
                return TranslationResult(False, 1001, None)

    def update_epub_title(self, epub_path, new_title):
        """更新EPUB标题"""
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

    def worker(self, queue, output_epub, new_book, lock, glossary=None):
        """线程工作函数，用于并行翻译"""
        try:
            while True:
                if self.stop_event.is_set():
                    break
                item = queue.get()
                if item is None:
                    break
                current_thread = threading.current_thread()
                if item.get_type() == 4 or item.get_type() == 9:
                    print(f"{current_thread.name} 正在处理 {item.file_name}")
                self.translate_and_save_item(item, output_epub, new_book, lock, glossary)
                queue.task_done()
        except Exception as e:
            print(f"{current_thread.name}发生异常")
            traceback.print_exc()
            queue.task_done()
            quit()

    def translate_and_save_item(self, item, output_epub, new_book, lock, glossary=None):
        """翻译并保存EPUB项目"""
        if item.get_type() == 9:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            p_list = soup.findAll("p")
            if len(p_list) == 0:
                new_book.add_item(item)
                return
            for p in p_list:
                if self.stop_event.is_set():
                    break
                print("翻前HTML：",p)
                tresult = self.translate_html(str(p), glossary)
                if tresult.result:
                    translated_text = tresult.data
                    newtag = BeautifulSoup(translated_text,'html.parser').p
                    p.replace_with(newtag)
                    print(f"翻后HTML：{newtag}")
            item.set_content(str(soup).encode('utf-8'))
        new_book.add_item(item)
        with lock:
            epub_options = {'ignore_ncx': False}
            epub.write_epub(output_epub, new_book, epub_options)

    def modify_links(self, item, glossary=None):
        """修改EPUB中的链接和目录项"""
        if isinstance(item, epub.Link):
            # Modify the title of the link
            print(f"开始翻译LINK： {item.title}")
            tresult = self.translate_text(item.title, glossary)
            if tresult.result == False:
                return epub.Link(item.href, item.title, item.uid)
            else:
                translated_text = tresult.data
                new_title = translated_text
                print(f"翻译完成： {new_title}")
                return epub.Link(item.href, new_title, item.uid)
        elif isinstance(item, tuple):
            # 解包
            toc_section, toc_links = item  # 解包元组
            print("Section Title:", toc_section.title)
            new_title = toc_section.title
            tresult = self.translate_text(toc_section.title, glossary)
            if tresult.result:
                translated_text = tresult.data
                new_title = translated_text
                print(f"翻译完成： {new_title}")
            new_links = [self.modify_links(link, glossary) for link in toc_links]
            # Return a tuple with the modified section and links
            return (epub.Section(new_title, toc_section.href), new_links)
        else:
            # Return the item unmodified if it's not a link or a section
            print("****啥也不是!****", type(item), item)
            # 如果 TOC 有不同类型的对象，可以在这里处理
            return item

    def load_glossary(self, input_file, user_glossary=None):
        """加载或创建专有名词词典"""
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        glossary_file = self.GLOSSARY_FILE.format(base_name)
        
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

    def load_checkpoint(self, input_file, output_file):
        """加载翻译进度检查点"""
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        checkpoint_file = self.CHECKPOINT_FILE.format(base_name)
        
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

    def save_checkpoint(self, checkpoint_data, input_file):
        """保存翻译进度检查点"""
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        checkpoint_file = self.CHECKPOINT_FILE.format(base_name)
        
        with open(checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)
        print(f"已保存断点，已完成项 {checkpoint_data['completed_items']} 个")

    def translate_epub(self, input_epub, output_epub=None, num_threads=5, user_glossary=None, resume=True):
        """翻译EPUB文件"""
        if output_epub is None:
            output_epub = input_epub.replace('.epub', '_cn.epub')
            
        try:
            # 加载或创建词汇表
            glossary = self.load_glossary(input_epub, user_glossary)
            
            # 加载断点
            checkpoint = None
            if resume:
                checkpoint = self.load_checkpoint(input_epub, output_epub)
            
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
                new_toc = [self.modify_links(link, glossary) for link in book.toc]
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
                self.save_checkpoint(checkpoint, input_epub)
            else:
                print(f"从断点恢复翻译，已完成 {checkpoint['completed_items']}/{checkpoint['book_data']['total_items']} 项...")
                new_book = epub.read_epub(output_epub)
            
            queue = Queue()
            lock = threading.Lock()
            threads = []
            
            # 创建工作线程
            for _index in range(num_threads):
                thread = threading.Thread(target=self.worker, args=(queue, output_epub, new_book, lock, glossary), name="Thread-"+_index.__str__())
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
                        self.save_checkpoint(checkpoint, input_epub)
                        last_checkpoint_save = time.time()
                    
                    all_tasks_completed = queue.unfinished_tasks == 0
                except KeyboardInterrupt:
                    print("侦测到Ctrl+C，正在保存断点并退出...")
                    checkpoint['completed_items'] = checkpoint['book_data']['total_items'] - queue.unfinished_tasks
                    self.save_checkpoint(checkpoint, input_epub)
                    # 通知终止所有子线程的操作
                    self.stop_event.set()
                    break
                    
            print("进入退出程序...")
            # 最终保存断点
            if not all_tasks_completed:
                checkpoint['completed_items'] = checkpoint['book_data']['total_items'] - queue.unfinished_tasks
                self.save_checkpoint(checkpoint, input_epub)
                
            for _ in threads:
                queue.put(None)
            for thread in threads:
                thread.join()
            print("退出程序执行完毕...")
            
            # 如果全部完成，可以删除断点文件
            if all_tasks_completed:
                base_name = os.path.splitext(os.path.basename(input_epub))[0]
                checkpoint_file = self.CHECKPOINT_FILE.format(base_name)
                if os.path.exists(checkpoint_file):
                    os.remove(checkpoint_file)
                    print("翻译完成，已删除断点文件")
            
            # 将翻译好的文件复制到TMP_DIR目录
            tmp_output_path = None
            translated_file_path = None
            if os.path.exists(output_epub) and all_tasks_completed:
                try:
                    # 创建目标文件名
                    base_name = os.path.splitext(os.path.basename(input_epub))[0]
                    # 临时目录版本
                    tmp_file_name = f"{base_name}_cn_{int(time.time())}.epub"
                    tmp_output_path = os.path.join(self.TMP_DIR, tmp_file_name)
                    
                    # 永久存储版本 
                    perm_file_name = f"{base_name}_cn_{int(time.time())}.epub"
                    translated_file_path = os.path.join(self.TRANSLATED_FILES_DIR, perm_file_name)
                    
                    # 复制文件到永久位置
                    shutil.copy2(output_epub, translated_file_path)
                    print(f"已将翻译结果保存到永久目录: {translated_file_path}")
                except Exception as e:
                    print(f"复制文件时出错: {e}")
                    traceback.print_exc()
                    
            # 返回输出文件路径、临时目录路径和永久存储路径
            return output_epub, tmp_output_path, translated_file_path
                    
        except KeyboardInterrupt:
            print("主线程侦测到Ctrl+C，正在退出...")
            checkpoint['completed_items'] = checkpoint['book_data']['total_items'] - queue.unfinished_tasks
            self.save_checkpoint(checkpoint, input_epub)
            for _ in threads:
                queue.put(None)
            for thread in threads:
                thread.join()
            return output_epub, None, None

    def export_glossary_to_excel(self, glossary, base_filename=None):
        """将词汇表导出为Excel文件，保存在临时目录中"""
        if pd is None:
            print("错误: 无法导出Excel文件，pandas库未安装")
            return None
            
        try:
            # 创建文件名
            if base_filename:
                filename = f"{base_filename}_glossary.xlsx"
            else:
                filename = f"glossary_{int(time.time())}.xlsx"
                
            # 完整文件路径
            file_path = os.path.join(self.TMP_DIR, filename)
            
            # 创建DataFrame
            df = pd.DataFrame({
                "专有名词": list(glossary.keys()),
                "中文翻译": list(glossary.values())
            })
            
            # 保存为Excel
            df.to_excel(file_path, index=False, engine="openpyxl")
            
            print(f"词汇表已导出为Excel: {file_path}")
            return file_path
        except Exception as e:
            print(f"导出Excel文件时出错: {e}")
            traceback.print_exc()
            return None
            
    def export_terms_to_excel(self, terms, translations=None, base_filename=None):
        """将提取的专有名词列表导出为Excel文件，可选添加已有的翻译"""
        if pd is None:
            print("错误: 无法导出Excel文件，pandas库未安装")
            return None
            
        try:
            # 创建文件名
            if base_filename:
                filename = f"{base_filename}_terms.xlsx"
            else:
                filename = f"terms_{int(time.time())}.xlsx"
                
            # 完整文件路径
            file_path = os.path.join(self.TMP_DIR, filename)
            
            # 准备数据
            translations_dict = translations or {}
            data = {
                "专有名词": terms,
                "中文翻译": [translations_dict.get(term, "") for term in terms]
            }
            
            # 创建DataFrame
            df = pd.DataFrame(data)
            
            # 保存为Excel
            df.to_excel(file_path, index=False, engine="openpyxl")
            
            print(f"专有名词已导出为Excel: {file_path}")
            return file_path
        except Exception as e:
            print(f"导出Excel文件时出错: {e}")
            traceback.print_exc()
            return None

# 主函数部分
if __name__ == '__main__':
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='翻译 EPUB 文件从英文到中文')
    parser.add_argument('input_file', help='输入的 EPUB 文件路径')
    parser.add_argument('--output', '-o', help='输出的 EPUB 文件路径 (默认为输入文件名_cn.epub)')
    parser.add_argument('--threads', '-t', type=int, default=5, help='使用的线程数 (默认: 5)')
    parser.add_argument('--glossary', '-g', help='使用的词汇表文件路径 (JSON 格式)')
    parser.add_argument('--no-resume', action='store_true', help='禁用断点续传')
    parser.add_argument('--extract-terms', action='store_true', help='仅提取专有名词并保存')
    parser.add_argument('--export-excel', action='store_true', help='导出专有名词为Excel格式')
    parser.add_argument('--export-glossary', action='store_true', help='导出当前词汇表为Excel格式')
    
    args = parser.parse_args()
    
    input_file = args.input_file
    if not input_file.endswith('.epub'):
        print("输入文件必须是 EPUB 文件。")
        sys.exit(1)
    
    # 设置输出文件路径
    output_file = args.output if args.output else input_file.replace('.epub', '_cn.epub')
    
    # 创建翻译器实例
    translator = EpubTranslator()
    
    # 如果只是提取专有名词
    if args.extract_terms:
        terms, excel_path = translator.extract_terms(input_file, export_excel=args.export_excel)
        # 保存为 JSON 文件
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        terms_file = f"{base_name}_terms.json"
        with open(terms_file, 'w', encoding='utf-8') as f:
            json.dump(terms, f, ensure_ascii=False, indent=2)
        print(f"已提取 {len(terms)} 个可能的专有名词并保存到 {terms_file}")
        if excel_path:
            print(f"已导出专有名词到Excel: {excel_path}")
        sys.exit(0)
    
    # 加载词汇表（如果提供）
    user_glossary = None
    if args.glossary:
        try:
            with open(args.glossary, 'r', encoding='utf-8') as f:
                user_glossary = json.load(f)
            print(f"已加载词汇表，包含 {len(user_glossary)} 个词条")
            
            # 如果需要导出词汇表为Excel
            if args.export_glossary and user_glossary:
                base_name = os.path.splitext(os.path.basename(args.glossary))[0]
                excel_path = translator.export_glossary_to_excel(user_glossary, base_name)
                if excel_path:
                    print(f"已导出词汇表到Excel: {excel_path}")
                    
        except Exception as e:
            print(f"加载词汇表出错: {e}")
            sys.exit(1)
    
    print("开始翻译...")
    translate_result = translator.translate_epub(
        input_file, 
        output_file, 
        num_threads=args.threads, 
        user_glossary=user_glossary, 
        resume=not args.no_resume
    )
    
    # 解包返回值
    output_path, tmp_output_path, translated_file_path = translate_result
    
    print("翻译完成！")
    print(f"输出文件: {output_path}")
    if translated_file_path:
        print(f"永久存储文件: {translated_file_path}")
