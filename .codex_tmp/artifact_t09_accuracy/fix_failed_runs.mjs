import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const input = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_30092026.xlsx`;
const output = String.raw`E:\Asoft\AI_BEM\BEM_AI_PROJECT\.codex_tmp\artifact_t09_accuracy\DATA_BEM AI_MEIKO_30092026_candidate_2.xlsx`;
const updates = [
  ['NVL/09/2026/0202', 200],
  ['NVL/09/2026/0221', 218],
  ['NVL/09/2026/0267', 264],
  ['NVL/09/2026/0455', 437],
];
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const sheet = workbook.worksheets.getItem('Kết quả tháng 09 và xử lý');
for (const [voucher, row] of updates) {
  sheet.getRange(`P${row}:T${row}`).values = [[
    '- Lần chạy AI mới nhất bị lỗi nên chưa có căn cứ kết luận AI đúng hay sai.',
    '- Không có kết quả AI',
    '- Cần chạy lại AI sau khi kiểm tra nguyên nhân lỗi.',
    0,
    '- Phiếu chưa có đủ tiêu chí đối chiếu từ lần chạy AI mới nhất.',
  ]];
  sheet.getRange(`Q${row}`).format.fill = '#FFE994';
}
const result = await SpreadsheetFile.exportXlsx(workbook);
await result.save(output);
console.log(JSON.stringify({ output, updated: updates.map(([voucher]) => voucher) }, null, 2));
