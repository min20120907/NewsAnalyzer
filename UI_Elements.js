window.addEventListener("load", checkFacebook.areYouInFacebook);
// Global Variables
// listing mode constant, one can select them by following enumerators
// blacklist: blacklist mode
// whitelist: whitelist mode
// none/default or any other strings: normal mode (No filterings) 
const class_post = "x9f619 x1n2onr6 x1ja2u2z x2bj2ny x1qpq9i9 xdney7k xu5ydu1 xt3gfkd xh8yej3 x6ikm8r x10wlt62 xquyuld";
// const class_linkpost = "x9f619 x1n2onr6 x1ja2u2z x2bj2ny x1qpq9i9 xdney7k xu5ydu1 xt3gfkd xh8yej3 x6ikm8r x10wlt62 xquyuld";
// const class_header = "x1cy8zhl x78zum5 x1q0g3np xod5an3 x1pi30zi x1swvt13 xz9dl7a";
// const class_linkaddr = "x10wlt62 x6ikm8r";
// const class_link = "x1i10hfl xjbqb8w x6umtig x1b1mbwd xaqea5y xav7gou x9f619 x1ypdohk xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x16tdsg8 x1hl2dhg xggy1nq x1a2a7pz x1heor9g x1lliihq x1lku1pv";
// const class_linktitle = "x1lliihq x6ikm8r x10wlt62 x1n2onr6 x1j85h84";

let UI_Elements = class {
    // Constructor initializing
    constructor() {
        // Proclaim the initial values of class variables
        // Construct the document object
        this.normal_posts = document.getElementsByClassName(class_post);
        this.linkposts = new Array();
        // filter the posts that 
        for(let i=0;i<this.normal_posts.length;i++)
            if(this.normal_posts[i]!=null)
                this.linkposts.push(this.normal_posts[i])
        
        this.headers = new Array();
        this.links = new Array();
        this.append_button();
    }


    // The function to add the button inside the post
    append_button() {
        for (let i = 0; i < this.linkposts.length; i++) {
            this.getLink(i);
            try {
                // Append Button
                this.linkposts[i]
                    .querySelector("div.x1iorvi4.x1pi30zi.x1l90r2v.x1swvt13")
                    .appendChild(new button(i, "More", "btn btn-warning", this.links[i]).dom);

            } catch (TargetExistedException){
            }
            try{
            this.linkposts[i]
            .querySelector("div.x1iorvi4.x1pi30zi.x1l90r2v.x1swvt13")
            .appendChild(new resultFrame(i,10, this.links[i]).frame);
            }catch(TargetExistedException){
            }
        }

    }
    // The function to export the link
    getLink(i) {
        this.links[i] = (new linkpost(
            this.linkposts[i].querySelector("a.x1i10hfl.xjbqb8w.x6umtig.x1b1mbwd.xaqea5y.xav7gou.x9f619.x1ypdohk.xt0psk2.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x16tdsg8.x1hl2dhg.xggy1nq.x1a2a7pz.x1heor9g.xt0b8zv.x5yr21d.x10l6tqk.x17qophe.x13vifvy.xh8yej3.x1vjfegm").href,
            this.linkposts[i].querySelectorAll("span.x1lliihq.x6ikm8r.x10wlt62.x1n2onr6")[1].innerText))
    }

    // The function creating the element div from pure HTML
    createElementFromHTML(htmlString) {	//createElementFromHTML
        let div = document.createElement('div');
        div.innerHTML = htmlString.trim();

        // Change this to div.childNodes to support multiple top-level nodes
        return div.firstChild;
    }

}
