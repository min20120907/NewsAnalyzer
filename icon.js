let icon = class{
    constructor(search_result) {
        this.dom = document.createElement("img");
        this.dom.src = "http://i.olsh.me//icon?url=" +
                         getLink(search_result.getElementsByTagName("A")[0].href).hostname + 
                         "&size=80..120..200";
        this.dom.width = 24;	//set width as 24
        this.dom.height = 24;	//set height as 24
        this.dom.style.position = "relative";
    }
    // The function to get link
    getLink(href) {
        let l = document.createElement("a");
        l.href = href;
        return l;
    }
}