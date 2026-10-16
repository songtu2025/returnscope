import { useEffect, useState } from "react";
import { Modal, InlineLoading } from "../../components/SharedUi";
import { Pagination } from "../../components/Pagination";
import { taskApi } from "../../shared/api/taskApi";
import { errorStatus } from "../../shared/api/requestErrors";
import "./planSegmentData.css";

/** @param {{input: import("./taskPlanContracts").TaskPlanPreviewInput, segment: import("./taskPlanContracts").TaskPlanSegment, onClose: () => void, onRecheck?: () => void | Promise<unknown>}} props */
export function PlanSegmentDataDialog({ input, segment, onClose, onRecheck }) {
  const [query, setQuery] = useState(
    /** @type {{view: "groups" | "records", group_no: number | null, page: number}} */ ({
      view: "groups",
      group_no: null,
      page: 1,
    }),
  );
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState(
    /** @type {{key: string, data: import("./taskPlanContracts").TaskPlanPreviewResponse | null, error: string, loading: boolean, status?: number}} */ ({
      key: "",
      data: null,
      error: "",
      loading: true,
    }),
  );
  const request = JSON.stringify({
    ...input,
    segment_key: segment.segment_key,
    ...query,
    page_size: 20,
  });
  const { data, error, loading } =
    load.key === request ? load : { data: null, error: "", loading: true };
  useEffect(() => {
    let active = true;
    setLoad({ key: request, data: null, error: "", loading: true });
    taskApi
      .previewTaskSegment(JSON.parse(request))
      .then(
        (/** @type {import("./taskPlanContracts").TaskPlanPreviewResponse} */ data) => {
          if (active) setLoad({ key: request, data, error: "", loading: false });
        },
      )
      .catch((failure) => {
        if (active)
          setLoad({
            key: request,
            data: null,
            error:
              failure instanceof Error ? failure.message : "读取分组数据失败，请重试。",
            status: Number(errorStatus(failure) || 0),
            loading: false,
          });
      });
    return () => {
      active = false;
    };
  }, [request, attempt]);
  return (
    <Modal
      title={`${segment.scope?.listing || segment.agent_family} · 分组数据`}
      className="plan-data-dialog"
      onClose={onClose}
    >
      <div className="modal-form">
        <p>
          {segment.scope?.store} · {segment.standard_name || segment.agent_family} ·{" "}
          {(data?.record_total ?? segment.record_count).toLocaleString()} 条源记录 /{" "}
          {(data?.group_total ?? segment.unique_comments).toLocaleString()} 个评论组
        </p>
        <div className="plan-data-tabs">
          <button
            type="button"
            className="secondary-button compact-button"
            aria-pressed={query.view === "groups"}
            onClick={() => setQuery({ view: "groups", group_no: null, page: 1 })}
          >
            评论组
          </button>
          <button
            type="button"
            className="secondary-button compact-button"
            aria-pressed={query.view === "records" && query.group_no === null}
            onClick={() => setQuery({ view: "records", group_no: null, page: 1 })}
          >
            全部源记录
          </button>
          {query.group_no !== null && <b>评论组 {query.group_no} 的源记录</b>}
        </div>
        <div className="plan-data-body" aria-busy={loading}>
          {loading && <InlineLoading label="正在读取分组数据…" />}
          {error && (
            <div role="alert">
              <p>{error}</p>
              <button
                type="button"
                className="secondary-button compact-button"
                onClick={() => {
                  if (load.status === 409 && onRecheck) {
                    onClose();
                    void onRecheck();
                  } else setAttempt((value) => value + 1);
                }}
              >
                {load.status === 409 && onRecheck ? "重新检查数据" : "重试读取"}
              </button>
            </div>
          )}
          {data && data.items.length === 0 && <p>当前分组暂无数据。</p>}
          {data &&
            data.items.map((row) => (
              <article
                className="plan-preview-row"
                key={query.view === "groups" ? row.group_no : row.source_row}
              >
                <header>
                  <b>评论组 {row.group_no}</b>
                  {query.view === "groups" ? (
                    <button
                      type="button"
                      className="text-button"
                      onClick={() =>
                        setQuery({ view: "records", group_no: row.group_no, page: 1 })
                      }
                    >
                      查看 {row.record_count} 条源记录
                    </button>
                  ) : (
                    <span>
                      源行 {row.source_row} · {row.date || "—"}
                    </span>
                  )}
                </header>
                {query.view === "records" && (
                  <p>
                    {row.sku || "—"} · {row.product_name || "—"}
                  </p>
                )}
                {row.title && (
                  <p>
                    <b>{row.title}</b>
                  </p>
                )}
                <p className="plan-preview-comment">{row.comment || "—"}</p>
              </article>
            ))}
        </div>
        {data && (
          <Pagination
            page={query.page}
            pageSize={20}
            total={data.total}
            totalPages={Math.max(1, Math.ceil(data.total / 20))}
            unit={query.view === "groups" ? "个评论组" : "条源记录"}
            onPage={(page) => setQuery({ ...query, page })}
            disabled={loading}
          />
        )}
      </div>
    </Modal>
  );
}
