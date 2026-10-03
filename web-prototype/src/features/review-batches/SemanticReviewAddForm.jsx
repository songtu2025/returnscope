import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import { labelText } from "../../lib/taxonomyPresentation";
import { selectedSentiment } from "./semanticReviewDrafts";
import { SentimentField } from "./SemanticSentimentField";

/** @param {import("./semanticLedgerContracts").SemanticLedgerContext} context */
export function SemanticReviewAddForm(context) {
  const { labels, setAdding, draft, setDraft, addItem } = context;
  return (
    <div className="semantic-review-add-form">
      <b>补充遗漏观点</b>
      <label>
        原文证据
        <Input
          value={draft.evidence_text}
          onChange={(event) =>
            setDraft({ ...draft, evidence_text: event.target.value })
          }
          placeholder="粘贴能够支持该观点的原文片段"
        />
      </label>
      <label>
        用户观点
        <Input
          value={draft.opinion}
          onChange={(event) => setDraft({ ...draft, opinion: event.target.value })}
          placeholder="用一句话概括用户表达的观点"
        />
      </label>
      <label>
        归类标签
        <Select
          aria-label="补充观点的归类标签"
          showSearch
          optionFilterProp="label"
          value={draft.label_code}
          onChange={(label_code) => setDraft({ ...draft, label_code, sentiment: "" })}
          options={[
            { value: "", label: "请选择分类标签" },
            ...labels.map((label) => ({
              value: label.code,
              label: `${labelText(label)} · ${label.code}`,
            })),
          ]}
        />
      </label>
      <SentimentField
        code={draft.label_code}
        labels={labels}
        value={draft.sentiment}
        name="补充观点的评价方向"
        onChange={(sentiment) => setDraft({ ...draft, sentiment })}
      />
      <div>
        <Button onClick={() => setAdding(false)}>取消</Button>
        <Button
          type="primary"
          disabled={
            !draft.evidence_text.trim() ||
            !draft.opinion.trim() ||
            !draft.label_code ||
            !selectedSentiment(draft.label_code, labels, draft.sentiment)
          }
          onClick={addItem}
        >
          添加观点
        </Button>
      </div>
    </div>
  );
}
