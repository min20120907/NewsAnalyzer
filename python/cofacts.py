# -*- coding: utf-8 -*-
import requests
import json
from typing import Union # For Python < 3.10 compatibility

# --- Cofacts API Configuration ---
COFACTS_API_URL = "https://cofacts-api.g0v.tw/graphql"
# Simplified GraphQL Query (Removed orderBy, first) - This version worked previously
GRAPHQL_QUERY = """
query SimpleListArticlesQuery($filter: ListArticleFilter) {
  ListArticles(filter: $filter) {
    edges {
      node {
        id
        text
        articleReplies(status: NORMAL) {
          reply {
            id
            text
            type # RUMOR, NOT_RUMOR, OPINIONATED, NOT_ARTICLE, TRUE, FALSE
          }
        }
      }
    }
  }
}
"""

# --- Cofacts API Query Function ---
def get_fact_check_status_cofacts(content: str) -> str:
    """
    使用 Cofacts API 透過文本相似度查詢事實查核狀態 (使用簡化查詢)。

    Args:
        content (str): 新聞內文 (會取片段進行查詢)。

    Returns:
        str: 'accurate', 'partial', 'inaccurate', 或 'not_found'。
    """
    if not content or not isinstance(content, str) or len(content.strip()) < 20:
        print("[Cofacts] 文本內容過短，跳過查詢。")
        return "not_found"

    # Use a snippet for matching
    content_snippet = content[:200]
    # Simplified Variables (only 'like')
    variables = {
        "filter": {
            "moreLikeThis": {
                "like": content_snippet
                # Removed "minimumShouldMatch" for simplicity based on previous tests
            }
        }
    }
    # Prepare payload using dictionary for json parameter
    payload_dict = {'query': GRAPHQL_QUERY, 'variables': variables}

    # Optional: Log the payload to be sent
    # print(f"[Cofacts] 準備發送 Payload (簡化版):\n{json.dumps(payload_dict, ensure_ascii=False, indent=2)}")

    print(f"[Cofacts] 正在查詢 API (查詢片段: \"{content_snippet}...\")...")

    try:
        # Use requests' json parameter for proper encoding and headers
        response = requests.post(COFACTS_API_URL, json=payload_dict, timeout=15) # 15 seconds timeout
        print(f"[Cofacts] API 回應狀態碼: {response.status_code}")
        response.raise_for_status() # Check for HTTP errors (like 4xx, 5xx)
        data = response.json()

        # --- Parse Response ---
        if 'errors' in data:
            print(f"[Cofacts] API 返回錯誤: {data['errors']}")
            return "not_found"

        # Check expected structure
        if not data.get('data') or not data['data'].get('ListArticles') or not data['data']['ListArticles'].get('edges'):
            print("[Cofacts] 未找到相似的已回報訊息或API回應格式不符。")
            return "not_found" # Includes case where 'edges' is null or empty list

        edges = data['data']['ListArticles']['edges']
        if not edges: # Explicitly check if edges list is empty
            print("[Cofacts] 未找到相似的已回報訊息。")
            return "not_found"

        print(f"[Cofacts] 找到 {len(edges)} 則相似訊息，正在分析查核回覆...")

        # --- Analyze replies ---
        has_false = False; has_true = False; has_opinion = False
        found_reply_types = []

        for edge in edges:
            node = edge.get('node', {})
            print(f"  - 檢查相似訊息 (ID: {node.get('id', 'N/A')}, Text: \"{node.get('text', '')[:30]}...\")")
            article_replies = node.get('articleReplies', [])
            if not article_replies: print("    - 此相似訊息無查核回覆。"); continue

            for articleReply in article_replies:
                reply = articleReply.get('reply', {})
                if reply and reply.get('type'):
                    reply_type = reply.get('type').upper()
                    found_reply_types.append(reply_type)
                    print(f"    - 找到回覆類型: {reply_type}")
                    if reply_type in ['FALSE', 'RUMOR']: has_false = True; break
                    elif reply_type in ['TRUE', 'NOT_RUMOR']: has_true = True
                    elif reply_type == 'OPINIONATED': has_opinion = True
            if has_false: break # Prioritize inaccurate

        # Determine final status based on priority
        if has_false: final_status = "inaccurate"; print_status = "不準確"
        elif has_true: final_status = "accurate"; print_status = "準確"
        elif has_opinion: final_status = "partial"; print_status = "部分準確/意見"
        else: final_status = "not_found"; print_status = f"未找到明確查核結果 (找到的回覆類型: {found_reply_types or '無'})"

        print(f"[Cofacts] 最終判定: {print_status} ({final_status})")
        return final_status

    except requests.exceptions.Timeout: print(f"[Cofacts] API 請求超時。"); return "not_found"
    except requests.exceptions.RequestException as e: print(f"[Cofacts] API 請求失敗 (狀態碼: {response.status_code if 'response' in locals() else 'N/A'}): {e}"); return "not_found"
    except json.JSONDecodeError as e: print(f"[Cofacts] 解析 API 回應 (JSON) 失敗: {e}"); return "not_found"
    except Exception as e: print(f"[Cofacts] 處理 API 回應時發生未知錯誤: {e}"); return "not_found"

# --- Example Usage ---
if __name__ == "__main__":
    print("\n" + "="*15 + " Cofacts API 獨立測試 (簡化查詢版) " + "="*15)
    print("請先確保已安裝 requests: pip install requests")

    test_texts_for_cofacts = [
        "LINE流傳影片「這是來自日本的視頻，教您正確戴口罩的方式...」？", # Known rumor likely in Cofacts
        "網傳「美國科學家發現，新冠病毒來自莫德納實驗室」？", # Known rumor likely in Cofacts
        "近日在某個小鎮發生了一件趣事，一隻貓咪學會了按門鈴，引起居民討論。", # Unlikely to be in Cofacts
        "台灣今日新增若干 COVID-19 病例，指揮中心呼籲民眾遵守防疫規定。", # Generic news text, might match something
        "地震後千萬不要先開燈、不要開瓦斯，這是真的嗎？", # Common safety advice, might have checks
        "這是完全原創的、沒有根據的測試文字，看看 Cofacts 會怎麼說。" # Original text
    ]

    for i, text in enumerate(test_texts_for_cofacts):
        print(f"\n--- 測試文本 {i+1} ---")
        # print(f"完整輸入內容: \"{text}\"") # Uncomment to see full text
        status = get_fact_check_status_cofacts(text)
        print(f"==> Cofacts 查核狀態: {status}")

    print("\n" + "="*15 + " 測試結束 " + "="*15)
