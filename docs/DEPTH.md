# 模块与边界验证

所属领域 AI/ML，子方向 传统ML。

## 功能模块

| 序号 | 模块 | 职责 | 实现 | 测试 |
| --- | --- | --- | --- | --- |
| M1 | charge_notices | 单据接入与时点裁决 | `src/peakledger/charge_notices/service.py` | `tests/test_charge_notices.py` |
| M2 | tariff_signature | 业务特征与时点档案 | `src/peakledger/tariff_signature/service.py` | `tests/test_tariff_signature.py` |
| M3 | penalty_logit | 训练、估计与基线 | `src/peakledger/penalty_logit/service.py` | `tests/test_penalty_logit.py` |
| M4 | billing_holdout | 时间回放与核验 | `src/peakledger/billing_holdout/service.py` | `tests/test_billing_holdout.py` |
| M5 | meter_regimes | 群组偏移与可信分派 | `src/peakledger/meter_regimes/service.py` | `tests/test_meter_regimes.py` |
| M6 | review_exposure | 业务锁与资源分派 | `src/peakledger/review_exposure/service.py` | `tests/test_review_exposure.py` |
| M7 | invoice_reconcile | 逐单证据与资源守恒 | `src/peakledger/invoice_reconcile/service.py` | `tests/test_invoice_reconcile.py` |
| M8 | appeal_release | 版本登记与追溯 | `src/peakledger/appeal_release/service.py` | `tests/test_appeal_release.py` |

## 易错边界

| 用例 | 业务后果 | 处理位置 | 验证位置 |
| --- | --- | --- | --- |
| TRAP-14 | 同版本异值隔离，较旧修订不能复活 | `src/peakledger/charge_notices/service.py` | `tests/test_charge_notices.py::test_conflicting_revision_is_quarantined` |
| TRAP-19 | 业务锁优先，未获准的单据不消耗资源 | `src/peakledger/review_exposure/service.py` | `tests/test_review_exposure.py::test_prohibited_entries_never_spend` |
| TRAP-26 | 使用过期版本登记被拒，保留前次结果 | `src/peakledger/appeal_release/service.py` | `tests/test_appeal_release.py::test_stale_generation_keeps_prior` |
| TRAP-32 | 零方差业务特征仍有有界尺度 | `src/peakledger/tariff_signature/service.py` | `tests/test_tariff_signature.py::test_zero_variance_uses_unit_scale` |
| TRAP-42 | 训练冻结后到达的单据或回执不会回填 | `src/peakledger/tariff_signature/service.py` | `tests/test_tariff_signature.py::test_future_and_late_measurements_do_not_fit` |
| TRAP-43 | 训练与独立回放的单据按时段隔离 | `src/peakledger/billing_holdout/service.py` | `tests/test_billing_holdout.py::test_holdout_separates_ordered_periods` |
| TRAP-44 | 稀疏或常量参考出现越界值时拦住自动分派 | `src/peakledger/meter_regimes/service.py` | `tests/test_meter_regimes.py::test_constant_distribution_detects_outside` |
| TRAP-53 | 同批重排仍得到相同证据和决策 | `src/peakledger/invoice_reconcile/service.py` | `tests/test_invoice_reconcile.py::test_report_is_permutation_invariant` |
| TRAP-54 | 单笔推理与合并调用的结果一致 | `src/peakledger/penalty_logit/service.py` | `tests/test_penalty_logit.py::test_score_is_batch_invariant` |
| TRAP-61 | 换档两档任一不满足复核条件即不占席位 | `src/peakledger/engine.py` | `tests/test_pending_gears.py::test_any_gear_failing_review_gives_up_the_seat` |
| TRAP-62 | 两档名单不同时改锁 maximin 名单，整数分不受舍入影响 | `src/peakledger/review_exposure/confirmation.py` | `tests/test_pending_gears.py::test_roster_is_maximin_when_gears_disagree` |
| TRAP-63 | 快照日后入账的档位不改变当班名单 | `src/peakledger/charge_notices/service.py` | `tests/test_pending_gears.py::test_late_gear_records_do_not_change_the_roster` |
