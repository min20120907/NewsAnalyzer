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



    }

    // The function to fetch the search results
    fetch_results() {
        for (let i = 0; i < this.rows; i++) {
            // initialize the structure
            let tr_ele = document.createElement("tr");
            let data = document.createElement("div");
            let title_elem = document.createElement("a");

            title_elem.innerText = this.search_result[i].title;
            title_elem.href = this.search_result[i].link;
            //console.log(this.search_result[i].link);
            let icon_elem = new icon(this.search_result[i].link).dom;
            data.appendChild(icon_elem);
            data.appendChild(title_elem);
            tr_ele.appendChild(data);
            this.tbody.appendChild(tr_ele);
            this.dom.appendChild(this.tbody);
        }
        this.dom.appendChild(this.tbody);
    }
    // Extract the keywords by title
    keyword_extract(title, k) {
        let xhttp = new XMLHttpRequest();
        xhttp.onreadystatechange = function () {
            if (this.readyState == 4 && this.status == 200) {
                // console.log(this.responseText);
                k.keywords = this.responseText;
                k.searchGoogle(this.responseText.replaceAll("//", " "), k);

                //console.log("searching completed!");
                return this.responseText;
            }
        };
        xhttp.open("GET", "https://min20120907.asuscomm.com:4000/extract?title=" + title, false);
        xhttp.send();
        return xhttp.responseText;
    }
    // async keyword_extract(title) {
    //     let text = await fetch('https://alumni.iit.tku.edu.tw:4000/extract?title='+title, {method:'GET'})
    //                         .then((responce) => {return responce.text()});
    //     return text;
    // }

    // The funciton that one can fetch the top 10 Google Results
    searchGoogle(keywords, outerThis) {	//searchGoogle
        // another keys

        let searchUrl = "https://min20120907.asuscomm.com/google-api-php-client-unlimited/example.php?q=" + keywords + "&num=" + this.rows;
        $(document).ready(function () {
            $.ajax({
                type: "GET",
                url: searchUrl,
                async: false,
                headers: {
                    "x-requested-with": "xhr"
                },
                mode: 'json',
                cache: 'default',
                success: function (text) {
                    //console.log(JSON.parse(text));
                    // assign the result to website element
                    outerThis.search_result = JSON.parse(text);
                    //console.log(outerThis.search_result);
                    outerThis.tbody = document.createElement("tbody");
                    outerThis.fetch_results();
                    return text;
                },
                error: function (text) {
                    console.log(text);
                }
            });
        });
    }
}
