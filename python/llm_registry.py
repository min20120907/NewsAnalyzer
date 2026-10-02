"""LLM 後端註冊表（單一事實來源）。

前端選單、`/models` 端點、離線評測都讀這裡——不要在別處再寫一份模型清單。

新增一個模型＝在 BACKENDS 加一筆，前端選單自動出現。
"""
import os

# ~/.hermes/.env 會被寫成遮罩字串 ***（實測 OPENROUTER_API_KEY 就是這樣），
# 所以 os.environ 拿不到。直接讀原始 bytes。
_ENV_CACHE = {}


def _read_raw_env(key: str) -> str:
    """從 ~/.hermes/.env 原始位元組讀值，繞過遮罩。找不到回空字串。"""
    if key in _ENV_CACHE:
        return _ENV_CACHE[key]
    val = ""
    try:
        with open(os.path.expanduser("~/.hermes/.env"), "rb") as f:
            raw = f.read().decode("utf-8", "replace")
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith(key + "="):
                val = s.split("=", 1)[1].strip().strip('"').strip("'")
                break
    except Exception:
        pass
    _ENV_CACHE[key] = val
    return val


def api_key_for(backend_cfg: dict) -> str:
    """依後端設定取得 api key：先環境變數，遮罩了就從原始 .env 挖。"""
    env_key = backend_cfg.get("api_key_env")
    if not env_key:
        return ""
    v = os.environ.get(env_key, "") or ""
    if v and not v.strip().startswith("***") and len(v) > 20:
        return v
    return _read_raw_env(env_key)

# 每個後端＝一組「base_url + 可選模型清單」。
#   probe_needed: 啟動時打一次 /chat/completions 確認活著（deep-proxy 會被 ban）
BACKENDS = {
    "local": {
        "label": "本機 Qwen3.8-27B (llama.cpp)",
        "base_url": os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8088/v1/chat/completions"),
        "slots_url": "http://127.0.0.1:8088/slots",
        "models": ["qwen3.8-27b-fastmtp"],
        "free": True,
        "local": True,          # 單槽、需排隊感知
        "serial": True,         # 不併發
    },
    "antigravity": {
        "label": "anti-api (Antigravity)",
        "base_url": os.environ.get("ANTIAPI_URL", "http://127.0.0.1:8964/v1/chat/completions"),
        # 2026-10-02 實測篩選：Gemini 保留 flash/pro；其餘只留 Claude + OSS 系列。
        # 已被排除（實測失敗，別再加回來）：
        #   gemini-3.1-pro/3.8-flash → HTTP 429 resource exhausted（暫時性額度）
        #   gpt-5.3 / glm-5 / deepseek-3.2 → HTTP 400 "No valid account routing entries"
        #   gpt-oss-120b 能回但整篇跳英文 → 中文新聞評分不可用
        "models": [
            "claude-sonnet-4-6", "claude-opus-4-6-thinking",
            "gemini-3.8-flash-high", "gemini-3.8-flash-medium",
            "gemini-3.1-pro-high",
        ],
        "free": True,
    },
    "openrouter": {
        # 真·OpenRouter 官方 API（不是本機 :8100 的 auto-router，那是另一個專案）
        "label": "OpenRouter 免費層",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_env": "OPENROUTER_API_KEY",
        "models": [
            "qwen/qwen3.8-27b:free",              # 262K ctx，與本機同權重可比
            "google/gemma-4-31b-it:free",
            "dots-studio/dots-3-note-preview:free",
            "apodex/apodex-1.1-mini:free",
            "poolside/laguna-s-2.1:free",
        ],
        "free": True,
        "external": True,      # 需要 api key
        # 2026-10-02 實測排除 nvidia/nemotron-3-{super,ultra}:free：
        # 免費層不支援 enable_thinking=False，reasoning 欄吃掉全部 max_tokens
        # （實測 5056 字元 reasoning、content 長度 0、finish_reason=length），
        # 評分 prompt 拿不到任何 JSON。這類模型要接需要自適應 max_tokens + 解析
        # reasoning 尾段，不是免費層能用的。
    },
    "deepproxy": {
        "label": "deep-proxy (DeepSeek Web)",
        "base_url": os.environ.get("QWEN_URL", "http://127.0.0.1:3000/v1/chat/completions"),
        "models": ["deepseek-chat"],
        "free": True,
        # 2026-10-02 實測：create_session error code=40003 → 被 ban。
        # 保留在選單（恢復後可用），但預設不選、啟動時探測，失敗就自動排除。
        "probe_needed": True,
        "disabled": os.environ.get("DEEP_PROXY_DISABLED", "0") == "1",
    },
}

# 預設後端：不在禁用清單裡的第一個。保持與既有 QWEN_URL 行為相容。
def default_backend() -> str:
    if os.environ.get("LLM_BACKEND"):
        return os.environ["LLM_BACKEND"]
    for k, v in BACKENDS.items():
        if not v.get("disabled") and not v.get("probe_needed"):
            return k
    return "local"


def model_catalog(include_disabled: bool = False) -> list:
    """回傳前端選單用的扁平清單：[{id, label, backend, free, local}]"""
    out = []
    for bkey, b in BACKENDS.items():
        if b.get("disabled") and not include_disabled:
            continue
        for m in b["models"]:
            out.append({
                "id": f"{bkey}/{m}",
                "backend": bkey,
                "model": m,
                "label": f"{b['label']} — {m}",
                "free": b.get("free", False),
                "local": b.get("local", False),
            })
    return out


def resolve(model_id: str):
    """'local/qwen3.8-27b-fastmtp' → (backend_key, model_name, backend_cfg)"""
    if not model_id or "/" not in model_id:
        bkey = default_backend()
        return bkey, BACKENDS[bkey]["models"][0], BACKENDS[bkey]
    bkey, m = model_id.split("/", 1)
    b = BACKENDS.get(bkey)
    if not b:
        bkey = default_backend()
        return bkey, BACKENDS[bkey]["models"][0], BACKENDS[bkey]
    return bkey, m, b


if __name__ == "__main__":
    d = default_backend()
    print(f"預設後端: {d} ({BACKENDS[d]['label']})")
    print(f"選單共 {len(model_catalog())} 個模型:")
    for m in model_catalog(include_disabled=True):
        flag = " [停用]" if BACKENDS[m["backend"]].get("disabled") else ""
        print(f"  {m['id']:45} {flag}")