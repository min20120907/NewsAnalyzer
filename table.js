let table = class {
    constructor(ID, rows, lpost) {
        this.rows = rows
        this.ID = ID;
        this.dom = document.createElement("table");
        this.dom.id = "table_" + ID;
        // add some style
        this.dom.setAttribute("class", "table table-striped");
        this.title = lpost.title;
        let delay = function (s) {
            return new Promise(function (resolve, reject) {
                setTimeout(resolve, s);
            });
        };
        delay().then(function () {
            return delay(3000); // 延遲3秒
        }).then(function () {
            this.resultContent = this.searchGoogle(this.keyword_extract(this.title));
        });
        this.page = new website(this.ID, this.resultContent);
        this.search_result = this.page.items;
        this.tbody = document.createElement("tbody");

    }
    // The function to fetch the search results
    fetch_results() {
        for (let i = 0; i < rows; i++) {
            // initialize the structure
            tr_ele = document.createElement("tr");
            this.page.dom.insertBefore(new icon(this.search_result[i]), search_result[i].firstChild);
            tr_ele.appendChild(search_result[i]);
            this.tbody.appendChild(tr_ele);
            this.dom.appendChild(this.tbody);
            // Initialize dom elements
            let result = document.createElement("div");
            result.id = "result_" + i;
            let link = document.createElement('a');
            link.href = this.search_result.URL;
            link.innerText = this.search_result.title;
            result.appendChild(link);
            this.search_result[i] = result;
        }
        this.dom.appendChild(this.tbody);
    }
    // The function to import all the icons by URLs
    importIcons() {
        for (let i = 0; i < this.results.length; i++) {
            this.icon_list.push(new icon(this.results[i]));
        }
    }
    // Extract the keywords by title
    keyword_extract(title) {
        let xhttp = new XMLHttpRequest();
        xhttp.onreadystatechange = function () {
            if (this.readyState == 4 && this.status == 200) {
                // console.log(this.responseText);
                return this.responseText;
            }
        };
        xhttp.open("GET", "https://shipaicraft.asuscomm.com:4000/extract?title=" + title, true);
        xhttp.send();
        return xhttp.responseText;
    }
    // async keyword_extract(title) {
    //     let text = await fetch('https://alumni.iit.tku.edu.tw:4000/extract?title='+title, {method:'GET'})
    //                         .then((responce) => {return responce.text()});
    //     return text;
    // }

    // The funciton that one can fetch the top 10 Google Results
    searchGoogle(keywords) {	//searchGoogle
        let searchUrl = "https://customsearch.googleapis.com/customsearch/v1?key=AIzaSyCLgHAaCCuvQjtDkWqUUzdIwCCs_yfGPXQ&cx=9f8b720f1b3abf296&q=" + keywords.replaceAll("//", "");
        $(document).ready(function () {
            $.ajax({
                type: "GET",
                url: searchUrl,
                async: true,
                headers: {
                    "x-requested-with": "xhr"
                },
                mode: 'json',
                cache: 'default',
                success: function (text) {
                    // assign the result to website element
                    try {
                        new website(this.ID, text);
                    } catch (TargetExistedException) {
                    }
                    return text;
                }
            });
        });
        return searchUrl;
    }
}