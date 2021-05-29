static class UI_Elements {
    // Constructor initializing
    constructor() {
        // Proclaim the initial values of class variables
        const class_linkpost = "rq0escxv l9j0dhe7 du4w35lb j83agx80 pfnyh3mw i1fnvgqd bp9cbjyn owycx6da btwxx1t3 b5q2rw42 lq239pai f10w8fjw hv4rvrfc dati1w0a pybr56ya";
        const class_post = "rq0escxv l9j0dhe7 du4w35lb hybvsw6c io0zqebd m5lcvass fbipl8qg nwvqtn77 k4urcfbm ni8dbmo4 stjgntxs sbcfpzgs";
        const class_header = "pybr56ya dati1w0a hv4rvrfc n851cfcs btwxx1t3 j83agx80 ll8tlv6m";
        const class_link = "l9j0dhe7";
        let linkposts = new Array();
        let headers = new Array();
        // Construct the document object

    }
    // The function to extract the class names into the elements array
    fetch_posts(params) {

    }

    // The function to add the button inside the post
    append_button(b) {

    }
    // The function to add the frame that contain the results into the post
    append_result(r) {

    }
    // The function that one can fetch the childnodes by providing the class names
    getChildNodesByClassName(element, classNames) {
        let ClassString = "." + classNames.replaceAll(" ", ".");
        let nodes = element.querySelector(ClassString);
        let found = false;
        let arrayOfNodes = new Array();       // untill spread operator is supported [...nodes], we have to use slice method
        // Scan over the nodes that
        for (let n of nodes) {
            if (n.className == ClassString) {
                arrayOfNodes.push(n);
                found = true;
            }
        }

        return {found: found, arrayOfNodes: arrayOfNodes};
    }

}