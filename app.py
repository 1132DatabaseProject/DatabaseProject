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
    body {{
        font-family: "Times New Roman", serif;
        margin: 50px;
        line-height: 1.8;
        font-size: 16px;
    }}
    h1 {{
        text-align: center;
        font-size: 28px;
        margin-bottom: 40px;
    }}
    h2 {{
        font-size: 22px;
        color: #2c3e50;
        margin-top: 30px;
        margin-bottom: 10px;
    }}
    .timestamp {{
        text-align: right;
        font-size: 12px;
        color: gray;
        margin-bottom: 30px;
    }}
    .highlight {{
        color: red;
        font-weight: bold;
    }}
    p {{
        text-indent: 2em;
        margin-top: 10px;
    }}
    .error-block {{
        margin-top: 10px;
    }}
</style>
</head>
<body>
<h1>英文寫作分析報告</h1>
<div class="timestamp">生成時間：{timestamp}</div>
{content}
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
    #global generated_html_content
    user_logged_in = 'user_email' in session
    user_email = session.get('user_email')

    if request.method == "POST":
        if not user_logged_in: # <--- 檢查 Flask session
            # 如果前端期望JSON回應來處理未登入狀態
            return jsonify({"error": "請先登入", "login_required": True}), 401 # 401 Unauthorized

        user_email = session['user_email'] # <--- 從 Flask session 獲取

        input_text = request.form.get("text_content", "")
        uploaded_file = request.files.get("file")

        if uploaded_file and uploaded_file.filename.endswith(".txt"):
            filename = secure_filename(uploaded_file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                input_text = f.read()

        if not input_text.strip():
            return jsonify({"result": "請輸入文章內容或上傳檔案。"})

        try:
            # 將 generated_html_content 的處理移到 process_text 內部或返回值中
            analysis_result_data = asyncio.run(process_text(input_text, user_email))

            # 為了讓前端可以下載PDF，我們仍然需要一個可訪問的PDF路徑
            # generated_html_content = analysis_result_data['html_content'] # 如果需要全域訪問，考慮 session
            session['last_analysis_html'] = analysis_result_data['html_content'] # 儲存到 session
            session['last_analysis_pdf_path'] = analysis_result_data['pdf_path'] # 儲存到 session

            return jsonify({
                "result": analysis_result_data['html_content'], # 直接顯示的HTML
                'pdf_url': url_for('download_specific_pdf', filename=os.path.basename(analysis_result_data['pdf_path'])) # 動態生成下載連結
            })
        except Exception as e:
            print(f"Error during processing text: {e}")
            return jsonify({"error": f"分析處理過程中發生錯誤: {e}"}), 500

    # GET 請求時，檢查用戶是否登入，以在模板中顯示不同內容 (例如，顯示/隱藏登入按鈕)
    user_logged_in = 'user_email' in session
    user_email = session.get('user_email')
    return render_template("index.html", user_logged_in=user_logged_in, user_email=user_email)



#@app.route('/login',methods=["GET", "POST"])
#def login():
#    if request.method == 'POST':
#        email = request.form.get('email')
#        password = request.form.get('password')
#        error = None # 初始化錯誤訊息
#
#        try:
#            # 首先嘗試登入
#            auth_response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
#            if auth_response.user: # Supabase-py v1.x
#                session['user_id'] = str(auth_response.user.id) # 儲存 user_id 更佳
#                session['user_email'] = auth_response.user.email
#                print(f"User {auth_response.user.email} logged in. Flask session set.")
#                return redirect('/')
#        except Exception as e:
#            # 如果登入失敗，嘗試註冊 (注意：這裡的錯誤處理比較簡化，實際應用可能需要更細緻的判斷)
#            # Supabase API 通常會對已存在的用戶註冊返回特定錯誤，可以捕捉並提示用戶登入
#            print(f"Sign-in attempt failed for {email}: {e}")
#            try:
#                auth_response = supabase.auth.sign_up({'email': email, 'password': password})
#                if auth_response.user: # Supabase-py v1.x
#                    session['user_id'] = str(auth_response.user.id)
#                    session['user_email'] = auth_response.user.email
#                    # 注意：新註冊用戶可能需要郵件驗證，這裡假設自動確認或後續處理
#                    print(f"User {auth_response.user.email} signed up. Flask session set.")
#                    return redirect('/')
#
#            except Exception as e_signup:
#                error = f"登入或註冊失敗: {e_signup}" # 提供一個統一的錯誤信息
#                print(f"Sign-up attempt failed for {email}: {e_signup}")
#        return render_template('login.html', error=error)
#    
#    return render_template('login.html')

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

# 分析並生成報告
#async def process_text(text_content, user_email):
#    gemini_api_key = os.environ.get("GEMINI_API_KEY")
#    if not gemini_api_key:
#        raise ValueError("請設定環境變數 GEMINI_API_KEY")
#
#    genai.configure(api_key=gemini_api_key)
#
#    model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")
#
#    print("正在分析文章內容...")
#    analysis_text = await analyze_text(text_content, model)
#
#    print("正在生成範例文章...")
#    sample_article_text = await generate_sample_article(text_content, model)
#    
#
#    if not analysis_text or not sample_article_text:
#        print("分析失敗，無法產生回應。")
#        return
#
#    html_content = generate_html_report(analysis_text, sample_article_text)
#    
#     # 儲存到 Supabase
#    try:
#        data = supabase.from_('analysis_history').insert([
#            {'user_email': user_email, 'original_text': text_content, 'analysis_result': analysis_text}
#        ]).execute()
#        print("資料已儲存到 Supabase")
#    except Exception as e:
#        print(f"儲存資料到 Supabase 失敗: {e}")
#
#    # 儲存HTML
#    html_output_path = os.path.join("static", "downloads", "analysis_result.html")
#    os.makedirs(os.path.dirname(html_output_path), exist_ok=True)
#    with open(html_output_path, "w", encoding="utf-8") as f:
#        f.write(html_content)
#    print(f"已將分析結果儲存為HTML: {html_output_path}")
#
#    # 轉成PDF
#    pdf_output_path = os.path.join("static", "downloads", "analysis_result.pdf")
#    pdfkit.from_file(html_output_path, pdf_output_path, configuration=pdfkit_config)
#    print(f"已將分析結果轉換成PDF: {pdf_output_path}")
#
#    return html_content

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


    # 注意: 你的 analysis_history 表儲存的是 analysis_result TEXT NOT NULL
    # 這裡的 analysis_text_from_gemini 是 Gemini 的原始回應，可能不是最終的 HTML
    # 你需要決定儲存到資料庫的是 Gemini 的原始分析文字，還是處理過的 HTML
    # 假設我們儲存 Gemini 的原始分析文字 (不含範例文章和 HTML 結構)
    # 如果要儲存完整報告的HTML，則 analysis_result 欄位需要改為儲存 html_content

    # 生成 HTML 報告 (包含範例文章)
    html_content_for_display_and_pdf = generate_html_report(analysis_text_from_gemini, sample_article_text)

    # 儲存到 Supabase (儲存原始分析文字，不含範例文章)
    try:
        # 這裡的 analysis_result 應該是 Gemini 的純文字分析結果，而不是完整 HTML
        # 如果你的需求是儲存 Gemini 的原始分析文字，那麼應該是 analysis_text_from_gemini
        # 如果你的需求是儲存整個生成的報告HTML，那麼欄位名可能需要調整，或就用 analysis_result 儲存 html_content_for_display_and_pdf
        # 目前按照你的表結構，analysis_result 應該是 Gemini 的分析結果
        insert_data = {
            'user_email': user_email,
            'original_text': text_content,
            'analysis_result': analysis_text_from_gemini # 儲存 Gemini 的核心分析
        }
        # 如果你也想把範例文章存到資料庫，需要新增欄位
        # 'sample_article': sample_article_text (可選)

        data, error = supabase.from_('analysis_history').insert(insert_data).execute()
        # supabase-py v1.x 返回 (data, error) tuple，需要檢查 error
        # supabase-py v0.x 可能是 response.data / response.error
        if hasattr(data, 'error') and data.error: # 檢查 execute() 的返回是否有 error 屬性 (舊版 SDK)
             print(f"儲存資料到 Supabase 失敗: {data.error}")
        elif isinstance(data, tuple) and len(data) > 1 and data[1]: # 新版 SDK (data, count=None) 或 (data, error=None)
            print(f"儲存資料到 Supabase 失敗: {data[1]}") # data[1] is error
        else:
            print("資料已儲存到 Supabase")

    except Exception as e:
        print(f"儲存資料到 Supabase 時發生異常: {e}")
        # 這裡可以決定是否因為DB儲存失敗而中斷整個請求

    # 為本次請求生成唯一的檔名，避免多人同時使用時覆蓋
    timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
    # 可以考慮加上 user_id 或 session_id 來進一步區分
    # user_specific_id = session.get('user_id', 'anonymous') # 假設 user_id 存在 session
    # base_filename = f"analysis_result_{user_specific_id}_{timestamp_str}"
    base_filename = f"analysis_result_{timestamp_str}"


    # 儲存HTML (這個HTML主要用於生成PDF，也可以考慮直接用html_content_for_display_and_pdf字串生成PDF)
    # html_output_path = os.path.join("static", "downloads", f"{base_filename}.html")
    # os.makedirs(os.path.dirname(html_output_path), exist_ok=True)
    # with open(html_output_path, "w", encoding="utf-8") as f:
    #     f.write(html_content_for_display_and_pdf)
    # print(f"已將分析結果儲存為HTML: {html_output_path}")

    # 轉成PDF
    pdf_output_path = os.path.join("static", "downloads", f"{base_filename}.pdf")
    os.makedirs(os.path.dirname(pdf_output_path), exist_ok=True)
    try:
        # pdfkit.from_file(html_output_path, pdf_output_path, configuration=pdfkit_config)
        # 直接從字串生成，避免寫入臨時HTML檔案
        options = {
            'encoding': "UTF-8",
            'enable-local-file-access': None # 如果HTML中有本地資源（CSS, JS, 圖片）需要此選項
        }
        pdfkit.from_string(html_content_for_display_and_pdf, pdf_output_path, configuration=pdfkit_config, options=options)
        print(f"已將分析結果轉換成PDF: {pdf_output_path}")
    except Exception as e:
        print(f"PDF生成失敗: {e}")
        # return {"error": f"PDF生成失敗: {e}", "html_content": html_content_for_display_and_pdf} # 返回HTML，即使PDF失敗
        raise Exception(f"PDF 生成失敗: {e}")


    return {
        "html_content": html_content_for_display_and_pdf,
        "pdf_path": pdf_output_path # 返回PDF的實際路徑
    }

#@app.route("/download_pdf")
#def download_pdf():
#    pdf_path = os.path.join("static", "downloads", "analysis_result.pdf")
#    if os.path.exists(pdf_path):
#        return send_file(pdf_path, as_attachment=True)
#    else:
#        return "PDF檔案不存在，請先生成報告。", 404

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

#@app.route("/generate_pdf", methods=["POST"])
#def generate_pdf():
#    data = request.get_json()
#    html_content = data.get("content")
#
#    if not html_content:
#        return jsonify({"error": "缺少 HTML 內容"}), 400
#
 #   # 加入中文字型與 UTF-8 編碼設定
#    html_content = f"""
#    <html>
#    <head>
#        <meta charset="utf-8">
#        <style>
#            body {{
#                font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", "SimHei", sans-serif;
#            }}
#        </style>
#    </head>
#    <body>
#    {html_content}
#    </body>
#    </html>
#    """
#
#    options = {
#        'encoding': "UTF-8",
#        'enable-local-file-access': None
#    }
#
#    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
#        pdf_path = tmp_pdf.name
#        try:
#            pdfkit.from_string(html_content, pdf_path, options=options, configuration=pdfkit_config)
#        except Exception as e:
#            return jsonify({"error": f"PDF 生成失敗: {e}"}), 500
#
#    return send_file(pdf_path, as_attachment=True, download_name="analysis_editresult.pdf")

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
    # finally: # 另一種確保刪除的方式
    #     if 'pdf_path' in locals() and os.path.exists(pdf_path):
    #         try:
    #             os.remove(pdf_path)
    #         except Exception as e_remove:
    #             print(f"Error removing temp pdf {pdf_path}: {e_remove}")

@app.route("/history")
def history():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    user_email = session['user_email']
    processed_history_data = [] # 用一個新的列表來存放處理後的數據
    try:
        query_response = supabase.from_('analysis_history').select('*').eq('user_email', user_email).order('created_at', desc=True).execute()
        
        raw_history_data = []
        if hasattr(query_response, 'data'):
            raw_history_data = query_response.data
        elif isinstance(query_response, list):
            raw_history_data = query_response

        for record in raw_history_data:
            if record.get('created_at') and isinstance(record['created_at'], str):
                try:
                    # dateutil.parser 可以很好地處理多種 ISO 8601 格式，包括帶時區的
                    record['created_at'] = parser.parse(record['created_at'])
                except ValueError:
                    # 如果解析失敗，可以選擇給一個預設值或記錄錯誤
                    print(f"Warning: Could not parse created_at string: {record['created_at']}")
                    record['created_at'] = None # 或者保持原樣，讓模板的 else '未知' 生效
            elif not record.get('created_at'): # 如果 created_at 本身就是 None 或空
                record['created_at'] = None

            processed_history_data.append(record)

    except Exception as e:
        print(f"查詢歷史紀錄時發生異常: {e}")
        # processed_history_data 仍然是空的

    return render_template("history.html", history_data=processed_history_data, user_email=user_email, user_logged_in=True)
# 啟動Flask
if __name__ == "__main__":
    generated_html_content = None  # 初始化全域變數
    app.run(debug=True)

