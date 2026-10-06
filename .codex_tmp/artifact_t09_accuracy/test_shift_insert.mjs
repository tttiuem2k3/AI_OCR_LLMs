import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const input = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_30092026.xlsx`;
const output = String.raw`E:\Asoft\AI_BEM\BEM_AI_PROJECT\.codex_tmp\artifact_t09_accuracy\shift_insert_test.xlsx`;
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const sheet = workbook.worksheets.getItem('Kết quả tháng 09 và xử lý');
sheet.getRange('A293:T966').copyFrom(sheet.getRange('A292:T965'), 'all');
sheet.getRange('A292:T292').values = [[290, 'TESTDATE', 'Nguyên vật liệu', 2026, 10, 'VND', 'VE01', 'NVL/09/2026/0298', 'OK', 2, null, null, 'NG', null, null, '- test P', '- Không có kết quả AI', '- test R', 0, '- test T']];
const result = await SpreadsheetFile.exportXlsx(workbook);
await result.save(output);
console.log(output);
