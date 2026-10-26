SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL
        THROW 51040, N'dbo.BEMT2009 does not exist.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE APK = CONVERT(uniqueidentifier, 'E700E2F8-34B6-4D6B-96E8-9F767B410AEC')
    )
        INSERT dbo.BEMT2009
        (
            APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
            DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
            NormalizeMode, CompareMode, CompareParams, LLMPolicy
        )
        VALUES
        (
            CONVERT(uniqueidentifier, 'E700E2F8-34B6-4D6B-96E8-9F767B410AEC'),
            'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE',
            'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount',
            'STATEMENT', 'Amount', 'OPTIONAL', 2, 'DECIMAL', NULL, NULL, NULL
        );

    UPDATE dbo.BEMT2009
    SET RecordType = 'MAPPING',
        GroupCode = 'NVL_SO_TIEN_V1',
        DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE',
        CriterionCode = 'CRITERIA_AMOUNT',
        Version = 'nvl-v1',
        IsActive = 1,
        DnttFieldCode = 'BEMT2002.RequestAmount',
        EvidenceTypeCode = 'STATEMENT',
        EvidenceFieldCode = 'Amount',
        MatchPolicy = 'OPTIONAL',
        Priority = 2,
        NormalizeMode = 'DECIMAL',
        CompareMode = NULL,
        CompareParams = NULL,
        LLMPolicy = NULL
    WHERE APK = CONVERT(uniqueidentifier, 'E700E2F8-34B6-4D6B-96E8-9F767B410AEC');

    UPDATE dbo.BEMT2009
    SET CompareParams = N'tolerance=10;ringiMinRatio=1;ringiMaxRatio=NONE;statementType=STATEMENT;statementInvoiceField=VoucherNo;missing=REVIEW;mismatch=NG'
    WHERE IsActive = 1
      AND RecordType = 'RULE'
      AND GroupCode = 'NVL_SO_TIEN_V1'
      AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_AMOUNT'
      AND Version = 'nvl-v1'
      AND CompareMode = 'NVL_AMOUNT_MATCH';

    IF
    (
        SELECT COUNT(*)
        FROM dbo.BEMT2009
        WHERE IsActive = 1
          AND RecordType = 'MAPPING'
          AND GroupCode = 'NVL_SO_TIEN_V1'
          AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
          AND CriterionCode = 'CRITERIA_AMOUNT'
          AND Version = 'nvl-v1'
    ) <> 5
        THROW 51041, N'NVL amount mappings must contain exactly five active rows.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE IsActive = 1
          AND RecordType = 'RULE'
          AND GroupCode = 'NVL_SO_TIEN_V1'
          AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
          AND CriterionCode = 'CRITERIA_AMOUNT'
          AND CompareMode = 'NVL_AMOUNT_MATCH'
          AND CompareParams LIKE '%ringiMinRatio=1%'
          AND CompareParams LIKE '%ringiMaxRatio=NONE%'
          AND CompareParams LIKE '%statementType=STATEMENT%'
          AND CompareParams LIKE '%statementInvoiceField=VoucherNo%'
    )
        THROW 51042, N'NVL amount rule parameters were not updated.', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SELECT RecordType, EvidenceTypeCode, EvidenceFieldCode, CompareMode, CompareParams
FROM dbo.BEMT2009
WHERE IsActive = 1
  AND GroupCode = 'NVL_SO_TIEN_V1'
  AND CriterionCode = 'CRITERIA_AMOUNT'
ORDER BY CASE WHEN RecordType = 'RULE' THEN 0 ELSE 1 END, Priority, EvidenceTypeCode;
GO
