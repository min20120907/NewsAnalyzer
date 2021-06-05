// Loading event listener
window.addEventListener("load", checkFacebook.areYouInFacebook);
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
