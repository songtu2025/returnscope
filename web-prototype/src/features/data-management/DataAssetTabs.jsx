import { FileCsv, ListBullets, ShieldCheck, Stack } from "@phosphor-icons/react";

const TABS = [
  { id: "returns", label: "退货数据", icon: FileCsv },
  { id: "products", label: "产品信息", icon: Stack },
  { id: "quality", label: "匹配与质量", icon: ShieldCheck },
  { id: "rules", label: "导入规则", icon: ListBullets },
];

export function DataAssetTabs({ current, onChange }) {
  return (
    <div className="data-tabs" aria-label="数据资产分类">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          className={current === id ? "active" : ""}
          aria-current={current === id ? "page" : undefined}
          onClick={() => onChange(id)}
        >
          <Icon size={19} />
          {label}
        </button>
      ))}
    </div>
  );
}
