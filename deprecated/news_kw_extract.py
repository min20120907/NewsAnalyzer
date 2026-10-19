from keybert import KeyBERT
import jieba
from textblob import TextBlob
from flask import Flask, redirect, url_for, request

app = Flask(__name__)


jieba.set_dictionary("dict.txt.big")
@app.route('/extract', methods = ['GET'])
def extract():
    model = KeyBERT('LaBSE')
    title = request.args.get('title')
    keywords = []
    lang = TextBlob(title)
    splitted_title = " ".join(jieba.cut(title))
    print("The Title is:\n",splitted_title)
    # Depricated Keyword Extraction: KeyBERT 
    keywords = model.extract_keywords(splitted_title,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推']) 
    return " ".join([i[0] for i in keywords])

if __name__ == '__main__':
    app.run(debug = True)

