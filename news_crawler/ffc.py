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

# 假設使用者瀏覽這篇不知道真假的新聞
# 抓取未知新聞標題關鍵字
list_title_kw=[]
title='''錯誤】網傳「寒流特報 今天5日(週二)氣溫開始下降到14°C 6日(週三)12°C 7日(週四) 7C 8日(週五)7°C 9日(週六) 9°C」？'''
title_cut=" ".join(jieba.cut(title))
kw_model = KeyBERT(model='paraphrase-multilingual-MiniLM-L12-v2')
title_kw = kw_model.extract_keywords(title_cut,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推','podcast']) 
for kw in title_kw:
    list_title_kw.append(kw[0])
title_kw = ','.join(str(x) for x in list_title_kw)
print(title_kw)

# 抓取未知新聞的標題關鍵字是 -> 氣溫,寒流,7c,週二,週三



# 以下開始必須進行fcc的查詢
# 藉由google news來輔助事實查核
# url='https://tfc-taiwan.org.tw/articles/8530'
# 制約網站域名確保搜尋結果乾淨
site_restrict=' site:https://tfc-taiwan.org.tw/'
query_url='https://news.google.com/search?q='+title_kw+site_restrict+'&hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'
print(query_url)
htmlfile=requests.get(query_url,headers=headers,timeout=5)
if htmlfile.status_code==requests.codes.ok:
    print("成功連線到google news! 帶著欲查詢字串")
htmlfile.encoding='utf-8'

# 對唯一的目標網站進行連接

#開始使用bs4 解析
url_link_list=[]
objsoup=BeautifulSoup(htmlfile.text,"lxml")
link=objsoup.find_all('div',{"class":"xrnccd"})
for lk in link:
    url_link_list.append(lk.find('a')['href'])
print(url_link_list)

url_link_list_remove_dot=[]
for link in url_link_list:
    url_link_list_remove_dot.append(link.replace('./','',1))
print(url_link_list_remove_dot)

# 解決短網址問題
def shortlink_converter(url):
    resp = requests.get(url)
    return resp.url


# 連到fcc事實查核中心
partial_url = ''.join(url_link_list_remove_dot)
url='https://news.google.com/'+str(partial_url)
original_url=shortlink_converter(url)
htmlfile=requests.get(original_url,headers=headers,timeout=5)
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

