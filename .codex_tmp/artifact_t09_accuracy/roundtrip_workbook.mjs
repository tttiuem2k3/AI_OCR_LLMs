import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const input = String.raw`E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_30092026.xlsx`;
const output = String.raw`E:\Asoft\AI_BEM\BEM_AI_PROJECT\.codex_tmp\artifact_t09_accuracy\roundtrip_test.xlsx`;
const blob = await FileBlob.load(input);
const workbook = await SpreadsheetFile.importXlsx(blob);
const result = await SpreadsheetFile.exportXlsx(workbook);
await result.save(output);
console.log(output);
