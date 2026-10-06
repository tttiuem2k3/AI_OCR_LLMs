import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const path = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM AI_MEIKO_25092026.rules-merged-tmp.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
const preview = await workbook.render({ sheetName: "Rules_Nguyên vật liệu", range: "O3:O12", scale: 1, format: "png" });
await fs.writeFile("E:/Asoft/AI_BEM/BEM_AI_PROJECT/.codex-artifact-rules-check/rules_nvl_merged_preview.png", new Uint8Array(await preview.arrayBuffer()));
