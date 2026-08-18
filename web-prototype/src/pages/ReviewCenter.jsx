import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, ListChecks } from "@phosphor-icons/react";
import { api } from "../api";
import {
  CardHeading,
  EmptyState,
  InfoRow,
  PageHeading,
  StatusBadge,
} from "../components/SharedUi";
import { formatTime } from "../lib/presentation";

export function ReviewCenter({ notify, onChanged, focus }) {
  const [status, setStatus] = useState("pending");
  const [rows, setRows] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [labels, setLabels] = useState([]);
  const [labelCode, setLabelCode] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const loadRequest = useRef(0);

  const load = useCallback(async () => {
    const request = ++loadRequest.current;
    const values = await api.reviews(status);
    if (request !== loadRequest.current) return;
    setRows(values);
    setSelectedId((current) =>
      values.some((item) => item.id === current) ? current : (values[0]?.id ?? null),
    );
  }, [status]);
  useEffect(() => {
    Promise.all([
      load(),
      api.taxonomy().then((value) => setLabels(value.labels)),
    ]).catch((error) => notify(error.message, "error"));
  }, [load, notify]);
  useEffect(() => {
    if (!focus) return;
    setStatus(focus.status);
    setSelectedId(focus.id);
  }, [focus]);
  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    api
      .review(selectedId)
      .then((value) => {
        setSelected(value);
        setLabelCode(
          value.classification.primary_label_codes?.[0] ??
            value.classification.problem_label_codes?.[0] ??
            "",
        );
        setNote("");
      })
      .catch((error) => notify(error.message, "error"));
  }, [selectedId, notify]);

  const resolve = async () => {
    setSaving(true);
    try {
      await api.resolveReview(selected.id, {
        expected_revision: selected.revision,
        label_code: labelCode || null,
        note,
      });
      notify("复核修改已写入新的结果版本");
      await load();
      onChanged();
    } catch (error) {
      notify(
        error.status === 409 ? "该记录已被他人修改，已为你刷新" : error.message,
        "error",
      );
      if (error.status === 409) setSelected(await api.review(selected.id));
    } finally {
      setSaving(false);
    }
  };
  const revisionLabel = (classification) => {
    const codes = classification?.primary_label_codes ?? [];
    return (
      codes
        .map((code) => labels.find((label) => label.code === code)?.name ?? code)
        .join("、") || "未标注"
    );
  };

  return (
    <div className="standard-page review-page">
      <PageHeading
        eyebrow="人工质量闸门"
        title="复核中心"
        description="所有用户可处理任意任务的待复核项；提交时使用版本号防止相互覆盖。"
      />
      <div className="review-layout">
        <aside className="review-list">
          <div className="segmented">
            <button
              className={status === "pending" ? "active" : ""}
              onClick={() => setStatus("pending")}
            >
              待复核
            </button>
            <button
              className={status === "resolved" ? "active" : ""}
              onClick={() => setStatus("resolved")}
            >
              已处理
            </button>
          </div>
          <div className="review-scroll">
            {rows.length === 0 && (
              <EmptyState
                icon={ListChecks}
                title="没有记录"
                description={
                  status === "pending" ? "当前无需人工复核。" : "尚无已处理记录。"
                }
              />
            )}
            {rows.map((row) => (
              <button
                key={row.id}
                className={selectedId === row.id ? "active" : ""}
                onClick={() => setSelectedId(row.id)}
              >
                <div>
                  <StatusBadge value={row.classification.status} />
                  <time>{formatTime(row.updated_at)}</time>
                </div>
                <p>{row.comment}</p>
                <small>
                  {row.task_title} · {row.owner_name}
                </small>
              </button>
            ))}
          </div>
        </aside>
        <section className="review-workspace">
          {!selected && (
            <EmptyState
              icon={ListChecks}
              title="选择一条复核记录"
              description="查看证据并完成标签确认。"
            />
          )}
          {selected && (
            <>
              <header className="review-header">
                <div>
                  <span className="asset-type">
                    {selected.workflow_status === "pending"
                      ? "等待人工判断"
                      : "已完成复核"}
                  </span>
                  <h2>{selected.task_title}</h2>
                  <p>
                    记录版本 #{selected.revision} · 最近修改{" "}
                    {formatTime(selected.updated_at)}
                  </p>
                </div>
                <StatusBadge value={selected.classification.status} />
              </header>
              <section className="evidence-panel">
                <span>客户评论原文</span>
                <blockquote>“{selected.comment}”</blockquote>
                <div className="model-evidence">
                  <b>模型证据</b>
                  <p>
                    {selected.classification.semantic_units
                      ?.map((unit) => unit.evidence)
                      .join(" · ") || "模型未提取到有效证据"}
                  </p>
                </div>
              </section>
              <div className="review-grid">
                <section className="content-card">
                  <CardHeading title="复核结论" note="修改会生成新结果版本" />
                  <label>
                    最终标签
                    <select
                      disabled={selected.workflow_status === "resolved"}
                      value={labelCode}
                      onChange={(event) => setLabelCode(event.target.value)}
                    >
                      <option value="">保持模型结论</option>
                      {labels.map((label) => (
                        <option key={label.code} value={label.code}>
                          {label.name} · {label.code}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    修改说明
                    <textarea
                      disabled={selected.workflow_status === "resolved"}
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      rows="4"
                      placeholder="必填：说明判断依据，便于后续追溯"
                      required
                    />
                  </label>
                  {selected.workflow_status === "pending" && (
                    <button
                      className="primary-button full-button"
                      disabled={saving || !note.trim()}
                      onClick={resolve}
                    >
                      {saving ? "正在写入新版本…" : "确认并完成复核"}
                      <CheckCircle size={18} />
                    </button>
                  )}
                </section>
                <section className="content-card">
                  <CardHeading
                    title="模型判断"
                    note={selected.classification.model_name}
                  />
                  <InfoRow
                    label="主因标签"
                    value={
                      selected.classification.primary_label_codes?.join("、") || "—"
                    }
                  />
                  <InfoRow
                    label="问题标签"
                    value={
                      selected.classification.problem_label_codes?.join("、") || "—"
                    }
                  />
                  <InfoRow
                    label="复核原因"
                    value={selected.classification.review_reasons?.join("；") || "—"}
                  />
                  <InfoRow
                    label="分类体系"
                    value={selected.classification.taxonomy_version}
                  />
                </section>
                <section className="content-card revision-card">
                  <CardHeading
                    title="修改留痕"
                    note={`${selected.revisions?.length ?? 0} 次人工修改`}
                  />
                  {selected.revisions?.length === 0 && (
                    <p className="muted-line">尚无人工修改。</p>
                  )}
                  {selected.revisions?.map((revision) => (
                    <div className="revision-row" key={revision.id}>
                      <span>{revision.actor_name?.slice(0, 1)}</span>
                      <div>
                        <b>
                          {revision.actor_name} · 结果版本 #{revision.revision}
                        </b>
                        <p className="revision-change">
                          {revisionLabel(revision.before)} →{" "}
                          {revisionLabel(revision.after)}
                        </p>
                        <p>{revision.note}</p>
                        <small>{formatTime(revision.created_at)}</small>
                      </div>
                    </div>
                  ))}
                </section>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
