// Loading event listener
window.addEventListener("load", UI_Elements.areYouInFacebook);
let UI = new UI_Elements();

let num = UI.linkposts.length;
let ticking = false;
let last_known_scroll_position = 0;
// Scrolling event listener
window.addEventListener("scroll", function (e) {
  last_known_scroll_position = window.scrollY;
  if (!ticking) {
    window.requestAnimationFrame(function () {
      ticking = false;
    });
  }
  ticking = true;
});
