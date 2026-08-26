# -*- coding: utf-8 -*-

from typing import Union
from datetime import datetime
from urllib.parse import urlparse
import re

TRANSFORMERS_AVAILABLE = False
SENTIMENT_PIPELINE = None
MODEL_LOAD_ERROR = None
MODEL_LABELS = {}

try:
    from transformers import pipeline, logging as hf_logging
    hf_logging.set_verbosity_error()
    TRANSFORMERS_AVAILABLE = True

    # --- 初始化 Pipeline (從本地路徑載入) ---

    # *** 步驟 1: 在這裡填寫你 clone 下來的模型的【完整本地路徑】 ***
    # *** 例如: "/home/user/my_models/distilbert-base-multilingual-cased-sentiments-student" ***
    # *** 或者相對於你執行 python 腳本的路徑: "./distilbert-base-multilingual-cased-sentiments-student" ***
    local_model_path = "distilbert-base-multilingual-cased-sentiments-student" # <--- !!! 修改這裡 !!!

    task_name = 'text-classification' # 或者 'sentiment-analysis' 也可以試試

    print(f"[初始化] 嘗試從【本地路徑】載入 Transformers 模型 for {task_name}: {local_model_path}...")

    # 將本地路徑傳遞給 pipeline 的 model 參數
    SENTIMENT_PIPELINE = pipeline(task_name, model=local_model_path)
    # pipeline 會自動從該路徑載入模型和分詞器

    print(f"[初始化] Transformers pipeline 從本地路徑 ({local_model_path}) 載入成功。")

    if SENTIMENT_PIPELINE and hasattr(SENTIMENT_PIPELINE.model, 'config'):
        MODEL_LABELS = SENTIMENT_PIPELINE.model.config.id2label
        print(f"[初始化] 模型標籤對應 (id2label): {MODEL_LABELS}")
    else:
         print("[警告] 無法獲取模型標籤對應關係。")

except ImportError:
    MODEL_LOAD_ERROR = "未找到 'transformers' 或其依賴庫 (torch/tensorflow)。"
    print(f"[錯誤] {MODEL_LOAD_ERROR}")
except Exception as e:
    MODEL_LOAD_ERROR = f"無法從本地路徑 '{local_model_path}' 載入 Transformers pipeline: {e}。\n[提示] 請確認路徑是否正確，且資料夾內包含有效的模型文件 (如 config.json, pytorch_model.bin 或 tf_model.h5)。"
    print(f"[錯誤] {MODEL_LOAD_ERROR}")

# --- 情感分析函數 (analyze_sentiment_transformer) ---
# (函數內容不需要修改，它會使用上面初始化的 SENTIMENT_PIPELINE)
def analyze_sentiment_transformer(text: str) -> Union[float, None]:
    # ... (函數內容和之前版本一樣) ...
    if not SENTIMENT_PIPELINE:
        print(f"[錯誤] 情感分析 Pipeline 未成功載入。{MODEL_LOAD_ERROR or ''}")
        return None
    if not text or not isinstance(text, str) or len(text.strip()) == 0:
        print("[警告] 輸入文本無效或為空。")
        return None
    try:
        print(f"  [分析中] 文本: \"{text[:60]}...\"")
        results = SENTIMENT_PIPELINE(text, truncation=True, max_length=512)
        if results and isinstance(results, list):
            result = results[0]; label = result.get('label'); score = result.get('score')
            if label is not None and score is not None:
                numeric_label = None
                if isinstance(label, str) and label.startswith('LABEL_'):
                    try:
                        label_id = int(label.split('_')[-1])
                        if label_id in MODEL_LABELS: label = MODEL_LABELS[label_id]; print(f"  - (標籤轉換: {label})")
                        else: print(f"  - [警告] 無法識別的數字標籤 {label}")
                    except ValueError: print(f"  - [警告] 無法解析數字標籤 {label}")
                label_lower = label.lower() if isinstance(label, str) else ''
                mapped_score = 0.0
                if label_lower == 'positive': mapped_score = score
                elif label_lower == 'negative': mapped_score = -score
                print(f"  - 分析結果: label='{label}', score={score:.4f} => 映射分數: {mapped_score:.4f}")
                return mapped_score
            else: print(f"  - 分析錯誤: Pipeline 返回格式不符: {results}"); return None
        else: print(f"  - 分析錯誤: Pipeline 未返回有效結果: {results}"); return None
    except Exception as e: print(f"  - 分析錯誤: Transformers pipeline 執行時出錯: {e}"); return None

# --- 範例使用 ---
if __name__ == "__main__":
    # ... (範例使用部分不變) ...
    print("\n" + "="*15 + " 情感分析獨立測試範例 (本地模型載入) " + "="*15)
    if not SENTIMENT_PIPELINE:
        print("\n情感分析 Pipeline 未載入，無法執行測試。請檢查錯誤訊息與模型路徑。")
    else:
        test_texts = [
            "這家餐廳的服務態度真好，餐點也很美味！",
            "今天天氣真不錯，陽光普照。",
            "真是太令人失望了，品質很差。",
            "這部電影真是難看，浪費我的時間。",
            "商品尚可，不好不壞。",
        ]
        for i, text in enumerate(test_texts):
            print(f"\n--- 測試文本 {i+1} ---")
            sentiment_value = analyze_sentiment_transformer(text)
            if sentiment_value is not None:
                print(f"==> 判斷的情感分數 (範圍 -1 到 1): {sentiment_value:.4f}")
                if sentiment_value >= 0.2: print("==> 傾向: 正面")
                elif sentiment_value <= -0.2: print("==> 傾向: 負面")
                else: print("==> 傾向: 中性")
            else: print("==> 無法獲取情感分數。")
    print("\n" + "="*15 + " 測試結束 " + "="*15)
