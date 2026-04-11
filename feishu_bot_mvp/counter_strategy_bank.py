#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class FamilyStrategy:
    counter_goal: str
    recommended_mode: str
    why: str
    follow_up_action: str
    evidence_advice: str
    escalation_hint: str


FAMILY_STRATEGIES: Dict[str, FamilyStrategy] = {
    "hard_deadline_push": FamilyStrategy(
        counter_goal="把口头催压翻译成优先级、截止时间和阻塞处理方式",
        recommended_mode="acknowledge_translate_confirm",
        why="对方在压缩决策时间，你如果只解释，很容易继续被推进“先出结果再说”的单向压力里。",
        follow_up_action="会后或 20 分钟内补一条书面状态：目标、当前阻塞点、预计完成时间、需要拍板的优先级。",
        evidence_advice="建议留痕",
        escalation_hint="暂不升级，先逼出优先级和时间口径。",
    ),
    "deny_explanation": FamilyStrategy(
        counter_goal="重新打开事实和风险通道，但不跟情绪争对错",
        recommended_mode="acknowledge_reopen_risk_channel",
        why="对方当前在堵解释空间，如果你继续正面辩解，容易被进一步打成态度问题。",
        follow_up_action="用书面形式同步当前状态、阻塞点和预计完成时间，避免最后才暴露风险。",
        evidence_advice="强烈建议留痕",
        escalation_hint="暂不升级，先把风险通道拉回书面。",
    ),
    "result_only": FamilyStrategy(
        counter_goal="把“只看结果”翻译成 owner、范围、时限和取舍",
        recommended_mode="clarify_scope_priority_tradeoff",
        why="这类话术把压力全压下来，但把拍板责任留空，最容易造成后续甩锅。",
        follow_up_action="追问三件事：最优先目标、可接受 tradeoff、什么时候回报结果。",
        evidence_advice="建议留痕",
        escalation_hint="如果目标和资源长期失配，再升级。",
    ),
    "abstract_criticism": FamilyStrategy(
        counter_goal="不接人格标签，只拉回具体问题和验收标准",
        recommended_mode="translate_label_to_facts",
        why="抽象词本身无法执行，真正有用的是把“不成熟/没格局”翻成具体差距。",
        follow_up_action="让对方给出 2 到 3 个具体问题点，并在书面里确认标准和复查时间。",
        evidence_advice="建议留痕",
        escalation_hint="若持续使用人格打压，可考虑升级。",
    ),
    "attitude_problem": FamilyStrategy(
        counter_goal="把“态度问题”翻回到事实、分歧点和执行动作",
        recommended_mode="depersonalize_and_clarify",
        why="这类指控的风险在于它会吞掉所有事实分歧，让你陷入自证态度。",
        follow_up_action="先承接执行，再要具体例子和下一步要求。",
        evidence_advice="建议留痕",
        escalation_hint="如果长期用态度压人且伴随羞辱，可升级。",
    ),
    "seniority_override": FamilyStrategy(
        counter_goal="不和世界观硬碰，要求当前约束和拍板依据",
        recommended_mode="respect_then_ask_for_current_criteria",
        why="对方在用资历封口，最稳的反制不是争资历，而是要求回到现在的约束、成本和风险。",
        follow_up_action="复述对方结论，再补一句：按什么标准、风险、时间点这么定。",
        evidence_advice="可留痕",
        escalation_hint="暂不升级，先把标准问出来。",
    ),
    "for_your_own_good": FamilyStrategy(
        counter_goal="把“为你好”重新翻译成工作边界、任务要求和支持方式",
        recommended_mode="stay_friendly_restore_boundary",
        why="这类话术表面是关心，实质是把控制包装成善意，最怕你把话题重新压回任务边界。",
        follow_up_action="回应时谢意可以有，但下一句必须回到范围、截止时间和具体动作。",
        evidence_advice="通常不必留痕，除非伴随控制或羞辱。",
        escalation_hint="若持续越界控制个人选择，再升级。",
    ),
    "family_boundary": FamilyStrategy(
        counter_goal="保持友善，同时把“自己人”翻回到角色边界和排期",
        recommended_mode="friendly_boundary_reset",
        why="关系绑架的本质是用亲近感压缩拒绝空间，所以最重要的是把关系语言翻译成排期和范围。",
        follow_up_action="明确你可以支持什么、何时支持、哪些需要重新排优先级。",
        evidence_advice="必要时留痕",
        escalation_hint="若长期借关系压边界，可升级。",
    ),
    "gratitude_pressure": FamilyStrategy(
        counter_goal="拒绝道德债框架，回到当前职责、标准和流程",
        recommended_mode="reject_moral_debt_return_to_scope",
        why="“平台/机会/培养”一旦变成道德债，后续所有不合理要求都会变得难拒绝。",
        follow_up_action="把未来承诺拆成当前标准和里程碑。",
        evidence_advice="建议留痕",
        escalation_hint="若承诺长期空转且伴随压榨，可升级。",
    ),
    "public_shame": FamilyStrategy(
        counter_goal="先止损，不在现场翻盘，尽快把问题移到私下和书面",
        recommended_mode="stop_loss_then_follow_up",
        why="公开场合最难赢，现场最重要的是止损和防止更多羞辱，不是立刻翻案。",
        follow_up_action="会后发原因、修复动作和时间点；必要时一对一确认边界。",
        evidence_advice="强烈建议留痕",
        escalation_hint="若多次公开羞辱，可升级。",
    ),
    "comparison_humiliation": FamilyStrategy(
        counter_goal="拒绝横向羞辱，把比较翻成具体差距和修复项",
        recommended_mode="stop_comparison_pull_back_to_gap",
        why="比较只会制造羞耻，不会带来执行；真正有用的是问清楚你和标准之间差了什么。",
        follow_up_action="要求对方说出具体差距、标准和复盘点。",
        evidence_advice="建议留痕",
        escalation_hint="若长期靠比较羞辱维持权威，可升级。",
    ),
    "overtime_loyalty": FamilyStrategy(
        counter_goal="把忠诚测试翻回加急安排、持续时长和优先级取舍",
        recommended_mode="force_priority_choice",
        why="这类话术最怕你问：要加多久、为什么要加、哪些工作顺延、是否补偿。",
        follow_up_action="确认加急时长、目标、牺牲项和补偿或后续安排。",
        evidence_advice="建议留痕",
        escalation_hint="若长期超负荷且伴随威胁，可升级。",
    ),
    "stability_control": FamilyStrategy(
        counter_goal="保留自己的判断权，把“别折腾”翻成客观 tradeoff",
        recommended_mode="acknowledge_then_keep_agency",
        why="这类控制常以保护为名，真正有用的是把它翻成成本、风险和选择条件。",
        follow_up_action="要求对方说明客观 tradeoff，而不是只讲“稳”。",
        evidence_advice="一般不必留痕",
        escalation_hint="若涉及岗位控制或前途绑架，可升级。",
    ),
    "blame_shift": FamilyStrategy(
        counter_goal="第一时间建立时间线、依赖链和决策记录，防止被甩锅",
        recommended_mode="timeline_and_dependency_rebuild",
        why="被甩锅时先喊冤没用，最稳的是把时间线、版本记录和关键决策点整理出来。",
        follow_up_action="用列表整理：何时提出、何时调整、何时执行、何时出问题。",
        evidence_advice="强烈建议留痕",
        escalation_hint="如已进入公开甩锅阶段，可考虑升级。",
    ),
    "obedience_first": FamilyStrategy(
        counter_goal="短暂承接执行，但尽快把命令翻成书面范围和拍板点",
        recommended_mode="narrow_compliance_then_document",
        why="对方在先要求服从，你现场硬顶成本高；更稳的是窄承接，再追书面边界。",
        follow_up_action="执行前后补一条书面确认：先做什么、不做什么、谁拍板。",
        evidence_advice="建议留痕",
        escalation_hint="如果长期不允许讨论、持续口头压制，再升级。",
    ),
    "emotional_blackmail": FamilyStrategy(
        counter_goal="不回应情感债，直接回到可执行动作和下一步",
        recommended_mode="do_not_defend_feelings_return_to_action",
        why="情感勒索最希望你进入“我是不是对不起你”的叙事，最稳的是回到任务、问题和下一步。",
        follow_up_action="把关系债拆开，只确认任务要求、下一步和结果。",
        evidence_advice="必要时留痕",
        escalation_hint="如果情感施压频繁且影响工作边界，可升级。",
    ),
    "upward_face_pressure": FamilyStrategy(
        counter_goal="把“我不好交代”翻成真实优先级和上行口径",
        recommended_mode="translate_face_pressure_into_decision_checkpoint",
        why="对方向下转嫁向上压力时，最怕你要求明确：保什么、砍什么、什么时候给口径。",
        follow_up_action="确认：现在最优先保哪个结果、是否需要你同步风险说明。",
        evidence_advice="建议留痕",
        escalation_hint="暂不升级，先逼出拍板点。",
    ),
    "boundary_mocking": FamilyStrategy(
        counter_goal="不为感受辩护，直接说明容量、安排和边界",
        recommended_mode="state_capacity_without_defending",
        why="对方在嘲讽你的感受，最稳的方式不是解释自己多难，而是说明客观容量和下一步安排。",
        follow_up_action="直接给出当前负荷、可交付时间和需要调整的优先级。",
        evidence_advice="建议留痕",
        escalation_hint="若持续羞辱式压负荷，可升级。",
    ),
}


