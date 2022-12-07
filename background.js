console.log("background javascript executed!");
chrome.action.onClicked.addListener(function(tab) {
    chrome.tabs.executeScript({
      file: "insert.js"
    });
  });