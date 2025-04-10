import os
from datetime import datetime
import gradio as gr
import pandas as pd
from dotenv import load_dotenv
from fpdf import FPDF
from google import genai
import pdfkit
from jinja2 import Template

# 載入環境變數並設定 API 金鑰
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# 路徑需自行更改
WKHTMLTOPDF_PATH=r"D:\Programmed Files\Python\TEST\wkhtmltox\bin\wkhtmltopdf.exe"

config=pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

# 定義 HTML 模板
html_template = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DataFrame PDF</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin: 20px; }
        .table { width: 80%; margin: auto; border-collapse: collapse; }
        .table th, .table td { border: 1px solid black; padding: 8px; text-align: center; }
        .table th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h2>PDF 生成</h2>
    {{ table | safe }}
</body>
</html>
"""


def get_chinese_font_file() -> str:
    """
    只檢查 Windows 系統字型資料夾中是否存在候選中文字型（TTF 格式）。
    若找到則回傳完整路徑；否則回傳 None。
    """
    fonts_path = r"C:\Windows\Fonts"
    candidates = ["kaiu.ttf"]  # 這裡以楷體為例，可依需要修改
    for font in candidates:
        font_path = os.path.join(fonts_path, font)
        if os.path.exists(font_path):
            print("找到系統中文字型：", font_path)
            return os.path.abspath(font_path)
    print("未在系統中找到候選中文字型檔案。")
    return None

def create_table(df: pd.DataFrame):
    return df.to_html(index=False,classes="table table-bordered")


def parse_markdown_table(markdown_text: str) -> pd.DataFrame:
    """
    從 Markdown 格式的表格文字提取資料，返回一個 pandas DataFrame。
    例如，輸入：
      | start | end | text | 分類 |
      |-------|-----|------|------|
      | 00:00 | 00:01 | 開始拍攝喔 | 備註 |
    會返回包含該資料的 DataFrame。
    """
    lines = markdown_text.strip().splitlines()
    # 過濾掉空行
    lines = [line.strip() for line in lines if line.strip()]
    # 找到包含 '|' 的行，假設這就是表格
    table_lines = [line for line in lines if line.startswith("|")]
    if not table_lines:
        return None
    # 忽略第二行（分隔線）
    header_line = table_lines[0]
    headers = [h.strip() for h in header_line.strip("|").split("|")]
    data = []
    for line in table_lines[2:]:
        row = [cell.strip() for cell in line.strip("|").split("|")]
        if len(row) == len(headers):
            data.append(row)
    df = pd.DataFrame(data, columns=headers)
    return df

#HW4 以HTML生成PDF
def generate_pdf(text: str = None, df: pd.DataFrame = None) -> str:

    print("開始生成 PDF")
    html_table=""
    if df is not None:
        create_table(df)
    elif text is not None:
        # 嘗試檢查 text 是否包含 Markdown 表格格式
        if "|" in text:
            # 找出可能的表格部分（假設從第一個 '|' 開始到最後一個 '|'）
            table_part = "\n".join([line for line in text.splitlines() if line.strip().startswith("|")])
            parsed_df = parse_markdown_table(table_part)
            if parsed_df is not None:
                html_table=create_table(parsed_df)
            else:
                pdf.multi_cell(0, 10, text)
        else:
            pdf.multi_cell(0, 10, text)
    else:
        pdf.cell(0, 10, "沒有可呈現的內容")


    template=Template(html_template)
    html_content=template.render(table=html_table)
    
    pdf_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    html_file="output.html"
    with open(html_file, "w", encoding="utf-8") as file:
        file.write(html_content)
    print("輸出 PDF 至檔案：", pdf_filename)
    pdfkit.from_file("output.html", pdf_filename, verbose=True, configuration=config, options={"enable-local-file-access": True})
    print("PDF 生成完成")
    return pdf_filename

def gradio_handler(csv_file, user_prompt):
    print("進入 gradio_handler")
    if csv_file is not None:
        print("讀取 CSV 檔案")
        df = pd.read_csv(csv_file.name)
        total_rows = df.shape[0]
        block_size = 30
        cumulative_response = ""
        block_responses = []
        # 依區塊處理 CSV 並依每區塊呼叫 LLM 產生報表分析結果
        for i in range(0, total_rows, block_size):
            block = df.iloc[i:i+block_size]
            block_csv = block.to_csv(index=False)
            prompt = (f"以下是CSV資料第 {i+1} 到 {min(i+block_size, total_rows)} 筆：\n"
                      f"{block_csv}\n\n請根據以下規則進行分析並產出報表：\n{user_prompt}")
            print("完整 prompt for block:")
            print(prompt)
            response = client.models.generate_content(
                model="gemini-2.5-pro-exp-03-25",
                contents=[prompt]
            )
            block_response = response.text.strip()
            cumulative_response += f"區塊 {i//block_size+1}:\n{block_response}\n\n"
            block_responses.append(cumulative_response)
            # 可考慮 yield 逐步更新（此處示範最終一次回傳）
        # 將所有區塊回應合併，並生成漂亮表格 PDF
        pdf_path = generate_pdf(text=cumulative_response)
        return cumulative_response, pdf_path
    else:
        context = "未上傳 CSV 檔案。"
        full_prompt = f"{context}\n\n{user_prompt}"
        print("完整 prompt：")
        print(full_prompt)
    
        response = client.models.generate_content(
            model="gemini-2.5-pro-exp-03-25",
            contents=[full_prompt]
        )
        response_text = response.text.strip()
        print("AI 回應：")
        print(response_text)
    
        pdf_path = generate_pdf(text=response_text)
        return response_text, pdf_path

#HW2 的prompt、csv讀入
default_prompt = """請分析以下日記中每一句話的出現的情緒，進行分類：

"快樂",
"難過",
"害怕",
"憤怒",
"愛",
"驚喜",
"備註"

請依據評估結果，對每個項目：若有觸及則標記為 1，否則留空。
最後請在備註欄為這句話下總結，
每一句請依照以下Markdown格式回應：
| 編號 | Text | 快樂 | 難過 | 害怕 | 憤怒 | 愛 | 驚喜 | 備註 |
並將所有類別進行統計、產出報表：
"""

with gr.Blocks() as demo:
    gr.Markdown("# CSV 報表生成器")
    with gr.Row():
        csv_input = gr.File(label="上傳 CSV 檔案")
        user_input = gr.Textbox(label="請輸入分析指令", lines=10, value=default_prompt)
    output_text = gr.Textbox(label="回應內容", interactive=False)
    output_pdf = gr.File(label="下載 PDF 報表")
    submit_button = gr.Button("生成報表")
    submit_button.click(fn=gradio_handler, inputs=[csv_input, user_input],
                        outputs=[output_text, output_pdf])

demo.launch()