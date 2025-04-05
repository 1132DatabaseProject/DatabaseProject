import subprocess

scripts = [
    "voceasy.py",
    "vocnormal.py",
    "vochard.py",
    "cloeasy.py",
    "clonormal.py",
    "clohard.py",
    "reaeasy.py",
    "reanormal.py",
    "reahard.py"
]

print("📚 啟動考卷生成器...\n")

for script in scripts:
    print(f"🚀 執行 {script} ...")
    try:
        result = subprocess.run(["python", script], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ 發生錯誤：{script} 執行失敗\n")
    print("----------")

print("✅ 所有題庫已完成或嘗試執行完畢。")
