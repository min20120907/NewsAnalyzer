let table = class{
    constructor(ID, page) {
        this.ID = ID;
        this.dom = document.createElement("table");
        this.dom.id = "table_" + ID;
        // add some style
        this.dom.setAttribute("class", "table table-striped");
        this.page = new website(this.ID);
        this.tbody = document.createElement("tbody");
        
        for (let i = 0; i < rows; i++) {
            tr_ele = document.createElement("tr");
            this.page.dom.insertBefore(icos[i], search_result[operator_m].firstChild);
            //tr_ele[operator_m].appendChild(icos[operator_m]);
            tr_ele.appendChild(search_result[operator_m]);
            this.tbody.appendChild(tr_ele);
            this.dom.appendChild(this.tbody);
          }
        this.dom.appendChild(this.tbody);
    }
}