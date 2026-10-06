import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
import fs from 'node:fs/promises';
const workbookPath = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_25092026.xlsx`;
const out = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Temp\dashboard_ncc_rows_51_52_verify.png`;
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const png = await wb.render({ sheetName: 'Dashboard T8-09', range: 'A49:R53', scale: 2, format: 'png' });
await fs.mkdir(String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Temp`, { recursive: true });
await fs.writeFile(out, new Uint8Array(await png.arrayBuffer()));
console.log(out);
