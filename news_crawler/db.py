import pymysql


# 資料庫參數設定
db_settings = {
    "host":"127.0.0.1",
    "port":3306,
    "user":"phpmyadmin",
    "password":"jefflin123",
    "db":"result",
    "charset":"utf8"
}

try:
    # 建立Connection物件
    conn = pymysql.connect(**db_settings)
    print("connect success")
    # 建立Cursor物件
    with conn.cursor() as cursor:

        # 新增資料SQL語法
        command = "INSERT INTO charts(id,news_title,news_content)VALUES(%d, %s, %s)"
        charts=['12']
        for chart in charts:
            cursor.execute(command, (chart["id"]))
    # 儲存變更
        conn.commit()
except Exception as ex:
    print(ex)
# 與資料庫的連線建立完成後，要進行相關的操作，
# 需要建立Cursor(指標)物件來執行，這邊使用Python的with陳述式，當資料庫存取完成後，自動釋放連線
