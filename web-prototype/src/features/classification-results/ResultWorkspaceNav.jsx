import { navigateHash } from "../../app/hashRouter";

const ITEMS = [
  { id: "results", label: "结果版本", query: {} },
  {
    id: "pending",
    label: "待复核",
    query: { quality_status: "review_required" },
  },
  { id: "reviews", label: "复核记录", query: { view: "reviews" } },
];

export function ResultWorkspaceNav({ active }) {
  return (
    <nav className="data-tabs result-workspace-tabs" aria-label="分类结果工作区">
      {ITEMS.map((item) => (
        <button
          className={active === item.id ? "active" : ""}
          aria-current={active === item.id ? "page" : undefined}
          onClick={() => navigateHash("classification-results", item.query)}
          key={item.id}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
