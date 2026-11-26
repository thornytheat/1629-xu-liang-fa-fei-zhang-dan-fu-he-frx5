# 服务接口

`GET /api/plan?capacity=16` 返回默认快照下的完整方案。`POST /api/plan` 支持提交本地记录，`packet` 内含 `observations`、`outcomes` 两份必需列表，以及可选的 `coefficients` 列表（见 [业务规格](SPEC.md#换档待确认系数)）。

`GET /api/summary` 返回简读版。`GET /api/decisions/<case_id>` 回读对应测量与标准化特征。`GET /api/compare?capacity=16&against=0` 显示两档额度的逐单状态变更。

以下模块证据可通过 `/api/modules/` 下的相同名称访问。

- `charge_notices`
- `tariff_signature`
- `penalty_logit`
- `billing_holdout`
- `meter_regimes`
- `review_exposure`

`GET /api/decisions.csv` 导出本次候选。`POST /api/releases` 接受规划请求的原参数及 `expected_generation`、`run_id`。重试同一个运行标识返回原版本，试图用过期版本登记其他方案返回 409。
