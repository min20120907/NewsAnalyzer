class website {
    constructor(){
        this.dom = document.createElement("div");
        this.search_result = [];
        for (let i = 0; i < g[operator_k].items.length; i++) {
          let result = document.createElement("div");
          this.result.id = "results_" + i;
          let item = g[operator_k].items[i];
          // in production code, item.htmlTitle should have the HTML entities escaped.
      
          let link = document.createElement('a');
          link.href = item.link;
          link.innerText = item.title;
          result.appendChild(link);
          search_result[i] = result;
        }
    }
}