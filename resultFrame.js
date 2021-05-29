class resultFrame {


    constructor(title, ID, icon_list, title_list, URL_list) {
        this.icon_list = icon_list;
        this.title_list = title_list;
        this.URL_list = URL_list;
        this.title = title;
        this.results = new Array();
        this.state = false;
        
        this.frame = document.createElement("div");
        this.frame.id = "frame_"+ID;
    }
    
    // The function that can toggle on and off
    toggleOnOff(frame) {	//toggleOnOff
        if (frame.style.display == "none") {
            frame.setAttribute("style", "display: block");
        } else {
            frame.setAttribute("style", "display: none");
        }
    }
    // Extract the keywords by title
    keyword_extract(title) {
      let xhttp = new XMLHttpRequest();
      xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
          // console.log(this.responseText);
          return this.responseText;
        }
      };
      xhttp.open("GET", "https://alumni.iit.tku.edu.tw:4000/extract?title=" + title, true);
      xhttp.send();
      return this.responseText;
      }
    // The funciton that one can fetch the top 10 Google Results
    searchGoogle(googleQuery) {	//searchGoogle
        if (!googleQuery.includes("中天新聞")) {
            let searchUrl = "https://www.googleapis.com/customsearch/v1?key=AIzaSyBOXrA4oFgl1SNyxm9sA_vTzaAVYorQDug&cx=9f8b720f1b3abf296&q=" + googleQuery.substring(0, 5);
        } else {
            let searchUrl = "https://www.googleapis.com/customsearch/v1?key=AIzaSyBOXrA4oFgl1SNyxm9sA_vTzaAVYorQDug&cx=9f8b720f1b3abf296&q=" + googleQuery.substring(googleQuery.length - 5, googleQuery.length);
        }
        $(document).ready(function () {
            $.ajax({
                type: "GET",
                url: filename,
                async: true,
                headers: {
                    "x-requested-with": "xhr"
                },
                mode: 'json',
                cache: 'default',
                success: function (text) {
                    g[operator_n] = text;
                    return text;
                }
            });
        });
        return searchUrl;
    }
    // The function that one can fetch the keys from the Flask ML Server
    getKeywords() {

    }

}