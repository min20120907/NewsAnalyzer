chrome.browserAction.onClicked.addListener(function(tab) {
    chrome.tabs.executeScript({
      file: "insert.js"
    });
  });