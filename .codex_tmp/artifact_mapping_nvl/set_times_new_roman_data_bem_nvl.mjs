import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM_NVL/DATA_BEM_NVL_Mapping.xlsx";
const ranges = {
  "00_Tong_quan": "A1:P4",
  "01_DNTT_Header_DB": "A1:Q4",
  "02_DNTT_Lines_DB": "A1:J39",
  "03_Files_DinhKem": "A1:N128",
  "04_DB_Section_Mapping": "A1:U138",
  "05_DB_Field_Long": "A1:N1071",
  "06_AI_Criteria_DB": "A1:G28",
  "07_Target_Mapping_Line": "A1:T41",
  "08_Target_File_Link": "A1:M213",
  "09_Target_Schema_AI": "A1:C9",
  "10_File_Coverage": "A1:G128",
  "11_Raw_Run_Text": "A1:K4",
};

const input = await FileBlob.load(xlsxPath);
const workbook = await SpreadsheetFile.importXlsx(input);
for (const [sheetName, address] of Object.entries(ranges)) {
  const range = workbook.worksheets.getItem(sheetName).getRange(address);
  range.format.setFont({ name: "Times New Roman" });
}
workbook.recalculate();
const result = await SpreadsheetFile.exportXlsx(workbook);
await result.save(xlsxPath);
console.log(JSON.stringify({ updated: xlsxPath, sheets: Object.keys(ranges).length, font: "Times New Roman" }));
