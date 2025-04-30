import os
import asyncio
import html
from datetime import datetime
import pdfkit
import webbrowser
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import tempfile


# Google Gemini
import google.generativeai as genai


# 初始化Flask
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# 確保上傳資料夾存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 載入.env
load_dotenv()

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
    global generated_html_content

    if request.method == "POST":
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

        analysis_html = asyncio.run(process_text(input_text))
        generated_html_content = analysis_html  # 記錄給下載用
        return jsonify({
            "result": analysis_html,
            'pdf_url':'/static/downloads/analysis_result.pdf'})

    return render_template("index.html")

# 分析並生成報告
async def process_text(text_content):
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("請設定環境變數 GEMINI_API_KEY")

    genai.configure(api_key=gemini_api_key)

    model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")

    print("正在分析文章內容...")
    analysis_text = await analyze_text(text_content, model)

    print("正在生成範例文章...")
    sample_article_text = await generate_sample_article(text_content, model)
    

    if not analysis_text or not sample_article_text:
        print("分析失敗，無法產生回應。")
        return

    html_content = generate_html_report(analysis_text, sample_article_text)
    
    # 儲存HTML
    html_output_path = os.path.join("static", "downloads", "analysis_result.html")
    os.makedirs(os.path.dirname(html_output_path), exist_ok=True)
    with open(html_output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"已將分析結果儲存為HTML: {html_output_path}")

    # 轉成PDF
    pdf_output_path = os.path.join("static", "downloads", "analysis_result.pdf")
    pdfkit.from_file(html_output_path, pdf_output_path, configuration=pdfkit_config)
    print(f"已將分析結果轉換成PDF: {pdf_output_path}")
    
    return html_content

@app.route("/download_pdf")
def download_pdf():
    pdf_path = os.path.join("static", "downloads", "analysis_result.pdf")
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True)
    else:
        return "PDF檔案不存在，請先生成報告。", 404

@app.route("/upload_txt", methods=["POST"])
def upload_txt():
    uploaded_file = request.files.get("file")
    if uploaded_file and uploaded_file.filename.endswith(".txt"):
        content = uploaded_file.read().decode("utf-8")
        return jsonify({"content": content})
    return jsonify({"error": "請上傳.txt格式檔案"}), 400

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    data = request.get_json()
    html_content = data.get("content")

    if not html_content:
        return jsonify({"error": "缺少 HTML 內容"}), 400

    # 加入中文字型與 UTF-8 編碼設定
    html_content = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", "SimHei", sans-serif;
            }}
        </style>
    </head>
    <body>
    {html_content}
    </body>
    </html>
    """

    options = {
        'encoding': "UTF-8",
        'enable-local-file-access': None
    }

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf_path = tmp_pdf.name
        try:
            pdfkit.from_string(html_content, pdf_path, options=options, configuration=pdfkit_config)
        except Exception as e:
            return jsonify({"error": f"PDF 生成失敗: {e}"}), 500

    return send_file(pdf_path, as_attachment=True, download_name="analysis_editresult.pdf")


# 啟動Flask
if __name__ == "__main__":
    generated_html_content = None  # 初始化全域變數
    app.run(debug=True)
