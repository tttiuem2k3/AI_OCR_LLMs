import { Workbook } from '@oai/artifact-tool';
const wb=Workbook.create();
for (const q of ['workbook create worksheet values table formatting export','worksheet add values','range values format autofit','SpreadsheetFile exportXlsx create']) {
  try { console.log('\nHELP',q); console.log(JSON.stringify(await wb.help(q,{maxChars:4000}),null,2)); }
  catch(e){ console.log('ERR',String(e)); }
}
