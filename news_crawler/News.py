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
from textblob import TextBlob

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
            self.domain_check(domain, news_url)
            # print("Checking", news_url, " at ", domain)

    # 解決短網址問題
    def shortlink_converter(self, url):
        resp = requests.get(url)
        return resp.url

    # toHTML function
    def toHTML(self):
        # print("generating html results")
        tmp = ""
        for i in range(len(self.news_title)):
            tmp += "(" + str(self.news_title[i]) + "','" + str(self.news_content[i]) + "','" + str(self.news_link[i]) + "','" + str(self.news_title_kw[i]) + "','" + str(self.news_content_kw[i]) + "','" + str(self.sentiment_analysis[i]) + "','" + str(self.Now) + ")<br>"
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
        title_kw = kw_model.extract_keywords(tags1,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推','podcast']) 
        for kw in title_kw:
            list_title_kw.append(kw[0])
        str1 = ','.join(str(x) for x in list_title_kw)
        # 抓出內文關鍵字
        tags2=" ".join(jieba.cut(content_str))
        content_kw = kw_model.extract_keywords(tags2,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推','podcast']) 
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
                sentiment_result = 'abs positive'
                ## print("abs positive")
            elif 0.7 <= average < 0.9:
                sentiment_result = 'strong positive'
                ## print("strong positive")
            elif 0.5 < average < 0.7:
                sentiment_result = 'quite positive'
                ## print("quite positive")
            elif average == 0.5:
                sentiment_result == 'neutrality'
                # # print("neutrality")
            elif 0.3 <= average < 0.5:
                sentiment_result = 'quite negative'
                ## print("quite negative")
            elif 0.1 < average < 0.3:
                sentiment_result = 'strong negative'
                ## print("strong negative")
            elif average <= 0.1:
                sentiment_result = 'abs negative'
                ## print("abs negative")
            else:
                sentiment_result = 'error occur'
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

        match domain:
            case 'chinatimes.com':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('chinatimes ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "article-title"})
                # print('新聞標題: ', title.text)
                # print("文章內容: ")
                contents = objsoup.find_all('p')
                for content in contents:
                    if content.text in ban_set:
                        pass
                    else:
                        # print(content.text)
                        content_str += content.text
                news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                    title.text, content_str)
                
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'cna.com.tw':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('cna ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1')
                # print("新聞標題: ", title.text)
                contents = objsoup.find_all('p')
                # print("文章內容: ")
                for content in contents:
                    if content.text in ban_set:
                        pass
                    else:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'ettoday.net':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('ettoday ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "title"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find(
                    'div', attrs={"class": "story"}).find_all('p')
                for content in contents:
                    if content.text in ban_set:
                        break
                    else:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'ltn.com.tw':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('ltn ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1')
                # print("新聞標題: ", title.text)
                contents = objsoup.find(
                    'div', {"class": "text boxTitle boxText"}).find_all('p')
                # print("文章內容: ")
                for content in contents:
                    if content.text in ban_set:
                        break
                    else:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'news.pts':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('news.pts ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "article-title"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find_all('p')
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'newtalk.tw':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('newtalk ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "content_title"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find(
                    'div', {"id": "news_content"}).find_all('p')
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'setn.com':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('setn ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "news-title-3"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find_all('p')
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", self.news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'thenewslens.com':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('thenewslens ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "article-title"})
                # print("新聞標題: ", title.text)
                contents = objsoup.find(
                    'div', {"class": "article-content AdAsia"}).find_all('p')
                # print("文章內容: ")
                for content in contents:
                    if content.text in ban_set:
                        pass
                    else:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'udn.com':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('udn.com ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                try:
                    title = objsoup.find(
                        'h1', {"class": "article-content__title"})
                    # 印出title的文字
                    # print("新聞標題: ", title.text)
                    contents = objsoup.find(
                        'div', {"class": "article-content__paragraph"}).find_all('p')
                    # print("文章內容: ")
                    for content in contents:
                        # print(content.text.strip())
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)

                    self.news_title.append(title.text)
                    # print("THE RESULT: ", title.text)
                    self.news_content.append(content_str)
                    # print("THE RESULT: ", content_str)
                    self.news_link.append(news_url)
                    # print("THE RESULT: ", news_url)
                    self.news_title_kw.append(news_title_kw)
                    # print("THE RESULT: ", news_title_kw)
                    self.news_content_kw.append(news_content_kw)
                    # print("THE RESULT: ", news_content_kw)
                    self.sentiment_analysis.append(sentiments_analysis)
                    # print("THE RESULT: ", sentiments_analysis)
                    # print(news_title_kw, news_content_kw, sentiments_analysis)
                except:  # 經濟日報
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('money udn ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find(
                        'div', {"class": "article-layout-wrapper"}).find('h1')
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find(
                        'section', {"class": "article-body__editor"}).find_all('p')
                    for content in contents:
                        # print(content.text.strip())
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.news_title.append(title.text)
                    # print("THE RESULT: ", title.text)
                    self.news_content.append(content_str)
                    # print("THE RESULT: ", content_str)
                    self.news_link.append(news_url)
                    # print("THE RESULT: ", news_url)
                    self.news_title_kw.append(news_title_kw)
                    # print("THE RESULT: ", news_title_kw)
                    self.news_content_kw.append(news_content_kw)
                    # print("THE RESULT: ", news_content_kw)
                    self.sentiment_analysis.append(sentiments_analysis)
                    # print("THE RESULT: ", sentiments_analysis)
                    # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'yahoo.com':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('yahoo.com ok')
                try:
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find(
                        'header', {"class": "caas-header"}).find('h1')
                    # print("新聞標題: ", title.text)
                    contents = objsoup.find(
                        'div', {"class": "caas-body"}).find_all('p')
                    # print("文章內容: ")
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        elif content.text in break_set:
                            break
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.news_title.append(title.text)
                    # print("THE RESULT: ", title.text)
                    self.news_content.append(content_str)
                    # print("THE RESULT: ", content_str)
                    self.news_link.append(news_url)
                    # print("THE RESULT: ", news_url)
                    self.news_title_kw.append(news_title_kw)
                    # print("THE RESULT: ", news_title_kw)
                    self.news_content_kw.append(news_content_kw)
                    # print("THE RESULT: ", news_content_kw)
                    self.sentiment_analysis.append(sentiments_analysis)
                    # print("THE RESULT: ", sentiments_analysis)
                    # print(news_title_kw, news_content_kw, sentiments_analysis)
                except:
                    # print(news_url)
                    try:
                        title = objsoup.find(
                            'h1', {"data-test-locator": "headline"})
                        # print("新聞標題: ", title.text)
                        contents = objsoup.find(
                            'div', {"class": "caas-body"}).find_all('p')
                        # print("文章內容: ")
                        for content in contents:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                        self.news_title.append(title.text)
                        # print("THE RESULT: ", title.text)
                        self.news_content.append(content_str)
                        # print("THE RESULT: ", content_str)
                        self.news_link.append(news_url)
                        # print("THE RESULT: ", news_url)
                        self.news_title_kw.append(news_title_kw)
                        # print("THE RESULT: ", news_title_kw)
                        self.news_content_kw.append(news_content_kw)
                        # print("THE RESULT: ", news_content_kw)
                        self.sentiment_analysis.append(sentiments_analysis)
                        # print("THE RESULT: ", sentiments_analysis)
                        # print(news_title_kw, news_content_kw, sentiments_analysis)
                    except:
                        # print(news_url)
                        try:
                            objsoup = BeautifulSoup(res.text, 'lxml')
                            title = objsoup.find(
                                'h1', {"class": "Fz(24px) Fw(b)"})
                            # print("新聞標題: ", title.text)
                            contents = objsoup.find(
                                'div', {"class": "Mt(12px) Fz(16px) Lh(1.5) C(#464e56) Whs(pl)"})
                            # print("文章內容: ")
                            for content in contents:
                                # print(contents.text)
                                content_str += content.text
                                news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                    title.text, content_str)
                            self.news_title.append(title.text)
                            # print("THE RESULT: ", title.text)
                            self.news_content.append(content_str)
                            # print("THE RESULT: ", content_str)
                            self.news_link.append(news_url)
                            # print("THE RESULT: ", news_url)
                            self.news_title_kw.append(news_title_kw)
                            # print("THE RESULT: ", news_title_kw)
                            self.news_content_kw.append(news_content_kw)
                            # print("THE RESULT: ", news_content_kw)
                            self.sentiment_analysis.append(sentiments_analysis)
                            # print("THE RESULT: ", sentiments_analysis)
                            # print(news_title_kw, news_content_kw, sentiments_analysis)
                        except:
                            pass
                            # print(news_url)
            case 'rfi.fr':
                content_str = ''
                res = requests.get(news_url, headers=headers)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print("rfi.fr ok")
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('article').find('h1')
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find('article').find(
                    'div', {"class": "t-content__body u-clearfix"}).find_all('p')
                for content in contents:
                    if content.text in ban_set:
                        pass
                    else:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'rti.org.tw':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('rti.org.tw ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find(
                    'section', {"class": "news-detail-box"}).find('h1')
                title=title.text.replace(' 用Podcast訂閱本節目 ','').strip()
                # print("新聞標題: ",title)
                # print("文章內容: ")
                contents = objsoup.find('article').find_all('p')
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title, content_str)
                self.news_title.append(title)
                # print("THE RESULT: ", title)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'storm.mg':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('storm.mg ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"id": "article_title"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find(
                    'div', {"id": "CMS_wrapper"}).find_all('p')
                for content in contents:
                    if content.text in ban_set:
                        pass
                    elif '更多風傳媒報導' in content.text:
                        break
                    else:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'bbc.com':
                content_str = ''
                res = requests.get(news_url)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('bbc.com ok')
                try:
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find(
                        'h1', {"class": "bbc-1tk77pb e1p3vdyi0"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all('p')
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.news_title.append(title.text)
                    # print("THE RESULT: ", title.text)
                    self.news_content.append(content_str)
                    # print("THE RESULT: ", content_str)
                    self.news_link.append(news_url)
                    # print("THE RESULT: ", news_url)
                    self.news_title_kw.append(news_title_kw)
                    # print("THE RESULT: ", news_title_kw)
                    self.news_content_kw.append(news_content_kw)
                    # print("THE RESULT: ", news_content_kw)
                    self.sentiment_analysis.append(sentiments_analysis)
                    # print("THE RESULT: ", sentiments_analysis)
                    # print(news_title_kw, news_content_kw, sentiments_analysis)
                except:
                    # print("error link at: ", news_url)
                    title = objsoup.find(
                        'strong', {"class": "ewk8wmc0 bbc-uky4hn eglt09e1"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all('p')
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.news_title.append(title.text)
                    # print("THE RESULT: ", title.text)
                    self.news_content.append(content_str)
                    # print("THE RESULT: ", content_str)
                    self.news_link.append(news_url)
                    # print("THE RESULT: ", news_url)
                    self.news_title_kw.append(news_title_kw)
                    # print("THE RESULT: ", news_title_kw)
                    self.news_content_kw.append(news_content_kw)
                    # print("THE RESULT: ", news_content_kw)
                    self.sentiment_analysis.append(sentiments_analysis)
                    # print("THE RESULT: ", sentiments_analysis)
                    # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'mirrormedia.mg':  # 鏡週刊
                content_str = ''
                res = requests.get(news_url, headers=headers)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print("mirrormedia.mg ok")
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "story__title"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find_all(
                    'p', attrs={"class": "g-story-paragraph"})
                for content in contents:
                    if '更多內容，歡迎鏡週刊紙本雜誌、鏡週刊數位訂閱、了解內容授權資訊。' in content.text:
                        break
                    else:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
                content_str = ''
                res = requests.get(news_url, headers=headers)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('nytimes.com ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find(
                    'div', {"class": "article-header"}).find('h1')
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find_all(
                    'div', {"class": "article-paragraph"})
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
                content_str = ''
                res = requests.get(news_url, headers=headers)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('wsj.com ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "wsj-article-headline"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find(
                    'div', {"class": "wsj-snippet-body"}).find_all('p')
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case'cw.com.tw':
                content_str = ''
                res = requests.get(news_url, headers=headers)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('cw.com.tw ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find(
                    'div', {"class": "article__head"}).find('h1')
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find(
                    'div', {"class": "article__content py20"}).find_all('p')
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'epochtimes.com':  # 大紀元
                content_str = ''
                res = requests.get(news_url, headers=headers)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('epochtimes.com ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "title"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find('div', {"id": "artbody"}).find_all('p')
                for content in contents:
                    # print(content.text)
                    content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'nytimes.com':  # 紐約時報
                content_str = ''
                res = requests.get(news_url, headers=headers)
                res.encoding = 'utf-8'
                if res.status_code == requests.codes.ok:
                    pass
                    # print('nytimes.com ok')
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find(
                    'div', {"class": "article-header"}).find('h1')
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find_all(
                    'div', {"class": "article-paragraph"})
                for content in contents:
                    # print(content.text)
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case 'wsj.com':  # 半島電視台
                content_str = ''
                res = requests.get(news_url, headers=headers)
                if res.status_code == requests.codes.ok:
                    pass
                    # print('wsj.com ok')
                res.encoding = 'utf-8'
                objsoup = BeautifulSoup(res.text, 'lxml')
                title = objsoup.find('h1', {"class": "wsj-article-headline"})
                # print("新聞標題: ", title.text)
                # print("文章內容: ")
                contents = objsoup.find(
                    'div', {"class": "wsj-snippet-body"}).find_all('p')
                for content in contents:
                    # print(content.text)
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                self.news_title.append(title.text)
                # print("THE RESULT: ", title.text)
                self.news_content.append(content_str)
                # print("THE RESULT: ", content_str)
                self.news_link.append(news_url)
                # print("THE RESULT: ", news_url)
                self.news_title_kw.append(news_title_kw)
                # print("THE RESULT: ", news_title_kw)
                self.news_content_kw.append(news_content_kw)
                # print("THE RESULT: ", news_content_kw)
                self.sentiment_analysis.append(sentiments_analysis)
                # print("THE RESULT: ", sentiments_analysis)
                # print(news_title_kw, news_content_kw, sentiments_analysis)
            case _:
                return "url missing!"
