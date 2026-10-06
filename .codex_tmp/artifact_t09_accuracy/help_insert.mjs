import { Workbook } from '@oai/artifact-tool';
const wb=Workbook.create();
const result=await wb.help('range.insert', { include: 'index,examples,notes', maxChars: 12000 });
console.log(JSON.stringify(result,null,2));
