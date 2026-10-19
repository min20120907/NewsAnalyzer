import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tldextract import tldextract
import datetime
import pymysql
import jieba
from keybert import KeyBERT
from snownlp import SnowNLP
# 設定fake-useragent
# 假的user-agent,產生 headers
ua=UserAgent()
usar=ua.random #產生header 字串
headers={'user-agent':usar}
url='https://tfc-taiwan.org.tw/articles/8530'
htmlfile=requests.get(url,headers=headers,timeout=5)
if htmlfile.status_code==requests.codes.ok:
    print("成功連線到fcc")
htmlfile.encoding='utf-8'

#開始使用bs4 解析
objsoup=BeautifulSoup(htmlfile.text,"lxml")
title=objsoup.find('h2',{"class":"node-title"})
print(title.text)
error_str='錯誤'
partial_error_str='部份錯誤'
real_str='事實釐清'
if error_str in title.text:
    print("錯誤!")
elif partial_error_str in title.text:
    print("部分錯誤")
elif real_str in title.text:
    print("事實釐清")
else:
    print("目前查無資料")

