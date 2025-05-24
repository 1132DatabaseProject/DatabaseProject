import os
import asyncio
import html
from datetime import datetime
import pdfkit
import webbrowser
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_file,session,redirect,url_for
from werkzeug.utils import secure_filename
import tempfile
from supabase import create_client
import secrets
import requests
from dateutil import parser


# Google Gemini
import google.generativeai as genai


# 初始化Flask
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = os.urandom(24)  # 設定 Session 的密鑰
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # Session 有效時間為 1 小時

# 確保上傳資料夾存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 載入.env
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# wkhtmltopdf路徑
WKHTMLTOPDF_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
pdfkit_config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>英文寫作分析報告</title>
<style>
    /* 
       關鍵：所有針對報告內容的樣式，都必須以 .pdf-report-view 作為前綴。
       這樣，當這段 HTML 被插入到 index.html 時，這些樣式只會影響
       <div class="pdf-report-view"> 內部的元素，不會污染外部頁面。
    */

    /* 針對 .pdf-report-view 容器本身的基礎樣式 (可選，主要用於PDF) */
    .pdf-report-view {{
        font-family: "Times New Roman", serif;
        margin: 20px; /* 這是指在 PDF 頁面中的邊距 */
        line-height: 1.8;
        font-size: 14pt; /* 調整為 pt 以便 PDF 渲染 */
        color: #333;
    }}

    /* 報告標題 */
    .pdf-report-view h1 {{
        text-align: center;
        font-size: 20pt;
        margin-bottom: 40px;
        color: #111;
    }}

    /* 各部分標題 */
    .pdf-report-view h2 {{
        font-size: 14pt;
        color: #2c3e50;
        margin-top: 30px;
        margin-bottom: 10px;
        border-bottom: 1px solid #eee;
        padding-bottom: 5px;
    }}

    .pdf-report-view .timestamp {{
        text-align: right;
        font-size: 10pt;
        color: gray;
        margin-bottom: 20px;
    }}

    .pdf-report-view .highlight {{
        color: red;
        /* 根據你的 Gemini Prompt，這裡不應該是 font-weight: bold; */
        /* 如果 Gemini 返回的 HTML 中 .highlight 已經包含了粗體，而你不想，
           可以在這裡強制取消：font-weight: normal !important;
           但最好是讓 Gemini 不要輸出粗體。
        */
    }}

    .pdf-report-view p {{
        text-indent: 2em;
        font-size: 12pt;
        margin-top: 10px;
        margin-bottom: 8px;
        text-align: justify;
    }}

    .pdf-report-view .error-block {{ /* 如果有的話 */
        margin-top: 10px;
        padding: 10px;
        background-color: #ffeeee;
        border-left: 3px solid red;
    }}

    /* 如果還有其他針對 ul, ol, li 等標籤的樣式，也要加上 .pdf-report-view 前綴 */
    .pdf-report-view ul, 
    .pdf-report-view ol {{
        padding-left: 40px; /* PDF 中列表的縮進 */
    }}

    .pdf-report-view li {{
        margin-bottom: 5px; /* PDF 中列表項的間距 */
    }}

</style>
</head>
<body>
    <!-- 
        關鍵：將所有實際的報告內容包裹在這個帶有 'pdf-report-view' class 的 div 中。
        注意，原始的 <h1>英文寫作分析報告</h1> 和 <div class="timestamp">...</div>
        現在也移到了這個包裹 div 的內部，這樣它們也會受到 .pdf-report-view 前綴樣式的控制。
    -->
    <div class="pdf-report-view">
        <h1>英文寫作分析報告</h1>
        <div class="timestamp">生成時間：{timestamp}</div>
        {content}
    </div>
</body>
</html>

