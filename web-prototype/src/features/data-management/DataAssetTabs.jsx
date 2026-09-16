import { FileCsv, ListBullets, Stack } from "@phosphor-icons/react";

const TABS = [
  { id: "returns", label: "退货数据", icon: FileCsv },
  { id: "products", label: "商品信息汇总", icon: Stack },
  { id: "rules", label: "导入规则", icon: ListBullets },
];

/** @param {{current: string, onChange: (view: string) => void}} props */
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
