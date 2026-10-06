import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const path = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM AI_MEIKO_25092026.xlsx";
const input = await FileBlob.load(path);
const workbook = await SpreadsheetFile.importXlsx(input);
const inspect = await workbook.inspect({ kind: "sheet", sheetId: "Rules_Nguyên vật liệu", range: "O3:O12", maxChars: 12000 });
console.log(inspect.ndjson ?? JSON.stringify(inspect, null, 2));
