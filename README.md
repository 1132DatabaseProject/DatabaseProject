# 英文寫作分析器

## 影片介紹
1. 第一次審查說明: https://youtu.be/UgYSmUlx4qM  
2. 第二次審查說明: https://youtu.be/Q-ppPWUA73w  
3. 期末專題影片: https://youtu.be/VyQuufedhH8  

## 簡介
這個應用程式能針對每一篇文章，完整分析出敘事方式、優缺點、佳句統整、用詞錯誤等內容，更快速、有效的得到完整回饋。

## 欲解決的問題
批改大量英文作文需花費大量時間和精力，且不一定能針對每一位學生的寫作內容完整進行評價與建議。

為單純想精進英文寫作，或是想了解他人文章的人，提供完整報告。

## 安裝步驟

### 1. 下載專案
```bash
git clone <你的-repo-url>
cd <你的專案資料夾>
```

### 2. 安裝所需 Python 套件
建議使用虛擬環境（venv、conda 等）：
```bash
pip install -r requirements.txt
```

### 3. 必要檔案與設定

**Google API 憑證 & Supabase 設定**  
建立 `.env` 檔案，內容如下（請填入你的資訊）：
```bash
GEMINI_API_KEY=你的 Gemini API Key
```

### 4. 啟動應用程式
```bash
python app.py
```

---

## APP使用流程

1. 使用者需提供一篇文本，

EX. 在文字輸入框中輸入文字、匯入TXT檔，

每當選擇匯入檔案時，文字輸入框會顯示檔案內的文字內容。

![文字輸入](https://github.com/user-attachments/assets/19155d1e-86dd-4f1c-8736-e3ef16cbf7e6)  
![匯入後文字呈現](https://github.com/user-attachments/assets/448e2e9d-8c0e-4d4c-9d5d-f4bcc09e0cdd)

2. 按下「開始分析」，產生分析內容
 
分析結果在介面下方產生，分析會註記分析日期與時間，以及五大段分析結果：

![分析畫面](https://github.com/user-attachments/assets/c02f706f-1328-447c-b9e3-89746f24cf9a)

最後根據提供文本，重新寫一篇同主題的範例文章。

![範例文章](https://github.com/user-attachments/assets/9afa4cf6-51fd-4dc9-8d27-55562fa1e253)

3. 分析下載、客製
使用者可將原始分析結果下載儲存成PDF檔案...
![PDF 下載](https://github.com/user-attachments/assets/397a986a-6d66-4d96-98e0-34f1c0f9ade8)  

或是使用應用程式內建的Quill編輯器編輯分析結果。

![Quill 編輯](https://github.com/user-attachments/assets/ba01a711-2b01-4bd0-91d4-455d28dae0ef)

---

## AI Agent 流程圖
```
+---------------------------+
| 輸入文章 / 上傳TXT檔案     |
+---------------------------+
              ↓
+---------------------------+
| 呼叫 Gemini API 執行分析    |
+---------------------------+
              ↓
+-----------------------------------------+
| 產出以下五段分析內容：                   |
| 1. 文章內容統整                         |
| 2. 敘事方式分析與佳句統整                |
| 3. 優點與缺點 + 整體回饋                 |
| 4. 錯誤偵測與標紅                        |
| 5. 改寫建議與替換說明                    |
+-----------------------------------------+
              ↓
+--------------------------------+
| 生成一篇相同主題的新範例英文文章 |
+--------------------------------+
              ↓
+----------------------------------+
| 整合分析內容與範例文章生成報告HTML  |
+----------------------------------+
              ↓
+-----------------------+
| 轉換成 PDF 格式下載報告 |
+-----------------------+
```
---

## AI Agents 任務分工

- **分析 Agent**：呼叫 Gemini API，執行五段式內容分析。
- **範例生成 Agent**：撰寫主題相同但敘事不同的範例文章。
- **輸出格式化 Agent**：整合 HTML 轉換 PDF。
- **資料庫 Agent**：將分析結果與使用者帳號存入 Supabase，供未來查詢。

---

## 詳細功能介紹

### Gemini AI 使用方式

- 使用 `google.generativeai` 串接 Gemini-1.5-Flash 模型。
- 透過 prompt 給定固定格式，強化穩定性。
- `analyze_text()` 與 `generate_sample_article()` 為兩個主要分析任務函式。

### PDF 輸出功能

- 使用 `pdfkit` + `wkhtmltopdf` 將分析報告轉成 PDF。
- 可下載原始分析結果 PDF，或修改後內容另存 PDF。

### 資料庫紀錄與登入機制

- 透過 Supabase 儲存下列資料：
  - 使用者帳號（登入/註冊）
  - 原始文章與 AI 分析結果（HTML 與 PDF 名稱）
- 歷史紀錄介面可載入過往結果、預覽與刪除。

### Quill 編輯器整合

- 使用者可點擊分析結果 → 匯入 Quill。
- 在編輯器內進行修改 → 點擊「另存 PDF」可轉換修改後版本。

### 使用者體驗功能

- 提供主題切換（淺色 / 深色）
- 提供上下捲動快捷鍵
- 分析結果可即時下載與切換顯示區域

---

## 路由說明

| 路由 | 功能 |
|------|------|
| `/` | 主頁：輸入分析與歷史紀錄 |
| `/login`, `/logout` | 登入、註冊、登出 |
| `/upload_txt` | 上傳 TXT 檔案 |
| `/generate_pdf` | 將 Quill 內容轉為 PDF |
| `/download_pdf/<filename>` | 下載指定 PDF 檔 |
| `/get_history_item/<id>` | 取得指定歷史紀錄 |
| `/delete_history_item/<id>` | 刪除指定紀錄 |

---

## 專題優勢

1. **輔助學習的工具**  
   減少學生尋求回饋的門檻，提升學習效率與動機。

2. **自動分析、不需輸入指令**  
   使用者只需上傳文章，即可獲得分析，不需額外設定。

3. **結果可記錄、下載與編輯**  
   所有分析結果可保存、查看與再次使用。

4. **良好介面與使用體驗**  
   提供舒適、視覺一致的使用者操作流程。
