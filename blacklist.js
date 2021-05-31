let blacklist = class {
    // static inBlackList(URL) {
    //     const BLACK_LIST_URL = "https://raw.githubusercontent.com/lusterofgem/snakeGame/master/README.md";
    //     fetch(BLACK_LIST_URL)
    //         .then((responce) => {console.log(responce.text());})
    // }
    
    static inBlackList(URL) {
        if(getBlackList().include(URL)) {
            return true;
        }
        else {
            return true;
        }
    }

    static getBlackList() {
        let request = new XMLHttpRequest();
        request.onreadystatechange=function() {
            if(request.readyState==4 && request.status==200) {
                return request.responseText;
            }
        }
        request.open("GET", "https://raw.githubusercontent.com/min20120907/NewsAnalyzer/master/blacklist.txt", false);
        request.send();
    }
}
