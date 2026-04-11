#!/usr/bin/env python3
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, List, Optional, Sequence, Tuple


_FOLD_REPLACEMENTS: Tuple[Tuple[str, str], ...] = (
    ("咱们", "我们"),
    ("这么点事", "这点事"),
    ("没必要把边界卡那么死", "别讲边界"),
    ("把边界卡那么死", "别讲边界"),
    ("边界卡那么死", "别讲边界"),
    ("边界卡太死", "别讲边界"),
    ("不要再", "别再"),
    ("不要", "别"),
    ("不用再", "别再"),
    ("借口", "理由"),
    ("客观原因", "解释"),
    ("原因", "解释"),
    ("申辩", "解释"),
    ("说辞", "解释"),
    ("结果给我", "发我"),
    ("给我结果", "发我"),
    ("给我个结果", "发我"),
    ("闭环", "搞定"),
    ("收掉", "搞定"),
    ("收口", "搞定"),
    ("处理掉", "搞定"),
    ("完成掉", "搞定"),
    ("干完", "搞定"),
    ("务必", "必须"),
    ("赶快", "赶紧"),
    ("赶紧", "马上"),
    ("立即", "立刻"),
    ("今天之内", "今天"),
    ("今天内", "今天"),
    ("今晚之前", "今晚"),
    ("下班之前", "下班前"),
    ("下班以前", "下班前"),
    ("别废话", "别解释"),
    ("别啰嗦", "别解释"),
    ("别扯这些", "别解释"),
    ("别跟我扯", "别解释"),
    ("先干", "先执行"),
    ("先做", "先执行"),
    ("照着做", "照做"),
    ("照我说的", "按我说的做"),
    ("别问为什么", "别问"),
    ("别问那么细", "别问"),
    ("顶嘴", "抬杠"),
    ("唱反调", "抬杠"),
    ("跟我杠", "抬杠"),
    ("不够大气", "没格局"),
    ("格局太小", "没格局"),
    ("不够老练", "不成熟"),
    ("幼稚", "不成熟"),
    ("站得不够高", "站位不够"),
    ("层次不够", "站位不够"),
    ("不像话", "不专业"),
    ("不够职业", "不专业"),
    ("我是在帮你", "为你好"),
    ("我是帮你", "为你好"),
    ("我也是替你考虑", "为你好"),
    ("以后你会明白", "以后会感谢我"),
    ("将来你会懂", "以后会感谢我"),
    ("都是一家人", "团队就是一家人"),
    ("都是一队的", "团队就是一家人"),
    ("不用分这么清", "别讲边界"),
    ("别卡那么死", "别讲边界"),
    ("公事公办", "边界感"),
    ("懂得感谢", "感恩"),
    ("知恩图报", "感恩"),
    ("别挑三拣四", "别挑"),
    ("别计较那么多", "别计较"),
    ("公开说一遍", "我在群里说一遍"),
    ("当众说", "当着大家的面"),
    ("大家评评理", "大家都看看"),
    ("别人都能做到", "别人都能做"),
    ("为什么就你不行", "你为什么不行"),
    ("怎么总是你", "就你有问题"),
    ("熬一熬", "加班"),
    ("顶一下", "加班"),
    ("别那么脆弱", "玻璃心"),
    ("别那么敏感", "玻璃心"),
    ("上面问下来", "领导那边"),
    ("老板那边", "领导那边"),
    ("没法回复", "没法交代"),
    ("没法解释", "没法交代"),
    ("别往外甩锅", "别把锅往外推"),
    ("外部问题", "环境"),
    ("稳定点", "稳定最重要"),
    ("别乱动", "别折腾"),
)


def _normalize(text: str) -> str:
    compact = re.sub(r"\s+", "", text.strip().lower())
    for src, dst in _FOLD_REPLACEMENTS:
        compact = compact.replace(src, dst)
    compact = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", compact)
    compact = compact.replace("我们我们", "我们")
    return compact


