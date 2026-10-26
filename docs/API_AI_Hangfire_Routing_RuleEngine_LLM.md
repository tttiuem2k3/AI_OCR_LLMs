# Hướng dẫn API-AI/Hangfire: tách đối chiếu Rule Engine và LLM

## 1. Mục tiêu

Sau khi OCR và trích xuất của một phiếu hoàn tất, API-AI phải tạo job đối chiếu theo **từng tiêu chí**. Mỗi tiêu chí được đưa ngay vào queue Rule Engine hoặc queue LLM để hai nhóm chạy song song.

- Rule Engine xử lý trước các tiêu chí đã đủ Mapping + Rule active trong `dbo.BEMT2009`.
- LLM xử lý các tiêu chí chưa có Rule khả dụng và các tiêu chí Rule trả `REVIEW` khi policy cho phép.
- API-AI quản lý queue, retry, trạng thái và lưu kết quả; AI Python chỉ xử lý đúng mode được chỉ định.

`BEMT2009.CompareMode` là mã thuật toán Rule Engine, ví dụ `NVL_INVOICE_NO_MATCH`. Không dùng tên này cho mode gọi API.

## 2. Luồng cần thay đổi tại API-AI

Luồng cũ tạo một job rồi `BuildCriteriaListAsync` gọi tuần tự từng prompt trong `ReadFileBackgroundWorkflow`.

Luồng Hangfire mới:

```text
OCR/Trích xuất của phiếu DONE
        |
        +-- lấy danh sách prompt tiêu chí và mã cấu hình
        |
        +-- đọc route cache BEMT2009
        |
        +-- Rule khả dụng  -> enqueue compare-rule / RULE_ENGINE
        |
        +-- Rule chưa khả dụng -> enqueue compare-llm / LLM
        |
        +-- Rule trả REVIEW -> enqueue compare-llm / LLM (nếu LLMPolicy cho phép)
        |
        +-- tất cả tiêu chí final -> tổng hợp/lưu BEMT2004 và hoàn tất phiếu
```

Không dùng `AUTO` làm mode chính trong Hangfire. `AUTO` chỉ giữ cho luồng cũ hoặc gọi thủ công tương thích ngược.

## 3. Mã định tuyến phải có trước khi enqueue

Không dùng `CriteriaName` tiếng Việt để route. Không hard-code sáu tiêu chí NVL trong C#.

`PromptContentViewModel` hiện chỉ có `APK`, `CriteriaName`, `PromptUser`, `PromptSystem`. Cần bổ sung hai mã ổn định khi lấy prompt từ `ONT1042/ONP1046`:

```csharp
public string DnttTypeCode { get; set; } = null!;
public string CriterionCode { get; set; } = null!;
```

- `DnttTypeCode`: ví dụ `BEM_AGENT_BEMF2000_WAREHOUSE`.
- `CriterionCode`: ví dụ `CRITERIA_INVOICE_NO`.
- Hai mã này phải lấy từ cấu hình Prompt/Parameter hiện có, không tự suy từ `CriteriaName` ở runtime.
- Hai mã phải trùng `BEMT2009.DnttTypeCode` và `BEMT2009.CriterionCode`.

Lý do: sửa tên hiển thị tiêu chí hoặc thêm tiêu chí mới không làm route Hangfire sai và không buộc sửa code API-AI.

## 4. Query tạo route cache từ BEMT2009

API-AI tải cache này lúc service khởi động và refresh ngắn hạn, ví dụ 30 giây. Cache chỉ phục vụ chọn queue; AI Python vẫn đọc đầy đủ Mapping/Rule để xử lý nghiệp vụ.

```sql
;WITH ActiveRule AS
(
    SELECT
        DnttTypeCode,
        CriterionCode,
        GroupCode,
        Version,
        MAX(LLMPolicy) AS LLMPolicy,
        COUNT(*) AS ActiveRuleCount
    FROM dbo.BEMT2009
    WHERE IsActive = 1
      AND RecordType = 'RULE'
    GROUP BY DnttTypeCode, CriterionCode, GroupCode, Version
), RuleSummary AS
(
    SELECT
        DnttTypeCode,
        CriterionCode,
        COUNT(*) AS ActiveRuleGroupCount,
        MAX(GroupCode) AS GroupCode,
        MAX(Version) AS Version,
        MAX(LLMPolicy) AS LLMPolicy
    FROM ActiveRule
    GROUP BY DnttTypeCode, CriterionCode
)
SELECT
    R.DnttTypeCode,
    R.CriterionCode,
    CASE
        WHEN R.ActiveRuleGroupCount = 1
         AND EXISTS
         (
             SELECT 1
             FROM dbo.BEMT2009 M
             WHERE M.IsActive = 1
               AND M.RecordType = 'MAPPING'
               AND M.DnttTypeCode = R.DnttTypeCode
               AND M.CriterionCode = R.CriterionCode
               AND M.GroupCode = R.GroupCode
               AND M.Version = R.Version
         )
        THEN 'RULE_ENGINE'
        ELSE 'LLM'
    END AS CompareExecutionMode,
    ISNULL(R.LLMPolicy, 'NEVER') AS LLMPolicy
FROM RuleSummary R;
```

Quy tắc route:

