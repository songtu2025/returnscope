import { describe, expect, test } from "vitest";
import { groupFactsByLabel } from "../src/features/classification-results/semanticFactGroups";
import { normalizedFact } from "../src/features/classification-results/semanticResultFacts";

function syntheticFact() {
  return normalizedFact(
    {
      fact_id: "SYNTHETIC-F1",
      label_code: "FIT_SMALL",
      label_path: ["尺码与适配", "偏小"],
      opinion: "合成反馈：穿着偏小",
      evidence: "Synthetic evidence one.",
      evidence_source: "BODY",
    },
    0,
  );
}

describe("标签事实归并", () => {
  test("保留首项对象、编号和证据的首次出现顺序，不改输入", () => {
    const first = syntheticFact();
    const duplicate = { ...first, factId: "SYNTHETIC-F2" };
    const secondEvidence = { ...duplicate, evidence: "Synthetic evidence two." };
    const otherSource = { ...first, evidenceSource: "TITLE" };
    const facts = [first, duplicate, secondEvidence, otherSource, duplicate];
    const original = structuredClone(facts);
    const groups = groupFactsByLabel(facts);

    expect(groups).toHaveLength(1);
    expect(groups[0].facts).toHaveLength(1);
    expect(groups[0].facts[0].fact).toBe(first);
    expect(groups[0].facts[0].factIds).toEqual(["SYNTHETIC-F1", "SYNTHETIC-F2"]);
    expect(groups[0].facts[0].evidences).toEqual([
      { source: "BODY", text: "Synthetic evidence one." },
      { source: "BODY", text: "Synthetic evidence two." },
      { source: "TITLE", text: "Synthetic evidence one." },
    ]);
    expect(facts).toEqual(original);
  });

  test.each([
    "subject",
    "direction",
    "assertion",
    "sourceRef",
    "experiencerRef",
    "productRef",
    "variantRef",
    "eventRef",
    "referenceBasis",
    "condition",
    "operation",
    "part",
    "decisionReason",
    "mappingReason",
    "relationType",
    "causalAttribution",
  ])("同标签的 %s 不同，保留独立事实", (field) => {
    const first = syntheticFact();
    const second = { ...first, [field]: "另一合成作用域" };
    expect(groupFactsByLabel([first, second])[0].facts).toHaveLength(2);
  });

  test("关联事实顺序、中文观点及完整标签路径参与事实区分", () => {
    const first = syntheticFact();
    const variants = [
      { ...first, relatedFactIds: ["SYNTHETIC-A", "SYNTHETIC-B"] },
      { ...first, relatedFactIds: ["SYNTHETIC-B", "SYNTHETIC-A"] },
      { ...first, opinion: "另一合成观点" },
      { ...first, labelPath: ["尺码与适配", "手指偏短"] },
    ];
    const groups = groupFactsByLabel([first, ...variants]);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("尺码与适配 → 偏小");
    expect(groups[0].facts).toHaveLength(5);
  });

  test("没有中文观点时以证据区分事实，空编号不写入编号列表", () => {
    const first = { ...syntheticFact(), opinion: "", factId: "" };
    const second = { ...first, evidence: "Different synthetic evidence." };
    const group = groupFactsByLabel([first, second])[0];
    expect(group.facts).toHaveLength(2);
    expect(group.facts[0].factIds).toEqual([]);
  });

  test("保留标签组首次顺序，缺少代码时按路径及原位置分组", () => {
    const first = syntheticFact();
    const pathOnly = { ...first, labelCode: "" };
    const unlabeled = { ...pathOnly, labelPath: [] };
    const groups = groupFactsByLabel([first, pathOnly, unlabeled, unlabeled]);
    expect(groups.map(({ key }) => key)).toEqual([
      "code:FIT_SMALL",
      "path:尺码与适配 → 偏小",
      "unlabeled:2",
      "unlabeled:3",
    ]);
    expect(groups.slice(2).map(({ label }) => label)).toEqual([
      "未映射标签",
      "未映射标签",
    ]);
    expect(groupFactsByLabel([])).toEqual([]);
  });
});
