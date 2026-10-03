import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import { FunnelSimple, MagnifyingGlass } from "@phosphor-icons/react";

/** @typedef {import("./classificationResultListContracts").ResultPoolContext} ResultPoolContext */

/** @param {ResultPoolContext} context */
export function ResultPoolFilters(context) {
  const { updateRoute, filters, setFilters } = context;
  return (
    <section className="result-pool-filters" aria-label="分类结果筛选">
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
        <span>结果质量</span>
        <Select
          aria-label="结果质量"
          value={filters.qualityStatus}
          onChange={(qualityStatus) => setFilters({ ...filters, qualityStatus })}
          options={[
            { value: "", label: "全部质量状态" },
            { value: "ready", label: "可用" },
            { value: "review_required", label: "需复核" },
            { value: "unusable", label: "不可用" },
          ]}
        />
      </label>
      <Button
        type="primary"
        icon={<FunnelSimple size={17} />}
        onClick={() => updateRoute({ ...filters, page: 1 })}
      >
        筛选
      </Button>
    </section>
  );
}
