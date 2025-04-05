import os
import google.generativeai as genai
import pandas as pd
from dotenv import load_dotenv
import csv

# 載入 .env 檔案中的環境變數
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# 設定 API 金鑰
genai.configure(api_key=API_KEY)

# 題型與難度對應表
categories = {
    "voc": "單字選擇",
    "clo": "克漏字",
    "rea": "閱讀測驗"
}

difficulties = {
    "easy": "易",
    "normal": "中",
    "hard": "難"
}

# 各難度參數
difficulty_settings = {
    "easy": {"word_count": 50, "max_questions": 3, "vocab_size": 1200},
    "normal": {"word_count": 100, "max_questions": 3, "vocab_size": 2500},
    "hard": {"word_count": 200, "max_questions": 5, "vocab_size": 5000}
}

# 產生題目
def generate_question(prompt):
    try:
        model = genai.GenerativeModel("models/gemini-1.5-pro")  # 修正模型名稱
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ 無法取得回應：{e}")
        return None

# 建立考卷並存成 CSV
def create_exam(category, difficulty):
    file_name = f"{category}{difficulty}.csv"
    print(f"📝 正在生成 {file_name} ...")
    settings = difficulty_settings[difficulty]

    with open(file_name, mode="w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)

        # 根據題型產生 prompt
        if category == "voc":
            writer.writerow(["問題", "選項1", "選項2", "選項3", "選項4", "答案"])
            prompt = f"請根據詞彙量{settings['vocab_size']}的範圍，生成10道四選一的單字選擇題，每題提供正確答案與三個混淆選項，格式如下：\n問題: ..., 選項: A. ..., B. ..., C. ..., D. ..., 答案: ..."
        
        elif category == "clo":
            writer.writerow(["句子", "選項1", "選項2", "選項3", "選項4", "答案"])
            prompt = f"請針對詞彙量{settings['vocab_size']}的範圍，生成10道克漏字填空題，每題提供正確答案與三個混淆選項，格式如下：\n句子: ..., 選項: A. ..., B. ..., C. ..., D. ..., 答案: ..."
        
        elif category == "rea":
            writer.writerow(["文章", "問題", "選項1", "選項2", "選項3", "選項4", "答案"])
            prompt = f"請根據詞彙量{settings['vocab_size']}的範圍，生成一篇{settings['word_count']}字的短文，並從中出{settings['max_questions']}道四選一的閱讀測驗題，每題提供正確答案與三個混淆選項，格式如下：\n文章: ..., 問題: ..., 選項: A. ..., B. ..., C. ..., D. ..., 答案: ..."

        # 呼叫 AI 生成題目
        questions = generate_question(prompt)
        if not questions:
            print(f"❌ 無法產生題目，略過 {file_name}")
            return

        # 將回傳內容解析寫入 CSV
        for question in questions.split("\n\n"):
            parts = question.strip().split("\n")
            if category == "rea":
                writer.writerow(parts[:7])  # 包含文章 + 題目 + 選項 + 答案
            else:
                writer.writerow(parts[:6])  # 題目 + 選項 + 答案

    print(f"✅ 已生成 {file_name}")

# 執行產生九種組合的考卷
for cat in categories.keys():
    for diff in difficulties.keys():
        create_exam(cat, diff)
