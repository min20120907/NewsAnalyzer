class resultFrame {
    results = new Array();
    state = false;

    constructor(title,icon_list, title_list, URL_list) {
        this.icon_list = icon_list;
        this.title_list = title_list;
        this.URL_list = URL_list;
        this.title = title;
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
    getKeywords(){

    }
    // toggle the button on off state
    toggleOnOff(operator_j) {	//toggleOnOff
        if (ifrm[operator_j].style.display == "none") {
          ifrm[operator_j].setAttribute("style", "display: block");
        } else {
          ifrm[operator_j].setAttribute("style", "display: none");
        }
      }
}