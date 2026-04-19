# Rule Templates

这批模板不是执行门禁，而是第一批面向交易语义的可配置规则模板。

当前已提供以下模板：

1. `entry_weak_to_strong.yaml`：弱转强入场候选。
2. `entry_limit_up_reseal.yaml`：炸板回封/回封打板候选。
3. `entry_overtake_rotation.yaml`：卡位上位候选。
4. `entry_catch_up_breakout.yaml`：补涨启动候选。
5. `watch_abandon_leader_replaced.yaml`：龙头被替代后放弃关注。
6. `exit_scale_out_take_profit.yaml`：分批止盈。
7. `exit_failed_rebound_engulfing.yaml`：反包失败退出。
8. `exit_acceptance_breakdown.yaml`：承接走弱退出。
9. `watch_high_divergence_weakening.yaml`：高位分歧转弱放弃关注。
10. `exit_broken_board_failed_rebound.yaml`：断板反抽失败退出。
11. `entry_emotion_reflow_repair.yaml`：情绪修复回流候选。
12. `watch_consensus_acceleration_exhaustion.yaml`：一致加速衰竭放弃关注。
13. `exit_floor_to_limit_failed.yaml`：地天板失败退出。
14. `watch_tail_ramp_next_day_weakening.yaml`：尾盘偷袭次日弱化放弃关注。
15. `exit_thin_volume_rebound_failed.yaml`：地量反抽失败退出。
16. `watch_afternoon_chase_then_fade.yaml`：午后抢筹回落放弃关注。
17. `watch_counter_nuke_confirmation_failed.yaml`：反核确认失败放弃关注。
18. `watch_afternoon_reseal_failed.yaml`：午后回封失败放弃关注。
19. `watch_first_board_next_day_weak_to_weaker.yaml`：首板次日弱转弱放弃关注。
20. `exit_low_volume_false_repair.yaml`：缩量假修复退出。
21. `watch_one_word_open_board_weakening.yaml`：一字开板转弱放弃关注。
22. `exit_engulfing_next_day_fade.yaml`：反包次日冲高回落退出。
23. `exit_reseal_board_break_loss.yaml`：回封后炸板失守退出。
24. `exit_engulfing_first_down_day_confirmed.yaml`：反包首阴确认退出。
25. `watch_gap_up_fade_breakdown.yaml`：高开低走失守放弃关注。
26. `exit_acceleration_volume_stall.yaml`：加速后放量滞涨退出。
27. `watch_spike_fail_before_limit.yaml`：冲高未板回落放弃关注。
28. `exit_second_wave_repair_failed.yaml`：二波修复失败退出。
29. `watch_intraday_break_ma_weakening.yaml`：分时破均线弱化放弃关注。
30. `exit_high_level_sideways_flush.yaml`：高位横盘后跳水退出。
31. `watch_low_volume_board_next_day_breakdown.yaml`：缩量上板次日失守放弃关注。
32. `watch_tail_repair_no_follow_through.yaml`：尾盘抢修无延续放弃关注。
33. `exit_high_volume_stall_reversal.yaml`：高位放量滞胀转杀退出。
34. `exit_rebound_over_previous_high_failed.yaml`：反抽过前高失败退出。
35. `watch_afternoon_reflow_next_day_below_expectation.yaml`：午后回流次日低于预期放弃关注。
36. `exit_board_fade_tail_breakdown.yaml`：炸板回落尾盘失守退出。
37. `exit_weak_repair_next_day_gap_down_kill.yaml`：弱修复次日低开再杀退出。
38. `watch_sector_reflow_symbol_lagging.yaml`：板块回流但个股掉队放弃关注。
39. `watch_gap_up_instant_limit_acceptance_collapse.yaml`：高开秒板后承接塌陷放弃关注。
40. `watch_low_level_first_board_no_premium.yaml`：低位首板隔日无溢价放弃关注。
41. `watch_sector_divergence_leader_follower_split.yaml`：板块分歧时核心与跟风分化放弃关注。
42. `watch_one_word_turnover_acceptance_decay.yaml`：一字换手后承接衰减放弃关注。
43. `exit_board_pullback_next_day_gap_down_confirmed.yaml`：冲板回落次日低开确认退出。
44. `watch_sector_repair_leader_only_followers_stall.yaml`：板块修复时核心独强后排失速放弃关注。
45. `exit_high_level_board_break_afternoon_second_kill.yaml`：高位炸板后午后再杀退出。
46. `exit_weak_to_strong_fail_consensus_take_profit.yaml`：弱转强失败转一致兑现退出。
47. `watch_repair_market_core_secondary_switch.yaml`：修复行情里核心与次核心切换放弃关注。
48. `watch_consensus_repair_next_day_acceptance_vanish.yaml`：一致修复次日承接消失放弃关注。
49. `exit_accelerated_catch_up_afternoon_blowup.yaml`：加速补涨午后炸裂退出。
50. `watch_cooling_end_counter_nuke_failed.yaml`：退潮末端反核失败放弃关注。
51. `exit_engulfing_board_blowup_take_profit.yaml`：反包冲板后炸裂兑现退出。
52. `watch_emotion_repair_second_divergence_failed.yaml`：情绪修复二次分歧失败放弃关注。
53. `watch_cooling_tail_low_level_first_board_follow_insufficient.yaml`：退潮尾声低位首板跟随不足放弃关注。
54. `watch_consensus_reflow_tail_weakening.yaml`：一致回流后尾盘走弱放弃关注。
55. `watch_overtake_success_next_day_no_strengthening.yaml`：卡位成功次日不加强放弃关注。
56. `exit_cooling_mid_weak_repair_rebreak.yaml`：退潮中继的弱修复再破位退出。
57. `watch_high_level_blowup_next_day_thin_volume_drift.yaml`：高位炸板次日缩量阴跌放弃关注。
58. `watch_emotion_repair_afternoon_reversal_kill.yaml`：情绪修复后午后反杀放弃关注。
59. `exit_weak_to_strong_failed_gap_down_no_acceptance.yaml`：弱转强失败后低开无承接退出。
60. `risk_market_emotion_cooling_freeze.yaml`：情绪退潮冻结新开仓。
61. `risk_market_high_level_open_board_deterioration_freeze.yaml`：高位炸板率恶化冻结新开仓。
62. `risk_market_reseal_rate_drop_freeze.yaml`：回封率下滑冻结新开仓。
63. `risk_market_theme_cooling_freeze.yaml`：题材退潮冻结新开仓。
64. `entry_pullback_ma20_support.yaml`：回踩20日线企稳候选。
65. `entry_pullback_ma60_support.yaml`：回踩60日线企稳候选。
66. `risk_market_emotion_repair_allow_entry.yaml`：情绪修复放行新开仓。
67. `risk_market_reseal_recovery_allow_entry.yaml`：回封率修复放行新开仓。
68. `entry_midterm_platform_breakout.yaml`：中期平台突破放量候选。
69. `entry_long_term_yearline_reclaim.yaml`：年线收复回踩确认候选。
70. `exit_long_term_ma120_break.yaml`：跌破120日线减仓/退出。
71. `entry_event_earnings_surprise_breakout.yaml`：业绩超预期放量突破候选。
72. `entry_hft_orderflow_reclaim.yaml`：盘口扫单回补高频候选。
73. `risk_market_bull_trend_allow_entry.yaml`：牛市趋势放行新开仓。
74. `risk_market_sideways_selective_entry.yaml`：震荡市精选放行。
75. `risk_market_bear_freeze_entry.yaml`：熊市冻结新开仓。

这些模板的定位是：

1. 先让使用者认识规则库能表达哪些市场语言。
2. 再逐步替换阈值、逻辑关系和状态输出。
3. 当前模板尽量使用现有规则骨架已支持的 DSL，不额外依赖新的执行器。

建议后续扩展方向：

1. 继续增加更多 A 股短线模板，例如高位反包次日量价背离、午后回封后尾盘漏单、修复一致后次日竞价低于预期。
2. 增加趋势和组合模板，例如多头排列、再平衡偏离修复。
3. 持续收敛特征词典，避免字段名在模板之间漂移。