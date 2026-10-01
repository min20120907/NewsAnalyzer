"""無回覆的 Cofacts 文章不算「查核判定」——不該帶 status 進下游。
2026-10-01 regression。跑：.venv/bin/python scripts/check_cofacts_no_reason.py
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from cofacts_local import _classify_candidate


def _node(text, replies):
    return {"id": "x1", "text": text, "createdAt": "2024-01-01T00:00:00Z",
            "articleReplies": replies, "replyCount": len(replies)}


def _reply(rtype, text):
    return {"feedbackCount": 0, "reply": {"type": rtype, "text": text}}


def demo():
    # 有實質回覆 → 正常帶 status
    with_reply = _node("某影片流傳謠言", [
        _reply("RUMOR", "查核：影片為舊片段重新剪輯，內容不符")])
    assert _classify_candidate(with_reply) is not None, "有回覆不該被丟棄"

    # 社群公告垃圾文、無任何回覆 → 必須丟棄，否則 fact_check=-30 鎖死真新聞
    no_reply = _node("🚨 緊急宣導 🚨 本社有人反饋被洩外資，重建聊天室", [])
    assert _classify_candidate(no_reply) is None, "無回覆文章應被丟棄"

    # 只有空白回覆（無實質文字）→ 不構成理由
    emoji = _node("某則內容", [_reply("RUMOR", "   ")])
    assert _classify_candidate(emoji) is None, "空白回覆應被丟棄"

    # 本地近鄲路徑：corpus 裡 reasons 幾乎全空，無回覆的鄰居不該被召回成判定
    import cofacts_local as C
    con = C._ensure_db()
    con.execute("INSERT OR REPLACE INTO corpus "
                "(key,text,status,feedback_count,created_at,article_id,reasons) "
                "VALUES ('test-noreason','社群公告垃圾文測試','inaccurate',0,NULL,'tst','')")
    con.commit()
    try:
        assert C.local_match("社群公告垃圾文測試", threshold=0.1) is None, \
            "無回覆的 corpus 鄰居不該被召回"
    finally:
        con.execute("DELETE FROM corpus WHERE key='test-noreason'")
        con.commit()
        con.close()

    # 2026-10-01：NOT_ARTICLE 的「無從判斷」型不算判定（只說長度 >=15 就放行會造出假 accurate）
    hedge = _node("資料來源：中時新聞網\nhttps://share.google/IKVx9fe2bGHsuNfTi", [
        _reply("NOT_ARTICLE", "訊息內容就是「資料來源：中時新聞網」加上一條 Google 分享轉址，"
                              "既沒寫是哪則新聞，也沒提出任何說法，因此這裡無從判斷真假。")])
    assert _classify_candidate(hedge) is None, "『無從判斷』的 NOT_ARTICLE 不該算查核判定"

    # 但機構真的查了並確認的 NOT_ARTICLE 仍是 accurate
    verified = _node("宣稱某活動存在", [
        _reply("NOT_ARTICLE", "經查證該活動確實於 2026 年 9 月 30 日舉行，"
                              "現場照片與主辦單位公告一致，內容屬實。")])
    got = _classify_candidate(verified)
    assert got and got["status"] == "accurate", "真查證的 NOT_ARTICLE 應維持 accurate"

    # 2026-10-01：本地近鄲路徑也要有實體門控。實測「藍優先法案列普發2萬 王婉諭批評」
    # 命中 corpus 裡「香蕉鳳梨謠言 國民黨道歉」(NOT_RUMOR→accurate) 拿到 89.61 高度可信，
    # 只因為兩者共用「國民黨」。GraphQL 路徑有擋，這條沒有 → 門控形同虛設。
    assert C.entity_gatekeeper(
        "藍優先法案列普發2萬 王婉諭：政治不能只做最容易討好的選擇",
        "香蕉鳳梨網路謠言元凶抓到了 農委會要國民黨道歉"), \
        "只共用『國民黨』不該通過實體門控"
    assert C.entity_gatekeeper("王婉諭批評普發2萬", "王婉諭批評普發2萬"), \
        "同一實體應該通過門控"

    print("ALL PASS — 無回覆文章不會再變成查核判定")


if __name__ == "__main__":
    demo()