def infer_sender_role(request_text: str) -> str:
    lowered = request_text.lower()
    if any(word in lowered for word in ("领导", "老板", "上级", "主管", "经理", "总监")):
        return "manager"
    if any(word in lowered for word in ("skip", "大老板", "更高一级", "vp", "ceo")):
        return "skip_level"
    if any(word in lowered for word in ("同事", "同级", "合作方", "同组", "搭子")):
        return "peer"
    return "unknown"


def _build_reply_variants(primary_key: str, sender_role: str) -> Dict[str, str]:
    progress_like = {"hard_deadline_push", "deny_explanation", "result_only", "blame_shift", "upward_face_pressure"}
    feedback_like = {"abstract_criticism", "attitude_problem", "comparison_humiliation"}
    moralizing_like = {"for_your_own_good", "family_boundary", "gratitude_pressure", "emotional_blackmail"}
    meeting_like = {"public_shame"}
    boundary_like = {"overtime_loyalty", "boundary_mocking"}
    authority_like = {"seniority_override", "stability_control", "obedience_first"}

    if primary_key in progress_like:
        if sender_role == "peer":
            return {
                "reply_soft": "我先把现状同步给你：当前卡点是 X，预计 Y 时间给你明确结果。为了避免反复来回，我也把依赖和风险一起说清楚。",
                "reply_balanced": "我会继续推进，但需要把当前阻塞点、预计完成时间和依赖关系对齐，不然口头催办解决不了问题。",
                "reply_firm": "我可以配合推进，但请先把优先级和完成口径定清楚；如果这是最高优先级，其他事项需要顺延。",
            }
        return {
            "reply_soft": "收到，我先不展开解释。为了按时推进，我会在 20 分钟内给您一版当前状态、阻塞点和预计完成时间。",
            "reply_balanced": "收到。我先按结果推进，同时把当前阻塞点和完成时间发您，避免最后才暴露风险。",
            "reply_firm": "收到，我先执行。涉及交期的阻塞我会同步成书面清单，请您一起确认优先级和取舍。",
        }

    if primary_key in feedback_like:
        if sender_role == "peer":
            return {
                "reply_soft": "收到。为了我能尽快改到位，你方便说下最关键的两个具体问题点吗？我按优先级处理。",
                "reply_balanced": "我先不接抽象评价，直接看具体差距。你把最关键的问题点和期望结果发我，我按这个改。",
                "reply_firm": "如果要我调整，请直接说事实、差距和标准；只用抽象标签，我没法高质量处理。",
            }
        return {
            "reply_soft": "收到，我先把这次结果补上。为了改到位，您方便说下这次最关键的两个具体问题点吗？我按优先级改。",
            "reply_balanced": "收到。我先不在抽象词上展开，您直接指出最关键的具体差距和期望标准，我按这个修正。",
            "reply_firm": "我先承接执行，但需要把问题落到具体事实和标准上，这样我才能按要求改到位。",
        }

    if primary_key in moralizing_like:
        if sender_role == "peer":
            return {
                "reply_soft": "我理解你是想把事情推进快一点。为了避免后面扯不清，我们还是把这次需要我支持的范围、时间点和配合方式说清楚。",
                "reply_balanced": "我可以配合，但还是按任务范围、截止时间和当前排期来对齐，这样后面边界不会乱。",
                "reply_firm": "我愿意配合工作，但还是按任务、排期和责任边界来执行，不太适合再上升到关系或态度。",
            }
        return {
            "reply_soft": "我理解您的出发点。为了把事情推进好，我们还是回到这件事本身：这次最需要我支持的任务范围、时间点和协作方式分别是什么？",
            "reply_balanced": "没问题，我先按工作要求推进。这件事我更想按任务范围、截止时间和排期来对齐，避免后面边界不清。",
            "reply_firm": "我会配合工作要求，但还是按任务、排期和责任边界来执行，不太适合再上升到关系或态度。",
        }

    if primary_key in meeting_like:
        return {
            "reply_soft": "收到，这个问题我先记下。会后我把原因、修复动作和时间点发出来，先把事情收住。",
            "reply_balanced": "收到，我先不在现场展开。会后我会把原因、修复动作和时间点书面同步，避免大家口径不一致。",
            "reply_firm": "收到，这个问题我会负责收口，但不建议继续在公开场合上升到人身评价。会后我发书面方案。",
        }

    if primary_key in boundary_like:
        return {
            "reply_soft": "我理解现在比较急。为了不影响结果，我先把可投入时间、当前负荷和需要调整的优先级说清楚。",
            "reply_balanced": "我可以支持加急，但需要先确认持续多久、为什么必须现在做，以及哪些事项顺延。",
            "reply_firm": "我会按优先级支持，但需要把时间范围、牺牲项和后续安排说清楚，否则很容易影响其他交付。",
        }

    if primary_key in authority_like:
        return {
            "reply_soft": "明白您的判断。我先按这个方向推进，同时想确认一下当前最关键的判断依据和风险边界，避免后面返工。",
            "reply_balanced": "收到，我可以先执行。为了保证执行准确，我会把当前理解、边界和风险点书面同步给您确认。",
            "reply_firm": "我先按结论推进，但需要把标准、边界和拍板点明确下来，不然执行层很容易失真。",
        }

    return {
        "reply_soft": "收到，我先把这件事落回到任务、边界和时间点上。",
        "reply_balanced": "我先不在情绪上展开，先把目标、范围和下一步动作对齐。",
        "reply_firm": "我可以继续推进，但需要把边界、责任和时间点明确下来。",
    }


