import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import { FunnelSimple, MagnifyingGlass } from "@phosphor-icons/react";
import { useRef } from "react";

const qualityOptions = [
  { value: "", label: "全部记录情况" },
  { value: "ready", label: "含可用记录" },
  { value: "review_required", label: "含待复核记录" },
  { value: "unusable", label: "含不可用记录" },
];

/** @typedef {import("./classificationResultListContracts").ResultPoolContext} ResultPoolContext */

/** @param {ResultPoolContext} context */
export function ResultPoolFilters(context) {
  const { updateRoute, filters, setFilters, route, clearFilters } = context;
  const composing = useRef(false);
  const applied = [
    route.q && `关键词：${route.q}`,
    route.storeSite && `店铺/站点：${route.storeSite}`,
    route.listing && `Listing：${route.listing}`,
    route.qualityStatus &&
      qualityOptions.find((item) => item.value === route.qualityStatus)?.label,
    route.lifecycle === "deleted" && "已删除",
  ].filter((value) => typeof value === "string" && value.length > 0);
  return (
    <form
      className="result-pool-filters"
      aria-label="分类结果筛选"
      onCompositionStart={() => {
        composing.current = true;
      }}
      onCompositionEnd={() => {
        composing.current = false;
      }}
      onKeyDownCapture={(event) => {
        if (
          event.key === "Enter" &&
          (composing.current || event.nativeEvent.isComposing || event.keyCode === 229)
        )
          event.preventDefault();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (!composing.current) updateRoute({ ...filters, page: 1 });
      }}
    >
      <label className="result-filter-field">
        <span>关键词</span>
        <Input
          aria-label="搜索分类结果"
          prefix={<MagnifyingGlass size={18} />}
          placeholder="搜索 Listing、产品名称或 SKU"
          value={filters.q}
          onChange={(event) => setFilters({ ...filters, q: event.target.value })}
        />
      </label>
      <label className="result-filter-field">
        <span>店铺/站点</span>
        <Input
          aria-label="店铺或站点"
          placeholder="店铺/站点"
          value={filters.storeSite}
          onChange={(event) =>
            setFilters({ ...filters, storeSite: event.target.value })
          }
        />
      </label>
      <label className="result-filter-field">
        <span>Listing</span>
        <Input
          aria-label="Listing"
          placeholder="Listing"
          value={filters.listing}
          onChange={(event) => setFilters({ ...filters, listing: event.target.value })}
        />
      </label>
      <label className="result-filter-field">
        <span>记录情况</span>
        <Select
          aria-label="记录情况"
          value={filters.qualityStatus}
          onChange={(qualityStatus) => setFilters({ ...filters, qualityStatus })}
          options={qualityOptions}
        />
      </label>
      <div className="result-filter-actions">
        <Button type="primary" icon={<FunnelSimple size={17} />} htmlType="submit">
          筛选
        </Button>
        <Button onClick={clearFilters}>清除筛选</Button>
      </div>
      {applied.length > 0 && (
        <div className="result-applied-filters" role="status" aria-label="已生效筛选">
          <b>已生效</b>
          {applied.map((label) => (
            <span key={String(label)}>{label}</span>
          ))}
        </div>
      )}
    </form>
  );
}
