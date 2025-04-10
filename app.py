import streamlit as st
import os
import json
import pandas as pd
import tempfile
from epubtranslator import translate_epub, extract_terms, load_glossary
import threading

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
                terms = extract_terms(input_path)
                
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
                    
                    # JSON 下载按钮
                    with col1:
                        if st.button("下载词汇表为 JSON"):
                            # 创建词汇表字典
                            glossary = {row["专有名词"]: row["中文翻译"] for _, row in edited_df.iterrows() if row["中文翻译"]}
                            # 保存为 JSON
                            base_name = os.path.splitext(os.path.basename(input_path))[0]
                            glossary_path = os.path.join(temp_dir, f"{base_name}_glossary.json")
                            with open(glossary_path, "w", encoding="utf-8") as f:
                                json.dump(glossary, f, ensure_ascii=False, indent=2)
                            
                            # 提供下载链接
                            with open(glossary_path, "r", encoding="utf-8") as f:
                                st.download_button(
                                    label="下载 JSON 文件",
                                    data=f,
                                    file_name=f"{base_name}_glossary.json",
                                    mime="application/json"
                                )
                    
                    # Excel 下载按钮
                    with col2:
                        if st.button("下载词汇表为 Excel"):
                            # 保存为 Excel
                            base_name = os.path.splitext(os.path.basename(input_path))[0]
                            excel_path = os.path.join(temp_dir, f"{base_name}_glossary.xlsx")
                            
                            # 从数据框中保存非空翻译
                            glossary_df = edited_df[edited_df["中文翻译"].notna() & (edited_df["中文翻译"] != "")]
                            
                            # 如果有空行也保留（全部保存）
                            if len(glossary_df) == 0:
                                glossary_df = edited_df
                                
                            # 保存为Excel
                            glossary_df.to_excel(excel_path, index=False)
                            
                            # 提供下载链接
                            with open(excel_path, "rb") as f:
                                st.download_button(
                                    label="下载 Excel 文件",
                                    data=f,
                                    file_name=f"{base_name}_glossary.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
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
                    translate_epub(
                        input_path, 
                        output_path, 
                        num_threads=num_threads, 
                        user_glossary=user_glossary,
                        resume=resume_translation
                    )
                    # 更新状态
                    st.session_state.translation_status = "翻译完成"
                    st.session_state.translation_done = True
                    st.session_state.translation_progress = 1.0
                except Exception as e:
                    st.session_state.translation_status = f"翻译失败: {str(e)}"
                    st.session_state.translation_done = True
            
            # 启动翻译线程
            translate_thread = threading.Thread(target=run_translation)
            translate_thread.start()
        
        # 刷新状态（每3秒自动刷新一次）
        status_container.info(f"状态: {st.session_state.translation_status}")
        
        # 如果翻译完成，提供下载链接
        if st.session_state.translation_done and st.session_state.translation_status == "翻译完成":
            # 显示成功消息
            st.success("翻译已完成！")
            
            # 提供下载链接
            with open(output_path, "rb") as f:
                st.download_button(
                    label="下载翻译后的 EPUB",
                    data=f,
                    file_name=uploaded_file.name.replace('.epub', '_cn.epub'),
                    mime="application/epub+zip"
                )
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