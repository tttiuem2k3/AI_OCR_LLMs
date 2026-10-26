# NVL AFTER INVOICE payment term aliases

## Approved scope
Continues the AFTER_INVOICE proposal in chat AI-BEM-Rules Engine. On 2026-10-14 the user approved aliases, including shortened terms and invoice date by TT.

## Design
- Centralize family alias patterns and display formats for AMS, AFTER_BL and AFTER_INVOICE.
- Recognize 30 AFTER INVOICE, 30 DAYS AFTER INVOICE, 30 DAYS AFTER INVOICE DATE BY TT, plus corresponding 60/90-day variants. Case, repeated whitespace, DAY/DAYS and TT/T/T do not change identity.
- Require one distinct positive day count and one recognized family. Literal 30/60/90 in one term remains ambiguous; never silently select one number.
- Group equivalent aliases before the existing PO majority selection. AFTER_INVOICE remains distinct from AFTER_BL.
- AFTER_INVOICE uses INVOICE/COMMERCIALINVOICE dates, adds days, takes month-end and uses the existing weekend/holiday adjustment. Display as {days} AFTER INVOICE.
- Preserve AMS/AFTER_BL behavior, source ordering, duplicate handling, response schema and no-LLM routing. No BEMT2009 or extraction prompt change.

## Verification
Cover alias parsing, 30/60/90-day calculations, invoice anchors, majority/ties, missing dates, mixed-family and multiple-day rejection, weekend/holiday adjustment and no-LLM integration. Run payment and rule-engine regressions.
