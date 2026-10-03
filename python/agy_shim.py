"""agy CLI → OpenAI 相容 HTTP shim（最小可用）。

為什麼需要：anti-api (:8964) 送 API-key proto 路徑，Antigravity 對該路徑回 429
resource_exhausted，即使帳號額度 100%（consumer/OAuth 路徑正常）。agy 走
v1internal:loadCodeAssist + authMethod=consumer，同模型同帳號可以成功回應。
改anti-api 的 proto 編碼要先逆出欄位佈局，成本高；這個 shim 先把路打開。

用法：python agy_shim.py [port]   # 預設 8965
然後 llm_registry 裡用 backend "agy"。
"""
import json
import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8965
AGY = "/home/min20120907/.local/bin/agy"
# agy 每次啟動會開一個 language server，並發會互相踩。ponytail: 全域鎖序列化，
# 換並行吞吐就改成長駐 server + 連線池。
_lock = threading.Lock()


def ask(model: str, prompt: str, timeout: int = 180) -> str:
    # ponytail: 全域鎖序列化。agy 每次開一個 language server，並發會互相踩。
    # 換並行吞吐就改成長駐 server + 連線池。
    # 鎖必須帶 timeout 釋放——否則一個卡住的請求會把後面全部鎖死
    # （2026-10-02 實測：一次 Read timeout 後 shim 對所有請求都逾時）。
    got = _lock.acquire(timeout=timeout + 15)
    if not got:
        raise TimeoutError("agy shim busy")
    try:
        proc = subprocess.Popen(
            [AGY, "--model", model, "-p", prompt],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            # 自成一個行程組，killpg 才不會誤殺本 shim 自己。
            start_new_session=True,
        )
    except Exception:
        _lock.release()
        raise
    try:
        out, _ = proc.communicate(timeout=timeout)
        return (out or "").strip()
    except subprocess.TimeoutExpired:
        # 只殺自己剛起的這個 PID 群組。絕不用 pkill -f（紅線：曾誤殺自身 shell
        # 進而關閉使用者的 Telegram）。
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        raise
    finally:
        _lock.release()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _reply(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        # 2026-10-03：HTTP/1.1 keep-alive 下沒有 Content-Length，client 會一直
        # 等到自己的 socket timeout 才讀 body → 每個請求固定多花 190s。
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        model = body.get("model") or "gemini-3.8-flash-high"
        msgs = body.get("messages") or []
        # agy -p 只吃一段純文字；把 system 併進 user，順序不變。
        prompt = "\n\n".join(
            f"{m.get('role','user')}: {m.get('content','')}" for m in msgs
        ).removeprefix("system: ").strip()
        try:
            out = ask(model, prompt)
            err = None
        except subprocess.TimeoutExpired:
            out, err = "", "agy timeout"
        except Exception as e:
            out, err = "", str(e)
        self._reply(200 if out else 502, {
            "choices": [{"message": {"content": out}, "finish_reason": "stop"}],
            "error": {"message": err} if err else None,
        })

    def do_GET(self):
        self._reply(200, {"data": [{ "id": m } for m in (
            "gemini-3.8-flash-high", "gemini-3.8-flash-medium",
            "gemini-3.8-flash-low", "gemini-3.7-flash-high",
            "gemini-3.6-flash-high", "gemini-3.1-pro-high",
            # 2026-10-03：agy 已升 Claude 5.5，4-6 名稱不再被 --model 接受
            "claude-sonnet-5-5-high", "claude-opus-5-5-high",
            "gpt-oss-120b-medium")]})


if __name__ == "__main__":
    print(f"agy shim → http://127.0.0.1:{PORT}/v1/chat/completions", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()