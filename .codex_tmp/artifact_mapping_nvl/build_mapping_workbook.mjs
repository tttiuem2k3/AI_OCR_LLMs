import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM_NVL";
const payloadPath = path.join(outputDir, "mapping_dataset_payload_20261002.json");
const outputXlsx = path.join(outputDir, "DATA_BEM_NVL_Mapping.xlsx");
const previewPng = path.join(outputDir, "preview_00_Tong_quan.png");
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));

function colLetter(n) {
  let s = "";
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function normalizeValue(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value.length > 32000 ? value.slice(0, 32000) : value;
  if (typeof value === "number" || typeof value === "boolean") return value;
  return String(value).slice(0, 32000);
}

function collectHeaders(rows) {
  const headers = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!headers.includes(key)) headers.push(key);
    }
  }
  return headers.length ? headers : ["Ghi chú"];
}

function safeTableName(sheetName) {
  return ("T_" + sheetName.replace(/[^A-Za-z0-9_]/g, "_")).slice(0, 250);
}

function estimateWidth(header, values) {
  const all = [header, ...values.slice(0, 80).map(v => String(v ?? "").split("\n")[0])];
  const maxLen = Math.max(...all.map(v => String(v).length));
  if (/Path|TextContent|MappingEvidence|MatchedFiles|MappingGap|ManualTargetMapping|Description|Note|CopiedFolder|PhysicalSourceFolder/.test(header)) return 42;
  if (/VoucherNo|DocumentGroupID|PaymentLineID/.test(header)) return 28;
  if (/AttachName|FileName|Tên file/.test(header)) return 34;
  if (/Amount|Số tiền|Converted|Total/.test(header)) return 16;
  if (/Status|Currency|Loại tiền|NCC/.test(header)) return 14;
  return Math.max(12, Math.min(32, maxLen + 2));
}

const workbook = Workbook.create();
for (const sheetPayload of payload.sheets) {
  const rows = sheetPayload.rows || [];
  const headers = collectHeaders(rows);
  const matrix = [headers, ...rows.map(row => headers.map(h => normalizeValue(row[h])))];
  const sheet = workbook.worksheets.add(sheetPayload.name);
  sheet.getRange("A1").values = matrix;
  const lastCol = colLetter(headers.length);
  const lastRow = Math.max(1, matrix.length);
  const used = sheet.getRange(`A1:${lastCol}${lastRow}`);
  const header = sheet.getRange(`A1:${lastCol}1`);
  const headerColor = sheetPayload.name.startsWith("07_") || sheetPayload.name.startsWith("08_") || sheetPayload.name.startsWith("09_") || sheetPayload.name.startsWith("10_") ? "#2E7D32" : (sheetPayload.name.startsWith("11_") ? "#5F6B7A" : "#1F4E78");
  header.format.fill = headerColor;
  header.format.font = { color: "#FFFFFF", bold: true };
  header.format.wrapText = true;
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "center";
  used.format.wrapText = true;
  used.format.verticalAlignment = "top";
  sheet.freezePanes.freezeRows(1);
  for (let i = 0; i < headers.length; i++) {
    const letter = colLetter(i + 1);
    const values = rows.map(row => row[headers[i]]);
    try { sheet.getRange(`${letter}:${letter}`).format.columnWidth = estimateWidth(headers[i], values); } catch {}
  }
  if (lastRow > 1) {
    try {
      const table = sheet.tables.add(`A1:${lastCol}${lastRow}`, true);
      table.name = safeTableName(sheetPayload.name);
    } catch {}
  }
}
workbook.recalculate();
const inspect = await workbook.inspect({ select: "$.sheets[*]", include: ["name", "range", "tables.name", "tables.range"] });
await fs.writeFile(path.join(outputDir, "workbook_inspect_20261002.json"), JSON.stringify(inspect.records ?? inspect, null, 2), "utf8");
try {
  const preview = await workbook.render({ sheetName: "00_Tong_quan", range: "A1:O5", format: "png", scale: 1 });
  await fs.writeFile(previewPng, new Uint8Array(await preview.arrayBuffer()));
} catch (error) {
  await fs.writeFile(path.join(outputDir, "preview_error.txt"), String(error), "utf8");
}
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputXlsx);
console.log(JSON.stringify({ outputXlsx, previewPng, sheetCount: payload.sheets.length, sheets: payload.sheets.map(s => ({ name: s.name, rows: s.rows.length })) }, null, 2));



