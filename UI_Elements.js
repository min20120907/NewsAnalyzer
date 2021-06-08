// Global Variables
// listing mode constant, one can select them by following enumerators
// blacklist: blacklist mode
// whitelist: whitelist mode
// none/default or any other strings: normal mode (No filterings) 
const listing_mode = "none";
const class_linkpost = "rq0escxv l9j0dhe7 du4w35lb j83agx80 pfnyh3mw i1fnvgqd bp9cbjyn owycx6da btwxx1t3 b5q2rw42 lq239pai f10w8fjw hv4rvrfc dati1w0a pybr56ya";
const class_post = "rq0escxv l9j0dhe7 du4w35lb hybvsw6c io0zqebd m5lcvass fbipl8qg nwvqtn77 k4urcfbm ni8dbmo4 stjgntxs sbcfpzgs";
const class_header = "ecm0bbzt hv4rvrfc ihqw7lf3 dati1w0a";
const class_linkaddr = "oajrlxb2 g5ia77u1 qu0x051f esr5mh6w e9989ue4 r7d6kgcz rq0escxv nhd2j8a9 a8c37x1j p7hjln8o kvgmc6g5 cxmmr5t8 oygrvhab hcukyx3x jb3vyjys rz4wbd8a qt6c0cv9 a8nywdso i1ao9s8h esuyzwwr f1sip0of lzcic4wl gmql0nx0 p8dawk7l";
const class_link = "l9j0dhe7";
const class_linktitle = "a8c37x1j ni8dbmo4 stjgntxs l9j0dhe7";

let UI_Elements = class {
    // Constructor initializing
    constructor() {
        // Proclaim the initial values of class variables

        this.linkposts = new Array();
        this.headers = new Array();
        this.links = new Array();
        // Construct the document object
        this.normal_posts = document.getElementsByClassName(class_post);
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