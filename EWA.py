import os
import asyncio
from datetime import datetime
import pdfkit
import webbrowser
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

load_dotenv()

# wkhtmltopdf.exe 的路徑
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

# 各區塊的模板
SECTION_TEMPLATE = """
<h2>{title}</h2>
{content}
"""

async def analyze_text(text_content, model_client, termination_condition):
    prompt = (
        "請根據下列格式分析這篇英文文章，並用正式繁體中文回答，不要有AI回應開場白。\n\n"
        "請按照以下五個部分依序分析，並清楚標示標題（每個標題前請加上『第X部分：』）：\n\n"
        "第1部分：文章內容統整：說明這篇文章的重點。\n"
        "第2部分：內容分析：【敘事方式說明】與【佳句統整】。\n"
        "第3部分：文章優、缺點：個別條列【優點】、【缺點】，並簡要說明【整體回饋】。\n"
        "第4部分：文法與用詞錯誤：用數字條列指出【原文】和【改進方式】。\n"
        "第5部分：文法、單字替換：用數字條列【原文】、【建議替換內容】、【簡要說明建議原因】\n\n"
        "注意：文中請用紅色字標出第4部分的錯誤之處（用<span class='highlight'>標記內容</span>），並不要使用粗體字。\n"
        "回覆時直接開始，不要有開場白。\n\n"
        "以下為文章內容：\n\n"
        f"{text_content}"
    )

    local_assistant = AssistantAgent("assistant", model_client)
    local_user_proxy = UserProxyAgent("user_proxy")
    local_team = RoundRobinGroupChat(
        [local_assistant, local_user_proxy],
        termination_condition=termination_condition
    )

    collected_messages = []

    async for event in local_team.run_stream(task=prompt):
        if isinstance(event, TextMessage):
            if event.source == "assistant":
                collected_messages.append(event.content)

    return "\n".join(collected_messages)

def generate_html_report(analysis_text):
    # 將分析內容直接分段
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

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_html = HTML_TEMPLATE.format(timestamp=timestamp, content="\n".join(formatted_sections))
    return final_html

async def main():
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("請檢查 .env 檔案中的 GEMINI_API_KEY。")
        return

    model_client = OpenAIChatCompletionClient(
        model="gemini-2.0-flash",
        api_key=gemini_api_key,
    )

    termination_condition = TextMentionTermination("exit")

    txt_file_path = "kao1.txt"
    with open(txt_file_path, "r", encoding="utf-8") as f:
        text_content = f.read()

    print("正在分析文章內容，請稍候...")
    analysis_text = await analyze_text(text_content, model_client, termination_condition)

    html_content = generate_html_report(analysis_text)

    html_output_path = "analysis_report.html"
    with open(html_output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"已將分析結果儲存為HTML: {html_output_path}")

    pdf_output_path = "analysis_report.pdf"
    pdfkit.from_file(html_output_path, pdf_output_path, configuration=pdfkit_config)
    print(f"已將分析結果轉換成PDF: {pdf_output_path}")

    # 生成後自動打開PDF
    webbrowser.open(f"file://{os.path.abspath(pdf_output_path)}")

if __name__ == "__main__":
    asyncio.run(main())
