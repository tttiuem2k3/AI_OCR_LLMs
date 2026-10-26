SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL
        THROW 51020, N'dbo.BEMT2009 does not exist.', 1;

    IF OBJECT_ID(N'dbo.ONT1042', N'U') IS NULL OR OBJECT_ID(N'dbo.ONT1041', N'U') IS NULL
        THROW 51021, N'dbo.ONT1041 or dbo.ONT1042 does not exist.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE APK = CONVERT(uniqueidentifier, 'AAB40CE9-B4E0-4EC0-8F65-C6F5BFE31D4C')
    )
        INSERT dbo.BEMT2009
        (
            APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
            DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
            NormalizeMode, CompareMode, CompareParams, LLMPolicy
        )
        VALUES
        (
            CONVERT(uniqueidentifier, 'AAB40CE9-B4E0-4EC0-8F65-C6F5BFE31D4C'),
            'MAPPING', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE',
            'CRITERIA_INVOICE_NO', 'nvl-v1', 1, 'BEMT2001.InvoiceNo',
            'STATEMENT', 'VoucherNo', 'OPTIONAL', 1, NULL, NULL, NULL, NULL
        );

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE APK = CONVERT(uniqueidentifier, 'C4C4B438-4770-4A78-91CD-3946F70B9B6E')
    )
        INSERT dbo.BEMT2009
        (
            APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
            DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
            NormalizeMode, CompareMode, CompareParams, LLMPolicy
        )
        VALUES
        (
            CONVERT(uniqueidentifier, 'C4C4B438-4770-4A78-91CD-3946F70B9B6E'),
            'MAPPING', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE',
            'CRITERIA_INVOICE_NO', 'nvl-v1', 1, 'BEMT2001.ListNo',
            'STATEMENT', 'ListNo', 'OPTIONAL', 2, NULL, NULL, NULL, NULL
        );

    UPDATE dbo.BEMT2009
    SET RecordType = 'MAPPING',
        GroupCode = 'NVL_SO_HOA_DON_V1',
        DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE',
        CriterionCode = 'CRITERIA_INVOICE_NO',
        Version = 'nvl-v1',
        IsActive = 1,
        DnttFieldCode = 'BEMT2001.InvoiceNo',
        EvidenceTypeCode = 'STATEMENT',
        EvidenceFieldCode = 'VoucherNo',
        MatchPolicy = 'OPTIONAL',
        Priority = 1,
        NormalizeMode = NULL,
        CompareMode = NULL,
        CompareParams = NULL,
        LLMPolicy = NULL
    WHERE APK = CONVERT(uniqueidentifier, 'AAB40CE9-B4E0-4EC0-8F65-C6F5BFE31D4C');

    UPDATE dbo.BEMT2009
    SET RecordType = 'MAPPING',
        GroupCode = 'NVL_SO_HOA_DON_V1',
        DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE',
        CriterionCode = 'CRITERIA_INVOICE_NO',
        Version = 'nvl-v1',
        IsActive = 1,
        DnttFieldCode = 'BEMT2001.ListNo',
        EvidenceTypeCode = 'STATEMENT',
        EvidenceFieldCode = 'ListNo',
        MatchPolicy = 'OPTIONAL',
        Priority = 2,
        NormalizeMode = NULL,
        CompareMode = NULL,
        CompareParams = NULL,
        LLMPolicy = NULL
    WHERE APK = CONVERT(uniqueidentifier, 'C4C4B438-4770-4A78-91CD-3946F70B9B6E');

    UPDATE dbo.BEMT2009
    SET CompareParams = N'primary=DNTT>INVOICE,COMMERCIALINVOICE;customs=CUSTOMSHEET>COMMERCIALINVOICE,INVOICE;statementType=STATEMENT;statementKeyField=ListNo;statementInvoiceField=VoucherNo;branchPolicy=ANY_COMPLETE_BRANCH_OK;stripSeparators=SPACE,-,.,/;stripCustomsPrefix=1;expandShortRange=1;similarity=0.8;missing=BLANK;mismatch=NG'
    WHERE IsActive = 1
      AND RecordType = 'RULE'
      AND GroupCode = 'NVL_SO_HOA_DON_V1'
      AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_INVOICE_NO'
      AND Version = 'nvl-v1'
      AND CompareMode = 'NVL_INVOICE_NO_MATCH';

    IF
    (
        SELECT COUNT(*)
        FROM dbo.BEMT2009
        WHERE IsActive = 1
          AND RecordType = 'MAPPING'
          AND GroupCode = 'NVL_SO_HOA_DON_V1'
          AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
          AND CriterionCode = 'CRITERIA_INVOICE_NO'
          AND Version = 'nvl-v1'
          AND EvidenceTypeCode = 'STATEMENT'
          AND EvidenceFieldCode IN ('VoucherNo', 'ListNo')
    ) <> 2
        THROW 51022, N'Invoice number STATEMENT mappings are incomplete.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE IsActive = 1
          AND RecordType = 'RULE'
          AND GroupCode = 'NVL_SO_HOA_DON_V1'
          AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
          AND CriterionCode = 'CRITERIA_INVOICE_NO'
          AND Version = 'nvl-v1'
          AND CompareMode = 'NVL_INVOICE_NO_MATCH'
          AND CompareParams LIKE '%statementType=STATEMENT%'
          AND CompareParams LIKE '%statementKeyField=ListNo%'
          AND CompareParams LIKE '%statementInvoiceField=VoucherNo%'
    )
        THROW 51023, N'Invoice number rule parameters were not updated.', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
GO

SELECT
    RecordType,
    GroupCode,
    CriterionCode,
    EvidenceTypeCode,
    EvidenceFieldCode,
    CompareMode,
    CompareParams
FROM dbo.BEMT2009
WHERE IsActive = 1
  AND GroupCode = 'NVL_SO_HOA_DON_V1'
  AND CriterionCode = 'CRITERIA_INVOICE_NO'
ORDER BY CASE WHEN RecordType = 'RULE' THEN 0 ELSE 1 END, Priority, APK;
GO
