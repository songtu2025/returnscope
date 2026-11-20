from __future__ import annotations

import re

EARLY_FAILURE = "首用或短期失效"

_TEXT_SIGNALS = {
    EARLY_FAILURE: re.compile(
        r"首次使用|第一次.{0,8}(?:穿|用)|刚.{0,4}(?:穿|用)|(?:一|两|二|三|几|[1-3])(?:次|天|小时|周)"
        r"|\b(?:first|one|1)\s+(?:uses?|wears?)\b"
        r"|\b(?:first|one|1)\s+time\b[^.!?\n]{0,30}\b(?:use|used|using|wear|wearing|wore|worn|put on)\b"
        r"|\b(?:use|used|using|wear|wearing|wore|worn|put on|broke|tore)\b[^.!?\n]{0,25}\b(?:first|one|1)\s+time\b"
        r"|\b(?:only|just)\s+once\b|\b(?:used|wore|worn|wearing|tried)\b[^.!?\n]{0,25}\bonce\b"
        r"|\bfirst\s+(?:day|week|hours?)\b"
        r"|\b(?:after|within|in|for|lasted|only|first)\b[^.!?\n]{0,14}\b(?:"
        r"(?:first|one|two|three|a few|few|a couple(?: of)?|[1-9]|1[0-9]|2[0-4])\s*[- ]?\s*(?:hours?|hrs?)"
        r"|(?:first|one|two|three|a few|few|a couple(?: of)?|[1-7]|a)\s*[- ]?\s*days?"
        r"|(?:first|one|two|a|a couple(?: of)?|[12])\s*[- ]?\s*weeks?)\b"
        r"|\b(?:one|two|three|a few|a couple(?: of)?|[1-3])\s+(?:uses|wears)\b",
        re.I,
    ),
    "涉水场景": re.compile(r"涉水|海滩|泳池|溯溪|浮潜|water|beach|pool|snorkel", re.I),
    "湿滑地面场景": re.compile(r"湿滑|湿地|湿岩|wet|slippery", re.I),
    "户外场景": re.compile(r"徒步|露营|户外|hiking|trails?|outdoor", re.I),
    "低温场景": re.compile(r"低温|雪地|冰上|寒冷|freez|snow|cold weather", re.I),
    "骑行场景": re.compile(r"骑行|骑车|cycling|bike riding", re.I),
    "作业场景": re.compile(r"作业|工地|施工|warehouse|construction|at work", re.I),
    "明确推荐": re.compile(
        r"(?:^|[。！!\s])(?:强烈推荐|值得推荐)|(?:would|highly|definitely) recommend",
        re.I,
    ),
    "明确不推荐": re.compile(
        r"不推荐|不建议购买|would not recommend|wouldn't recommend|do not recommend",
        re.I,
    ),
    "明确复购意向": re.compile(r"会回购|会复购|还会买|buy again|purchase again", re.I),
    "明确不再购买": re.compile(
        r"不会回购|不会复购|不会再买|will not buy again|won't buy again|never buy again",
        re.I,
    ),
}


def collect_text_signals(text: str) -> set[str]:
    matches = {key for key, pattern in _TEXT_SIGNALS.items() if pattern.search(text)}
    if "明确不推荐" in matches:
        matches.discard("明确推荐")
    if "明确不再购买" in matches:
        matches.discard("明确复购意向")
    return matches
