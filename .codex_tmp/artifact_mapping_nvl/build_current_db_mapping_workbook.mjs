import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM_NVL";
const payloadPath = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/Temp/DATA_BEM_NVL_Audit_20261002/current_db_mapping_payload_20261002.json";
const outputXlsx = path.join(outputDir, "DATA_BEM_NVL_Mapping.xlsx");
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));

function colLetter(n) {
  let result = "";
  while (n > 0) {
    const remainder = (n - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    n = Math.floor((n - 1) / 26);
  }
  return result;
}
function normalizeValue(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value.slice(0, 32000);
  if (typeof value === "number" || typeof value === "boolean") return value;
  return String(value).slice(0, 32000);
}
function headersFor(rows) {
  const headers = [];
  for (const row of rows) for (const key of Object.keys(row)) if (!headers.includes(key)) headers.push(key);
  return headers.length ? headers : ["Ghi chú"];
}
function tableName(sheetName) { return ("T_" + sheetName.replace(/[^A-Za-z0-9_]/g, "_")).slice(0, 200); }
function widthFor(header, values) {
  if (/TextContent|Raw_Run|Description|GioiHan|LienKet|DuLieuDangMap|CurrentMappingLevel|CopiedPath|PhysicalSourceFolder|PhamVi/.test(header)) return 46;
  if (/VoucherNo|VoucherAPK|RunAPK|SectionAPK|RelatedTo|AttachID/.test(header)) return 28;
  if (/AttachName|Tên file|FileName/.test(header)) return 34;
  if (/Amount|Số tiền|Total|Percentage/.test(header)) return 16;
  const max = Math.max(header.length, ...values.slice(0, 80).map(v => String(v ?? "").split("\n")[0].length));
  return Math.max(12, Math.min(30, max + 2));
}

const workbook = Workbook.create();
for (const sheetData of payload.sheets) {
  const headers = headersFor(sheetData.rows || []);
  const data = [headers, ...(sheetData.rows || []).map(row => headers.map(header => normalizeValue(row[header])))];
  const sheet = workbook.worksheets.add(sheetData.name);
  sheet.getRange("A1").values = data;
  const lastColumn = colLetter(headers.length);
  const lastRow = Math.max(1, data.length);
  const all = sheet.getRange(`A1:${lastColumn}${lastRow}`);
  const header = sheet.getRange(`A1:${lastColumn}1`);
  all.format.setFont({ name: "Times New Roman" });
  all.format.wrapText = true;
  all.format.verticalAlignment = "top";
  header.format.fill = sheetData.name.startsWith("09_") ? "#5F6B7A" : "#1F4E78";
  header.format.font = { name: "Times New Roman", color: "#FFFFFF", bold: true };
  header.format.wrapText = true;
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "center";
  sheet.freezePanes.freezeRows(1);
  for (let index = 0; index < headers.length; index++) {
    const letter = colLetter(index + 1);
    sheet.getRange(`${letter}:${letter}`).format.columnWidth = widthFor(headers[index], (sheetData.rows || []).map(row => row[headers[index]]));
  }
  if (lastRow > 1) {
    try { const table = sheet.tables.add(`A1:${lastColumn}${lastRow}`, true); table.name = tableName(sheetData.name); } catch {}
  }
}
workbook.recalculate();
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputXlsx);
console.log(JSON.stringify({ output: outputXlsx, sheets: payload.sheets.map(sheet => [sheet.name, sheet.rows.length]) }, null, 2));
