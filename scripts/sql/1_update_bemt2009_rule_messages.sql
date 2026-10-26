/*
  Update deployed BEMT2009 rule config after Rule Engine message/strict-date changes.
  Run on the target MEIKO2026_BEM_AI database after 20261008_migrate_ont1043_to_bemt2009.sql.
*/
SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.BEMT2009
    SET CompareParams = REPLACE(CompareParams, N'dateToleranceDays=1', N'dateToleranceDays=0')
    WHERE RecordType = 'RULE'
      AND GroupCode = 'NVL_NGAY_HOA_DON_V1'
      AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_INVOICE_DATE'
      AND CompareMode = 'NVL_INVOICE_DATE_BY_NO'
      AND CompareParams LIKE N'%dateToleranceDays=1%';

    IF @@ROWCOUNT = 0
       AND NOT EXISTS
       (
           SELECT 1
           FROM dbo.BEMT2009
           WHERE RecordType = 'RULE'
             AND GroupCode = 'NVL_NGAY_HOA_DON_V1'
             AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
             AND CriterionCode = 'CRITERIA_INVOICE_DATE'
             AND CompareMode = 'NVL_INVOICE_DATE_BY_NO'
             AND CompareParams LIKE N'%dateToleranceDays=0%'
       )
        THROW 51020, N'Không tìm thấy rule NVL_NGAY_HOA_DON_V1 để cập nhật dateToleranceDays=0.', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SELECT APK, GroupCode, CriterionCode, CompareMode, CompareParams
FROM dbo.BEMT2009
WHERE RecordType = 'RULE'
  AND GroupCode = 'NVL_NGAY_HOA_DON_V1'
  AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
  AND CriterionCode = 'CRITERIA_INVOICE_DATE';
GO
