# 数学对对碰：本地存储与后台同步接口方案

## 1. 当前决策

- 黑客松版本继续使用 localStorage，不调用后台接口。
- 当前存储键保持为 `memoryStationUserV2`，避免破坏已有演示数据。
- 同步方案仅作为后续产品化接口约定，不影响游戏离线启动、完成和查看成绩。
- HTML 中不得写入固定 Token、App Secret、长期密钥或真实学生身份。

## 2. 同步目标

后台同步用于：

- 将已完成的游戏对局关联到公司学生账号。
- 支持管理后台查看局数、得分、用时和不同难度表现。
- 支持未来跨设备恢复成长记录。
- 保证重复提交不会产生重复成绩。

首期不上传每次翻牌轨迹、音效设置、页面点击或不必要的个人信息。

## 3. 对局数据结构

每完成一局生成一条不可变的对局记录：

```json
{
  "schemaVersion": 1,
  "appVersion": "hackathon-demo-v1",
  "contentVersion": "question-bank-v1",
  "scoreRuleVersion": 1,
  "sessionId": "0dcbce55-62d7-4fd5-b69f-420bf742df99",
  "studentId": "由公司登录环境提供的匿名学生ID",
  "startedAt": "2026-08-15T10:20:00+08:00",
  "completedAt": "2026-08-15T10:21:05+08:00",
  "timezone": "Asia/Shanghai",
  "difficulty": "basic",
  "boardSize": 4,
  "mode": "normal",
  "questionIds": ["basic-add-001", "basic-formula-002"],
  "moves": 20,
  "durationSeconds": 65,
  "matchedPairs": 8,
  "score": 860,
  "syncStatus": "local",
  "syncAttempts": 0,
  "lastSyncAt": null
}
```

### 字段约束

- `sessionId`：客户端创建的全局唯一 ID，是接口幂等键。
- `studentId`：只能由公司账号环境提供；未登录时为空，不由游戏自行生成真实身份。
- `startedAt`、`completedAt`：使用带时区偏移的 ISO 8601 时间，不能只使用 UTC 日期截断。
- `difficulty`：仅允许 `basic`、`advanced`、`challenge`。
- `boardSize`：仅允许 `3`、`4`、`5`。
- `mode`：首期仅允许 `normal`、`daily`。
- `questionIds`：使用稳定题目 ID，不上传完整题面作为统计主键。
- `syncStatus`：本地状态为 `local`；未来接入后可使用 `syncing`、`synced`、`failed`。
- 对局完成后，除同步状态外不修改原始记录；统计结果由对局记录派生。

## 4. 本地数据建议结构

后续升级时仍可沿用 `memoryStationUserV2`，在数据根节点增加版本：

```json
{
  "dataVersion": 3,
  "history": [],
  "settings": {
    "sound": true,
    "delay": 900
  },
  "daily": [],
  "sync": {
    "enabled": false,
    "lastSuccessAt": null
  }
}
```

实施数据升级时必须：

- 为旧历史记录补充默认字段，不能因字段缺失导致页面打不开。
- 先写入新结构并验证成功，再清理旧结构。
- 未同步记录不能因为“最多保留 50 条历史”的限制被删除。
- 本地存储失败时仍允许继续游戏，并向用户显示非阻断提示。

## 5. 后台接口草案

### 批量提交对局

```text
POST /api/v1/learning-games/math-match/sessions:batchUpsert
Authorization: Bearer <公司提供的短期令牌>
Content-Type: application/json
```

请求：

```json
{
  "requestId": "7e905430-e1be-4fd4-b960-f739390cf9b1",
  "sessions": [
    {
      "schemaVersion": 1,
      "appVersion": "hackathon-demo-v1",
      "contentVersion": "question-bank-v1",
      "scoreRuleVersion": 1,
      "sessionId": "0dcbce55-62d7-4fd5-b69f-420bf742df99",
      "startedAt": "2026-08-15T10:20:00+08:00",
      "completedAt": "2026-08-15T10:21:05+08:00",
      "timezone": "Asia/Shanghai",
      "difficulty": "basic",
      "boardSize": 4,
      "mode": "normal",
      "questionIds": ["basic-add-001", "basic-formula-002"],
      "moves": 20,
      "durationSeconds": 65,
      "matchedPairs": 8,
      "score": 860
    }
  ]
}
```

响应：

```json
{
  "requestId": "7e905430-e1be-4fd4-b960-f739390cf9b1",
  "serverTime": "2026-08-15T10:21:10+08:00",
  "accepted": [
    {
      "sessionId": "0dcbce55-62d7-4fd5-b69f-420bf742df99",
      "status": "stored"
    }
  ],
  "rejected": []
}
```

### 查询成长摘要（可选）

```text
GET /api/v1/learning-games/math-match/me/summary
Authorization: Bearer <公司提供的短期令牌>
```

该接口仅在需要跨设备成长报告时实现，返回各难度局数、平均分、最佳成绩和最近完成日期。

## 6. 接口行为要求

- 使用 HTTPS，并允许公司生成的 OSS 来源访问接口。
- 学生身份以令牌为准，后台不能信任请求体传入的 `studentId`。
- 以 `sessionId` 幂等写入；重复提交返回成功但不重复计数。
- 单条记录失败不能导致整个批次全部失败。
- 后台校验枚举、时间、数值范围和版本字段。
- 如果成绩进入正式学习报告，后台应按 `scoreRuleVersion` 复核或重新计算得分。
- 返回明确错误码：令牌失效、参数错误、记录冲突、限流和服务异常。
- 明确保留期限、学生数据删除方式和管理后台访问权限。

## 7. 未来前端同步流程

```text
完成一局
  ↓
先写入 localStorage，状态 local
  ↓
游戏立即展示结果，不等待网络
  ↓
检测到登录身份与可用接口
  ↓
批量上传 local/failed 记录
  ↓
成功：标记 synced
失败：标记 failed，增加 syncAttempts，稍后重试
```

同步必须遵守：

- 上传永远在本地保存之后执行。
- 网络失败不能影响游戏、成绩展示和下一局。
- 使用指数退避，不进行高频无限重试。
- 页面关闭前不强制等待同步完成。
- 同步接口未配置时不得产生报错弹窗。

## 8. 公司技术对接清单

未来正式接入前，只需确认：

- 学生匿名 ID 和短期 Token 如何提供给 OSS 页面。
- API 测试地址、正式地址和接口负责人。
- OSS 来源的 CORS 配置。
- 单批最大记录数、超时和限流规则。
- 后台要求的字段、错误码和数据保留政策。
- 管理后台需要展示哪些统计指标。

## 9. 黑客松验收边界

- 游戏所有功能在没有后台的情况下正常运行。
- localStorage 可保存并恢复成绩、设置和每日挑战。
- 本文档中的数据结构能够覆盖当前游戏记录。
- 不在 HTML 中加入虚假的同步按钮、固定密钥或不可用接口地址。
- 汇报中将后台同步描述为“已完成结构与接口设计，待公司接口准备后接入”。