"""

# 區塊模板
SECTION_TEMPLATE = """
<h2>{title}</h2>
{content}
"""

# 分析文章
async def analyze_text(text_content, model_client):
    prompt = (
        "請根據下列格式分析這篇英文文章，並用正式繁體中文回答，不要有AI回應開場白。\n\n"
        "請按照以下五個部分依序分析，並清楚標示標題（每個標題前請加上『第X部分：』）：\n\n"
        "第1部分：文章內容統整：說明這篇文章的重點。\n"
        "第2部分：內容分析：【敘事方式說明】與【佳句統整】。\n"
        "第3部分：文章優、缺點：個別條列【優點】、【缺點】，並簡要說明【整體回饋】。\n"
        "第4部分：文法與用詞錯誤：用數字條列指出【原文】和【改進方式】。\n"
        "第5部分：文法、單字替換：用數字條列【原文】、【建議替換內容】、【簡要說明建議原因】\n\n"
        "注意：文中請用紅色字標出第4部分的英文文法或用詞錯誤之處（用<span class='highlight'>標記內容</span>），並不要使用粗體字。\n"
        "請盡量詳細分析。\n"
        "回覆時直接開始，不要有開場白。\n\n"
        f"以下為文章內容：\n\n{text_content}"
    )
    try:
        response = await model_client.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print("呼叫API時出錯:", e)
        return "目前無法取得回應，請稍後再試。"

# 生成範例文章
async def generate_sample_article(text_content, model_client):
    prompt = (
        "請根據以下英文文章的主題，重新寫一篇相同主題但敘事方式不同或更優秀的英文範例文章。"
        "新文章請自然流暢、用字適切且文法正確。請直接給出完整英文文章，不要有任何中文說明或開場白。\n\n"
        f"以下為原始文章：\n\n{text_content}"
    )
    try:
        response = await model_client.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print("產生範例文章時出錯:", e)
        return "目前無法取得範例文章，請稍後再試。"

# 生成HTML報告
def generate_html_report(analysis_text, sample_article_text):
    print(f"sample_article_text: {repr(sample_article_text)}")  # 加這行！
    sections = []
    current_title = None
    current_content = []

    for line in analysis_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(kw in line for kw in ["第1部分", "第2部分", "第3部分", "第4部分", "第5部分"]):
            if current_title:
                sections.append((current_title, "\n".join(current_content)))
            current_title = line
            current_content = []
        else:
            current_content.append(line)
    if current_title:
        sections.append((current_title, "\n".join(current_content)))

    formatted_sections = []
    for title, content in sections:
        formatted_sections.append(SECTION_TEMPLATE.format(
            title=title,
            content="<p>" + content.replace("\n", "</p><p>") + "</p>"
        ))


    # 正確處理 sample_article_text
    sample_article_html = html.escape(sample_article_text).replace('\n', '</p><p>')
    formatted_sections.append(SECTION_TEMPLATE.format(
        title="範例文章參考",
        content=f"<p>{sample_article_html}</p>"
    ))


    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_html = HTML_TEMPLATE.format(timestamp=timestamp, content="\n".join(formatted_sections))
    return final_html


# 主頁路由
@app.route("/", methods=["GET", "POST"])
def index():
    user_logged_in = 'user_email' in session
    user_email = session.get('user_email')

    if 'user_email' not in session:
        return redirect(url_for('login'))
    if request.method == "POST":

        # --- POST Request Logic ---
        if not user_logged_in:
            app.logger.warning("POST attempt to / by non-logged-in user.")
            return jsonify({"error": "請先登入", "login_required": True}), 401
        else:
            # user_email is already set from above if user_logged_in is True
            app.logger.info(f"POST request to / by user: {user_email}")
            app.logger.debug(f"Flask request.form: {request.form}")
            app.logger.debug(f"Flask request.files: {request.files}")

            input_text = request.form.get("text_content", "")
            uploaded_file = request.files.get("file")

            app.logger.debug(f"Received input_text: '{input_text}'")
            if uploaded_file and uploaded_file.filename: # Check filename here too
                app.logger.debug(f"Received uploaded_file: '{uploaded_file.filename}'")
            else:
                app.logger.debug("No valid uploaded file received.")
                uploaded_file = None # Ensure it's None if not valid

            is_input_empty = not input_text.strip()
            is_file_empty = not (uploaded_file and uploaded_file.filename)

            app.logger.debug(f"Is input_text empty? {is_input_empty}")
            app.logger.debug(f"Is uploaded_file empty? {is_file_empty}")

            if is_input_empty and is_file_empty:
                app.logger.info("Both text and file are empty. Returning JSON error.")
                return jsonify({"result": "請輸入文章內容或上傳檔案。"})

            # File processing should happen *after* checking if input_text itself is sufficient
            if uploaded_file: # No need to check filename.endswith(".txt") here if we already did is_file_empty
                filename = secure_filename(uploaded_file.filename)
                if filename.endswith(".txt"): # Check extension here
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    try:
                        uploaded_file.save(filepath)
                        with open(filepath, "r", encoding="utf-8") as f:
                            input_text = f.read() # Overwrites input_text if file is provided
                        app.logger.info(f"Read content from uploaded file: {filename}")
                    except Exception as e:
                        app.logger.error(f"Error saving or reading uploaded file {filename}: {e}")
                        return jsonify({"error": f"處理上傳檔案時發生錯誤: {e}"}), 500
                else:
                    app.logger.warning(f"Uploaded file {filename} is not a .txt file.")
                    # Decide how to handle non-txt files if input_text was also empty.
                    # For now, if it's not a .txt and input_text was empty, it would have already returned above.
                    # If input_text had content, this non-txt file is ignored.

            # Final check if input_text (possibly from file) is now empty
            if not input_text.strip():
                app.logger.info("After potential file read, input_text is still empty.")
                return jsonify({"result": "請輸入文章內容或上傳檔案。"})

            try:
                app.logger.info(f"Processing text for user {user_email}. Text length: {len(input_text)}")
                analysis_result_data = asyncio.run(process_text(input_text, user_email))
                #session['last_analysis_html'] = analysis_result_data['html_for_result_tab']
                #session['last_analysis_pdf_path'] = analysis_result_data['pdf_url']
                return jsonify({
                    "html_for_result_tab": analysis_result_data.get("html_for_result_tab"),
                    "html_for_quill_editor": analysis_result_data.get("html_for_quill_editor"),
                    'pdf_url': analysis_result_data.get('pdf_url') # 假設 pdf_url 是正確的
                    #"result": analysis_result_data['html_for_result_tab'],
                    #'pdf_url': url_for('download_specific_pdf', filename=os.path.basename(analysis_result_data['pdf_path']))
                })
            except Exception as e:
                app.logger.error(f"Error during processing text for user {user_email}: {e}", exc_info=True)
                return jsonify({"error": f"分析處理過程中發生錯誤: {e}"}), 500

    else: # --- GET Request Logic ---
        history_data_for_template = []
        if user_logged_in:
            app.logger.info(f"GET request to / by user: {user_email}. Fetching history.")
            try:
                query_execution_result = supabase.from_('analysis_history').select('*').eq('user_email', user_email).order('created_at', desc=True).execute()
                if query_execution_result.data:
                    raw_history_data = query_execution_result.data
                    for record in raw_history_data:
                        if record.get('created_at') and isinstance(record['created_at'], str):
                            try:
                                record['created_at'] = parser.parse(record['created_at'])
                            except (parser.ParserError, ValueError):
                                app.logger.warning(f"Could not parse created_at string: {record['created_at']}")
                        elif not record.get('created_at'):
                            record['created_at'] = None
                        history_data_for_template.append(record)
                else:
                    if hasattr(query_execution_result, 'error') and query_execution_result.error:
                        app.logger.error(f"Error fetching history for {user_email}: {query_execution_result.error}")

            except Exception as e:
                app.logger.error(f"Exception fetching history for {user_email}: {e}", exc_info=True)
        
        return render_template("index.html",
                               user_logged_in=user_logged_in,
                               user_email=user_email,
                               history_data=history_data_for_template)


@app.route("/history") # This route might now be redundant
def history_page_explicit(): # Renamed to avoid conflict if you merge
    if 'user_email' not in session:
        return redirect(url_for('login'))

    user_email = session['user_email']
    processed_history_data = []
    # ... (same history fetching logic as in index GET) ...
    try:
        query_response = supabase.from_('analysis_history').select('*').eq('user_email', user_email).order('created_at', desc=True).execute()
        raw_history_data = []
        if hasattr(query_response, 'data') and query_response.data is not None:
            raw_history_data = query_response.data
        # ... (rest of Supabase version handling and date parsing) ...
        for record in raw_history_data:
            if record.get('created_at') and isinstance(record['created_at'], str):
                try:
                    record['created_at'] = parser.parse(record['created_at'])
                except (parser.ParserError, ValueError):
                    print(f"Warning: Could not parse created_at string: {record['created_at']}")
            elif not record.get('created_at'):
                record['created_at'] = None
            processed_history_data.append(record)
    except Exception as e:
        print(f"查詢歷史紀錄時發生異常: {e}")
    
    # Render index.html, which will now always display history if available
    return render_template("index.html", 
                           history_data=processed_history_data, 
                           user_email=user_email, 
                           user_logged_in=True)

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        error = None

        try:
            # 首先嘗試登入
            auth_response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
            if auth_response.user:
                session['user_id'] = str(auth_response.user.id)
                session['user_email'] = auth_response.user.email
                print(f"User {auth_response.user.email} logged in. Flask session set.")
                return redirect(url_for('index')) # 登入成功後跳轉到主頁
            # ... 其他 supabase-py 版本兼容性寫法 ...
        except Exception as e_signin:
            # 檢查是否是 "Invalid login credentials" 之類的錯誤，如果是，則可能是新用戶或密碼錯誤
            # Supabase 通常對不存在的用戶登入和密碼錯誤返回相同的通用錯誤
            print(f"Sign-in attempt failed for {email}: {e_signin}")
            # 嘗試註冊 (如果登入失敗)
            try:
                auth_response_signup = supabase.auth.sign_up({'email': email, 'password': password})
                if auth_response_signup.user:
                    session['user_id'] = str(auth_response_signup.user.id)
                    session['user_email'] = auth_response_signup.user.email
                    print(f"User {auth_response_signup.user.email} signed up. Flask session set.")
                    # 新註冊用戶可能需要郵件驗證，這裡假設自動確認或後續處理
                    return redirect(url_for('index')) # 註冊成功後跳轉到主頁
                # ... 其他 supabase-py 版本兼容性寫法 ...
            except Exception as e_signup:
                # 如果註冊也失敗 (例如，因為 email 格式不對，或 Supabase 端其他驗證)
                # 或者，如果 sign_in 失敗是因為密碼錯誤（用戶已存在），sign_up 會報用戶已存在
                # 需要更細緻的錯誤判斷來給出友好提示
                if "User already registered" in str(e_signup): # 捕獲用戶已存在錯誤
                    error = "此電子郵件已被註冊，請檢查您的密碼是否正確或嘗試直接登入。"
                else:
                    error = f"登入或註冊失敗: {e_signup}"
                print(f"Sign-up attempt failed for {email}: {e_signup}")
        
        # 如果執行到這裡，表示登入和註冊都未成功跳轉
        return render_template('login.html', error=error or "登入或註冊時發生未知錯誤")

    # GET 請求，正常顯示登入頁面
    # 如果用戶已登入 (Flask session 中有 user_email)，可以選擇直接跳轉到首頁
    if 'user_email' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    session.pop('user_id', None)
    session.clear() # 更徹底地清除 session
    # 可選: 如果你還想通知 Supabase JS SDK 清除客戶端 token
    # (通常在客戶端點擊登出按鈕時，如果按鈕同時觸發了 supabase.auth.signOut() 和跳轉到 Flask /logout，則這裡不需要)
    print("User logged out. Flask session cleared.")
    return redirect(url_for('login')) # 或跳轉到主頁

from bs4 import BeautifulSoup # 確保已安裝 pip install beautifulsoup4

# HTML_TEMPLATE 和 SECTION_TEMPLATE 保持你提供的版本 (帶 .pdf-report-view 前綴)

# generate_html_report 函數也保持你提供的版本，它返回完整的 HTML 字符串

def extract_quill_content_from_full_html(full_html_string):
    """
    從完整的 HTML 報告字符串中提取 <div class="pdf-report-view"> 的 innerHTML。
    """
    if not full_html_string:
        return ""
    try:
        soup = BeautifulSoup(full_html_string, 'html.parser')
        report_view_div = soup.find('div', class_='pdf-report-view')
        if report_view_div:
            return report_view_div.decode_contents() # 返回 div 內部的 HTML
        else:
            # 如果找不到 .pdf-report-view，嘗試從 body 提取（作為後備）
            body_tag = soup.body
            if body_tag:
                print("警告: 未在完整HTML中找到 'div.pdf-report-view'，嘗試返回 body 內容給 Quill。")
                return body_tag.decode_contents()
            print("警告: 未在完整HTML中找到 'div.pdf-report-view' 或 body 標籤。")
            return "" # 或者返回 full_html_string 本身讓前端調試
    except Exception as e:
        print(f"從完整HTML提取Quill內容時發生錯誤: {e}")
        return "" # 或者 full_html_string

async def process_text(text_content, user_email):
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        # 可以在這裡返回一個錯誤訊息或拋出異常，讓上層處理
        # return {"error": "請設定環境變數 GEMINI_API_KEY"}
        raise ValueError("請設定環境變數 GEMINI_API_KEY")

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")

    print("正在分析文章內容...")
    analysis_text_from_gemini = await analyze_text(text_content, model) # 改個名字以區分

    print("正在生成範例文章...")
    sample_article_text = await generate_sample_article(text_content, model)

    if not analysis_text_from_gemini or (isinstance(analysis_text_from_gemini, str) and "無法取得回應" in analysis_text_from_gemini):
        print("分析失敗，無法產生回應。")
        # return {"error": "Gemini 分析失敗"}
        raise Exception("Gemini 分析文章失敗") # 或者返回具體的錯誤信息
    
    if not sample_article_text or (isinstance(sample_article_text, str) and "無法取得範例文章" in sample_article_text):
        print("範例文章生成失敗。")
        # 可以選擇是否中止，或者繼續產生沒有範例文章的報告
        # sample_article_text = "範例文章生成失敗。" # 給一個預設值


    # 1. 生成完整的 HTML (用於 PDF 和 #result div 的直接顯示)
    full_html_content = generate_html_report(analysis_text_from_gemini, sample_article_text)

    # 2. 從完整 HTML 中提取核心內容給 Quill
    core_html_for_quill = extract_quill_content_from_full_html(full_html_content)
    if not core_html_for_quill:
         print(f"警告:未能從新分析的完整HTML中提取Quill的核心內容。完整HTML:{full_html_content[:300]}...")

    timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
    base_filename = f"analysis_result_{timestamp_str}"
    # ⭐ pdf_output_path 現在在這裡定義
    pdf_output_path = os.path.join(app.config.get('STATIC_DOWNLOADS_FOLDER', os.path.join(app.root_path, 'static', 'downloads')), f"{base_filename}.pdf")
    # 確保目錄存在 (雖然下面轉 PDF 前也會做，但提前做無害)
    os.makedirs(os.path.dirname(pdf_output_path), exist_ok=True)

    # 儲存到 Supabase (儲存原始分析文字，不含範例文章)
    try:
        pdf_filename_for_db = os.path.basename(pdf_output_path)
        insert_data = {
            'user_email': user_email,
            'original_text': text_content,
            'analysis_result': analysis_text_from_gemini, # Gemini's core analysis
            'report_html': full_html_content, # <<<< ADD THIS
            'pdf_filename': os.path.basename(pdf_output_path)
            
        }
        
        # Supabase v2+ style
        response = supabase.from_('analysis_history').insert(insert_data).execute()
        if response.data:
             print("資料已儲存到 Supabase (including report_html)")
        else: # Check for error in v2, though error might raise exception
             if hasattr(response, 'error') and response.error: # More explicit error check for v2
                print(f"儲存資料到 Supabase 失敗: {response.error}")
             else: # Fallback for older client or unexpected response
                print(f"儲存資料到 Supabase 可能失敗或無返回資料。Response: {response}")

    except Exception as e:
        import sys
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(f"儲存資料到 Supabase 時發生異常: {e} (在文件 {fname} 的第 {exc_tb.tb_lineno} 行)")
        # 這裡可以決定是否因為DB儲存失敗而中斷整個請求

    try:
        # pdfkit.from_file(html_output_path, pdf_output_path, configuration=pdfkit_config)
        # 直接從字串生成，避免寫入臨時HTML檔案
        options = {
            'encoding': "UTF-8",
            'enable-local-file-access': None # 如果HTML中有本地資源（CSS, JS, 圖片）需要此選項
        }
        pdfkit.from_string(full_html_content, pdf_output_path, configuration=pdfkit_config, options=options)
        print(f"已將分析結果轉換成PDF: {pdf_output_path}")
    except Exception as e:
        print(f"PDF生成失敗: {e}")
        # return {"error": f"PDF生成失敗: {e}", "html_content": html_content_for_display_and_pdf} # 返回HTML，即使PDF失敗
        raise Exception(f"PDF 生成失敗: {e}")


    return {
        "html_for_result_tab": full_html_content,    # ⭐ 給 #result div
        "html_for_quill_editor": core_html_for_quill, # ⭐ 給 Quill
        "pdf_url": url_for('download_specific_pdf', filename=os.path.basename(pdf_output_path))
    }

# 新的下載路由，接受檔名作為參數
@app.route("/download_pdf/<filename>")
def download_specific_pdf(filename):
    # 安全性：確保 filename 不包含路徑遍歷字符 ('../', '/')
    # secure_filename 適用於上傳，這裡需要自己檢查或確保傳入的 filename 是安全的
    if ".." in filename or "/" in filename:
        return "無效的檔案名", 400
    
    pdf_path = os.path.join(app.config['STATIC_DOWNLOADS_FOLDER'], filename) # 假設你定義了這個配置
    # 或者直接用 "static/downloads"
    # pdf_path = os.path.join("static", "downloads", filename)

    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True)
    else:
        return "PDF檔案不存在。", 404

# 你需要在 Flask app config 中定義這個路徑
app.config['STATIC_DOWNLOADS_FOLDER'] = os.path.join(app.root_path, 'static', 'downloads')
# 並確保該資料夾存在
os.makedirs(app.config['STATIC_DOWNLOADS_FOLDER'], exist_ok=True)

@app.route("/upload_txt", methods=["POST"])
def upload_txt():
    uploaded_file = request.files.get("file")
    if uploaded_file and uploaded_file.filename.endswith(".txt"):
        content = uploaded_file.read().decode("utf-8")
        return jsonify({"content": content})
    return jsonify({"error": "請上傳.txt格式檔案"}), 400

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    if 'user_email' not in session: # <--- 檢查 Flask session (可選，取決於此功能是否需登入)
        return jsonify({"error": "請先登入後操作", "login_required": True}), 401

    data = request.get_json()
    html_content_from_quill = data.get("content") # 這是從 Quill 來的 HTML

    if not html_content_from_quill:
        return jsonify({"error": "缺少 HTML 內容"}), 400

    # 這裡的 HTML_TEMPLATE 包含了完整的 head 和 body
    # 而 Quill 的內容通常是 body 內部的一段 HTML
    # 你需要決定如何組合。是直接用 Quill 的內容，還是將它嵌入到你的標準模板中。

    # 方案A: 直接使用 Quill 的內容，並加上必要的元數據和樣式 (如你目前所做)
    # 加入中文字型與 UTF-8 編碼設定
    final_html_for_pdf = f"""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="utf-8">
        <title>編輯後的分析報告</title> <!-- 可以加個標題 -->
        <style>
            body {{
                font-family: "Times New Roman", "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", "SimHei", serif; /* 優先使用 Times New Roman */
                margin: 50px;
                line-height: 1.8;
                font-size: 16px;
            }}
            /* 可以從 HTML_TEMPLATE 複製更多樣式過來，如果需要的話 */
            h1 {{ text-align: center; font-size: 28px; margin-bottom: 40px; }}
            h2 {{ font-size: 22px; color: #2c3e50; margin-top: 30px; margin-bottom: 10px; }}
            .highlight {{ color: red; font-weight: bold; }}
            p {{ text-indent: 2em; margin-top: 10px; }}
        </style>
    </head>
    <body>
    {html_content_from_quill}
    </body>
    </html>
    """

    options = {
        'encoding': "UTF-8",
        'enable-local-file-access': None, # 如果 Quill 內容有引用本地圖片等
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
    }

    try:
        # 使用 tempfile 來創建臨時 PDF 檔案更安全，它會自動處理刪除
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix="analysis_edit_") as tmp_pdf:
            pdf_path = tmp_pdf.name
        
        pdfkit.from_string(final_html_for_pdf, pdf_path, options=options, configuration=pdfkit_config)
        
        # send_file 會在響應結束後嘗試刪除文件，如果 delete=False 的 NamedTemporaryFile 由它管理
        # 但為了確保刪除，最好手動刪除或使用 delete=True 並在 finally 中關閉
        # return send_file(pdf_path, as_attachment=True, download_name="analysis_edited_result.pdf")
        # 為了確保能正確刪除臨時檔案，可以這樣做：
        response = send_file(pdf_path, as_attachment=True, download_name="analysis_edited_result.pdf")
        # os.remove(pdf_path) # 如果send_file不能可靠刪除NamedTemporaryFile(delete=False)創建的檔案
        return response

    except Exception as e:
        # 如果生成失敗，也要確保刪除臨時檔案（如果已創建）
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            os.remove(pdf_path)
        return jsonify({"error": f"編輯後 PDF 生成失敗: {e}"}), 500


@app.route("/get_history_item/<string:item_id>", methods=["GET"])
def get_history_item(item_id):
    if 'user_email' not in session:
        app.logger.warning(f"Unauthorized attempt to access history item {item_id}") # Use app.logger
        return jsonify({"error": "Not authenticated"}), 401

    user_email = session['user_email']
    app.logger.info(f"User {user_email} requesting history item {item_id}")

    try:
        # Ensure the item belongs to the logged-in user for security
        # Using single() is good. It will error if not exactly one row.
        #response = supabase.from_('analysis_history').select('id, original_text, report_html').eq('id', item_id).eq('user_email', user_email).single().execute()
        response = supabase.from_('analysis_history').select('id, original_text, report_html', 'pdf_filename').eq('id', item_id).eq('user_email', user_email).single().execute()
        # For supabase-py v2+, response.data should be the way
        record_data = response.data 
        app.logger.debug(f"Supabase response for item {item_id}: {response}") # Log the whole response for inspection

        if record_data:
            full_html_from_db = record_data.get("report_html") # 從DB獲取完整HTML
            core_html_for_quill_history = extract_quill_content_from_full_html(full_html_from_db)
            # 假設我們為歷史記錄也構建或獲取 pdf_url (這部分需要你根據實際情況實現)
            pdf_url_for_history = None
            example_filename_from_db = record_data.get("pdf_filename") # 如果你在DB存了檔名
            if example_filename_from_db:
                pdf_url_for_history = url_for('download_specific_pdf', filename=example_filename_from_db)
            
            if not core_html_for_quill_history:
                print(f"警告:未能從歷史記錄 (ID:{item_id}) 的完整HTML中提取Quill的核心內容。完整HTML:{full_html_from_db[:300]}...")

            app.logger.info(f"Found history item {item_id} for user {user_email}. Original text length: {len(record_data.get('original_text', ''))}, Report HTML length: {len(record_data.get('report_html', ''))}")
            return jsonify({
                "original_text": record_data.get("original_text"),
                "html_for_result_tab": full_html_from_db,       # ⭐ 給 #result div
                "html_for_quill_editor": core_html_for_quill_history, # ⭐ 給 Quill
                "pdf_url": pdf_url_for_history # ⭐ 如果歷史記錄也支持下載原始 PDF
                #"analysis_result_html": record_data.get("report_html"), # This should now have the full HTML
                # "pdf_url": "..." # If you decide to store and retrieve PDF path/URL
            })
        else:
            # This else might not be reached if .single() errors out on no data,
            # but good as a fallback.
            app.logger.warning(f"History item {item_id} not found for user {user_email} or no data in response.")
            return jsonify({"error": "Item not found or access denied"}), 404
            
    except Exception as e:
        
        app.logger.error(f"Error fetching history item {item_id} for user {user_email}: {e}", exc_info=True) # exc_info=True logs traceback
        
        # A more generic check for "no rows found" type errors from PostgREST if .single() was not used or error is different
        if "PGRST116" in str(e) or "PGRST204" in str(e): # PGRST116 (single row not found), PGRST204 (no content, for non-single queries)
             app.logger.warning(f"History item {item_id} likely not found due to PostgREST error: {e}")
             return jsonify({"error": "Item not found"}), 404
        return jsonify({"error": "Server error while fetching history item"}), 500

@app.route("/delete_history_item/<string:item_id>", methods=["DELETE"]) # 使用 DELETE HTTP 方法更符合 RESTful 風格
def delete_history_item_route(item_id): # 函數名與之前的 get_history_item 區分
    if 'user_email' not in session:
        app.logger.warning(f"Unauthorized DELETE attempt for history item {item_id} - User not logged in.")
        return jsonify({"success": False, "error": "使用者未認證，請先登入。"}), 401

    user_email = session['user_email']
    app.logger.info(f"User '{user_email}' attempting to delete history item ID: {item_id}")

    try:
        # 執行刪除操作，確保只刪除屬於該用戶的記錄
        response = supabase.from_('analysis_history') \
                           .delete() \
                           .eq('id', item_id) \
                           .eq('user_email', user_email) \
                           .execute()

        # 檢查 Supabase 返回的響應
        # supabase-py v2+ delete 操作成功時，data 可能是個列表 (包含被刪除的記錄)，或者為空
        # 如果記錄不存在或不屬於該用戶，則 data 可能為空，且 count 為 0 (如果可用)
        
        app.logger.debug(f"Supabase delete response for item {item_id}: {response}")

        if hasattr(response, 'error') and response.error:
            app.logger.error(f"Supabase error deleting history item {item_id} for user {user_email}: {response.error}")
            return jsonify({"success": False, "error": "刪除歷史紀錄時發生資料庫錯誤。"}), 500
        
        # 檢查是否真的有記錄被刪除
        # Supabase delete 通常在成功時 data 是一個包含被刪除記錄的列表（即使只有一條）
        # 如果沒有匹配的記錄被刪除，data 可能是空列表
        if response.data: # 或者檢查 response.count (如果適用)
            app.logger.info(f"Successfully deleted history item {item_id} for user {user_email}.")
            return jsonify({"success": True, "message": "歷史紀錄已成功刪除。"}), 200
        else:
            app.logger.warning(f"History item {item_id} not found or not owned by user {user_email} for deletion.")
            # 即使記錄不存在，從客戶端角度看，操作也算“完成”了，只是沒有實際刪除
            # 可以返回成功，或者返回一個特定的“未找到”狀態
            return jsonify({"success": False, "error": "找不到要刪除的歷史紀錄，或您沒有權限。"}), 404

    except Exception as e:
        app.logger.error(f"Exception deleting history item {item_id} for user {user_email}: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"刪除歷史紀錄時發生伺服器內部錯誤: {str(e)}"}), 500

# 啟動Flask
if __name__ == "__main__":
    generated_html_content = None  # 初始化全域變數
    app.run(debug=True)
