/*
  One-time deployment script for Mapping + Rule Engine configuration.
  - Creates dbo.BEMT2009 when it does not exist.
  - Converts an old BEMT2009 table that still has ONT1041 APK columns.
  - Seeds exactly 35 approved code-based configuration rows.
  - Drops dbo.ONT1043 only after BEMT2009 is validated.
  BEMT2009.APK remains a technical row key; business configuration uses stable Code columns.
*/
SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    /* Existing old BEMT2009 schema: convert APK references to stable ParameterName codes. */
    IF OBJECT_ID(N'dbo.BEMT2009', N'U') IS NOT NULL
       AND COL_LENGTH(N'dbo.BEMT2009', N'DnttTypeCode') IS NULL
    BEGIN
        IF OBJECT_ID(N'dbo.BEMT2009_CodeMigration', N'U') IS NOT NULL
            DROP TABLE dbo.BEMT2009_CodeMigration;

        CREATE TABLE dbo.BEMT2009_CodeMigration
        (
            APK uniqueidentifier NOT NULL CONSTRAINT DF_BEMT2009_CodeMigration_APK DEFAULT (newid()),
            RecordType varchar(20) NOT NULL,
            GroupCode varchar(100) NOT NULL,
            DnttTypeCode varchar(100) NOT NULL,
            CriterionCode varchar(100) NOT NULL,
            Version varchar(50) NOT NULL,
            IsActive bit NOT NULL CONSTRAINT DF_BEMT2009_CodeMigration_IsActive DEFAULT ((1)),
            DnttFieldCode varchar(200) NULL,
            EvidenceTypeCode varchar(100) NULL,
            EvidenceFieldCode varchar(100) NULL,
            MatchPolicy varchar(50) NULL,
            Priority int NULL,
            NormalizeMode varchar(50) NULL,
            CompareMode varchar(100) NULL,
            CompareParams nvarchar(4000) NULL,
            LLMPolicy varchar(100) NULL,
            CONSTRAINT PK_BEMT2009_CodeMigration PRIMARY KEY CLUSTERED (APK ASC)
        );

        /* Dynamic SQL prevents SQL Server from compiling obsolete APK columns
           when the current BEMT2009 table is already code-based. */
        EXEC sys.sp_executesql N'
            INSERT INTO dbo.BEMT2009_CodeMigration
            (
                APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
                DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
                NormalizeMode, CompareMode, CompareParams, LLMPolicy
            )
            SELECT
                O.APK, O.RecordType, O.GroupCode,
                DT.ParameterName, CR.ParameterName, O.Version, O.IsActive,
                O.DnttFieldCode, ET.ParameterName, EF.ParameterName, O.MatchPolicy, O.Priority,
                O.NormalizeMode, O.CompareMode, O.CompareParams, O.LLMPolicy
            FROM dbo.BEMT2009 O
            INNER JOIN dbo.ONT1041 DT ON DT.APK = O.DnttTypeAPK
            INNER JOIN dbo.ONT1041 CR ON CR.APK = O.CriterionAPK
            LEFT JOIN dbo.ONT1041 ET ON ET.APK = O.EvidenceTypeAPK
            LEFT JOIN dbo.ONT1041 EF ON EF.APK = O.EvidenceFieldAPK;';

        IF (SELECT COUNT(*) FROM dbo.BEMT2009_CodeMigration) <> 33
            THROW 51002, N'BEMT2009 conversion failed: expected exactly 33 current rows.', 1;

        IF EXISTS
        (
            SELECT 1
            FROM dbo.BEMT2009_CodeMigration
            WHERE DnttTypeCode IS NULL
               OR CriterionCode IS NULL
               OR (RecordType = 'MAPPING' AND (EvidenceTypeCode IS NULL OR EvidenceFieldCode IS NULL))
        )
            THROW 51003, N'BEMT2009 conversion failed: missing required business code.', 1;

        DROP TABLE dbo.BEMT2009;
        EXEC sp_rename N'dbo.BEMT2009_CodeMigration', N'BEMT2009';
        EXEC sp_rename N'dbo.PK_BEMT2009_CodeMigration', N'PK_BEMT2009', N'OBJECT';
        IF OBJECT_ID(N'dbo.DF_BEMT2009_CodeMigration_APK', N'D') IS NOT NULL
            EXEC sp_rename N'dbo.DF_BEMT2009_CodeMigration_APK', N'DF_BEMT2009_APK', N'OBJECT';
        IF OBJECT_ID(N'dbo.DF_BEMT2009_CodeMigration_IsActive', N'D') IS NOT NULL
            EXEC sp_rename N'dbo.DF_BEMT2009_CodeMigration_IsActive', N'DF_BEMT2009_IsActive', N'OBJECT';
    END;

    /* Fresh deployment: create the final code-based schema. */
    IF OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL
    BEGIN

        CREATE TABLE dbo.BEMT2009
        (
            APK uniqueidentifier NOT NULL CONSTRAINT DF_BEMT2009_APK DEFAULT (newid()),
            RecordType varchar(20) NOT NULL,
            GroupCode varchar(100) NOT NULL,
            DnttTypeCode varchar(100) NOT NULL,
            CriterionCode varchar(100) NOT NULL,
            Version varchar(50) NOT NULL,
            IsActive bit NOT NULL CONSTRAINT DF_BEMT2009_IsActive DEFAULT ((1)),
            DnttFieldCode varchar(200) NULL,
            EvidenceTypeCode varchar(100) NULL,
            EvidenceFieldCode varchar(100) NULL,
            MatchPolicy varchar(50) NULL,
            Priority int NULL,
            NormalizeMode varchar(50) NULL,
            CompareMode varchar(100) NULL,
            CompareParams nvarchar(4000) NULL,
            LLMPolicy varchar(100) NULL,
            CONSTRAINT PK_BEMT2009 PRIMARY KEY CLUSTERED (APK ASC)
        );
    END;

    IF COL_LENGTH(N'dbo.BEMT2009', N'DnttTypeCode') IS NULL
        THROW 51004, N'BEMT2009 is not using the required code-based schema.', 1;

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.BEMT2009') AND name = N'IX_BEMT2009_RuntimeLookup'
    )
        CREATE INDEX IX_BEMT2009_RuntimeLookup
            ON dbo.BEMT2009
            (
                DnttTypeCode ASC,
                CriterionCode ASC,
                IsActive ASC,
                GroupCode ASC,
                Version ASC
            )
            INCLUDE
            (
                RecordType, DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode,
                MatchPolicy, Priority, NormalizeMode, CompareMode, LLMPolicy
            );

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.BEMT2009') AND name = N'UX_BEMT2009_ActiveRule'
    )
        CREATE UNIQUE INDEX UX_BEMT2009_ActiveRule
            ON dbo.BEMT2009 (DnttTypeCode ASC, CriterionCode ASC, GroupCode ASC)
            WHERE IsActive = 1 AND RecordType = 'RULE';

    ;WITH SeedData
    (
        APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
        DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
        NormalizeMode, CompareMode, CompareParams, LLMPolicy
    ) AS
    (
        SELECT CONVERT(uniqueidentifier, '01101BCE-CCBD-4694-B318-2D49A1133C21'), 'MAPPING', 'NVL_DIEU_KIEN_GIAO_HANG_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INCOTERM', 'nvl-v1', 1, 'BEMT2001.APK', 'CUSTOMSHEET', 'DeliveryTerm', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'C27657E4-43B1-4A72-A5DA-6940EF4FAEE3'), 'MAPPING', 'NVL_DIEU_KIEN_GIAO_HANG_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INCOTERM', 'nvl-v1', 1, 'BEMT2001.APK', 'PO', 'DeliveryTerm', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '9F458A98-0886-49B9-AA4B-D60C1F79B107'), 'MAPPING', 'NVL_DIEU_KIEN_GIAO_HANG_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INCOTERM', 'nvl-v1', 1, 'BEMT2001.APK', 'COMMERCIALINVOICE', 'DeliveryTerm', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'D6255CEC-8068-4FBF-B38F-7218C83C8B5A'), 'RULE', 'NVL_DIEU_KIEN_GIAO_HANG_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INCOTERM', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'DELIVERY_TERM', 'NVL_DELIVERY_TERM_COMPATIBILITY', N'docTypes=PO,COMMERCIALINVOICE,CUSTOMSHEET;minimumValidTypes=2;representative=MAJORITY;tie=NG;noise=IGNORE;coverage=INCOTERM>COUNTRY>PROVINCE;missing=BLANK;mismatch=NG', 'REVIEW_ON_UNKNOWN_LOCATION'
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'EAF438E2-59A3-49B0-A7BE-083891D92F57'), 'MAPPING', 'NVL_HAN_THANH_TOAN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_PAYMENT_DEADLINE', 'nvl-v1', 1, 'BEMT2000.Deadline', 'PO', 'PaymentTerm', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'CCE88023-1C12-415E-A9C4-75A23D2229CB'), 'MAPPING', 'NVL_HAN_THANH_TOAN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_PAYMENT_DEADLINE', 'nvl-v1', 1, 'BEMT2000.Deadline', 'CUSTOMSHEET', 'ArrivalDate', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '438E4AE9-C17F-49B1-A1B6-A41E90783274'), 'MAPPING', 'NVL_HAN_THANH_TOAN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_PAYMENT_DEADLINE', 'nvl-v1', 1, 'BEMT2000.Deadline', 'INVOICE', 'VoucherDate', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'D76EC3EB-D274-4321-97A6-DEE86D9D9B55'), 'MAPPING', 'NVL_HAN_THANH_TOAN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_PAYMENT_DEADLINE', 'nvl-v1', 1, 'BEMT2000.Deadline', 'COMMERCIALINVOICE', 'VoucherDate', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '15CD0A80-8C8A-4F4C-9B8C-17513DBEFF6A'), 'MAPPING', 'NVL_HAN_THANH_TOAN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_PAYMENT_DEADLINE', 'nvl-v1', 0, 'BEMT2000.Deadline', 'BILL', 'BillDate', 'OPTIONAL', 2, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'A6C8F996-7714-4A25-ABF1-3374B0E81386'), 'RULE', 'NVL_HAN_THANH_TOAN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_PAYMENT_DEADLINE', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'PAYMENT_TERM_AND_DATE', 'NVL_PAYMENT_DEADLINE', N'paymentTerm=PO.PaymentTerm;selectTerm=MAJORITY;AMS=CUSTOMSHEET.ArrivalDate;AFTER_BL=INVOICE.VoucherDate,COMMERCIALINVOICE.VoucherDate;monthEnd=1;holiday=PREVIOUS_WORKDAY;compareWith=BEMT2000.Deadline;missing=BLANK;conflict=BLANK', 'NEVER'
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '6FCE9EDC-26C8-4EF3-A0B2-07EAA3CFB7F9'), 'MAPPING', 'NVL_LOAI_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CURRENCY', 'nvl-v1', 1, 'BEMT2001.CurrencyID', 'CUSTOMSHEET', 'Currency', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'A5CC7732-10BD-493F-BE64-53D854302371'), 'MAPPING', 'NVL_LOAI_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CURRENCY', 'nvl-v1', 1, 'BEMT2001.CurrencyID', 'COMMERCIALINVOICE', 'Currency', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '520B57CB-3F5E-4E6C-B8B1-9D5A4A164EC0'), 'MAPPING', 'NVL_LOAI_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CURRENCY', 'nvl-v1', 1, 'BEMT2001.CurrencyID', 'INVOICE', 'Currency', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'F12DB6E4-6A7B-4210-9260-DE4B9EB7A99A'), 'MAPPING', 'NVL_LOAI_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CURRENCY', 'nvl-v1', 1, 'BEMT2001.CurrencyID', 'PO', 'Currency', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '837B78D4-B95E-47F5-A19D-9A442B2EF6C3'), 'MAPPING', 'NVL_LOAI_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CURRENCY', 'nvl-v1', 1, 'BEMT2001.CurrencyID', 'RINGI', 'Currency', 'OPTIONAL', 2, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'D435646D-A835-4E91-9146-E4471CF6A9BD'), 'MAPPING', 'NVL_LOAI_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CURRENCY', 'nvl-v1', 1, 'BEMT2001.CurrencyID', 'STATEMENT', 'Currency', 'OPTIONAL', 2, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'FC7F3AD2-8EB6-409D-BD48-C1D57AF3F428'), 'RULE', 'NVL_LOAI_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CURRENCY', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'CURRENCY', 'NVL_CURRENCY_ALL_MATCH', N'includeDntt=1;aliases=USD:US$,US_DOLLAR|JPY:JY,YEN,YEN_JAPAN,¥|VND:VNĐ,VIETNAM_DONG|EUR:€,EURO;missing=BLANK;mismatch=NG', 'REVIEW_ON_UNKNOWN_CURRENCY'
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '4A94C6A7-5342-462C-9D0B-2FE2E126B84A'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceDate', 'CUSTOMSHEET', 'VoucherDate', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'B614FAC7-C808-484A-8987-342D65BAFFAF'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'COMMERCIALINVOICE', 'VoucherNo', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '751AC3EA-7CBD-4EFE-B273-4DFF50AC7CC5'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceDate', 'INVOICE', 'VoucherDate', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '86717D0D-18CE-476A-A40C-6A22DD2616EE'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'CUSTOMSHEET', 'VoucherNo', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '2C185271-289F-4E24-9517-82827B419E79'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceDate', 'COMMERCIALINVOICE', 'VoucherDate', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '9E0A27A6-16FD-40F8-84A9-C6060DB42DFB'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'INVOICE', 'VoucherNo', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'B9A3C5A7-DACF-432C-A9D7-0F3D40CC0C06'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'STATEMENT', 'VoucherNo', 'OPTIONAL', 2, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'D2FB06ED-FF36-4667-9B09-35E86E6E2A46'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceDate', 'STATEMENT', 'VoucherDate', 'OPTIONAL', 2, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'D3602460-2286-47F7-A970-5CCAA0BF7B15'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'PACKINGLIST', 'PackingListNo', 'OPTIONAL', 2, 'INVOICE_NO_AND_DATE', NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'CFAE20C3-3D8E-4050-A504-CA22D178099C'), 'MAPPING', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, 'BEMT2001.InvoiceDate', 'PACKINGLIST', 'PackingListDate', 'OPTIONAL', 2, 'DATE', NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'F9EEE98A-1F3E-452F-8C31-069A213362AE'), 'RULE', 'NVL_NGAY_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_DATE', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'INVOICE_NO_AND_DATE', 'NVL_INVOICE_DATE_BY_NO', N'groupBy=VoucherNo;customsPriority=COMMERCIALINVOICE,INVOICE;statement=OPTIONAL;packingList=OPTIONAL;dateToleranceDays=0;stripCustomsPrefix=1;missing=BLANK;unmatched=NG', 'REVIEW_ON_AMBIGUOUS_GROUP'
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'B3247DCE-E9D3-450E-8E3A-3727B021E1C4'), 'MAPPING', 'NVL_NGAY_HOAN_THANH_KIEM_TRA_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CHECK_COMPLETED_DATE', 'nvl-v1', 1, 'BEMT2001.APK', 'CUSTOMSHEET', 'ClearanceStatus', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '1BDDDC2B-B0EA-40BF-BC1B-FF83C10E71BA'), 'RULE', 'NVL_NGAY_HOAN_THANH_KIEM_TRA_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_CHECK_COMPLETED_DATE', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'CLEARANCE_STATUS', 'NVL_CLEARANCE_STATUS_ALL_YES', N'docTypes=CUSTOMSHEET;yes=OK;no=NG;missing=BLANK', 'NEVER'
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '503169C0-0DEF-4632-876F-3C22AD703254'), 'MAPPING', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_NO', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'INVOICE', 'VoucherNo', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '337BCE0A-DF63-4B4E-978B-940C01F1DFB6'), 'MAPPING', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_NO', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'COMMERCIALINVOICE', 'VoucherNo', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'A3B48FDC-8140-4070-ACB0-FACE4064BF78'), 'MAPPING', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_NO', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'CUSTOMSHEET', 'VoucherNo', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'AAB40CE9-B4E0-4EC0-8F65-C6F5BFE31D4C'), 'MAPPING', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_NO', 'nvl-v1', 1, 'BEMT2001.InvoiceNo', 'STATEMENT', 'VoucherNo', 'OPTIONAL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'C4C4B438-4770-4A78-91CD-3946F70B9B6E'), 'MAPPING', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_NO', 'nvl-v1', 1, 'BEMT2001.ListNo', 'STATEMENT', 'ListNo', 'OPTIONAL', 2, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '51BA011D-EED0-4971-AADA-49F90922B023'), 'RULE', 'NVL_SO_HOA_DON_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_INVOICE_NO', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'INVOICE_NO', 'NVL_INVOICE_NO_MATCH', N'primary=DNTT>INVOICE,COMMERCIALINVOICE;customs=CUSTOMSHEET>COMMERCIALINVOICE,INVOICE;statementType=STATEMENT;statementKeyField=ListNo;statementInvoiceField=VoucherNo;branchPolicy=ANY_COMPLETE_BRANCH_OK;stripSeparators=SPACE,-,.,/;stripCustomsPrefix=1;expandShortRange=1;similarity=0.8;missing=BLANK;mismatch=NG', 'REVIEW_ON_AMBIGUITY'
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'D7B92E37-C8CE-451F-BEB8-17C0C155F976'), 'MAPPING', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, 'BEMT2001.APK', 'PO', 'Signature', 'ALL', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '00FD8D88-F403-4CDB-9470-180C530CBDDE'), 'MAPPING', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, 'BEMT2001.APK', 'INVOICE', 'Signature', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '4254C22F-99A2-4B23-A0AA-4167A654CC06'), 'MAPPING', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, 'BEMT2001.APK', 'COMMERCIALINVOICE', 'Signature', 'ANY', 1, NULL, NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'F83ACF96-4FBF-44FB-9AF0-8544C79662E2'), 'RULE', 'NVL_CHU_KY_CON_DAU_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_SIGNATURE_STAMP', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'SIGNATURE_STATUS', 'NVL_SIGNATURE_STAMP_VALIDATION', N'requiredAll=PO;requiredAny=INVOICE,COMMERCIALINVOICE;selectedBlank=NG;fallbackBlank=BLANK;missing=BLANK', 'NEVER'
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '7C788856-FE36-41CC-B8C2-6DCB48967A28'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'INVOICE', 'Amount', 'ANY', 1, 'DECIMAL', NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '581063E2-254A-4FE3-B200-67F315458D0F'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'COMMERCIALINVOICE', 'Amount', 'ANY', 1, 'DECIMAL', NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '3591FA92-E56F-434D-A74D-20FD01A49417'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'CUSTOMSHEET', 'Amount', 'ALL', 1, 'DECIMAL', NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, 'E700E2F8-34B6-4D6B-96E8-9F767B410AEC'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2002.RequestAmount', 'STATEMENT', 'Amount', 'OPTIONAL', 2, 'DECIMAL', NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '8C051A90-1EAC-40AE-8DB1-0514AD623F1F'), 'MAPPING', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, 'BEMT2001.TotalAmount', 'RINGI', 'Amount', 'OPTIONAL', 2, 'DECIMAL', NULL, NULL, NULL
        UNION ALL
        SELECT CONVERT(uniqueidentifier, '0FFAD700-3D9B-459A-A0C5-836EAA824EF2'), 'RULE', 'NVL_SO_TIEN_V1', 'BEM_AGENT_BEMF2000_WAREHOUSE', 'CRITERIA_AMOUNT', 'nvl-v1', 1, NULL, NULL, NULL, NULL, NULL, 'DECIMAL', 'NVL_AMOUNT_MATCH', N'tolerance=10;ringiMinRatio=1;ringiMaxRatio=NONE;statementType=STATEMENT;statementInvoiceField=VoucherNo;missing=REVIEW;mismatch=NG', 'NEVER'
    )
    INSERT INTO dbo.BEMT2009
    (
        APK, RecordType, GroupCode, DnttTypeCode, CriterionCode, Version, IsActive,
        DnttFieldCode, EvidenceTypeCode, EvidenceFieldCode, MatchPolicy, Priority,
        NormalizeMode, CompareMode, CompareParams, LLMPolicy
    )
    SELECT *
    FROM SeedData S
    WHERE NOT EXISTS (SELECT 1 FROM dbo.BEMT2009 B WHERE B.APK = S.APK);

    IF (SELECT COUNT(*) FROM dbo.BEMT2009) <> 46
        THROW 51005, N'BEMT2009 seed failed: row count must be exactly 46.', 1;

    IF OBJECT_ID(N'dbo.ONT1043', N'U') IS NOT NULL
        DROP TABLE dbo.ONT1043;


    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    DECLARE @ErrorMessage nvarchar(4000) = ERROR_MESSAGE();
    DECLARE @ErrorSeverity int = ERROR_SEVERITY();
    DECLARE @ErrorState int = ERROR_STATE();
    RAISERROR(@ErrorMessage, @ErrorSeverity, @ErrorState);
END CATCH;
GO

SELECT
    CASE WHEN OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL THEN 0 ELSE 1 END AS HasBEMT2009,
    CASE WHEN OBJECT_ID(N'dbo.ONT1043', N'U') IS NULL THEN 0 ELSE 1 END AS HasONT1043,
    CASE WHEN COL_LENGTH(N'dbo.BEMT2009', N'DnttTypeCode') IS NULL THEN 0 ELSE 1 END AS HasDnttTypeCode,
    CASE WHEN COL_LENGTH(N'dbo.BEMT2009', N'DnttTypeAPK') IS NULL THEN 0 ELSE 1 END AS HasDnttTypeAPK,
    CASE WHEN OBJECT_ID(N'dbo.BEMT2009', N'U') IS NULL THEN 0 ELSE (SELECT COUNT(*) FROM dbo.BEMT2009) END AS BEMT2009_RowCount;
GO
