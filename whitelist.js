let whitelist = class {
    static isAllow(URL) {
        /* IE only */
        let fso = ActiveXObject(Scripting.FileSystemObject);
        let whiteListData = fso.createtextfile("whitelist.txt",1,false);
        while(!whiteListData.AtEndOfStream) {
            if(URL == whiteListData.ReadLine()) {
                return true;
            }
        }
        return false;

        /* Node.js */
        // const fs = require('fs');
        // const readline = require('readline')
        // let inputStream = fs.createReadStream('whitelist.txt');
        // let lineReader = readline.createInterface({input:inputStream});
        // lineReader.on('line', function(line) {
        //     console.log(line);
        // });

        /* read local file */
        // let rawFile = new XMLHttpRequest();
        // rawFile.open("GET", "./whitelist.txt", false);
        // rawFile.onreadystatechange = function() {
        //     if(rawFile.readyState === 4) {
        //         if(rawFile.status === 200 || rawFile.status == 0) {
        //             console.log(rawFile.responceText);
        //         }
        //     }
        // }
    }
}
