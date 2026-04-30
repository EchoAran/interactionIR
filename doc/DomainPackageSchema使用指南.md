## 目标
这份文档解释 domain package（领域包）里各字段的语义、哪些字段是引擎保留字段、以及你可以如何自定义一个新 package 而不需要改代码。

对应 schema 文件：packages_schema.json

## 顶层字段
- domain_id / version：领域包标识与版本号，写入 interactionIR.meta 用于运行时加载正确的包。
- description：纯文案，可省略。
- slot_status_enum：可选。slot.status 的默认枚举集合（如果 slot_blueprint 未单独覆盖）。
- parser_guidance.instruction：给解析器的自然语言提示（不影响引擎逻辑，只影响 parse）。
- slot_blueprint_catalog：定义有哪些信息槽（slot），以及类型/渲染提示。
- intention_catalog：定义解析器可输出的 intention_type 列表与说明。
- checkpoint_catalog：定义阶段（checkpoint）推进与冻结规则，并提供偏好策略/动作。
- policy_catalog：定义策略（policy）如何触发，以及给外部执行代理的策略指令文案。
- act_catalog：定义动作（act）如何触发，以及给外部执行代理的动作指令文案。
- turn_pipeline：可选但推荐。定义一轮内多动作组合的阶段顺序与每阶段的候选动作列表。

## slot_blueprint_catalog（信息槽）
每个 slot blueprint 最关键字段：
- slot_key：槽的逻辑名（例如 goal / roles），用于解析器输出 target_slot_keys，也用于 checkpoint 的 entry_conditions 引用。
- value_type：string/text/number/boolean/enum/array/object。
- creation_rule.create_at_init：是否初始化时创建 slot（当前引擎仅支持该规则）。
- update_rule.must_mark_conflict / allow_direct_overwrite_when_frozen：更新冲突与冻结覆盖行为。
- renderer.missing_hint / value_hint：用于外部执行代理理解如何提问与补齐。

## intention_catalog（意图）
意图用于描述用户本轮输入属于哪类行为（补充信息、修正、跑题等）。
- intention_type：唯一 id（例如 off_topic）。
- description / renderer.instruction：纯文案，用于解释该意图含义。

解析器输出的 parsed_intentions 必须来自 intention_catalog；引擎不对 intention_type 做业务特判。

## policy_catalog（策略）
策略只做两件事：
- 触发：trigger.conditions（通用表达式 DSL）
- 指令：renderer.instruction（纯自然语言）

字段说明：
- trigger.conditions：字符串表达式数组，全部为 true 时该策略命中。
  - 目前可用上下文变量：checkpoint / intentions / slot_statuses / completion_state
  - 目前可用通用函数：has_intention(x), slot_status_any_of([...]), slot_status_all_in([...])
- renderer.instruction：对外部执行代理的策略约束文案（建议写“必须遵守”的要求）。

注意：policy.renderer.notes 已移除；如需补充建议，直接写进 instruction。

## act_catalog（动作）
动作只做两件事：
- 触发：planner.when.conditions（通用表达式 DSL）
- 指令：renderer.instruction / renderer.output_hint（纯自然语言）

字段说明：
- planner.when.conditions：字符串表达式数组，全部为 true 时该动作命中。
- planner.focus：为动作选择“需要优先看的槽”，减少外部执行代理上下文负担。
  - source：选择槽集合的方式（引擎保留字段）
  - limit：最多返回多少个 slot_id（防止一次输出过多槽）

### focus.source 的取值从哪来
它不是随便写的，是引擎内置的“通用枚举”，由 acts_Planner.py 实现：
- none：不聚焦任何槽
- all_open：按顺序合并 conflict + ambiguous + unfilled（再按 limit 截断）
- all_slots：全部槽（再按 limit 截断）
- conflict / ambiguous / unfilled / partial / filled / frozen：对应各状态分组（按 limit 截断）
- matched_status：需要 focus.statuses 指定要尝试的状态列表（按顺序找到第一个非空组）

如果你要自定义新的 source，需要改引擎代码；推荐只用上述通用枚举。

## turn_pipeline（同一轮组合多个 act）
最小结构（够用）：
- id：阶段名，仅用于人读/调试
- act_types：该阶段按顺序尝试的动作列表（act_type）
- limit：该阶段最多挑选多少个命中的动作（通常为 1）

引擎行为：
- 先按阶段顺序遍历 turn_pipeline
- 每阶段按 act_types 顺序挑选命中 when.conditions 的动作，直到达到 limit
- 输出 selected_act_types（有序列表）

## checkpoint_catalog（阶段推进）
checkpoint 用于：
- 推进 current_checkpoint（由 slots_Updater.py 计算）
- 冻结部分槽（freeze_slot_keys）
- 提供偏好策略/动作（preferred_policy_ids / preferred_act_types）

字段说明：
- entry_conditions：字符串数组，目前仅支持非常有限的语法：
  - <slot_key>.status in [...]
  - <slot_key>.status == ...
  - <slot_key>.status != ...
  其中 <slot_key> 必须来自 slot_blueprint_catalog.slot_key。
- freeze_slot_keys：达到该 checkpoint 后需要冻结的 slot_key 列表（状态会从 filled 转 frozen）。
- preferred_policy_ids / preferred_act_types：在同等触发条件下的偏好顺序（仅偏好，不做业务特判）。