class IncomingCounterPlanner:
    def plan(
        self,
        incoming_text: str,
        analysis: Dict[str, Any],
        sender_role: str = "unknown",
        channel: str = "unknown",
        user_preference: str = "balanced",
    ) -> Dict[str, Any]:
        matched = analysis["matched_families"]
        primary_key = analysis["primary_family"]["key"]
        strategy = FAMILY_STRATEGIES.get(
            primary_key,
            FamilyStrategy(
                counter_goal="把模糊压力翻译成具体目标、边界、优先级和记录",
                recommended_mode="clarify_and_document",
                why="这类话术最怕你把模糊部分重新翻译成具体任务和书面记录。",
                follow_up_action="把关键事项书面确认下来。",
                evidence_advice="建议留痕",
                escalation_hint="暂不升级，先明确口径。",
            ),
        )
        replies = _build_reply_variants(primary_key, sender_role)
        return {
            "risk_level": analysis["risk_level"],
            "scene": analysis["scene"],
            "sender_role": sender_role,
            "channel": channel,
            "matched_families": [item["key"] for item in matched],
            "matched_red_flags": analysis["red_flags"],
            "counter_goal": strategy.counter_goal,
            "recommended_mode": strategy.recommended_mode,
            "reply_soft": replies["reply_soft"],
            "reply_balanced": replies["reply_balanced"],
            "reply_firm": replies["reply_firm"],
            "follow_up_action": strategy.follow_up_action,
            "evidence_advice": strategy.evidence_advice,
            "escalation_hint": strategy.escalation_hint,
            "why": strategy.why,
            "user_preference": user_preference,
            "incoming_text": incoming_text,
        }


def format_counter_text(plan: Dict[str, Any]) -> str:
    lines: List[str] = [
        f"场景：{plan['scene']}",
        f"你的即时目标：{plan['counter_goal']}",
        "",
        "建议这样回：",
        plan["reply_balanced"],
        "",
        "如果你想更坚定一点：",
        plan["reply_firm"],
    ]
    follow_up_action = str(plan.get("follow_up_action", "")).strip()
    if follow_up_action:
        lines.extend(["", f"后续：{follow_up_action}"])
    return "\n".join(lines)
