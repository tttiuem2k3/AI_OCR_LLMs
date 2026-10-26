SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL
        THROW 51020, N'dbo.BEMT2009 does not exist.', 1;

    UPDATE dbo.BEMT2009
    SET IsActive = 0
    WHERE DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_SIGNATURE_STAMP'
      AND (GroupCode <> 'NVL_CHU_KY_CON_DAU_V1' OR Version <> 'nvl-v1');

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, 'D7B92E37-C8CE-451F-BEB8-17C0C155F976'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, 'D7B92E37-C8CE-451F-BEB8-17C0C155F976'), 'MAPPING', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, 'BEMT2001.APK', 'PO', 'Signature', 'ALL', 1, NULL, NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, '00FD8D88-F403-4CDB-9470-180C530CBDDE'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, '00FD8D88-F403-4CDB-9470-180C530CBDDE'), 'MAPPING', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, 'BEMT2001.APK', 'INVOICE', 'Signature', 'ANY', 1, NULL, NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, '4254C22F-99A2-4B23-A0AA-4167A654CC06'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, '4254C22F-99A2-4B23-A0AA-4167A654CC06'), 'MAPPING', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, 'BEMT2001.APK', 'COMMERCIALINVOICE', 'Signature', 'ANY', 1, NULL, NULL, NULL, NULL);

    IF NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE APK = CONVERT(uniqueidentifier, 'F83ACF96-4FBF-44FB-9AF0-8544C79662E2'))
        INSERT dbo.BEMT2009 (APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority, NormalizeMode, CompareMode, CompareParams, LLMPolicy)
        VALUES (CONVERT(uniqueidentifier, 'F83ACF96-4FBF-44FB-9AF0-8544C79662E2'), 'RULE', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'SIGNATURE_STATUS', 'NVL_SIGNATURE_STAMP_VALIDATION', N'requiredAll=PO;requiredAny=INVOICE,COMMERCIALINVOICE;selectedBlank=NG;fallbackBlank=BLANK;missing=BLANK', 'NEVER');

    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_CHU_KY_CON_DAU_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_SIGNATURE_STAMP', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2001.APK', EvidenceTypeCode = 'PO', EvidenceFieldCode = 'Signature', MatchPolicy = 'ALL', Priority = 1, NormalizeMode = NULL, CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, 'D7B92E37-C8CE-451F-BEB8-17C0C155F976');
    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_CHU_KY_CON_DAU_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_SIGNATURE_STAMP', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2001.APK', EvidenceTypeCode = 'INVOICE', EvidenceFieldCode = 'Signature', MatchPolicy = 'ANY', Priority = 1, NormalizeMode = NULL, CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, '00FD8D88-F403-4CDB-9470-180C530CBDDE');
    UPDATE dbo.BEMT2009 SET RecordType = 'MAPPING', GroupCode = 'NVL_CHU_KY_CON_DAU_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_SIGNATURE_STAMP', Version = 'nvl-v1', IsActive = 1, DnttFieldCode = 'BEMT2001.APK', EvidenceTypeCode = 'COMMERCIALINVOICE', EvidenceFieldCode = 'Signature', MatchPolicy = 'ANY', Priority = 1, NormalizeMode = NULL, CompareMode = NULL, CompareParams = NULL, LLMPolicy = NULL WHERE APK = CONVERT(uniqueidentifier, '4254C22F-99A2-4B23-A0AA-4167A654CC06');

    UPDATE dbo.BEMT2009
    SET RecordType = 'RULE', GroupCode = 'NVL_CHU_KY_CON_DAU_V1', DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE', CriterionCode = 'CRITERIA_SIGNATURE_STAMP', Version = 'nvl-v1', IsActive = 1,
        DnttFieldCode = NULL, EvidenceTypeCode = NULL, EvidenceFieldCode = NULL, MatchPolicy = NULL, Priority = NULL,
        NormalizeMode = 'SIGNATURE_STATUS', CompareMode = 'NVL_SIGNATURE_STAMP_VALIDATION',
        CompareParams = N'requiredAll=PO;requiredAny=INVOICE,COMMERCIALINVOICE;selectedBlank=NG;fallbackBlank=BLANK;missing=BLANK',
        LLMPolicy = 'NEVER'
    WHERE APK = CONVERT(uniqueidentifier, 'F83ACF96-4FBF-44FB-9AF0-8544C79662E2');

    IF EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE IsActive = 1 AND GroupCode = 'NVL_CHU_KY_CON_DAU_V1' AND Version = 'nvl-v1' AND RecordType = 'RULE' HAVING COUNT(*) <> 1)
        THROW 51021, N'NVL signature rule validation failed.', 1;

    IF EXISTS (SELECT 1 FROM dbo.BEMT2009 WHERE IsActive = 1 AND GroupCode = 'NVL_CHU_KY_CON_DAU_V1' AND Version = 'nvl-v1' AND RecordType = 'MAPPING' HAVING COUNT(*) <> 3)
        THROW 51022, N'NVL signature mapping validation failed.', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
