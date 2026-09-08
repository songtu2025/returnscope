from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InsightReportProfile:
    key: str
    version: str
    category_name: str
    preferred_reason_codes: tuple[str, ...]
    diagnostic_title: str
    diagnostic_empty: str
    variant_label: str
    diagnostic_action: str
    diagnostic_rationale: str
    diagnostic_success_signal: str
    further_questions: tuple[str, ...]

    def snapshot(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "category_name": self.category_name,
            "preferred_reason_codes": list(self.preferred_reason_codes),
            "variant_label": self.variant_label,
        }


GENERIC_PROFILE = InsightReportProfile(
    key="generic",
    version="generic-comment-insight-v1",
    category_name="商品",
    preferred_reason_codes=(),
    diagnostic_title="核心问题需要按商品变体和时间继续拆解",
    diagnostic_empty="高频商品问题需要按商品变体和时间继续拆解。",
    variant_label="商品变体",
    diagnostic_action="核对高频问题对应的商品变体、实物表现和页面说明。",
    diagnostic_rationale="评论只能确认顾客感知的问题，需要结合商品信息验证具体原因。",
    diagnostic_success_signal="目标问题在相同评论口径下持续下降，且相关反向问题不升高。",
    further_questions=(
        "问题是否集中在特定商品变体或时间段？",
        "原始评论是否提供了更具体的部位、场景或失效表现？",
        "补充销量分母后，当前问题优先级是否仍然成立？",
    ),
)


PROFILES = {
    "footwear": InsightReportProfile(
        key="footwear",
        version="footwear-comment-insight-v1",
        category_name="鞋履",
        preferred_reason_codes=(
            "FIT_TOO_SMALL",
            "FIT_TOO_LARGE",
            "OTHER_BUYER_CHANGED_MIND",
        ),
        diagnostic_title="偏小与偏大信号需要按鞋款和尺码段分别验证",
        diagnostic_empty="尺码与合脚问题需要按鞋款、尺码段和时间继续拆解。",
        variant_label="鞋款尺码",
        diagnostic_action=(
            "分别核对热点鞋款尺码的长度、宽窄、实物测量、尺码表和页面说明。"
        ),
        diagnostic_rationale=(
            "偏小与偏大可能来自不同尺码段，统一调整会掩盖长度和宽窄差异。"
        ),
        diagnostic_success_signal=(
            "目标鞋款尺码的对应问题连续两个完整周期下降，且反向问题不升高。"
        ),
        further_questions=(
            "偏小与偏大是否集中在不同鞋款、尺码段或时间窗口？",
            "评论中的偏短、偏长、偏窄和偏宽能否解释整体尺码问题？",
            "补充销量分母后，当前鞋款和尺码优先级是否仍然成立？",
        ),
    ),
    "gloves": InsightReportProfile(
        key="gloves",
        version="gloves-comment-insight-v1",
        category_name="手套",
        preferred_reason_codes=(
            "GLOVE_SIZE_SMALL",
            "GLOVE_SIZE_LARGE",
            "GLOVE_WARMTH",
        ),
        diagnostic_title="尺码适配与保暖表现需要按手套尺码和场景分别验证",
        diagnostic_empty="手套问题需要按尺码、手部部位、功能和使用场景继续拆解。",
        variant_label="手套尺码",
        diagnostic_action=(
            "按尺码核对掌围、指长、入口和内衬占用空间，并结合温度与使用场景验证保暖表现。"
        ),
        diagnostic_rationale=(
            "整体偏大或偏小可能来自不同手部部位，保暖反馈也会受温度和使用场景影响。"
        ),
        diagnostic_success_signal=(
            "目标尺码的适配问题下降，且在明确使用场景下的保暖负面反馈同步下降。"
        ),
        further_questions=(
            "偏大或偏小具体来自掌围、指长、入口还是内衬空间？",
            "保暖、防水和触屏问题分别发生在什么温度、时长和使用场景？",
            "Listing 是否明确承诺了评论中被质疑的功能表现？",
        ),
    ),
}


def resolve_insight_report_profile(
    sources: list[dict[str, Any]] | None,
) -> InsightReportProfile:
    agent_keys = {
        str(source.get("agent_key") or "").strip()
        for source in sources or []
        if str(source.get("agent_key") or "").strip()
    }
    if len(agent_keys) != 1:
        return GENERIC_PROFILE
    return PROFILES.get(next(iter(agent_keys)), GENERIC_PROFILE)


def get_insight_report_profile(profile_key: str | None) -> InsightReportProfile:
    return PROFILES.get((profile_key or "").strip(), GENERIC_PROFILE)
