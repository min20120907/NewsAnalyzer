import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
from tldextract import tldextract
from urllib import request
from requests import get
import urllib3
#設定fake-useragent
#假的user-agent,產生 headers
ua=UserAgent()
usar=ua.random #產生header 字串
headers={'user-agent':usar}
#if key words are 烏克蘭 戰爭 俄羅斯
keywords="烏克蘭 戰爭 俄羅斯"
url='https://news.google.com/topstories?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
same_url='https://news.google.com/search?q='+keywords+'&hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'
htmlfile=requests.get(same_url,headers=headers,timeout=3)#他這邊請求website後,得到一個物件

if htmlfile.status_code==requests.codes.ok:
    print("成功連線到google news with keywords")
htmlfile.encoding='utf-8'
