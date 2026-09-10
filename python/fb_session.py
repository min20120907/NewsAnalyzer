#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Session 管理模組
自動從本機 Chrome Profile (~/.config/google-chrome/Default/Cookies) 解密並注入 Facebook/Messenger session cookies
不需要使用者手動輸入帳密或開啟視窗登入
"""

import os
import re
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
            page.wait_for_timeout(3000)

            title = page.title()
            text = page.locator("body").inner_text()
            html = page.content()

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

            # 判斷是否為無效或阻擋內容
            if "必須登入才能繼續" in text or "登入 Facebook" in text and len(text) < 300:
                print(f"[FB Session] 頁面提示需要登入或內容受限 ({url})")

            return {
                "title": title,
                "text": text,
                "publish_date": publish_date
            }

        except Exception as e:
            print(f"[FB Session] Playwright 擷取異常: {e}")
            return None


def extract_facebook_playwright(url: str, timeout: int = 20) -> Optional[Dict]:
    """相容舊介面"""
    return get_facebook_post(url, timeout=timeout)
