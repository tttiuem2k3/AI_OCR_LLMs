IF EXISTS (SELECT TOP 1 1 FROM DBO.SYSOBJECTS WHERE ID = OBJECT_ID(N'[DBO].[ONP1046]') AND  OBJECTPROPERTY(ID, N'IsProcedure') = 1)			
DROP PROCEDURE [DBO].[ONP1046]
GO
SET QUOTED_IDENTIFIER ON
GO
SET ANSI_NULLS ON
GO
CREATE PROCEDURE [dbo].[ONP1046]
(
	@CaseType		INT,				-- 1: ONT1041 -> NodeParent -> ParameterID -> query động ONT1042
									-- 2: ONT1040 theo TypeConfigID -> ONT1042 theo APK_ONT1040
	@ParameterName	NVARCHAR(250) = NULL,	-- dùng cho Case 1
	@TypeConfigID	NVARCHAR(50)  = NULL	-- dùng cho Case 2
)
AS
BEGIN
	SET NOCOUNT ON;

	DECLARE 
		@APK_ONT1041		UNIQUEIDENTIFIER,
		@NodeParent			UNIQUEIDENTIFIER,
		@ColumnName			SYSNAME,
		@SQL				NVARCHAR(MAX),
		@APK_ONT1040		UNIQUEIDENTIFIER,
		@CriteriaName		NVARCHAR(250);

	-- CASE 1: sử dụng map ONT1041 -> ONT1042
	IF @CaseType = 1
    BEGIN
        -- Tìm dòng ONT1041 theo ParameterName
        SELECT TOP 1
            @APK_ONT1041 = APK,
            @NodeParent   = NodeParent
        FROM ONT1041 WITH (NOLOCK)
        WHERE ParameterName = @ParameterName
          AND ISNULL(Disabled, 0) = 0;

        IF @APK_ONT1041 IS NULL
        BEGIN
            RAISERROR (N'Không tìm thấy ONT1041 theo ParameterName.', 16, 1);
            RETURN;
        END

        -- Từ NodeParent lấy ParameterID
        -- ParameterID này là tên cột động dùng để lọc ONT1042
        SELECT TOP 1
            @ColumnName = ParameterID
        FROM ONT1041 WITH (NOLOCK)
        WHERE APK = @NodeParent
          AND ISNULL(Disabled, 0) = 0;

        IF ISNULL(@ColumnName, '') = ''
        BEGIN
            RAISERROR (N'Không tìm thấy ParameterID từ NodeParent.', 16, 1);
            RETURN;
        END

        -- Kiểm tra cột động có tồn tại trong ONT1042
        IF NOT EXISTS
        (
            SELECT 1
            FROM sys.columns
            WHERE object_id = OBJECT_ID(N'dbo.ONT1042')
              AND name = @ColumnName
        )
        BEGIN
            RAISERROR (N'Cột động không tồn tại trong bảng ONT1042.', 16, 1);
            RETURN;
        END

        -- Query ONT1042 theo điều kiện động.
        -- Sau khi lấy được ONT1042, dùng ParameterID07
        -- để truy ngược ONT1041 lấy CriteriaName và MatchedColumn.
        SET @SQL = N'
            SELECT
                T42.*,

                -- Tên tiêu chí thực tế
                T41Criteria.DisplayName AS CriteriaName,

                -- ParameterID thực tế của tiêu chí
                T41Criteria.ParameterID AS MatchedColumn,

                @APK_ONT1041 AS SourceAPK_ONT1041,
                @NodeParent AS SourceNodeParent

            FROM ONT1042 T42 WITH (NOLOCK)

            LEFT JOIN ONT1041 T41Criteria WITH (NOLOCK)
                ON T41Criteria.APK = T42.ParameterID07
               AND ISNULL(T41Criteria.Disabled, 0) = 0

            WHERE ' + QUOTENAME(@ColumnName) + N' = @APK_ONT1041
              AND ISNULL(T42.Disabled, 0) <> 1
        ';

        EXEC sp_executesql
            @SQL,
            N'@APK_ONT1041 UNIQUEIDENTIFIER,
              @NodeParent UNIQUEIDENTIFIER',
            @APK_ONT1041 = @APK_ONT1041,
            @NodeParent  = @NodeParent;

        RETURN;
    END

	-- CASE 2: ONT1040 theo TypeConfigID -> ONT1042 theo APK_ONT1040
	IF @CaseType = 2
	BEGIN
		IF ISNULL(@TypeConfigID, '') = ''
		BEGIN
			RAISERROR (N'Case 2 yêu cầu truyền @TypeConfigID.', 16, 1);
			RETURN;
		END

		SELECT TOP 1
			@APK_ONT1040 = APK
		FROM ONT1040 WITH (NOLOCK)
		WHERE TypeConfigID = @TypeConfigID
		  AND ISNULL(Disabled, 0) <> 1;

		IF @APK_ONT1040 IS NULL
		BEGIN
			RAISERROR (N'Không tìm thấy ONT1040 theo TypeConfigID.', 16, 1);
			RETURN;
		END

		SELECT 
			ON42.*,
			ON40.TypeName AS CriteriaName
		FROM ONT1042 ON42 WITH (NOLOCK)
		INNER JOIN ONT1040 ON40 WITH (NOLOCK) ON ON40.APK = ON42.APK_ONT1040
		WHERE ON42.APK_ONT1040 = @APK_ONT1040
		  AND ISNULL(ON42.Disabled, 0) <> 1;

		RETURN;
	END

	RAISERROR (N'@CaseType không hợp lệ. Chỉ chấp nhận 1 hoặc 2.', 16, 1);
END
GO
SET QUOTED_IDENTIFIER OFF
GO
SET ANSI_NULLS ON
GO

