//checkFacebook.js

let checkFacebook = class{
    static areYouInFacebook() {	//areYouInFacebook
        if (window.location.hostname.includes("facebook.com")) {
            return true;
        } else {
            return false;
        }
    }
}

//linkpost.js

let linkpost = class{
    constructor(URL, title){
        this.URL = URL;
        this.title = title;
    }
}

//exceptions.js

function TargetExistedException(message, metadata) {
    const error = new Error(message);
    error.metadata = metadata;
    return error;
}
  
TargetExistedException.prototype = Object.create(Error.prototype);

//resultFrame.js

let resultFrame = class {


    constructor(ID, rows, lpost, onclick) {
        this.state = false;
        this.clickTime = 0;
        // initialize the DOM object
        // if element existed change the state of display
        if (document.getElementById("frame_" + ID) != null) {
            if (onclick) {
                
                this.frame = document.getElementById("frame_" + ID);
                this.frame.setAttribute("clicktime", this.frame.getAttribute("clicktime")+1);
                if (this.frame.getAttribute("clicktime") >= 0){
                    this.clickTime = this.frame.getAttribute("clicktime");
                   //  console.log("attribute set!");
                }
                // console.log(this.frame.getAttribute("clicktime"));
                if (this.frame.getAttribute("clicktime")==1){
                    this.frame.appendChild(new table(ID, rows, lpost).dom);}
                this.state = !this.state;
                this.toggleOnOff();
                
            }
            throw (new TargetExistedException("[WARNING] Target element is existed!"));
        }
        this.frame = document.createElement("div");
        this.frame.id = "frame_" + ID;
        this.frame.setAttribute("style", "display: none");
        // console.log("frame created!");

    }

    // toggle the button on off state
    toggleOnOff() {	//toggleOnOff
        if (this.frame.style.display == "none") {
            this.frame.setAttribute("style", "display: block");
        } else {
            this.frame.setAttribute("style", "display: none");
        }
    }

}

//button.js

let button = class {

    constructor(ID, text, className, lpost) {
  
  
      this.ID = ID;
      if (document.getElementById("btn_" + this.ID) != null)
        throw (new TargetExistedException("[WARNING] Target element is existed!"));
      this.text = text;
      this.className = className;
      this.lpost = lpost;
      this.constructButton();
    }
    constructButton() {
      // DOM
      this.dom = document.createElement("BUTTON");
      this.dom.setAttribute("class", this.className);
      this.dom.innerText = this.text;
      this.dom.id = "btn_" + this.ID;
      // onclick function
      (function (ID, btn) {
        btn.dom.onclick = function () {
          // console.log(ID);
          try{
          new resultFrame(ID, 10, btn.lpost,true);
          }catch(TargetExistedException){}
          // createIFrame(i);
        };
      })(this.ID, this);
    }
  }

//icon.js

let icon = class{
    constructor(search_result) {
        this.dom = document.createElement("img");
        this.dom.src = "https://www.google.com/s2/favicons?sz=64&domain_url=" +
                         new URL(search_result).hostname;
        this.dom.width = 24;	//set width as 24
        this.dom.height = 24;	//set height as 24
        this.dom.style.position = "relative";
    }
}

//table.js

