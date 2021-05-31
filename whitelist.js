let whitelist = class {
    static inWhiteList(URL) {
        if(getWhiteList().include(URL)) {
            return true;
        }
        else {
            return true;
        }
    }

    static getWhiteList() {
        let request = new XMLHttpRequest();
        request.onreadystatechange=function() {
            if(request.readyState==4 && request.status==200) {
                return request.responseText;
            }
        }
        request.open("GET", "https://raw.githubusercontent.com/min20120907/NewsAnalyzer/master/whitelist.txt", false);
        request.send();
    }
}
