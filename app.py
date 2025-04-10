import streamlit as st
import os
import json
import pandas as pd
import tempfile
from epubtranslator import translate_epub, extract_terms, load_glossary, export_glossary_to_excel, TRANSLATED_FILES_DIR
import threading
import shutil
from dotenv import load_dotenv
import openai
load_dotenv()

# 设置OpenAI的API密钥
# 通过环境变量读取配置信息


openai.api_key = os.getenv('API_KEY')
openai.api_base = os.getenv('BASE_URL')
model_name = os.getenv('MODEL_NAME')


st.set_page_config(page_title="EPUB 翻译器", page_icon="📚", layout="wide")

# 创建侧边栏
st.sidebar.title("EPUB 翻译器")
st.sidebar.markdown("将英文 EPUB 文件翻译成中文")

# 上传 EPUB 文件
uploaded_file = st.sidebar.file_uploader("上传 EPUB 文件", type=["epub"])

if uploaded_file is not None:
    # 保存上传的文件到临时文件
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, uploaded_file.name)
    output_path = os.path.join(temp_dir, uploaded_file.name.replace('.epub', '_cn.epub'))
    
    with open(input_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    st.sidebar.success(f"文件已上传: {uploaded_file.name}")
    
    # 主要内容区域
    st.title(f"翻译 EPUB: {uploaded_file.name}")
    
    # 创建标签页
    tab1, tab2, tab3 = st.tabs(["专有名词", "翻译设置", "开始翻译"])
    
    # 标签页1：专有名词提取和编辑
    with tab1:
        st.header("专有名词词典")
        
        # 提取专有名词的按钮
        if st.button("从 EPUB 中提取专有名词"):
            with st.spinner("正在提取专有名词..."):
                # 提取专有名词并直接导出为Excel
                terms, excel_path = extract_terms(input_path, export_excel=True)
                
                # 将提取的词条显示在表格中
                if terms:
                    # 创建一个带有翻译列的 DataFrame
                    df = pd.DataFrame({
                        "专有名词": terms,
                        "中文翻译": [""] * len(terms)
                    })
                    
                    # 将 DataFrame 保存到会话状态
                    st.session_state.terms_df = df
                    
                    # 显示可编辑的表格
                    edited_df = st.data_editor(
                        st.session_state.terms_df, 
                        use_container_width=True,
                        num_rows="dynamic",
                        hide_index=True
                    )
                    st.session_state.terms_df = edited_df
                    
                    # 提供下载按钮
                    col1, col2 = st.columns(2)
                    
                    # 初始化会话状态变量
                    if "excel_path" not in st.session_state:
                        st.session_state.excel_path = excel_path
                    else:
                        st.session_state.excel_path = excel_path
                        
                    if "json_path" not in st.session_state:
                        st.session_state.json_path = None
                    
                    # JSON 下载按钮
                    with col1:
                        if st.button("生成JSON词汇表", key="generate_json_btn"):
                            # 创建词汇表字典
                            glossary = {row["专有名词"]: row["中文翻译"] for _, row in edited_df.iterrows() if row["中文翻译"]}
                            # 保存为 JSON
                            base_name = os.path.splitext(os.path.basename(input_path))[0]
                            glossary_path = os.path.join(temp_dir, f"{base_name}_glossary.json")
                            with open(glossary_path, "w", encoding="utf-8") as f:
                                json.dump(glossary, f, ensure_ascii=False, indent=2)
                            
                            # 保存文件路径到会话状态
                            st.session_state.json_path = glossary_path
                            st.success(f"JSON文件已生成，包含 {len(glossary)} 个词条")
                            
                        # 如果已生成JSON文件，提供下载按钮
                        if st.session_state.json_path and os.path.exists(st.session_state.json_path):
                            with open(st.session_state.json_path, "r", encoding="utf-8") as f:
                                st.download_button(
                                    label="下载JSON文件",
                                    data=f,
                                    file_name=os.path.basename(st.session_state.json_path),
                                    mime="application/json",
                                    key="download_json_file"
                                )
                    
                    # Excel 下载按钮
                    with col2:
                        # 如果已有Excel文件路径，直接提供下载按钮
                        if st.session_state.excel_path and os.path.exists(st.session_state.excel_path):
                            with open(st.session_state.excel_path, "rb") as f:
                                file_data = f.read()
                                
                            st.download_button(
                                label="下载Excel文件",
                                data=file_data,
                                file_name=os.path.basename(st.session_state.excel_path),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_excel_file"
                            )
                            st.success(f"Excel文件已生成: {os.path.basename(st.session_state.excel_path)}")
                        
                        # 如果编辑后需要重新生成Excel
                        if st.button("更新Excel词汇表", key="update_excel_btn"):
                            try:
                                # 从编辑后的DataFrame创建新的词汇表
                                glossary = {row["专有名词"]: row["中文翻译"] for _, row in edited_df.iterrows() if pd.notna(row["中文翻译"])}
                                
                                if glossary:
                                    # 使用epubtranslator的函数导出Excel
                                    base_name = os.path.splitext(os.path.basename(input_path))[0]
                                    excel_path = export_glossary_to_excel(glossary, base_name)
                                    
                                    if excel_path:
                                        st.session_state.excel_path = excel_path
                                        st.success(f"Excel文件已更新，包含 {len(glossary)} 条记录")
                                else:
                                    st.warning("没有找到有效的翻译内容，请先添加翻译")
                            except Exception as e:
                                st.error(f"更新Excel文件时出错: {str(e)}")
                                import traceback
                                st.code(traceback.format_exc())
                else:
                    st.info("未找到专有名词")
                    
        # 上传自定义词汇表（新增支持Excel格式）
        st.subheader("上传自定义词汇表")
        uploaded_glossary = st.file_uploader("上传 JSON 或 Excel 格式的词汇表", type=["json", "xlsx", "xls"])
        
        if uploaded_glossary is not None:
            try:
                # 根据文件类型读取
                if uploaded_glossary.name.endswith(('.xlsx', '.xls')):
                    # 读取Excel
                    glossary_df = pd.read_excel(uploaded_glossary)
                    
                    # 确保有正确的列名
                    if '专有名词' in glossary_df.columns and '中文翻译' in glossary_df.columns:
                        # 转换为字典
                        glossary_data = dict(zip(glossary_df['专有名词'], glossary_df['中文翻译']))
                    else:
                        # 假设前两列是术语和翻译
                        col_names = glossary_df.columns.tolist()
                        if len(col_names) >= 2:
                            glossary_df.columns = ['专有名词', '中文翻译'] + col_names[2:]
                            glossary_data = dict(zip(glossary_df['专有名词'], glossary_df['中文翻译']))
                        else:
                            st.error("Excel 文件格式不正确：至少需要两列（专有名词和中文翻译）")
                            glossary_data = {}
                else:
                    # 读取JSON
                    glossary_data = json.load(uploaded_glossary)
                
                # 显示加载信息
                if glossary_data:
                    st.success(f"已上传词汇表，包含 {len(glossary_data)} 个词条")
                    
                    # 转换为 DataFrame 并显示
                    glossary_df = pd.DataFrame({
                        "专有名词": list(glossary_data.keys()),
                        "中文翻译": list(glossary_data.values())
                    })
                    st.session_state.user_glossary = glossary_data
                    
                    # 显示可编辑的表格
                    edited_glossary_df = st.data_editor(
                        glossary_df,
                        use_container_width=True,
                        num_rows="dynamic",
                        hide_index=True
                    )
                    
                    # 更新会话状态中的词汇表
                    st.session_state.user_glossary = dict(zip(
                        edited_glossary_df['专有名词'], 
                        edited_glossary_df['中文翻译']
                    ))

                    # 初始化会话状态变量
                    if "custom_excel_path" not in st.session_state:
                        st.session_state.custom_excel_path = None
                    if "custom_json_path" not in st.session_state:
                        st.session_state.custom_json_path = None

                    # 提供导出按钮
                    col1, col2 = st.columns(2)
                    
                    # 导出到JSON
                    with col1:
                        if st.button("生成JSON词汇表", key="generate_custom_json"):
                            try:
                                # 保存为 JSON
                                base_name = "custom_glossary"
                                glossary_path = os.path.join(temp_dir, f"{base_name}.json")
                                with open(glossary_path, "w", encoding="utf-8") as f:
                                    json.dump(st.session_state.user_glossary, f, ensure_ascii=False, indent=2)
                                
                                # 保存到会话状态
                                st.session_state.custom_json_path = glossary_path
                                st.success(f"JSON文件已生成，包含 {len(st.session_state.user_glossary)} 个词条")
                            except Exception as e:
                                st.error(f"导出JSON文件时出错: {str(e)}")
                                
                        # 如果已生成文件，提供下载按钮
                        if st.session_state.custom_json_path and os.path.exists(st.session_state.custom_json_path):
                            with open(st.session_state.custom_json_path, "r", encoding="utf-8") as f:
                                st.download_button(
                                    label="下载JSON文件",
                                    data=f,
                                    file_name=os.path.basename(st.session_state.custom_json_path),
                                    mime="application/json",
                                    key="download_custom_json"
                                )
                    
                    # 导出到Excel
                    with col2:
                        if st.button("生成Excel词汇表", key="generate_custom_excel"):
                            try:
                                # 使用epubtranslator的函数导出Excel
                                excel_path = export_glossary_to_excel(st.session_state.user_glossary, "custom_glossary")
                                
                                if excel_path:
                                    # 保存到会话状态
                                    st.session_state.custom_excel_path = excel_path
                                    st.success(f"Excel文件已生成，包含 {len(st.session_state.user_glossary)} 条记录")
                                else:
                                    st.error("导出Excel失败，请检查控制台日志")
                            except Exception as e:
                                st.error(f"导出Excel文件时出错: {str(e)}")
                                import traceback
                                st.code(traceback.format_exc())
                                
                        # 如果已生成文件，提供下载按钮
                        if st.session_state.custom_excel_path and os.path.exists(st.session_state.custom_excel_path):
                            with open(st.session_state.custom_excel_path, "rb") as f:
                                file_data = f.read()
                                
                            st.download_button(
                                label="下载Excel文件",
                                data=file_data,
                                file_name=os.path.basename(st.session_state.custom_excel_path),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_custom_excel"
                            )
            except Exception as e:
                st.error(f"读取词汇表出错: {str(e)}")
    
    # 标签页2：翻译设置
    with tab2:
        st.header("翻译设置")
        
        # API 配置信息（仅显示，实际配置在 .env 文件中）
        st.subheader("API 配置")
        st.info("API 配置在 .env 文件中设置，请确保已正确配置。")
        
        # 翻译设置
        st.subheader("翻译参数")
        
        # 线程数
        num_threads = st.slider("线程数", min_value=1, max_value=10, value=5, 
                                help="使用的线程数量，越多速度越快，但可能会导致 API 限流")
        
        # 断点续传
        resume_translation = st.checkbox("启用断点续传", value=True,
                                        help="如果翻译过程中断，下次可以从断点继续")
        
        # 使用自定义词汇表
        use_glossary = st.checkbox("使用自定义词汇表", value=True,
                                  help="将使用上传的或提取的词汇表进行翻译")
    
    # 标签页3：开始翻译
    with tab3:
        st.header("开始翻译")
        
        # 翻译状态
        if "translation_status" not in st.session_state:
            st.session_state.translation_status = "准备就绪"
            st.session_state.translation_progress = 0
            st.session_state.translation_done = False
        
        # 显示翻译状态
        status_container = st.container()
        progress_bar = st.progress(st.session_state.translation_progress)
        
        # 停止翻译按钮（仅在翻译进行中显示）
        if st.session_state.translation_status == "翻译中" and not st.session_state.translation_done:
            if st.button("停止翻译"):
                # 发送停止翻译的信号
                st.session_state.stop_translation = True
                st.session_state.translation_status = "正在停止..."
                status_container.info(f"状态: {st.session_state.translation_status}")
        
        # 开始翻译按钮
        if st.button("开始翻译", disabled=(st.session_state.translation_status == "翻译中")):
            # 重置状态
            st.session_state.translation_status = "翻译中"
            st.session_state.translation_progress = 0
            st.session_state.translation_done = False
            st.session_state.stop_translation = False
            
            status_container.info(f"状态: {st.session_state.translation_status}")
            
            # 获取用户词汇表
            user_glossary = st.session_state.get("user_glossary", None)
            
            # 在后台线程中启动翻译
            def run_translation():
                try:
                    # 开始翻译
                    translate_result = translate_epub(
                        input_path, 
                        num_threads=num_threads, 
                        user_glossary=user_glossary,
                        resume=resume_translation
                    )
                    
                    # 解包返回值
                    output_path, tmp_output_path, translated_file_path = translate_result
                    
                    # 更新状态
                    st.session_state.translation_status = "翻译完成"
                    st.session_state.translation_done = True
                    st.session_state.translation_progress = 1.0

                    # 在翻译完成后立即尝试提供下载链接，不等待页面刷新
                    if os.path.exists(output_path):
                        try:
                            # 将翻译完成的文件复制到一个新的位置来避免文件锁定问题
                            final_output_path = os.path.join(temp_dir, "final_" + uploaded_file.name.replace('.epub', '_cn.epub'))
                            shutil.copy2(output_path, final_output_path)
                            st.session_state.final_output_path = final_output_path
                            st.session_state.output_filename = uploaded_file.name.replace('.epub', '_cn.epub')
                            print(f"翻译文件已保存到: {final_output_path}")
                            
                            # 如果有临时目录的路径，也保存下来
                            if tmp_output_path and os.path.exists(tmp_output_path):
                                st.session_state.tmp_output_path = tmp_output_path
                                print(f"翻译文件也保存在临时目录: {tmp_output_path}")
                                
                            # 如果有永久存储的路径，保存下来
                            if translated_file_path and os.path.exists(translated_file_path):
                                st.session_state.translated_file_path = translated_file_path
                                print(f"翻译文件也保存在永久目录: {translated_file_path}")
                        except Exception as e:
                            print(f"复制翻译结果时出错: {str(e)}")
                            import traceback
                            traceback.print_exc()
                except Exception as e:
                    st.session_state.translation_status = f"翻译失败: {str(e)}"
                    st.session_state.translation_done = True
                    print(f"翻译过程出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            # 启动翻译线程
            translate_thread = threading.Thread(target=run_translation)
            translate_thread.start()
        
        # 刷新状态（每3秒自动刷新一次）
        status_container.info(f"状态: {st.session_state.translation_status}")
        
        # 如果翻译完成，提供下载链接
        if st.session_state.translation_done and st.session_state.translation_status == "翻译完成":
            # 显示成功消息
            st.success("翻译已完成！")
            
            # 检查文件是否存在并提供下载链接
            if hasattr(st.session_state, "final_output_path") and os.path.exists(st.session_state.final_output_path):
                try:
                    with open(st.session_state.final_output_path, "rb") as f:
                        file_data = f.read()
                        
                    st.download_button(
                        label="下载翻译后的 EPUB",
                        data=file_data,
                        file_name=st.session_state.output_filename,
                        mime="application/epub+zip",
                        key="download_translated_epub"
                    )
                    
                    # 显示文件信息和状态
                    file_size = os.path.getsize(st.session_state.final_output_path) / 1024
                    st.info(f"翻译文件已准备好: {st.session_state.output_filename} ({file_size:.2f} KB)")
                except Exception as e:
                    st.error(f"准备下载时出错: {str(e)}")
                    # 提供备用方案
                    st.warning(f"如果下载按钮不起作用，请在文件夹 {temp_dir} 中查找翻译后的文件")
            else:
                # 尝试直接从output_path读取
                try:
                    # 提供下载链接
                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="下载翻译后的 EPUB",
                            data=f,
                            file_name=uploaded_file.name.replace('.epub', '_cn.epub'),
                            mime="application/epub+zip",
                            key="download_original_path"
                        )
                except Exception as e:
                    st.error(f"无法访问翻译文件: {str(e)}")
                    st.warning(f"请手动从以下路径获取翻译文件: {output_path}")
                    
            # 如果有临时目录中的文件，也提供下载
            if hasattr(st.session_state, "tmp_output_path") and os.path.exists(st.session_state.tmp_output_path):
                try:
                    with open(st.session_state.tmp_output_path, "rb") as f:
                        file_data = f.read()
                    
                    tmp_filename = os.path.basename(st.session_state.tmp_output_path)
                    st.download_button(
                        label="从临时目录下载翻译后的 EPUB",
                        data=file_data,
                        file_name=tmp_filename,
                        mime="application/epub+zip",
                        key="download_tmp_epub"
                    )
                    
                    # 显示临时文件的路径
                    st.info(f"翻译文件保存在临时目录: {st.session_state.tmp_output_path}")
                except Exception as e:
                    st.error(f"访问临时目录文件时出错: {str(e)}")
                    
            # 如果有永久存储目录中的文件，提供下载
            if hasattr(st.session_state, "translated_file_path") and os.path.exists(st.session_state.translated_file_path):
                try:
                    with open(st.session_state.translated_file_path, "rb") as f:
                        file_data = f.read()
                    
                    perm_filename = os.path.basename(st.session_state.translated_file_path)
                    st.download_button(
                        label="从永久存储目录下载翻译后的 EPUB",
                        data=file_data,
                        file_name=perm_filename,
                        mime="application/epub+zip",
                        key="download_translated_file"
                    )
                    
                    # 显示永久文件的路径和信息
                    file_size = os.path.getsize(st.session_state.translated_file_path) / 1024
                    st.success(f"翻译文件已永久保存在: {st.session_state.translated_file_path} ({file_size:.2f} KB)")
                    st.success(f"所有翻译文件都保存在应用程序的 translated_files 目录下，路径: {TRANSLATED_FILES_DIR}")
                except Exception as e:
                    st.error(f"访问永久存储文件时出错: {str(e)}")
else:
    # 如果没有上传文件，显示欢迎信息
    st.title("EPUB 翻译器")
    st.markdown("""
    ### 使用说明
    
    1. 在左侧侧边栏上传一个 EPUB 文件
    2. 提取专有名词并进行编辑（可选）
    3. 上传自定义词汇表（可选，支持JSON和Excel格式）
    4. 调整翻译设置
    5. 开始翻译并下载结果
    
    ### 特性
    
    * 使用 OpenAI API 进行高质量翻译
    * 支持专有名词词典
    * 支持断点续传
    * 多线程加速翻译过程
    """)
    
    # 显示环境配置要求
    st.subheader("环境配置")
    st.markdown("""
    在运行此应用前，请确保已正确配置 `.env` 文件，其中包含以下环境变量：
    
    **配置示例：**
    ```
    API_KEY=your_api_key_here
    MODEL_NAME=gpt-3.5-turbo
    # 如果使用代理服务器
    BASE_URL=https://your-proxy-server.com/v1
    ```
    """) 