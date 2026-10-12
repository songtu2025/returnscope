import { ListBullets, Stack } from "@phosphor-icons/react";

const TABS = [
  { id: "products", label: "产品信息管理", icon: Stack },
  { id: "rules", label: "导入规则", icon: ListBullets },
];

/** @param {{current: string, onChange: (view: string) => void}} props */
export function DataAssetTabs({ current, onChange }) {
  return (
    <div className="data-tabs page-loading-navigation" aria-label="产品信息管理导航">
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
