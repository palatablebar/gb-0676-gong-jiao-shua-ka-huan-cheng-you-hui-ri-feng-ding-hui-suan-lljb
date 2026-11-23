# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。流水线共8个阶段：taps、routes、fares、journeys、discounts、emergency、clearing、settlement；每个阶段返回rows、quarantine、metrics，应急阶段额外返回compensation_ledger，后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV，证据kind含accepted、compensation、quarantine。

## 应急补偿

- 应急指令随运行参数 `emergency_directives` 提交（见数据字典）。`typhoon.csv` 不传指令时使用默认台风指令。
- `GET/POST /api/emergency` 预览应急阶段：逐行给出 `emergency`、`emergency_directive_id`、`emergency_basis`、`original_payable`、`reported`、`government_compensation`，并给出每线路每业务日唯一的 `compensation_ledger`。
- `POST /api/runs/<id>/compensation` body为 `{version, decision}`，decision仅允许 `补偿已确认` 或 `退回重算`。采用版本条件更新：版本陈旧返回409 `STALE_VERSION`，旧版结果完整保留且 `GET /api/runs/<id>` 仍可读取；成功后 version 自增并更新 comp_decision。
- 来源未对平（balanced=false）或台账键重复时，归档阶段直接422拒绝，证据不封存。
