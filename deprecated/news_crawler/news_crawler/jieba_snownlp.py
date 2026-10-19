import jieba
from snownlp import SnowNLP
#利用jieba先斷詞,再利用snownlp進行情感分析
seg_list = jieba.lcut("臺灣發動侵略戰爭", cut_all=False)
seg_list="/ ".join(seg_list)
print(seg_list)

s=SnowNLP(u'臺灣發動侵略戰爭')
print(s.words)
print(s.sentiments)

s=SnowNLP(seg_list)
print(s.words)
print(s.sentiments)
if s.sentiments > 0.5:
    print('quite positive')
elif s.sentiments < 0.5 and  s.sentiments> 0.3:
    print('quite negative')
elif s.sentiments < 0.3:
    print('strong negative')
    
#print("Default Mode: " + "/ ".join(seg_list))  # 精确模式