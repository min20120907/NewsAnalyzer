import pymysql
news_url='https://www.rfi.fr/tw/%E6%AD%90%E6%B4%B2/20221208-%E9%96%83%E9%9B%BB%E6%8B%BF%E4%B8%8B%E7%83%8F%E5%85%8B%E8%98%AD%E5%A4%A2%E7%A2%8E-%E6%99%AE%E4%BA%AC%E6%89%BF%E8%AA%8D%E9%99%B7%E5%85%A5%E6%88%B0%E7%88%AD%E6%B3%A5%E6%B7%96'
# check db before start to search
def check_db(news_url):
    # 資料庫參數設定
    db_settings = {
        "host":"127.0.0.1",
        "port":3306,
        "user":"phpmyadmin",
        "password":"1234",
        "db":"result",
        "charset":"utf8"
    }
    # 需要建立Cursor(指標)物件來執行，這邊使用Python的with陳述式，當資料庫存取完成後，自動釋放連線
    # 建立Connection物件
    conn = pymysql.connect(**db_settings)
    # 建立Cursor物件
    with conn.cursor() as cursor:
        # 查詢資料SQL語法
        sql = "SELECT news_link FROM news_titles_contents" # 檢查以前有沒有查過
        # 執行指令
        cursor.execute(sql)
        # 取得所有資料
        result_news_link = cursor.fetchall()
        
        for news in result_news_link:
            if news_url == news:
                sql = "SELECT * FROM news_titles_contents WHERE news_link,createdDate NOT IN (SELECT news_link,createdDate FROM news_titles_contents) WHERE news_link = news_url"
            else:
                print("error occur")

result=check_db(news_url)

