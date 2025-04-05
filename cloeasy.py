import os, csv
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

prompt = """
請根據詞彙量 1200 的範圍，生成 10 道克漏字選擇題，每題為四選一，測試文法、單字、介係詞等，格式如下：
問題: ...
選項: A. ..., B. ..., C. ..., D. ...
答案: ...
"""
file_name = "cloeasy.csv"


def generate_question(prompt):
    try:
        model = genai.GenerativeModel("models/gemini-1.5-pro")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ 無法取得回應：{e}")
        return None

def create_csv():
    file_name = "voceasy.csv"
    print(f"📝 正在生成 {file_name} ...")
    questions = generate_question(prompt)
    if not questions:
        print(f"❌ 無法產生題目，略過 {file_name}")
        return
    with open(file_name, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["問題", "選項1", "選項2", "選項3", "選項4", "答案"])
        for block in questions.split("\n\n"):
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                q = lines[0].replace("問題:", "").strip()
                opts = [o.strip()[2:].strip() for o in lines[1].replace("選項:", "").split(",")]
                ans = lines[2].replace("答案:", "").strip()
                writer.writerow([q] + opts + [ans])
    print(f"✅ 已完成：{file_name}")

create_csv()
