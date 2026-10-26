SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL
        THROW 51060, N'dbo.BEMT2009 does not exist.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE APK = CONVERT(uniqueidentifier, 'D3602460-2286-47F7-A970-5CCAA0BF7B15')
    )
        INSERT dbo.BEMT2009
        (
            APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
            DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
            NormalizeMode, CompareMode, CompareParams, LLMPolicy
        )
        VALUES
        (
            CONVERT(uniqueidentifier, 'D3602460-2286-47F7-A970-5CCAA0BF7B15'),
            'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE',
            'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceNo',
            'PACKINGLIST', 'PackingListNo', 'OPTIONAL', 2,
            'INVOICE_NO_AND_DATE', NULL, NULL, NULL
        );

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE APK = CONVERT(uniqueidentifier, 'CFAE20C3-3D8E-4050-A504-CA22D178099C')
    )
        INSERT dbo.BEMT2009
        (
            APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
            DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
            NormalizeMode, CompareMode, CompareParams, LLMPolicy
        )
        VALUES
        (
            CONVERT(uniqueidentifier, 'CFAE20C3-3D8E-4050-A504-CA22D178099C'),
            'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE',
            'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceDate',
            'PACKINGLIST', 'PackingListDate', 'OPTIONAL', 2,
            'DATE', NULL, NULL, NULL
        );

    UPDATE dbo.BEMT2009
    SET IsActive = 1,
        MatchPolicy = 'OPTIONAL',
        Priority = 2
    WHERE APK IN
    (
        CONVERT(uniqueidentifier, 'D3602460-2286-47F7-A970-5CCAA0BF7B15'),
        CONVERT(uniqueidentifier, 'CFAE20C3-3D8E-4050-A504-CA22D178099C')
    );

    UPDATE dbo.BEMT2009
    SET CompareParams = N'groupBy=VoucherNo;customsPriority=COMMERCIALINVOICE,INVOICE;statement=OPTIONAL;packingList=OPTIONAL;dateToleranceDays=0;stripCustomsPrefix=1;missing=BLANK;unmatched=NG'
    WHERE IsActive = 1
      AND RecordType = 'RULE'
      AND GroupCode = 'NVL_NGAY_HOA_DON_V1'
      AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_INVOICE_DATE'
      AND CompareMode = 'NVL_INVOICE_DATE_BY_NO';

    UPDATE dbo.BEMT2009
    SET IsActive = 1,
        MatchPolicy = 'OPTIONAL',
        Priority = 2
    WHERE GroupCode = 'NVL_LOAI_TIEN_V1'
      AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_CURRENCY'
      AND RecordType = 'MAPPING'
      AND EvidenceTypeCode = 'RINGI'
      AND EvidenceFieldCode = 'Currency';

    DELETE FROM dbo.BEMT2009
    WHERE GroupCode = 'NVL_DIEU_KIEN_GIAO_HANG_V1'
      AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_INCOTERM'
      AND RecordType = 'MAPPING'
      AND EvidenceTypeCode = 'INVOICE'
      AND EvidenceFieldCode = 'DeliveryTerm';

    UPDATE dbo.BEMT2009
    SET CompareParams = N'docTypes=PO,COMMERCIALINVOICE,CUSTOMSHEET;minimumValidTypes=2;representative=MAJORITY;tie=NG;noise=IGNORE;coverage=INCOTERM>COUNTRY>PROVINCE;missing=BLANK;mismatch=NG'
    WHERE IsActive = 1
      AND RecordType = 'RULE'
      AND GroupCode = 'NVL_DIEU_KIEN_GIAO_HANG_V1'
      AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
      AND CriterionCode = 'CRITERIA_INCOTERM'
      AND CompareMode = 'NVL_DELIVERY_TERM_COMPATIBILITY';

    IF
    (
        SELECT COUNT(*)
        FROM dbo.BEMT2009
        WHERE IsActive = 1
          AND GroupCode = 'NVL_NGAY_HOA_DON_V1'
          AND EvidenceTypeCode = 'PACKINGLIST'
          AND EvidenceFieldCode IN ('PackingListNo', 'PackingListDate')
    ) <> 2
        THROW 51061, N'Packing list invoice-date mappings were not synchronized.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE IsActive = 1
          AND GroupCode = 'NVL_LOAI_TIEN_V1'
          AND EvidenceTypeCode = 'RINGI'
          AND EvidenceFieldCode = 'Currency'
    )
        THROW 51062, N'Ringi currency mapping was not activated.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.BEMT2009
        WHERE IsActive = 1
          AND GroupCode = 'NVL_DIEU_KIEN_GIAO_HANG_V1'
          AND EvidenceTypeCode = 'INVOICE'
    )
        THROW 51063, N'Invoice delivery-term mapping is still active.', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SELECT CriterionCode, RecordType, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, CompareParams
FROM dbo.BEMT2009
WHERE IsActive = 1
  AND DnttTypeCode = 'BEM_AGENT_BEMF2000_WAREHOUSE'
  AND CriterionCode IN ('CRITERIA_INVOICE_DATE', 'CRITERIA_CURRENCY', 'CRITERIA_INCOTERM')
ORDER BY CriterionCode, CASE WHEN RecordType = 'RULE' THEN 0 ELSE 1 END, Priority, EvidenceTypeCode;
GO

-- Sau script này, chạy ba file prompt SQL tương ứng để đồng bộ ONT1042:
-- Prompt_WareHouse_VoucherDate.sql
-- Prompt_WareHouse_Currency.sql
-- Prompt_WareHouse_DeliveryTerm.sql