- Có đúng một group `RULE` active và có ít nhất một dòng `MAPPING` active cùng `GroupCode`/`Version` -> `RULE_ENGINE`.
- Không có route trong cache, có nhiều group Rule active, thiếu Mapping hoặc cấu hình không hợp lệ -> `LLM`.
- Khi thêm/sửa Rule, cache tự refresh; không cần hard-code lại tiêu chí ở API-AI.

## 5. Gọi AI Python

Vẫn gọi endpoint hiện tại:

```text
POST /llms/api/ai_llms_models?Token=...
```

System Prompt/User Prompt giữ nguyên. Bổ sung field top-level:

```json
{
  "messages": [
    { "role": "system", "content": "System Prompt hiện tại" },
    { "role": "user", "content": "User Prompt hiện tại" }
  ],
  "CompareExecutionMode": "RULE_ENGINE"
}
```

Giá trị hợp lệ:

| Giá trị | AI Python xử lý |
| --- | --- |
| `RULE_ENGINE` | Mapping -> Rule Engine. Không gọi LLM. Không có cấu hình/không đủ căn cứ thì trả `REVIEW`. |
| `LLM` | Không chạy Mapping/Rule Engine mới từ `BEMT2009`; chạy nhánh LLM đối chiếu hiện tại. |
| `AUTO` hoặc không gửi | Tương thích ngược: Python tự chạy Rule Engine trước rồi mới fallback LLM theo `LLMPolicy`. Không dùng làm luồng Hangfire chính. |

AI Python chấp nhận alias cũ `RULE_ONLY`, `LLM_ONLY`, `CompareMode`, `compareMode` để triển khai không bị lỗi tên field; API-AI mới chỉ nên gửi `CompareExecutionMode`.

Kết quả cuối vẫn theo schema đang dùng:

```json
{
  "criteria": {
    "CriteriaName": "Số hóa đơn",
    "CriteriaStatus": "OK",
    "FileName": "CI.pdf",
    "Description": "..."
  }
}
```

## 6. Cách xử lý response trong Hangfire

### Queue `compare-rule`

- Gọi Python với `CompareExecutionMode = RULE_ENGINE`.
- `CriteriaStatus = OK`, `NG`, `BLANK`: kết quả cuối. Lưu bằng luồng ghi `BEMT2004` hiện có; `BLANK` giữ cách quy đổi hiện tại của API-AI.
- `CriteriaStatus = REVIEW`: không ghi `BEMT2004` là kết quả cuối. Đọc `LLMPolicy` của route cache:
  - bắt đầu bằng `REVIEW_` -> enqueue `compare-llm` cho cùng phiếu/cùng Prompt APK;
  - `NEVER` -> đánh dấu tiêu chí cần xử lý nghiệp vụ theo quy ước vận hành, không tự biến thành `NG`.
- HTTP `503`/`504`: retry job theo chính sách Hangfire.
- HTTP `400`/`415`: lỗi request/dữ liệu, không retry mù quáng.

### Queue `compare-llm`

- Gọi Python với `CompareExecutionMode = LLM`.
- Kết quả `OK`/`NG` là kết quả cuối và được lưu `BEMT2004`.
- HTTP `503`/`504`: retry; hết retry thì trạng thái Compare lỗi.

## 7. Idempotency và song song

- Một job đối chiếu phải mang định danh tối thiểu: `RunAPK/BEMT2003APK`, `PromptAPK`, `CompareExecutionMode`.
- Không tạo trùng job final cho cùng `RunAPK + PromptAPK`.
- Job Rule và LLM của các tiêu chí khác nhau được chạy song song.
- Chỉ có một kết quả final cho một `RunAPK + PromptAPK`; job LLM fallback thay thế `REVIEW`, không tạo thêm một dòng kết quả final thứ hai.
- Worker `compare-rule` có thể nhiều hơn worker `compare-llm`; Rule Engine không cần GPU, LLM phải giới hạn theo năng lực GPU/model.

## 8. Điểm sửa code API-AI hiện tại

- `ReadFileOrchestratorService`: thay queue `ReadFileJob` tổng bằng các Hangfire job theo bước OCR/Extract/Compare.
- `PromptContentViewModel` và `ONT1042Service.GetDataPrompt`: mang thêm `DnttTypeCode`, `CriterionCode` cho từng prompt.
- `ReadFileBackgroundWorkflow.BuildCriteriaListAsync`: thay vòng lặp gọi tuần tự bằng enqueue Compare job theo route cache.
- `AgentCompareService.CompareAsync` -> `AgentPromptService.SendPromptWithLocalsAsync` -> `ChatResponseHandlerService.InvokeAsync`: thêm tham số `compareExecutionMode`, rồi thêm vào request JSON top-level.
- Luồng parse/lưu `BEMT2004`: chỉ nhận response final; `REVIEW` là response trung gian của queue Rule.

## 9. Trình tự rollout

1. Bổ sung mã `DnttTypeCode`/`CriterionCode` vào prompt model và xác nhận khớp `BEMT2009`.
2. Tạo route cache và log mode đã chọn cho từng tiêu chí.
3. Chạy canary một số phiếu NVL với queue Rule/LLM, đối chiếu kết quả với luồng cũ.
4. Bật song song toàn bộ sáu tiêu chí NVL có cấu hình active.
5. Theo dõi `REVIEW`, retry, thời gian từng queue và tỷ lệ gọi LLM trước khi mở rộng các rule còn lại.
