import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const input = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_30092026.xlsx`;
const output = String.raw`E:\Asoft\AI_BEM\BEM_AI_PROJECT\.codex_tmp\artifact_t09_accuracy\edit_api_test.xlsx`;
const blob = await FileBlob.load(input);
const workbook = await SpreadsheetFile.importXlsx(blob);
const sheet = workbook.worksheets.getItem('Kết quả tháng 09 và xử lý');
sheet.getRange('A966:T966').copyFrom(sheet.getRange('A965:T965'), 'all');
sheet.getRange('A966:T966').values = [[...Array(20).fill(null)]];
sheet.getRange('Q11').format.fill = '#77BC65';
sheet.getRange('S11').values = [[1]];
const result = await SpreadsheetFile.exportXlsx(workbook);
await result.save(output);
console.log(output);
