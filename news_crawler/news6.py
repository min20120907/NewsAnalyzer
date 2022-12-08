from flask import Flask, redirect, url_for, request
from News import News
from flask_cors import CORS



app = Flask(__name__)
CORS(app)
# 資料庫參數設定,注意這邊的設定要依據使用者而定
db_settings = {
    "host":"127.0.0.1",
    "port":3306,
    "user":"phpmyadmin",
    "password":"jefflin123",
    "db":"result",
    "charset":"utf8"
}

@app.route('/extract', methods = ['GET'])
def extract():
    # create news objects
    a = News(request.args.get('title'))
    # submit the News object to the mysql server
    a.submitSQL(db_settings)
    # return the results to the Flask server
    return a.toHTML()
    
if __name__ == '__main__':
    app.run(host="0.0.0.0", ssl_context=('/etc/letsencrypt/live/min20120907.asuscomm.com/fullchain.pem', '/etc/letsencrypt/live/min20120907.asuscomm.com/privkey.pem'), debug = True)