def _char_ngrams(text: str, size: int = 2) -> frozenset[str]:
    if not text:
        return frozenset()
    if len(text) <= size:
        return frozenset({text})
    return frozenset(text[index : index + size] for index in range(len(text) - size + 1))


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    if union == 0:
        return 0.0
    return intersection / union


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    sequence_score = difflib.SequenceMatcher(None, left, right).ratio()
    bigram_score = _jaccard(_char_ngrams(left, 2), _char_ngrams(right, 2))
    trigram_score = _jaccard(_char_ngrams(left, 3), _char_ngrams(right, 3))
    return (sequence_score * 0.45) + (bigram_score * 0.35) + (trigram_score * 0.20)


def _dedupe(items: Sequence[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _combine(parts: Sequence[Sequence[str]], limit: int) -> Tuple[str, ...]:
    samples: List[str] = []
    seen = set()
    for combo in product(*parts):
        sentence = "".join(part for part in combo if part)
        sentence = re.sub(r"[，]{2,}", "，", sentence)
        sentence = sentence.strip("，。 ")
        if not sentence or sentence in seen:
            continue
        seen.add(sentence)
        samples.append(sentence)
        if len(samples) >= limit:
            break
    return tuple(samples)


@dataclass(frozen=True)
class PatternFamily:
    key: str
    scene: str
    style: str
    risk_level: str
    red_flag: str
    strong_phrases: Tuple[str, ...]
    signal_groups: Tuple[Tuple[str, ...], ...]
    min_groups: int
    sample_templates: Tuple[str, ...]

    def normalized_samples(self) -> Tuple[str, ...]:
        return tuple(_normalize(item) for item in self.sample_templates)

    def normalized_strong_phrases(self) -> Tuple[str, ...]:
        return tuple(_normalize(item) for item in self.strong_phrases)

    def normalized_signal_groups(self) -> Tuple[Tuple[str, ...], ...]:
        return tuple(tuple(_normalize(item) for item in group) for group in self.signal_groups)


def _build_pattern_families() -> Tuple[PatternFamily, ...]:
    families = [
        PatternFamily(
            key="hard_deadline_push",
            scene="催进度/催交付",
            style="progress",
            risk_level="medium",
            red_flag="只有截止压力，没有明确优先级、卡点处理或支持",
            strong_phrases=(
                "今晚必须改完",
                "今天必须给我",
                "下班前必须搞定",
                "现在就给我结果",
                "今天晚上必须收口",
            ),
            signal_groups=(
                ("今晚", "今天", "下班前", "下午五点前", "今天晚上", "现在", "马上", "立刻", "尽快"),
                ("必须", "务必", "赶紧", "马上", "立刻", "现在就"),
                ("改完", "搞定", "处理完", "收口", "发我", "给我结果", "闭环", "交上来", "推进完"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("今晚", "今天", "下班前", "下午五点前", "今天晚上", "现在", "马上", "立刻", "尽快"),
                    ("必须", "务必", "赶紧", "现在就"),
                    ("改完", "搞定", "处理完", "收口", "发我", "给我结果", "闭环", "交上来", "推进完"),
                    ("", "，别拖", "，不要再往后放", "，这是最高优先级", "，别让我再追"),
                ),
                limit=160,
            ),
        ),
        PatternFamily(
            key="deny_explanation",
            scene="催进度/催交付",
            style="progress",
            risk_level="high",
            red_flag="把正常解释和风险同步打成“找理由”或“找借口”",
            strong_phrases=(
                "别再给我找理由",
                "不要总给我找借口",
                "先别解释",
                "我不想听原因",
            ),
            signal_groups=(
                ("别", "不要", "别再", "不要再", "先别"),
                ("理由", "借口", "解释", "原因", "客观原因"),
                ("先做完", "结果先给我", "别说这些", "没必要解释", "我不想听"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("别给我", "不要再给我", "别再拿", "不要总拿", "先别"),
                    ("理由", "借口", "解释", "原因", "客观原因"),
                    ("", "，先把事情做完", "，结果先给我", "，别说这些没用的", "，做不到就提前说"),
                ),
                limit=90,
            ),
        ),
        PatternFamily(
            key="result_only",
            scene="催进度/催交付",
            style="progress",
            risk_level="medium",
            red_flag="只谈结果，不给范围、支持和权衡",
            strong_phrases=(
                "我只看结果",
                "过程我不关心",
                "办法你自己想",
                "做不出来就是你的问题",
            ),
            signal_groups=(
                ("只看结果", "过程我不关心", "结果给我", "我要的是结果"),
                ("办法你自己想", "自己想办法", "别问我", "自己解决"),
                ("做不出来", "搞不定", "完不成"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("我只看结果", "过程我不关心", "我要的是结果", "结果给我就行"),
                    ("，办法你自己想", "，自己想办法", "，别问我怎么做", "，资源你自己协调"),
                    ("", "，做不出来就是你的问题", "，别到时候再说困难"),
                ),
                limit=72,
            ),
        ),
        PatternFamily(
            key="abstract_criticism",
            scene="反馈/批评",
            style="feedback",
            risk_level="high",
            red_flag="用抽象人格标签代替具体反馈",
            strong_phrases=(
                "你不成熟",
                "你没格局",
                "你站位不够",
                "你不专业",
            ),
            signal_groups=(
                ("你就是", "你现在的问题就是", "说白了你就是", "你这人就是"),
                ("不成熟", "没格局", "站位不够", "不专业", "抗压不行", "不够稳", "玻璃心", "情商不够"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("你就是", "你现在的问题就是", "说白了你就是", "你这人就是"),
                    ("不成熟", "没格局", "站位不够", "不专业", "抗压不行", "不够稳", "玻璃心", "情商不够"),
                    ("", "，所以事情才做成这样", "，这就是你现在上不去的原因", "，带不动你很正常"),
                ),
                limit=120,
            ),
        ),
        PatternFamily(
            key="attitude_problem",
            scene="反馈/批评",
            style="feedback",
            risk_level="high",
            red_flag="把分歧或风险提醒上升成态度问题",
            strong_phrases=(
                "你态度有问题",
                "你这是抬杠",
                "先统一思想",
                "执行力不行",
            ),
            signal_groups=(
                ("态度有问题", "抬杠", "不服从", "执行力不行", "思想没统一", "总爱质疑"),
                ("先统一思想", "先别讨论", "不要质疑", "先按我说的做"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("你这是", "你现在就是", "说到底你是"),
                    ("态度有问题", "抬杠", "不服从", "执行力不行", "思想没统一", "总爱质疑"),
                    ("", "，先统一思想再说", "，别总跟我争", "，先照做别废话"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="seniority_override",
            scene="资历/权威压制",
            style="authority",
            risk_level="medium",
            red_flag="用资历或代际身份压过事实讨论",
            strong_phrases=(
                "我做这行这么多年",
                "你还年轻",
                "我见得多了",
                "按我说的做就行",
            ),
            signal_groups=(
                ("我做这行", "我带过的人", "我见得多", "我吃的盐", "我干这行"),
                ("你还年轻", "年轻人", "你不懂", "你经验还不够"),
                ("按我说的做", "别问那么多", "先照做"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("我做这行这么多年", "我见得多了", "我带过的人比你见过的都多", "我吃的盐比你吃的饭还多"),
                    ("，你还年轻", "，年轻人先别急着反驳", "，你经验还不够", "，你不懂这里面的门道"),
                    ("", "，按我说的做就行", "，先别解释", "，先照做再说"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="for_your_own_good",
            scene="说教/关系绑架",
            style="moralizing",
            risk_level="medium",
            red_flag="用“为你好”包装控制或施压",
            strong_phrases=(
                "我都是为你好",
                "我骂你是在培养你",
                "你以后会感谢我",
            ),
            signal_groups=(
                ("为你好", "培养你", "以后会感谢我", "我是在帮你"),
                ("骂你", "严一点", "管你", "替你决定"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("我都是为你好", "我骂你是在培养你", "我现在对你严一点是为你好", "你以后会感谢我", "我这是在帮你", "我替你考虑得更多"),
                    ("", "，现在听着难受很正常", "，别不识好歹", "，我是在帮你少走弯路"),
                    ("", "，以后你就知道了", "，别把好心当驴肝肺", "，我懒得对别人这么费劲"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="family_boundary",
            scene="说教/关系绑架",
            style="moralizing",
            risk_level="medium",
            red_flag="用“团队像一家人”压低边界感和角色边界",
            strong_phrases=(
                "团队就是一家人",
                "自己人别讲边界",
                "别老讲边界感",
            ),
            signal_groups=(
                ("一家人", "自己人", "别讲边界", "别那么见外", "不要分那么清"),
                ("团队", "同事", "这点事", "互相帮忙"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("团队就是一家人", "都是自己人", "自己人别讲边界", "别老讲边界感", "我们不是外人", "别把关系弄得这么公事公办"),
                    ("", "，这点事别分那么清", "，互相兜一下很正常", "，别搞得那么生分"),
                    ("", "，不要什么都按制度卡", "，大家互相体谅一下", "，别把话说那么绝"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="gratitude_pressure",
            scene="说教/关系绑架",
            style="moralizing",
            risk_level="high",
            red_flag="把平台、机会或培养包装成必须感恩的道德压力",
            strong_phrases=(
                "公司给你平台要懂感恩",
                "给你机会了就别挑",
                "年轻人先学会感恩",
            ),
            signal_groups=(
                ("平台", "机会", "培养", "资源"),
                ("感恩", "别挑", "别计较", "知足"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("公司给你平台", "给你机会了", "我们愿意培养你", "团队已经给你资源了"),
                    ("要懂感恩", "就别挑三拣四", "别老计较", "先学会知足"),
                    ("", "，别总想着要条件", "，先把事情做好再说"),
                ),
                limit=80,
            ),
        ),
        PatternFamily(
            key="public_shame",
            scene="会议/公开施压",
            style="meeting",
            risk_level="high",
            red_flag="把纠正放进公开场合，容易变成示众式施压",
            strong_phrases=(
                "你给大家解释解释",
                "大家都看看",
                "我在群里说一遍",
                "这么简单都做不好",
            ),
            signal_groups=(
                ("大家都看看", "给大家解释解释", "我在群里说一遍", "当着大家的面"),
                ("做不好", "搞成这样", "丢人", "怎么会出这种错"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("大家都看看", "你给大家解释解释", "我在群里说一遍", "当着大家的面我再说一次", "我就在会上把这件事摊开说", "大家都听一下"),
                    ("这都做不好", "怎么会搞成这样", "这点事都能翻车", "这个水平说不过去", "这也能出错", "这做得也太离谱了"),
                    ("", "，顺便让大家都长个记性", "，以后别再发生", "，省得下次还有人犯同样的问题"),
                ),
                limit=120,
            ),
        ),
        PatternFamily(
            key="comparison_humiliation",
            scene="会议/公开施压",
            style="meeting",
            risk_level="high",
            red_flag="用横向比较羞辱个人，而不是说清具体差距",
            strong_phrases=(
                "别人都能做你为什么不行",
                "同级谁像你这样",
                "人家都没问题就你有问题",
            ),
            signal_groups=(
                ("别人都能", "同级谁像你这样", "人家都没问题", "别人怎么就行"),
                ("你为什么不行", "就你有问题", "就你掉链子", "怎么偏偏是你"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("别人都能做", "同级谁像你这样", "人家都没问题", "别人怎么就行", "同样的事别人都能交", "同级里谁会像你这样"),
                    ("你为什么不行", "偏偏就你掉链子", "怎么就你有问题", "就你还没搞定", "为什么总是你卡住", "怎么偏偏你最慢"),
                    ("", "，自己想想问题出在哪", "，别总让我替你收尾", "，别让我每次都盯着你"),
                ),
                limit=108,
            ),
        ),
        PatternFamily(
            key="overtime_loyalty",
            scene="加班/边界施压",
            style="boundary",
            risk_level="high",
            red_flag="把额外投入包装成忠诚考验，却不先说清边界和安排",
            strong_phrases=(
                "关键时期就别计较加班了",
                "这个时候还谈下班",
                "年轻人多干点",
            ),
            signal_groups=(
                ("加班", "下班", "周末", "熬一下", "顶一下"),
                ("别计较", "多干点", "关键时期", "大家都得扛", "别那么较真"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("关键时期", "这个时候", "项目收口阶段", "最近这么忙"),
                    ("就别计较加班了", "还谈什么下班", "大家都得扛一下", "年轻人多干点"),
                    ("", "，别这么较真", "，先把项目保住", "，后面再说补休"),
                ),
                limit=100,
            ),
        ),
        PatternFamily(
            key="stability_control",
            scene="资历/权威压制",
            style="authority",
            risk_level="medium",
            red_flag="用“稳定”“别折腾”压制对方的判断和选择空间",
            strong_phrases=(
                "稳定最重要别折腾",
                "我替你决定更好",
                "先别想那么多",
            ),
            signal_groups=(
                ("稳定最重要", "别折腾", "我替你决定", "先别想那么多", "听我的更稳"),
                ("跳槽", "转岗", "offer", "去留", "换工作", "职业选择"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("稳定最重要", "别折腾了", "我替你决定更好", "听我的更稳", "你现在最需要的是稳定", "先按我给你定的来"),
                    ("", "，先别想那么多", "，你以后会明白的", "，现在不是你做判断的时候"),
                    ("", "，我比你更清楚哪条路稳", "，先别自己乱做决定", "，别拿前途试错"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="blame_shift",
            scene="催进度/催交付",
            style="progress",
            risk_level="high",
            red_flag="把资源、依赖和拍板责任一股脑压给执行者",
            strong_phrases=(
                "做不出来就是你的问题",
                "别跟我说资源不够",
                "没做好别怪环境",
            ),
            signal_groups=(
                ("资源不够", "人手不够", "依赖没给", "需求在变", "接口没开"),
                ("别跟我说", "别怪环境", "就是你的问题", "自己消化"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("别跟我说资源不够", "别跟我说人手不够", "没做好别怪环境", "做不出来就是你的问题", "别拿依赖当理由", "需求变了也不是借口"),
                    ("", "，这些你自己消化", "，别把锅往外推", "，我只要结果"),
                    ("", "，协调不动你也得想办法", "，不要总想着往外归因", "，别把压力往上甩"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="obedience_first",
            scene="资历/权威压制",
            style="authority",
            risk_level="medium",
            red_flag="先要求服从，再决定是否允许讨论",
            strong_phrases=(
                "不要讨论先执行",
                "先照做再说",
                "这不是你该问的",
            ),
            signal_groups=(
                ("不要讨论", "先执行", "先照做", "先别问", "别质疑"),
                ("不是你该问的", "不是你该管的", "先做了再说"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("不要讨论", "先照做", "先执行", "先别问", "先按我说的做", "别急着发表看法"),
                    ("", "，这不是你该问的", "，先做了再说", "，别在这时候提意见"),
                    ("", "，等做完了我再决定要不要解释", "，先服从安排", "，现在不是你提建议的时候"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="emotional_blackmail",
            scene="说教/关系绑架",
            style="moralizing",
            risk_level="high",
            red_flag="把投入和照顾说成情感债，逼对方用顺从来还",
            strong_phrases=(
                "我对你这么上心你还这样",
                "我花这么多时间带你",
                "别让我失望",
            ),
            signal_groups=(
                ("我对你这么上心", "我花这么多时间带你", "我这么帮你", "我替你扛了这么多"),
                ("你还这样", "别让我失望", "你就这么回报我", "别辜负我"),
            ),
            min_groups=1,
            sample_templates=_combine(
                (
                    ("我对你这么上心", "我花这么多时间带你", "我这么帮你", "我替你扛了这么多"),
                    ("你还这样", "别让我失望", "你就这么回报我", "别辜负我"),
                    ("", "，我真是白费心了", "，你自己想想合不合适"),
                ),
                limit=80,
            ),
        ),
        PatternFamily(
            key="upward_face_pressure",
            scene="催进度/催交付",
            style="progress",
            risk_level="medium",
            red_flag="把向上交代的压力全转成对下施压",
            strong_phrases=(
                "别让我在领导那边难做",
                "你这是让我没法交代",
                "我怎么跟上面说",
            ),
            signal_groups=(
                ("领导那边", "上面", "老板", "总监", "汇报"),
                ("难做", "没法交代", "怎么说", "脸往哪放"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("别让我在领导那边难做", "你这是让我没法交代", "我怎么跟上面说", "老板问下来我怎么回", "总监追下来我怎么答", "你这是把我架在火上烤"),
                    ("", "，你今天必须给我个说法", "，别让我背这个锅", "，先把结果拿出来"),
                    ("", "，别让我替你兜这个底", "，我不想在上面那里丢脸", "，你先把口子堵上"),
                ),
                limit=96,
            ),
        ),
        PatternFamily(
            key="boundary_mocking",
            scene="加班/边界施压",
            style="boundary",
            risk_level="high",
            red_flag="把正常的边界或感受表达嘲讽成矫情、脆弱或不投入",
            strong_phrases=(
                "别这么玻璃心",
                "这点强度都扛不住",
                "怎么这么矫情",
            ),
            signal_groups=(
                ("玻璃心", "矫情", "娇气", "扛不住", "这点强度"),
                ("加班", "压力", "辛苦", "累", "强度"),
            ),
            min_groups=2,
            sample_templates=_combine(
                (
                    ("别这么玻璃心", "怎么这么矫情", "这点强度都扛不住", "别那么娇气", "别一有压力就喊累", "怎么一点委屈都吃不了"),
                    ("", "，大家都这么过来的", "，别动不动就喊累", "，这都受不了以后怎么办"),
                    ("", "，别把正常强度说得像天塌了一样", "，别总拿感受说事", "，以后压力只会更大"),
                ),
                limit=96,
            ),
        ),
    ]
    return tuple(families)


class FastReviewer:
    def __init__(
        self,
        fuzzy_strict_threshold: float = 0.90,
        fuzzy_assisted_threshold: float = 0.80,
    ) -> None:
        if not 0.0 <= fuzzy_assisted_threshold <= 1.0:
            raise ValueError("fuzzy_assisted_threshold must be between 0.0 and 1.0")
        if not 0.0 <= fuzzy_strict_threshold <= 1.0:
            raise ValueError("fuzzy_strict_threshold must be between 0.0 and 1.0")
        if fuzzy_assisted_threshold > fuzzy_strict_threshold:
            raise ValueError("fuzzy_assisted_threshold must be less than or equal to fuzzy_strict_threshold")
        raw_families = _build_pattern_families()
        self.families = []
        for family in raw_families:
            normalized_samples = family.normalized_samples()
            self.families.append(
                {
                    "family": family,
                    "normalized_samples": normalized_samples,
                    "normalized_strong_phrases": family.normalized_strong_phrases(),
                    "normalized_signal_groups": family.normalized_signal_groups(),
                    "sample_ngrams_2": tuple(_char_ngrams(item, 2) for item in normalized_samples),
                    "sample_ngrams_3": tuple(_char_ngrams(item, 3) for item in normalized_samples),
                }
            )
        self.total_templates = sum(len(item["family"].sample_templates) for item in self.families)
        self.fuzzy_strict_threshold = fuzzy_strict_threshold
        self.fuzzy_assisted_threshold = fuzzy_assisted_threshold

    def stats(self) -> Dict[str, Any]:
        return {
            "family_count": len(self.families),
            "template_count": self.total_templates,
            "fuzzy_matching": {
                "strict_threshold": self.fuzzy_strict_threshold,
                "assisted_threshold": self.fuzzy_assisted_threshold,
            },
            "families": [
                {
                    "key": item["family"].key,
                    "scene": item["family"].scene,
                    "templates": len(item["family"].sample_templates),
                }
                for item in self.families
            ],
        }

    def analyze(self, draft_text: str) -> Optional[Dict[str, Any]]:
        text = " ".join(draft_text.strip().split())
        compact = _normalize(text)
        if not compact:
            return None

        matches = []
        for item in self.families:
            family: PatternFamily = item["family"]
            score = 0
            matched_groups = 0
            exact_hit = compact in item["normalized_samples"]
            strong_hit = any(phrase and phrase in compact for phrase in item["normalized_strong_phrases"])
            fuzzy_score = 0.0
            if exact_hit:
                score += 4
            if strong_hit:
                score += 3
            for group in item["normalized_signal_groups"]:
                if any(term and term in compact for term in group):
                    matched_groups += 1
                    score += 1
            fuzzy_score = self._best_fuzzy_score(compact, item)
            strict_fuzzy_hit = fuzzy_score >= self.fuzzy_strict_threshold
            assisted_fuzzy_hit = fuzzy_score >= self.fuzzy_assisted_threshold and matched_groups >= max(1, family.min_groups - 1)
            if strict_fuzzy_hit:
                score += 3
            elif assisted_fuzzy_hit:
                score += 2
            if exact_hit or strong_hit or matched_groups >= family.min_groups or strict_fuzzy_hit or assisted_fuzzy_hit:
                matches.append(
                    {
                        "key": family.key,
                        "scene": family.scene,
                        "style": family.style,
                        "risk_level": family.risk_level,
                        "red_flag": family.red_flag,
                        "score": score,
                        "matched_groups": matched_groups,
                        "fuzzy_score": round(fuzzy_score, 4),
                        "exact_hit": exact_hit,
                        "strong_hit": strong_hit,
                        "strict_fuzzy_hit": strict_fuzzy_hit,
                        "assisted_fuzzy_hit": assisted_fuzzy_hit,
                    }
                )

        if not matches:
            return None

        matches.sort(
            key=lambda item: (
                item["score"],
                item["matched_groups"],
                item["fuzzy_score"],
            ),
            reverse=True,
        )
        selected = matches[:4]
        primary = selected[0]
        red_flags = _dedupe([item["red_flag"] for item in selected])[:4]
        risk_level = "high" if any(item["risk_level"] == "high" for item in selected) else primary["risk_level"]
        return {
            "text": text,
            "normalized_text": compact,
            "scene": primary["scene"],
            "style": primary["style"],
            "risk_level": risk_level,
            "red_flags": red_flags,
            "matched_families": selected,
            "primary_family": primary,
        }

    def _best_fuzzy_score(self, compact: str, family_entry: Dict[str, Any]) -> float:
        best_score = 0.0
        compact_ngrams_2 = _char_ngrams(compact, 2)
        compact_ngrams_3 = _char_ngrams(compact, 3)
        for sample, sample_ngrams_2, sample_ngrams_3 in zip(
            family_entry["normalized_samples"],
            family_entry["sample_ngrams_2"],
            family_entry["sample_ngrams_3"],
        ):
            sequence_score = difflib.SequenceMatcher(None, compact, sample).ratio()
            bigram_score = _jaccard(compact_ngrams_2, sample_ngrams_2)
            trigram_score = _jaccard(compact_ngrams_3, sample_ngrams_3)
            score = (sequence_score * 0.45) + (bigram_score * 0.35) + (trigram_score * 0.20)
            if score > best_score:
                best_score = score
        return best_score

    def review(self, draft_text: str) -> Optional[Dict[str, Any]]:
        analysis = self.analyze(draft_text)
        if not analysis:
            return None
        primary_key = analysis["primary_family"]["key"]
        primary = next(item["family"] for item in self.families if item["family"].key == primary_key)
        return self._build_review(primary, analysis["text"], analysis["red_flags"], analysis["risk_level"])

    def _infer_deadline(self, text: str) -> str:
        for phrase in ("今晚", "今天", "下班前", "下午五点前", "今天晚上", "现在", "马上", "立刻", "尽快"):
            if phrase in text:
                if phrase in {"现在", "马上", "立刻", "尽快"}:
                    return "尽快"
                return phrase
        return "今天"

    def _build_review(
        self,
        primary: PatternFamily,
        text: str,
        red_flags: List[str],
        risk_level: str,
    ) -> Dict[str, Any]:
        style = primary.style
        deadline = self._infer_deadline(text)

        if style == "progress":
            return {
                "risk_level": risk_level,
                "scene": primary.scene,
                "summary": "主要问题是只丢压力，不给清晰边界、支持方式或真实卡点空间。",
                "red_flags": red_flags,
                "impact": "对方容易只感到被压，不愿主动暴露风险；短期也许会先答应，长期更容易拖到最后才同步真实问题。",
                "standard_rewrite": f"这项需要在{deadline}前完成并发我确认。如果现在有阻塞点，请直接同步具体问题、影响范围和预计完成时间，我来一起判断怎么处理。",
                "firm_rewrite": f"这项我现在提到最高优先级，请在{deadline}前完成并发我。若有阻塞，马上同步具体问题和需要的支持，不要拖到最后。",
                "next_move": "如果这真是硬截止，最好补一句为什么必须在这个时间点前完成，以及哪些事项可以顺延。",
            }

        if style == "feedback":
            return {
                "risk_level": risk_level,
                "scene": primary.scene,
                "summary": "主要问题是把反馈和分歧说成了人格、态度或成熟度问题。",
                "red_flags": red_flags,
                "impact": "对方会更在意“你是不是在否定我这个人”，而不是具体该改什么，结果就是防御上升、执行性下降。",
                "standard_rewrite": "我想指出的不是你这个人有问题，而是这次输出里有几个具体点没达标。我们直接对齐事实、差距和下一步怎么改。",
                "firm_rewrite": "这次结果还不能过，问题在具体输出而不在态度标签。我们现在把缺的点列清楚，按标准改到位。",
                "next_move": "最好紧接着补上 2 到 3 个可观察的问题点、对应标准和复查时间，不要停留在抽象评价上。",
            }

        if style == "moralizing":
            return {
                "risk_level": risk_level,
                "scene": primary.scene,
                "summary": "主要问题是用关系、感恩或“为你好”替代清晰的业务边界和任务说明。",
                "red_flags": red_flags,
                "impact": "对方会觉得你在用情感债或关系亲近感压缩讨论空间，短期也许更顺从，但长期的信任和边界感都会受损。",
                "standard_rewrite": "我说这件事不是为了上价值，而是想把要求说清楚：这次需要你支持的具体任务、范围、截止时间和协作方式分别是什么。",
                "firm_rewrite": "这件事按工作要求推进就行，我们把任务范围、截止时间和责任边界讲清楚，不需要再上升到关系、感恩或态度。",
                "next_move": "把“为你好”“一家人”“要懂感恩”这类说法换成具体要求、边界和支持方式，会更稳。",
            }

        if style == "meeting":
            return {
                "risk_level": risk_level,
                "scene": primary.scene,
                "summary": "主要问题是把纠正和施压放进了公开场合，容易从对事变成示众式羞辱。",
                "red_flags": red_flags,
                "impact": "公开点名会让人先保脸面，再考虑问题本身；短期可能服软，长期更容易沉默、甩锅或回避责任。",
                "standard_rewrite": "这个问题我先和你单独对一下。请你在会后把当前情况、风险和解决方案发我，我们对齐后再同步团队。",
                "firm_rewrite": "这个问题需要尽快收口，但不适合在公开场合上升到人身。会后请你把现状、风险和方案发我，我来拍板下一步。",
                "next_move": "如果必须在会上处理，也尽量只讲事实、影响和 owner，不做横向羞辱和人格评价。",
            }

        if style == "boundary":
            return {
                "risk_level": risk_level,
                "scene": primary.scene,
                "summary": "主要问题是用忠诚、吃苦或抗压包装额外索取，边界和安排都不够清楚。",
                "red_flags": red_flags,
                "impact": "对方会觉得你在用态度和投入感压过实际负荷，表面也许会答应，心里却更容易积累抵触和不信任。",
                "standard_rewrite": "这项现在确实比较急，我先把要求说清楚：需要额外投入多久、为什么必须现在做、其他优先级怎么调整，我也会一起协调资源。",
                "firm_rewrite": "这项今天需要加急，我会明确优先级和持续时间。请你先按这个安排执行；如果负荷冲突，马上同步，我来取舍。",
                "next_move": "涉及加班、周末或持续高压时，最好把时间范围、补偿方式和优先级调整明确说出来。",
            }

        return {
            "risk_level": risk_level,
            "scene": primary.scene,
            "summary": "主要问题是用资历、服从或“我来替你决定”压过事实讨论和对方的判断空间。",
            "red_flags": red_flags,
            "impact": "对方会感觉自己没有表达分歧和风险的空间，团队容易表面服从、私下失真，真实问题也更难被提早暴露。",
            "standard_rewrite": "这里我先把当前约束和判断依据说清楚。你也把分歧点和风险说出来，我们在这个边界内定最后方案。",
            "firm_rewrite": "这件事现在需要统一执行，我来承担拍板责任。但执行前请把关键风险说清楚，避免因为信息被压住而返工。",
            "next_move": "如果必须拍板，就把原因、边界和复盘点讲明白，而不是只强调身份、年资或服从。",
        }
