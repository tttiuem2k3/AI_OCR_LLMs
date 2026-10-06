import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const workbookPath = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_25092026.xlsx`;
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheets = await workbook.inspect({ kind: 'sheet', include: 'id,name', maxChars: 8000 });
console.log(sheets.ndjson);
const region = await workbook.inspect({ kind: 'region', sheetId: 'Dashboard T8-09', range: 'A51:R52', maxChars: 5000, tableMaxRows: 4, tableMaxCols: 18, tableMaxCellChars: 300 });
console.log('\nREGION\n' + region.ndjson);
const drawing = await workbook.inspect({ kind: 'drawing', sheetId: 'Dashboard T8-09', maxChars: 2000 });
console.log('\nDRAWING\n' + drawing.ndjson);
