#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Session 管理模組
自動從本機 Chrome Profile (~/.config/google-chrome/Default/Cookies) 解密並注入 Facebook/Messenger session cookies
不需要使用者手動輸入帳密或開啟視窗登入
"""

import os
import re
import json
import sqlite3
import shutil
import urllib.parse
from typing import Dict, Optional, List
from hashlib import pbkdf2_hmac

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

try:
    import secretstorage
    SECRETSTORAGE_AVAILABLE = True
except ImportError:
    SECRETSTORAGE_AVAILABLE = False


def _get_chrome_safe_storage_key() -> bytes:
    """從 GNOME Keyring (SecretService) 獲取 Chrome Safe Storage 解密金鑰"""
    if SECRETSTORAGE_AVAILABLE:
        try:
            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            for item in collection.get_all_items():
                if item.get_label() == 'Chrome Safe Storage':
                    return item.get_secret()
        except Exception:
            pass
    return b'peanuts'


def extract_facebook_cookies() -> List[Dict]:
    """
    從本機 Chrome Default profile (~/.config/google-chrome/Default/Cookies)
    自動解密 Facebook & Messenger Cookies
    """
    if not CRYPTO_AVAILABLE:
        print("[FB Session] cryptography 模組不可用，無法自動解密 Chrome Cookies")
        return []

    # 1. 取得金鑰與衍生 PBKDF2 key
    my_pass = _get_chrome_safe_storage_key()
    key = pbkdf2_hmac('sha1', my_pass, b'saltysalt', 1, 16)

    # 2. 檢查 Cookies 資料庫路徑
    cookie_paths = [
        os.path.expanduser('~/.config/google-chrome/Default/Cookies'),
        os.path.expanduser('~/.config/google-chrome/Default/Network/Cookies'),
        os.path.expanduser('~/.config/google-chrome-mfp/Default/Cookies'),
        os.path.expanduser('~/.config/google-chrome-mfp/Default/Network/Cookies'),
    ]

    extracted_cookies = []
    seen = set()

    for db_path in cookie_paths:
        if not os.path.exists(db_path):
            continue

        tmp_db = f'/tmp/fb_cookies_{hash(db_path)}.db'
        try:
            shutil.copy2(db_path, tmp_db)
            conn = sqlite3.connect(tmp_db)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT host_key, name, path, CAST(encrypted_value AS BLOB), is_secure, is_httponly FROM cookies'
            )

            for host, name, path, enc_val, is_secure, is_httponly in cursor.fetchall():
                if not enc_val:
                    continue
                # 只處理 Facebook / Messenger / 相關認證 cookies
                is_fb_domain = any(k in host for k in ['facebook.com', 'messenger.com'])
                is_auth_cookie = name in ('c_user', 'xs', 'datr', 'sb', 'fr', 'wd', 'presence')
                if not (is_fb_domain or is_auth_cookie):
                    continue

                if enc_val.startswith(b'v10') or enc_val.startswith(b'v11'):
                    try:
                        iv = b' ' * 16
                        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                        decryptor = cipher.decryptor()
                        decrypted = decryptor.update(enc_val[3:]) + decryptor.finalize()
                        unpadder = padding.PKCS7(128).unpadder()
                        plain = unpadder.update(decrypted) + unpadder.finalize()
                        plain_str = plain.decode('utf-8', errors='ignore')
                        if not plain_str:
                            continue

                        # 處理 xs cookie 解碼
                        val = urllib.parse.unquote(plain_str) if name == 'xs' else plain_str

                        # 將 cookie 注入 Facebook/Messenger 相關網域
                        domains = ['.facebook.com', '.messenger.com', 'www.facebook.com']
                        for d in domains:
                            cookie_key = (d, name, path)
                            if cookie_key not in seen:
                                seen.add(cookie_key)
                                extracted_cookies.append({
                                    'name': name,
                                    'value': val,
                                    'domain': d,
                                    'path': path or '/',
                                    'secure': bool(is_secure),
                                    'httpOnly': bool(is_httponly)
                                })
                    except Exception:
                        pass
            conn.close()
        except Exception as e:
            print(f"[FB Session] 讀取 {db_path} 時發生錯誤: {e}")
        finally:
            if os.path.exists(tmp_db):
                try:
                    os.remove(tmp_db)
                except Exception:
                    pass

    return extracted_cookies


def _clean_fb_title(title: str) -> str:
    """清掉 FB 標題的未讀通知前綴 '(N) ' 與 ' | Facebook' 尾綴。

    注意：'(1) ' 前綴在正常登入狀態下也會出現（未讀通知數），
    不可拿它當登入牆訊號（舊版 judge 守門即因此誤殺所有 FB 連結）。
    """
    t = re.sub(r'^\(\d+\)\s*', '', (title or "").strip())
    t = re.sub(r'\s*\|\s*Facebook\s*$', '', t).strip()
    return t


# 貼文本體候選容器（依序嘗試）。實測（2026-09-23, share/p 永久連結頁）：
#   - div[role="article"] 會先命中側欄/河道裡「別人的貼文」→ 不可單獨使用
#   - [data-ad-rendering-role="story_message"] / [data-ad-comet-preview="message"] 命中本體（可能被 See more 截斷）
#   - 頁面 HTML 內嵌的 "message":{"text":"..."} 為完整貼文（2725 字 vs 容器 475 字）
_POST_TEXT_SELECTORS = (
    'div[data-ad-rendering-role="story_message"]',
    'div[data-ad-comet-preview="message"]',
    'div[data-ad-preview="message"]',
    'div[data-testid="post_message"]',
    'div[aria-posinset]',
)

_FB_MESSAGE_JSON_RE = re.compile(r'"message":\{"text":"((?:[^"\\]|\\.)*)"')


def _fb_post_start_from_title(title: str) -> str:
    """從 FB 頁面標題抽出貼文開頭：標題格式為「<頁面名> - <貼文開頭…> | Facebook」。"""
    t = _clean_fb_title(title)
    if " - " in t:
        t = t.rsplit(" - ", 1)[-1]
    return re.sub(r"\s+", "", t)[:12]


def _fb_html_message_texts(html: str) -> List[str]:
    """從頁面 HTML 解出所有 "message":{"text":"…"} 的完整貼文文字（含 \\uXXXX 轉義）。"""
    out: List[str] = []
    for m in _FB_MESSAGE_JSON_RE.finditer(html or ""):
        try:
            out.append(json.loads('"' + m.group(1) + '"'))
        except Exception:
            continue
    return out


def _pick_post_text(candidates: List[str], title: str) -> str:
    """挑出真正的貼文本體：優先用「與標題開頭相符」的候選，否則退回最長候選。

    FB 永久連結頁會在 DOM 先渲染側欄/河道貼文，因此不能只看順序或第一個命中；
    頁面 title 由本體貼文開頭組成，是最可靠的身分線索。
    """
    cands = [c.strip() for c in (candidates or []) if c and c.strip()]
    if not cands:
        return ""
    key = _fb_post_start_from_title(title)
    if key:
        for c in cands:
            if key in re.sub(r"\s+", "", c):
                return c
    best = max(cands, key=len)
    return best if len(best) >= 80 else ""


def get_facebook_post(url: str, timeout: int = 20) -> Optional[Dict]:
    """
    使用 Playwright 加上自動注入的 Facebook Session Cookies 抓取 FB 貼文內容
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FB Session] Playwright 模組未安裝")
        return None

    # 設定系統 DISPLAY 環境變數
    os.environ["DISPLAY"] = ":1"
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    os.environ["XAUTHORITY"] = "/run/user/1000/gdm/Xauthority"

    # 解密獲得本機 Chrome 的 FB/Messenger session cookies
    cookies = extract_facebook_cookies()
    print(f"[FB Session] 已載入 {len(cookies)} 個本機 Facebook Session Cookies")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-web-security",
                ]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.1 Safari/537.36"
            )

            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception as e:
                    print(f"[FB Session] 注入 Cookies 時警告: {e}")

            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            # 動態等待貼文容器（原本固定等 3s 純浪費；容器出現就往下走，最長仍等 4s）
            try:
                page.wait_for_selector(", ".join(_POST_TEXT_SELECTORS), state="attached", timeout=4000)
            except Exception:
                pass
            page.wait_for_timeout(1200)

            raw_title = page.title() or ""
            title = _clean_fb_title(raw_title)
            html = page.content()

            # 收集候選：① 頁面內嵌 JSON 的完整貼文 ② DOM 容器（可能被 See more 截斷）
            # 再由 _pick_post_text 以頁面 title 開頭做身分比對，避免拿到側欄別人的貼文。
            candidates: List[str] = _fb_html_message_texts(html)
            for sel in _POST_TEXT_SELECTORS:
                try:
                    loc = page.locator(sel)
                    for i in range(min(loc.count(), 5)):
                        t = (loc.nth(i).inner_text() or "").strip()
                        if t:
                            candidates.append(t)
                except Exception:
                    continue
            post_text = _pick_post_text(candidates, title)
            is_post_body = len(post_text) >= 80

            # 登入牆：以登入表單欄位為主訊號（字串比對只在必要時才做，避免抓整頁 inner_text）
            login_wall = False
            try:
                if page.locator('input[name="pass"], input[name="email"], form[action*="login"]').count() > 0:
                    login_wall = True
            except Exception:
                pass

            body_text = ""
            if not login_wall and (not is_post_body or len(post_text) < 200):
                body_text = page.locator("body").inner_text()
                if "必須登入才能繼續" in body_text or "You must log in to continue" in body_text:
                    login_wall = True
            text = post_text if is_post_body else body_text

            # 嘗試提取發布時間 (creation_time)
            publish_date = None
            try:
                match = re.search(r'"creation_time":(\d+)', html)
                if match:
                    from datetime import datetime
                    timestamp = int(match.group(1))
                    publish_date = datetime.fromtimestamp(timestamp).isoformat()
            except Exception:
                pass

            browser.close()

            if login_wall:
                print(f"[FB Session] ⚠️ 偵測到登入牆（session cookies 可能失效）({url})")

            return {
                "title": title,
                "text": text,
                "publish_date": publish_date,
                "login_wall": login_wall,
                "is_post_body": is_post_body,
            }

        except Exception as e:
            print(f"[FB Session] Playwright 擷取異常: {e}")
            return None


def extract_facebook_playwright(url: str, timeout: int = 20) -> Optional[Dict]:
    """相容舊介面"""
    return get_facebook_post(url, timeout=timeout)
