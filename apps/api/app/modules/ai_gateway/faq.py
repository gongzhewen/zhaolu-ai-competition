import re
from dataclasses import dataclass

from app.modules.agent.demo_catalog import DEMO_STATIC_ANSWERS


@dataclass(frozen=True)
class FaqItem:
    faq_id: str
    question: str
    keywords: tuple[str, ...]
    answer: str
    sources: tuple[dict[str, str], ...]


OFFICIAL_SOURCES = {
    "sun": {
        "title": "阳光高考：2026高考咨询Q&A",
        "url": "https://gaokao.chsi.com.cn/gkxx/zt/2026gkzx.shtml",
    },
    "people": {
        "title": "人民日报：志愿填报必看的22个问题",
        "url": "https://news.cnr.cn/native/gd/20260613/t20260613_527658967.shtml",
    },
    "eol": {
        "title": "中国教育在线：20个高考志愿填报核心问题",
        "url": "https://eol.cn/kaoshi/gaokao/bkzn/202606/t20260630_2750661.shtml",
    },
    "cctv": {
        "title": "央视网：志愿填报必看的22个问题",
        "url": "https://news.cctv.com/2026/06/13/ARTI9LdyWyEHaghLvxayodLp260613.shtml",
    },
}


FAQ_ITEMS = [
    FaqItem("new-arrival-ratio", "新生到校比例怎么理解？", ("新生到校比例怎么理解", "到校比例怎么理解", "入学率怎么理解", "报到比例怎么理解"), DEMO_STATIC_ANSWERS["new-arrival-ratio"], ({"title": "招录智策演示口径说明", "url": "local://demo-catalog/new-arrival-ratio"},)),
    FaqItem("parallel", "什么是平行志愿？", ("平行志愿", "平行志愿规则", "平行志愿投档"), "平行志愿是同一录取批次内按“分数优先、遵循志愿、一次投档”原则进行投档的模式。具体批次和实施范围以本省考试院规定为准。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("order", "平行志愿的填报顺序重要吗？", ("顺序", "排序", "先后", "志愿顺序", "顺序重要"), "重要。平行志愿虽然按分数和位次排队，但检索到考生时会按填报顺序依次判断，前面的院校专业组先满足条件就可能先投档。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["people"])),
    FaqItem("group", "什么是院校专业组？", ("院校专业组", "专业组", "院校组"), "院校专业组是高校按选科要求和培养要求设置的志愿单位。一个专业组内通常包含若干专业，考生填报时需要同时关注组内专业和是否服从调剂。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["cctv"])),
    FaqItem("grade-difference", "什么是专业级差？", ("专业级差", "级差"), "专业级差是部分高校在安排专业时对非第一专业志愿考生减分排序的规则，但并非所有高校都采用。应以当年学校招生章程为准。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("adjust", "服从专业调剂有什么作用？", ("服从调剂", "调剂", "专业调剂"), "服从调剂通常可以降低因所填专业无法满足而被退档的风险，但可能被调剂到该专业组内其他专业。是否服从要结合专业接受度和退档风险决定。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["people"])),
    FaqItem("no-adjust", "不服从调剂会有什么风险？", ("不服从", "拒绝调剂"), "不服从调剂时，如果所填专业均无法满足，可能被退档。退档后通常不能在同一批次继续投档，只能等待征集志愿或下一批次。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("withdraw", "退档和滑档有什么区别？", ("退档", "滑档"), "滑档通常指志愿填报过高，未能被任何志愿投档；退档通常指已经投档到学校，但因专业不服从调剂、体检限制、单科要求等原因被退回。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("strategy", "冲稳保志愿应该怎么设置？", ("冲稳保", "梯度", "志愿梯度"), "冲稳保是常见的志愿梯度策略：前段安排有一定挑战的志愿，中段安排匹配度较高的志愿，后段安排录取把握更大的保底志愿。比例应结合位次和风险承受能力调整。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("lines", "分数线、投档线和位次有什么区别？", ("投档线", "分数线", "最低位次", "位次", "录取线"), "分数线通常指录取最低分，投档线是投档环节形成的最低成绩，位次是考生在全省同类考生中的排名。跨年度比较时，位次通常比绝对分数更稳定。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("score-rank", "填志愿看分数还是看位次？", ("看分数", "看位次", "参考位次"), "建议以位次为主、分数为辅，同时关注招生计划、专业组和选科要求变化。不同年份试题难度不同，单纯比较分数容易产生偏差。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["people"])),
    FaqItem("history-data", "如何查询高校和专业历年录取数据？", ("历年数据", "录取数据", "历年分数", "往年分数"), "可通过省考试院、学校招生网和阳光高考平台查询历年投档线、最低分、最低位次和招生计划，并注意区分院校、专业组和专业口径。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("subject-requirement", "新高考选科要求在哪里查询？", ("选科要求", "选考科目", "科目要求"), "应查询省考试院发布的选考科目要求以及学校当年招生专业目录。相同专业在不同学校的选科要求可能不同，必须以当年正式文件为准。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["cctv"])),
    FaqItem("medical", "体检结果会影响专业录取吗？", ("体检受限", "体检", "色盲", "色弱", "视力"), "会影响。部分专业对视力、色觉、身高或其他身体条件有要求，考生应查看体检指导意见和学校招生章程，提前排除受限专业。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("big-major", "什么是大类招生？", ("大类招生", "大类", "分专业"), "大类招生是按学科大类录取，入学后再按学校规则分流到具体专业。填报前应了解分流时间、分流依据、可选专业和限制条件。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["cctv"])),
    FaqItem("cooperative", "中外合作办学值得报考吗？", ("中外合作", "合作办学", "国际项目"), "中外合作办学需要综合考虑学费、培养模式、外语要求、出国安排、证书和深造就业情况，不能只看录取分数较低这一项。", (OFFICIAL_SOURCES["eol"], OFFICIAL_SOURCES["sun"])),
    FaqItem("private-undergrad", "民办本科和公办专科怎么选？", ("民办本科", "公办专科", "本科专科"), "需要结合学历层次、学费、专业、城市、就业和专升本机会综合判断。民办本科成本较高，公办专科在部分技能型专业上也有优势。", (OFFICIAL_SOURCES["eol"], OFFICIAL_SOURCES["sun"])),
    FaqItem("hot-major", "热门专业一定好就业吗？", ("热门专业", "就业", "专业前景"), "不一定。专业就业与学校平台、个人能力、行业周期和继续深造密切相关。应结合课程内容、培养方向和目标行业判断，而不是只看热度。", (OFFICIAL_SOURCES["eol"], OFFICIAL_SOURCES["sun"])),
    FaqItem("collection", "征集志愿是什么？", ("征集志愿", "补录"), "征集志愿是部分批次录取未完成计划时，面向符合条件的考生再次公开征集志愿。时间和资格由省考试院公布，考生需及时关注。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("early-batch", "提前批有哪些类型？", ("提前批", "提前批次"), "提前批通常包括军事、公安、师范、医学定向、艺术体育及其他特殊类型招生，不同省份范围不同，填报前需核对资格和录取规则。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["people"])),
    FaqItem("special-plans", "强基计划、综合评价和专项计划能同时报吗？", ("强基计划", "综合评价", "专项计划", "高校专项", "地方专项"), "通常可以按各自简章分别报名或填报，但录取批次、资格限制和是否冲突要以当年招生简章及省考试院规定为准。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["cctv"])),
    FaqItem("not-attend", "被录取后不去会有什么影响？", ("录取后不去", "不去报到", "放弃录取"), "部分省份会将放弃录取或未报到行为记入诚信档案，并影响下一年度志愿填报数量或资格。应以本省当年政策为准。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("change-major", "大学入学后可以转专业吗？", ("转专业", "换专业"), "多数高校允许转专业，但通常有成绩、名额、专业类别和时间限制。应查看学校学籍管理规定和学院实施细则。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["cctv"])),
    FaqItem("charter", "招生章程和招生简章有什么区别？", ("招生章程", "招生简章", "章程"), "招生章程是高校招生录取的重要依据，包含录取规则、专业要求和收费标准等；招生简章更偏宣传介绍。填报时应优先阅读招生章程。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("ratio", "什么是投档比例？", ("投档比例", "投档"), "投档比例是高校招生计划与投档考生数量之间的比例。平行志愿批次通常会按一定比例投档，比例过大会增加退档风险。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
    FaqItem("result-query", "高考录取结果可以通过哪些渠道查询？", ("录取结果", "录取查询"), "应通过省考试院、学校招生网和官方指定平台查询，警惕非官方收费查询、内部指标和保录取等诈骗信息。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["people"])),
    FaqItem("materials", "填报志愿前需要准备哪些资料？", ("填报资料", "准备资料", "招生计划", "招生章程"), "建议准备省考试院政策文件、招生计划、历年投档和位次数据、学校招生章程、专业选科要求和体检限制说明。", (OFFICIAL_SOURCES["sun"], OFFICIAL_SOURCES["eol"])),
]


def _tokens(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for size in (2, 3, 4):
        for index in range(max(0, len(normalized) - size + 1)):
            tokens.add(normalized[index:index + size])
    return tokens


def search_faq(question: str) -> FaqItem | None:
    if "不服从" in question and "调剂" in question:
        return next(item for item in FAQ_ITEMS if item.faq_id == "no-adjust")
    if "服从调剂" in question and "不服从" not in question:
        return next(item for item in FAQ_ITEMS if item.faq_id == "adjust")
    if "顺序" in question and "平行志愿" in question:
        return next(item for item in FAQ_ITEMS if item.faq_id == "order")
    question_tokens = _tokens(question)
    best: FaqItem | None = None
    best_score = 0.0
    for item in FAQ_ITEMS:
        score = 0.0
        for keyword in item.keywords:
            if keyword in question:
                score += 3.0 + len(keyword) * 0.3
        score += len(question_tokens & _tokens(item.question)) * 0.15
        if score > best_score:
            best = item
            best_score = score
    return best if best_score >= 1.5 else None
