delay = function (s) {
    return new Promise(function (resolve, reject) {
        setTimeout(resolve, s);
    });
};
let table = class {
    constructor(ID, rows, lpost) {
        this.rows = rows;
        this.ID = ID;
        this.dom = document.createElement("table");
        this.dom.id = "table_" + ID;

        // add some style
        this.dom.setAttribute("class", "table table-striped");
        this.title = lpost.title;
        this.search_result = null;
        this.keywords = "default";
        //console.log("searching title...");
        this.keywords = this.keyword_extract(this.title, this);
        this.dom.innerHTML += this.keywords;


    }

    // Extract the keywords by title
    keyword_extract(title, k) {
        let xhttp = new XMLHttpRequest();
        xhttp.onreadystatechange = function () {
            if (this.readyState == 4 && this.status == 200) {
                console.log("searching completed!");
                console.log(this.responseText);
                
                return this.responseText;
            }
        };
        xhttp.open("GET", "https://na.shipaicraft.com:5005/extract?title=" + title, false);
        xhttp.send();
        return xhttp.responseText;
    }
    // async keyword_extract(title) {
    //     let text = await fetch('https://alumni.iit.tku.edu.tw:4000/extract?title='+title, {method:'GET'})
    //                         .then((responce) => {return responce.text()});
    //     return text;
    // }

    
}
