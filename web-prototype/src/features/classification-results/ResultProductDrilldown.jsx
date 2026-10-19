import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { api } from "../../api";
import { InlineLoading } from "../../components/SharedUi";
import { Pagination } from "../../components/Pagination";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { errorMessage } from "../../shared/api/requestErrors";
import { runResultRequest } from "../../shared/api/requestLifecycle";
import { DrilldownColumn } from "./ClassificationResultDetailParts";

/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ResultRoute */
/** @param {{route: ResultRoute, groupBy: "product_name" | "product_sku", title: string, items: import("../../shared/api/generated/classification-results/types.gen").ClassificationResultDrilldownItemResponse[], total?: number, selected: string, onSelect: (value:string)=>void}} props */
export function ResultProductDrilldown(props) {
  const { route, groupBy } = props;
  // 上级范围变化时同步重建分页状态，旧页不会短暂冒充新候选。
  const scope = JSON.stringify([
    route.version,
    route.problem,
    groupBy === "product_sku" ? route.productName : "",
  ]);
  return <ProductDrilldownPage key={scope} {...props} />;
}

/** @param {Parameters<typeof ResultProductDrilldown>[0]} props */
function ProductDrilldownPage({
  route,
  groupBy,
  title,
  items,
  total: initialTotal,
  selected,
  onSelect,
}) {
  const [expanded, setExpanded] = useState(false);
  const [page, setPage] = useState(1);
  const listRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const controller = useRef(/** @type {AbortController | null} */ (null));
  const query = useMemo(
    () => ({
      page,
      page_size: 20,
      problem: route.problem,
      ...(groupBy === "product_sku" ? { product_name: route.productName } : {}),
    }),
    [page, route.problem, route.productName, groupBy],
  );
  const identity = JSON.stringify([route.version, groupBy, query]);
  const load = useCallback(
    () =>
      runResultRequest(
        controller,
        (signal) =>
          api.classificationResultDrilldown(route.version, groupBy, query, { signal }),
        (value) => value,
      ),
    [route.version, groupBy, query],
  );
  useLayoutEffect(() => () => controller.current?.abort(), [identity, expanded]);
  const { data, error, isLoading, mutate } = useSWR(
    expanded ? ["classification-results", "drilldown", identity] : null,
    load,
    MANAGED_REFRESH_OPTIONS,
  );
  const total = expanded && data ? data.total : (initialTotal ?? items.length);
  const totalPages = Math.max(Math.ceil(total / 20), 1);
  const status = expanded
    ? drilldownReadStatus(error, isLoading, () => void mutate(), title)
    : null;
  return (
    <div ref={listRef} className="result-product-drilldown">
      <DrilldownColumn
        title={title}
        items={expanded ? (data?.items ?? []) : items}
        selected={selected}
        onSelect={onSelect}
        emptyLabel="未提供"
        limit={expanded ? Infinity : 12}
        status={status}
      >
        <ProductDrilldownFooter
          title={title}
          selected={selected}
          total={total}
          expanded={expanded}
          page={page}
          totalPages={totalPages}
          isLoading={isLoading}
          failed={Boolean(error)}
          onToggle={() => {
            setExpanded(!expanded);
            setPage(1);
          }}
          onPage={(next) => {
            setPage(next);
            listRef.current?.querySelector(".drilldown-items")?.scrollTo({ top: 0 });
          }}
        />
      </DrilldownColumn>
    </div>
  );
}

/** @param {unknown} error @param {boolean} isLoading @param {()=>void} retry @param {string} title */
function drilldownReadStatus(error, isLoading, retry, title) {
  return error ? (
    <div role="alert">
      <p>{errorMessage(error)}</p>
      <button className="secondary-button" onClick={retry}>
        重新读取{title}
      </button>
    </div>
  ) : isLoading ? (
    <InlineLoading label={`正在读取${title}…`} compact />
  ) : null;
}

/** @param {{title:string,selected:string,total:number,expanded:boolean,page:number,totalPages:number,isLoading:boolean,failed:boolean,onToggle:()=>void,onPage:(page:number)=>void}} props */
function ProductDrilldownFooter({
  title,
  selected,
  total,
  expanded,
  page,
  totalPages,
  isLoading,
  failed,
  onToggle,
  onPage,
}) {
  return (
    <footer className="result-drilldown-footer">
      {selected && (
        <p className="drilldown-current" title={selected}>
          当前选中：{selected}
        </p>
      )}
      <span>
        共 {total.toLocaleString()} 项
        {!expanded && total > 12 ? " · 快捷显示前12项" : ""}
      </span>
      {(expanded || total > 12) && (
        <button className="text-button" aria-expanded={expanded} onClick={onToggle}>
          {expanded ? "收起全部" : `查看全部${title}`}
        </button>
      )}
      {expanded && total > 0 && !failed && (
        <Pagination
          page={page}
          pageSize={20}
          total={total}
          totalPages={totalPages}
          simple
          showTotal={false}
          disabled={isLoading}
          onPage={onPage}
        />
      )}
    </footer>
  );
}
