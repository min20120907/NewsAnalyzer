let table = class{
    constructor(ID, page) {
        this.ID = ID;
        this.dom = document.createElement("table");
        this.dom.id = "table_" + ID;
        // add some style
        this.dom.setAttribute("class", "table table-striped");
        this.page = new website(this.ID);
        tbody = document.createElement("tbody");
        for (let operator_m = 0; operator_m < search_result.length; operator_m++) {
            search_result[operator_m].insertBefore(icos[operator_m], search_result[operator_m].firstChild);
            //tr_ele[operator_m].appendChild(icos[operator_m]);
            tr_ele[operator_m].appendChild(search_result[operator_m]);
            tbody[operator_k].appendChild(tr_ele[operator_m]);
            table[operator_k].appendChild(tbody[operator_k]);
          }
        this.dom.appendChild(tbody[operator_k]);
    }
}