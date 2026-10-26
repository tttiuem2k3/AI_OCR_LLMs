SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL
        THROW 51030, N'dbo.BEMT2009 does not exist.', 1;

    UPDATE dbo.BEMT2009
    SET IsActive = 0
    WHERE DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_AMOUNT'
      AND (GroupCode <> 'NVL_SO_TIEN_V1' OR Version <> 'nvl-v1');

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, '7C788856-FE36-41CC-B8C2-6DCB48967A28'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, '7C788856-FE36-41CC-B8C2-6DCB48967A28'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'INVOICE', 'Amount', 'ANY', 1, 'DECIMAL', NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, '581063E2-254A-4FE3-B200-67F315458D0F'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, '581063E2-254A-4FE3-B200-67F315458D0F'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'COMMERCIALINVOICE', 'Amount', 'ANY', 1, 'DECIMAL', NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, '3591FA92-E56F-434D-A74D-20FD01A49417'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, '3591FA92-E56F-434D-A74D-20FD01A49417'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'CUSTOMSHEET', 'Amount', 'ALL', 1, 'DECIMAL', NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, '8C051A90-1EAC-40AE-8DB1-0514AD623F1F'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, '8C051A90-1EAC-40AE-8DB1-0514AD623F1F'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2001.TotalAmount', 'RINGI', 'Amount', 'OPTIONAL', 2, 'DECIMAL', NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, 'E700E2F8-34B6-4D6B-96E8-9F767B410AEC'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, 'E700E2F8-34B6-4D6B-96E8-9F767B410AEC'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'STATEMENT', 'Amount', 'OPTIONAL', 2, 'DECIMAL', NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, '0FFAD700-3D9B-459A-A0C5-836EAA824EF2'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, '0FFAD700-3D9B-459A-A0C5-836EAA824EF2'), 'RULE', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'DECIMAL', 'NVL_AMOUNT_MATCH', N'tolerance=10;ringiMinRatio=1;ringiMaxRatio=NONE;statementType=STATEMENT;statementInvoiceField=VoucherNo;missing=REVIEW;mismatch=NG', 'NEVER');

    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_SO_TIEN_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_AMOUNT', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2002.RequestAmount', EvidenceTypeCode = 'INVOICE', EvidenceFieldCode = 'Amount', MatchPolicy = 'ANY', Priority = 1, NormalizeMode = 'DECIMAL', CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, '7C788856-FE36-41CC-B8C2-6DCB48967A28');
    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_SO_TIEN_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_AMOUNT', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2002.RequestAmount', EvidenceTypeCode = 'COMMERCIALINVOICE', EvidenceFieldCode = 'Amount', MatchPolicy = 'ANY', Priority = 1, NormalizeMode = 'DECIMAL', CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, '581063E2-254A-4FE3-B200-67F315458D0F');
    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_SO_TIEN_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_AMOUNT', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2002.RequestAmount', EvidenceTypeCode = 'CUSTOMSHEET', EvidenceFieldCode = 'Amount', MatchPolicy = 'ALL', Priority = 1, NormalizeMode = 'DECIMAL', CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, '3591FA92-E56F-434D-A74D-20FD01A49417');
    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_SO_TIEN_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_AMOUNT', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2002.RequestAmount', EvidenceTypeCode = 'STATEMENT', EvidenceFieldCode = 'Amount', MatchPolicy = 'OPTIONAL', Priority = 2, NormalizeMode = 'DECIMAL', CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, 'E700E2F8-34B6-4D6B-96E8-9F767B410AEC');
    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_SO_TIEN_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_AMOUNT', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2001.TotalAmount', EvidenceTypeCode = 'RINGI', EvidenceFieldCode = 'Amount', MatchPolicy = 'OPTIONAL', Priority = 2, NormalizeMode = 'DECIMAL', CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, '8C051A90-1EAC-40AE-8DB1-0514AD623F1F');

    UPDATE dbo.BEMT2009
    SET RecordType = 'RULE', GroupCode = 'NVL_SO_TIEN_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_AMOUNT', Version = 'nvl-v1', IsActive = 1,
        DnttFieldCode = NULL, EvidenceTypeCode = NULL, EvidenceFieldCode = NULL, MatchPolicy = NULL, Priority = NULL,
        NormalizeMode = 'DECIMAL', CompareMode = 'NVL_AMOUNT_MATCH',
        CompareParams = N'tolerance=10;ringiMinRatio=1;ringiMaxRatio=NONE;statementType=STATEMENT;statementInvoiceField=VoucherNo;missing=REVIEW;mismatch=NG',
        LLMPolicy = 'NEVER'
    WHERE APK = CONVERT(uniqueidentifier, '0FFAD700-3D9B-459A-A0C5-836EAA824EF2');

    IF EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE IsActive = 1 AND GroupCode = 'NVL_SO_TIEN_V1' AND Version = 'nvl-v1' AND RecordType = 'RULE' HAVING COUNT(*) <> 1)
        THROW 51031, N'NVL amount rule validation failed.', 1;

    IF EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE IsActive = 1 AND GroupCode = 'NVL_SO_TIEN_V1' AND Version = 'nvl-v1' AND RecordType = 'MAPPING' HAVING COUNT(*) <> 5)
        THROW 51032, N'NVL amount mapping validation failed.', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