delay = function (s) {
    return new Promise(function (resolve, reject) {
        setTimeout(resolve, s);
    });
};
let table = class {
    constructor(ID, rows, lpost) {
        this.rows = rows
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

//UI_Elements.js

// Loading event listener
window.addEventListener("load", checkFacebook.areYouInFacebook);
// Global Variables
// listing mode constant, one can select them by following enumerators
// blacklist: blacklist mode
// whitelist: whitelist mode
// none/default or any other strings: normal mode (No filterings) 
const class_post = "x9f619 x1n2onr6 x1ja2u2z x2bj2ny x1qpq9i9 xdney7k xu5ydu1 xt3gfkd xh8yej3 x6ikm8r x10wlt62 xquyuld";
const class_linkpost = "x9f619 x1n2onr6 x1ja2u2z x2bj2ny x1qpq9i9 xdney7k xu5ydu1 xt3gfkd xh8yej3 x6ikm8r x10wlt62 xquyuld";
const class_header = "x1cy8zhl x78zum5 x1q0g3np xod5an3 x1pi30zi x1swvt13 xz9dl7a";
const class_linkaddr = "x10wlt62 x6ikm8r";
const class_link = "x1i10hfl xjbqb8w x6umtig x1b1mbwd xaqea5y xav7gou x9f619 x1ypdohk xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x16tdsg8 x1hl2dhg xggy1nq x1a2a7pz x1heor9g x1lliihq x1lku1pv";
const class_linktitle = "x1lliihq x6ikm8r x10wlt62 x1n2onr6 x1j85h84";

let UI_Elements = class {
    // Constructor initializing
    constructor() {
        // Proclaim the initial values of class variables
        // Construct the document object
        this.normal_posts = document.getElementsByClassName(class_post);
        this.linkposts = new Array();
        this.headers = new Array();
        this.links = new Array();
        // Define functions this class can perform
        this.fetch_posts();
        this.append_button();
    }
    // The function to extract the class names into the elements array
    fetch_posts() {
        for (let i = 0; i < this.normal_posts.length; i++) {
            let p = this.normal_posts[i];
            if (this.getChildNodesByClassName(p, class_linkpost).length > 0)
                this.linkposts.push(p);
        }
    }

    // The function to add the button inside the post
    append_button() {

        for (let i = 0; i < this.linkposts.length; i++) {
            this.getLink(i);
            try {
                // Append Button
                this.linkposts[i]
                    .getElementsByClassName(class_header)[0]
                    .appendChild(new button(i, "More", "btn btn-warning", this.links[i]).dom);

            } catch (TargetExistedException){
            }
            try{
            this.linkposts[i]
            .getElementsByClassName(class_header)[0]
            .appendChild(new resultFrame(i,10, this.links[i]).frame);
            }catch(TargetExistedException){
            }
        }

    }
    // The function to export the link
    getLink(i) {
        this.links[i] = (new linkpost(
            this.FacebookLinkParse(
            document.querySelectorAll("a." + this.queryOf(class_linkaddr))[i].href),
            document.querySelectorAll("a." + this.queryOf(class_linkaddr))[i]
                .querySelectorAll("span." + this.queryOf(class_linktitle))[1].innerText
        ));
    }
    // The function to parse facebook link into normal simple form
    FacebookLinkParse(URL){
        return decodeURIComponent(URL)
        .substring(0,URL.indexOf("fbclid")-1)
        .replace("https://l.facebook.com/l.php?u=","");
    }
    
    // The function to convert class name into query selector
    queryOf(className) {
        return className.replaceAll(" ", ".");
    }
    // The function creating the element div from pure HTML
    createElementFromHTML(htmlString) {	//createElementFromHTML
        let div = document.createElement('div');
        div.innerHTML = htmlString.trim();

        // Change this to div.childNodes to support multiple top-level nodes
        return div.firstChild;
    }
    // The function that one can fetch the childnodes by providing the class names
    getChildNodesByClassName(element, classNames) {
        let ClassString = "." + classNames.replaceAll(" ", ".");
        let nodes = element.querySelectorAll(ClassString);
        return nodes;
    }

}

//insert.js

let UI = new UI_Elements();
// delay function
let delay = function (s) {
    return new Promise(function (resolve, reject) {
        setTimeout(resolve, s);
    });
};
let num = UI.linkposts.length;
let ticking = false;
let last_known_scroll_position = 0;
// Scrolling event listener
window.addEventListener("scroll", function (e) {
    last_known_scroll_position = window.scrollY;
    if (!ticking) {
        window.requestAnimationFrame(function () {
            UI = new UI_Elements();
            ticking = false;
        });
    }
    ticking = true;
});
