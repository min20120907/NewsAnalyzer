import jieba
import jieba.analyse
from keybert import KeyBERT
from snownlp import SnowNLP

#只用jieba斷詞以及關鍵字榨取
doc = """
    華爾街日報」報導，俄羅斯否認烏克蘭稱俄方將放棄3月以來就奪得的札波羅熱核電廠；俄烏目前在烏東戰況仍熾，俄方有意將巴赫姆特市當「絞肉機」消耗烏軍兵力，赫松市現換烏克蘭撤離居民。
    在烏東頓內茨克（Donetsk），俄軍正費勁要奪取戰術要地巴赫姆特（Bakhmut）市，為連月來的失利止血；烏克蘭9月以來的反攻已收復東北部哈爾科夫（Kharkiv）地區大片失土及開戰之初就淪陷的南部港市赫松（Kherson）市。

烏克蘭參謀總部今天表示，俄國正準備把部署於鄰近烏北白俄斯邊界的部隊調動至烏克蘭佔領區，強化防守並阻止烏軍推進。烏克蘭國防部今晚在社群媒體Telegram表示，俄軍又開始禁止不願與俄國國營核能企業（Rosatom）簽約的烏克蘭電廠員工進入札波羅熱核電廠；烏軍則破壞札波羅熱州一聚落舊博格達尼夫卡（Starobohdanivka）附近一座鐵路橋梁，俄軍用這座橋運送武器與裝備。

烏南赫松市在淪陷8個多月後日前被烏軍收復，但現在經常遭第聶伯河（Dnipro River）對岸的俄軍砲擊；烏方雖在俄軍撤離後努力恢復市內局部電力，但市內重要民生基礎設施仍未恢復正常。本月初烏軍收復赫松市進城的歡愉場景如今已被日趨猛烈的砲擊緊張氛圍取代。先前是俄方撤離市內親俄居民，如今換烏方安排市內親烏居民撤離，當地每晚6時都有一列開往烏西的免費火車。

烏克蘭總統澤倫斯基（Volodymyr Zelenskyy）警告，烏國正因俄國更多飛彈空襲面臨艱難的一周；俄軍目標是癱瘓關鍵基礎設施打擊烏克蘭民心士氣。雖寒冬腳步逼近，烏克蘭與西方官員已對可能發生的人道災難示警，尤其烏克蘭各大城因俄軍空襲而拉長停水斷電時間，無法在氣溫下降之際供暖。

烏克蘭國防部長列茲尼科夫（Oleksiy Reznikov）今天推文指稱，俄國過去9個月來已對烏克蘭發動1萬6000次飛彈攻擊。

雖然烏克蘭聲稱俄軍有意奪取巴赫姆特，但社群媒體上有俄國傭兵組織「瓦格納集團」老闆普里格津（Yevgeny Prigozhin）受訪談話，顯示俄軍對巴赫姆特「另有打算」。

普里格津說：「巴赫姆特是一座大型、工事良好的據點，有道路、郊區和攔水壩，烏軍早做足充分準備並能頑抗。」「我們的任務並非巴赫姆特這座城本身，更非進城，而是摧毀烏軍有生力量、減少烏軍作戰潛能，這會對戰場其他地區帶來積極影響，這也是為何這裡的作戰稱為『巴赫姆特絞肉機』。」  
      """


# 斷詞
seg_list = jieba.cut(doc, cut_all=False) # cut_all 參數為 True ->全模式，預設為 False ->精確模式
seg_list="/ ".join(seg_list)
#print(seg_list)
#print(type(seg_list))


# 關鍵字榨取
tags=jieba.analyse.extract_tags(doc,topK=5,withWeight=True,allowPOS=False)
for tag in tags:
    print('word:',tag[0],'tf-idf:',tag[1])
        # 情感分析
    s=SnowNLP(tag[0])
    #print(s.words)
    #print(s.sentiments)
    if s.sentiments>=0.9:
        print("abs positive")
    elif 0.7 <= s.sentiments < 0.9: 
        print("strong positive")
    elif 0.5 < s.sentiments < 0.7:
        print("quite positive")
    elif s.sentiments==0.5:
        print("neutrality")
    elif 0.3 <= s.sentiments <0.5:
        print("quite negative")
    elif 0.1<=s.sentiments<0.3:
        print("strong negative")
    elif s.sentiments<=0.1:
        print("abs negative")
    