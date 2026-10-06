import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const path = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_30092026.xlsx`;
const file = await FileBlob.load(path);
const workbook = await SpreadsheetFile.importXlsx(file);
console.log('WORKSHEETS', workbook.worksheets.items.map((w) => w.name).join(' | '));
const sheet = workbook.worksheets.getItem('Kết quả tháng 09 và xử lý');
const values = await sheet.getRange('A1:T12').values;
console.log(JSON.stringify(values, null, 2));
