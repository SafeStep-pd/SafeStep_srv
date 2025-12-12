import os
import subprocess
import datetime
import requests
import locale

# --- 設定エリア ---
GIT_DIR = "/home/kit/safestep/SafeStep_srv"
FILENAME = "weather.txt"
AREA_CODE = "170000"             # 170000=石川県 (東京:130000, 大阪:270000)
# 天気概況（テキストデータ）のエンドポイント
JMA_URL = f"https://www.jma.go.jp/bosai/forecast/data/overview_forecast/{AREA_CODE}.json"
# ------------------

def get_nerv_style_text():
    try:
        response = requests.get(JMA_URL)
        data = response.json()
        
        # 1. ヘッドライン（短い警告文）を取得
        text = data.get("headlineText")
        
        # ヘッドラインが空（平穏な時）は、概況の冒頭を使うか、平穏なメッセージにする
        if not text:
            full_text = data.get("text", "")
            # 最初の句点(。)までを取得してみる
            text = full_text.split("。")[0] + "。"
            
            # それでも空ならデフォルトメッセージ
            if not text:
                text = "現在、特筆すべき気象警報はありません。"

        # 2. 全角数字を半角に直す（NERV風のクールさを出すため）
        # 簡易的な置換
        table = str.maketrans({chr(0xFF10 + i): str(i) for i in range(10)})
        text = text.translate(table)

        # 3. 署名と日付のフォーマット作成
        # 英語形式の日付 (例: December 12, 2025 14:30)
        # ロケールを一時的にUSにして英語表記を取得する
        try:
            locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
        except:
            pass # ラズパイにen_USが入ってない場合はデフォルト動作
            
        now_str = datetime.datetime.now().strftime('%B %d, %Y %H:%M')
        
        # 4. 最終的な文字列結合（修正箇所：textを追加）
        final_output = (
            f"{text}\n"
            f"Last updated: {now_str}"
        )

        return final_output

    except Exception as e:
        return f"System Error: {e}"

def git_push():
    os.chdir(GIT_DIR)
    
    # 編集前にまずPullして最新状態にする
    print("--- Pulling latest changes from remote... ---")
    try:
        subprocess.run(["git", "pull", "origin", "main"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Git Pull Error: {e}")
        print("Pullに失敗しました。手動で競合を解決する必要があるかもしれません。処理を中断します。")
        return
    
    content = get_nerv_style_text()
    print("--- 生成された文章 ---")
    print(content)
    print("----------------------")
    
    # ファイル書き込み
    with open(FILENAME, "w", encoding="utf-8") as f:
        f.write(content)
    
    # Git操作
    try:
        subprocess.run(["git", "add", FILENAME], check=True)
        
        # 変更チェック
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("No changes detected.")
            return

        commit_msg = f"Alert Update: {datetime.datetime.now().strftime('%H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("Push completed.")
        
    except subprocess.CalledProcessError as e:
        print(f"Git Error: {e}")

if __name__ == "__main__":
    git_push()