def fcc_search(news_title_kw):
    # 以下開始必須進行fcc的查詢
    # 藉由google news來輔助事實查核
    # url='https://tfc-taiwan.org.tw/articles/8530'
    # 制約網站域名確保搜尋結果乾淨
    fcc_result=''
    site_restrict=' site:https://tfc-taiwan.org.tw/'
    query_url='https://news.google.com/search?q='+news_title_kw+site_restrict+'&hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'
    #print(query_url)
    htmlfile=requests.get(query_url,headers=headers,timeout=5)
    if htmlfile.status_code==requests.codes.ok:
        print("成功連線到google news! 帶著欲查詢字串")
    htmlfile.encoding='utf-8'

    # 對唯一的目標網站進行連接
    try:
        #開始使用bs4 解析
        url_link_list=[]
        objsoup=BeautifulSoup(htmlfile.text,"lxml")
        link=objsoup.find_all('div',{"class":"xrnccd"})
        for lk in link:
            url_link_list.append(lk.find('a')['href'])
        #print(url_link_list)

        url_link_list_remove_dot=[]
        for link in url_link_list:
            url_link_list_remove_dot.append(link.replace('./','',1))
        #print(url_link_list_remove_dot)

        # 解決短網址問題
        def shortlink_converter(url):
            resp = requests.get(url)
            return resp.url

        # 連到fcc事實查核中心
        partial_url = ''.join(url_link_list_remove_dot)
        url='https://news.google.com/'+str(partial_url)
        original_url=shortlink_converter(url)
        print("original"+original_url)
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
            fcc_result="錯誤"
            #print("錯誤!")
        elif partial_error_str in title.text:
            fcc_result="部份錯誤"
            #print("部分錯誤")
        elif real_str in title.text:
            fcc_result="事實釐清"
            #print("事實釐清")
    except:
        fcc_result='目前查無資料'
    return fcc_result
