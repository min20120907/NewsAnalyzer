// Only using native browser features (no jQuery).
// Uses `fetch`, `DOMParser` and `querySelectorAll`.

const getTitle = (url) => {  
    return fetch(`https://crossorigin.me/${url}`)
      .then((response) => response.text())
      .then((html) => {
        const doc = new DOMParser().parseFromString(html, "text/html");
        const title = doc.querySelectorAll('title')[0];
        return title.innerText;
      });
  };
  
  
  var urls = [
    'https://medium.com/@unakravets/the-sad-state-of-entitled-web-developers-e4f314764dd',
    'http://frontendnewsletter.com/issues/1#start',
    'https://groups.google.com/forum/#!topic/v8-users/PInzACvS5I4',
    'https://www.youtube.com/watch?v=9kJVYpOqcVU',
  ]
  
  // This one keeps the order the same as the URL list.
  Promise.all(
    urls.map((url) => getTitle(url))
  ).then((titles) => {
    console.log(titles);
  });