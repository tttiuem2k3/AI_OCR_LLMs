import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const path = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM AI_MEIKO_25092026.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
const sheet = workbook.worksheets.getItem("Rules_Nguyên vật liệu");
console.log(JSON.stringify(sheet.getRange("O3:O12").values, null, 2));
const preview = await workbook.render({ sheetName: "Rules_Nguyên vật liệu", range: "A1:O12", scale: 1, format: "png" });
await fs.writeFile("E:/Asoft/AI_BEM/BEM_AI_PROJECT/.codex-artifact-rules-check/rules_nvl_preview.png", new Uint8Array(await preview.arrayBuffer()));
