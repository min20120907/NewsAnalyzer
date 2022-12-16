import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tldextract import tldextract
import datetime
import pymysql
import jieba
import jieba.analyse
from snownlp import SnowNLP
from keybert import KeyBERT
import threading

# 設定fake-useragent
# 假的user-agent,產生 headers
ua = UserAgent()
usar = ua.random  # 產生header 字串

headers = {'user-agent': usar}

# Get the current datetime


class News:
    # The constructor of the object News
    def __init__(self, title):
        self.Now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        model = KeyBERT('LaBSE')
        splitted_title = " ".join(jieba.cut(title))
        # initialize the keyword extraction model
        keywords = model.extract_keywords(splitted_title, stop_words=[',', '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-',
                                          '_', '＿', '——', '－', '-', '−', '我', '你', '妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推'])
        keywords_str = " ".join([i[0] for i in keywords])
        # send the query into Google News
        same_url = 'https://news.google.com/search?q=' + \
            keywords_str+'&hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'
        # print("sending query to google news...", keywords_str)
        self.htmlfile = requests.get(same_url, headers=headers, timeout=5)

        # The source title, keywords which is from the extension in Facebook link posts.
        self.src_title = title
        self.src_keywords = keywords_str
        # The result of the news that fetched from Google News.
        self.news_title = []
        self.news_content = []
        self.news_link = []
        # The results of Keyword Extraction
        self.news_title_kw = []
        self.news_content_kw = []
        # The results of sentiment analysis
        self.sentiment_analysis = []
        # The domain of the news
        self.domain = []
        # 開始使用bs4解析
        objsoup = BeautifulSoup(self.htmlfile.text, "lxml")

        # 取得objsoup所有的文字
        # # print(objsoup.get_text())

        # 找到所有google新聞的link
        self.url_link_list = []
        h3_all_links = objsoup.find_all(
            'h3', {"class": "ipQwMb ekueJc RD0gLb"})
        for counter, h3_all_link in enumerate(h3_all_links):
            # # print(h3_all_link.text)
            self.url_link_list.append(h3_all_link.find('a')['href'])
            if counter >= 11:
                break

        # 把link拿出來看看
        # print("The length of list: ", len(self.url_link_list))
        self.url_link_list_remove_dot = []
        for link in self.url_link_list:
            self.url_link_list_remove_dot.append(link.replace('./', '', 1))
        t = []
        # 連到多家新聞媒體
        for link in self.url_link_list_remove_dot:
            url = 'https://news.google.com/'+str(link)
            original_url = self.shortlink_converter(url)
            res = requests.get(original_url, headers=headers, timeout=10)
            # if res.status_code==requests.codes.ok:
            #    # print('ok')

            # 判斷連到的是哪個domain,以抓去特定媒體的內文tag
            news_url = res.request.url  # 特定新聞媒體的url
            # 解析domain
            tld_result = tldextract.extract(news_url)
            domain = '{}.{}'.format(tld_result.domain, tld_result.suffix)
            # Single thread
            # self.domain_check(domain, news_url)
            # Multi-threading
            t.append(threading.Thread(target=self.domain_check, args=(domain, news_url)))
            # print("Checking", news_url, " at ", domain)
        
        for thread in t:
            thread.start()
        for thread in t:
            thread.join()
        

    # 解決短網址問題
    def shortlink_converter(self, url):
        resp = requests.get(url)
        return resp.url

    # toHTML function
    def toHTML(self):
        # print("generating html results")
        tmp = "<table>"
        # Add table headers
        tmp += "<tr><th>新聞標題</th><th>新聞標題關鍵字</th><th>新聞內文關鍵字</th><th>情感分析</th></tr>"
        for i in range(len(self.news_title)):
            tmp += "<tr>"
            # Add table cells for each news item
            tmp += "<td><img src='http://www.google.com/s2/favicons?domain=" + str(self.news_link[i]) + "' />" + "<a href='" + str(self.news_link[i]) + "'>" + str(self.news_title[i]) + "</a></td>"
            tmp += "<td>" + str(self.news_title_kw[i]) + "</td>"
            tmp += "<td>" + str(self.news_content_kw[i]) + "</td>"
            tmp += "<td>" + str(self.sentiment_analysis[i]) + "</td>"
            tmp += "</tr>"
        tmp += "</table>"
        return tmp

    # The function to submit the results

    def submitSQL(self, db_settings):

        # establish the connection by the argument "db_settings"
        db = pymysql.connect(**db_settings)
        # 建立操作游標
        cursor = db.cursor()
        for i in range(len(self.news_title)):
            # SQL語法      news_title_kw,news_content_kw,
            sql = "INSERT INTO news_titles_contents(ID,news_title,news_content,news_link,news_title_kw,news_content_kw,sentiment_analysis,createdDate, post_title, post_kw) VALUES ('0','" + str(self.news_title[i]) + "','" + str(
                    self.news_content[i]) + "','" + str(self.news_link[i]) + "','" + str(self.news_title_kw[i]) + "','" + str(self.news_content_kw[i]) + "','" + str(self.sentiment_analysis[i]) + "','" + str(self.Now) + "', '"+str(self.src_title)+"', '"+str(self.src_keywords)+"')"
            # 執行語法
            try:
                cursor.execute(sql)
                # 提交修改
                db.commit()
                # # print('success')
            except Exception as ex:
                # 發生錯誤時停止執行SQL
                db.rollback()
                # print('error')
                # print(ex)
        # 關閉連線
        db.close()

    # 新聞標題以及內文斷詞,並回傳positive還是negative
    # 關鍵字榨取與情感分析
    def kw(self, title, content_str):
        # 關鍵字榨取
        list_title_kw=[]
        list_content_kw=[]
        list_sentiment=[]
        sentiment_result="undefined"
        # 抓出標題關鍵字
        tags1=" ".join(jieba.cut(title))
        kw_model = KeyBERT(model='paraphrase-multilingual-MiniLM-L12-v2')
        title_kw = kw_model.extract_keywords(tags1,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推','podcast','啊啊']) 
        for kw in title_kw:
            list_title_kw.append(kw[0])
        str1 = ','.join(str(x) for x in list_title_kw)
        # 抓出內文關鍵字
        tags2=" ".join(jieba.cut(content_str))
        content_kw = kw_model.extract_keywords(tags2,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推','podcast','啊啊']) 
        for kw in content_kw:
            list_content_kw.append(kw[0]) 
            s=SnowNLP(kw[0]) # 把內文關鍵字丟入情感分析
            list_sentiment.append(s.sentiments) # 把結果串接起來
        str2 = ','.join(str(x) for x in list_content_kw)
        # 判斷新聞內文關鍵字是正面還是負面
        total = 0
        for r in list_sentiment:
            total += r
            average = total/len(list_sentiment)
            if average >= 0.9:
                sentiment_result = '絕對正面'
                ## print("abs positive")
            elif 0.7 <= average < 0.9:
                sentiment_result = '極度正面'
                ## print("strong positive")
            elif 0.5 < average < 0.7:
                sentiment_result = '相對正面'
                ## print("quite positive")
            elif average == 0.5:
                sentiment_result == '中立'
                # # print("neutrality")
            elif 0.3 <= average < 0.5:
                sentiment_result = '相對負面'
                ## print("quite negative")
            elif 0.1 < average < 0.3:
                sentiment_result = '極度負面'
                ## print("strong negative")
            elif average <= 0.1:
                sentiment_result = '絕對負面'
                ## print("abs negative")
            else:
                sentiment_result = '錯誤發生'
                ## print("error occur")
        return str1, str2, sentiment_result
    # The funciton to fetch the URL and the domain

    # Main function to fetch the news
    def domain_check(self, domain, news_url):
        # ban strings
        ban_set = {"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。", "圖像來源，Reuters", "中時新聞網對留言系統使用者發布的文字、圖片或檔案保有片面修改或移除的權利。當使用者使用本網站留言服務時，表示已詳細閱讀並完全了解，且同意配合下述規定：", "違反上述規定者，中時新聞網有權刪除留言，或者直接封鎖帳號！請使用者在發言前，務必先閱讀留言板規則，謝謝配合。", "本網站之文字", "本網站之文字、圖片及影音，非經授權，不得轉載、公開播送或公開傳輸及利用。", "省錢大作戰！超夯優惠等你GO",
                   "請繼續往下閱讀...", "不用抽 不用搶 現在用APP看新聞 保證天天中獎", "Photo Credit:", "每月一杯咖啡的金額，支持優質觀點的誕生，享有更好的閱讀體驗。", "本文經《BBC News 中文》授權轉載，原文發表於此", "更多 TVBS 報導", "更多相關新聞,'相關新聞影音", '圖／TVBS', '圖像來源，NCA', '原始連結', '點我看更多華視新聞＞＞＞', '圖像來源，Getty Images', '相關新聞影音', '[啟動LINE推播] 每日重大新聞通知', '下載法廣應用程序跟蹤國際時事'}
        # break string
        break_set = {'點我看更多華視新聞＞＞＞', '更多風傳媒報導', '更多 TVBS 報導'}

        def process_news(news_url, ban_set):
            content_str = ''
            res = requests.get(news_url)
            res.encoding = 'utf-8'
            if res.status_code == requests.codes.ok:
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1')
                contents = objsoup.find_all('p')
                for content in contents:
                    if content.text in ban_set:
                        pass
                    else:
                        content_str += content.text
            return self.kw(title.text, content_str)

        if domain == 'chinatimes.com':
            news_title_kw, news_content_kw, sentiments_analysis = process_news(news_url, ban_set)
        elif domain == 'cna.com.tw':
            news_title_kw, news_content_kw, sentiments_analysis = process_news(news_url, ban_set)
        elif domain == 'ettoday.net':
            res = requests.get(news_url)
            res.encoding = 'utf-8'
            if res.status_code != requests.codes.ok:
                return
            objsoup = BeautifulSoup(res.text, 'lxml')
            title = objsoup.find('h1', {"class": "title"})
            contents = objsoup.find('div', attrs={"class": "story"}).find_all('p')
            content_str = ''
            for content in contents:
                if content.text in ban_set:
                    break
                content_str += content.text
            news_title_kw, news_content_kw, sentiments_analysis = self.kw(title.text, content_str)
        elif domain == 'ltn.com.tw':
            news_title_kw, news_content_kw, sentiments_analysis = process_news(news_url, ban_set)
        elif domain == 'news.pts':
            news_title_kw, news_content_kw, sentiments_analysis = process_news(news_url, ban_set)
        elif domain == 'udn.com':
            news_title_kw, news_content_kw, sentiments_analysis = process_news(news_url, ban_set)

        self.news_title.append(title.text)
        self.news_content.append(content_str)
        self.news_link.append(news_url)
        self.news_title_kw.append(news_title_kw)
        self.news_content_kw.append(news_content_kw)
        self.sentiment_analysis.append(sentiments_analysis)
