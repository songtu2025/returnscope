import { ArrowRight, Clock, ShieldCheck } from "@phosphor-icons/react";
import { CardHeading, InfoRow } from "../../components/SharedUi";
import { classNames, formatTime } from "../../lib/presentation";
import { configValue } from "./modelServiceConfig";

export function ModelServiceInspector({
  selectedConnection,
  selectedVersion,
  previousVersion,
  versionChanges,
  busy,
  validationActive,
  onShowVersion,
  onCreateDraft,
}) {
  return (
    <aside className="config-inspector">
      <section className="content-card">
        <CardHeading title="发布状态" />
        <div
          className={classNames(
            "large-connection-status",
            selectedConnection?.active_version && "online",
          )}
        >
          <span />
          <b>{selectedConnection?.active_version ? "运行配置正常" : "尚未发布"}</b>
        </div>
        <InfoRow
          label="当前版本"
          value={
            selectedConnection?.active_version
              ? `#${selectedConnection.active_version.version}`
              : "—"
          }
        />
        <InfoRow
          label="共享验证模型"
          value={selectedConnection?.active_version?.primary_model ?? "—"}
        />
        <InfoRow
          label="最后验证"
          value={formatTime(selectedConnection?.active_version?.validated_at)}
        />
      </section>
      {selectedConnection && (
        <section className="content-card config-version-card">
          <CardHeading
            title="配置版本"
            note={`${selectedConnection.versions.length} 个不可变版本`}
          />
          <div className="config-version-list">
            {selectedConnection.versions.map((version) => (
              <button
                key={version.id}
                className={selectedVersion?.id === version.id ? "active" : ""}
                onClick={() => onShowVersion(version)}
              >
                <b>#{version.version}</b>
                <span>{version.change_note || "未填写原因"}</span>
                <em>
                  {version.id === selectedConnection.active_version_id
                    ? "当前运行"
                    : !version.published_at
                      ? "未发布草稿"
                      : "历史版本"}
                </em>
                <small>
                  {version.creator_name} · {formatTime(version.created_at)}
                </small>
              </button>
            ))}
          </div>
        </section>
      )}
      {selectedVersion && (
        <section className="content-card config-diff-card">
          <CardHeading
            title="相对上一版"
            note={
              previousVersion
                ? `#${previousVersion.version} → #${selectedVersion.version}`
                : "首个版本"
            }
            action={
              <button
                className="secondary-button compact-button"
                onClick={() => onCreateDraft(selectedVersion)}
                disabled={Boolean(busy) || validationActive}
              >
                基于此版本创建草稿
              </button>
            }
          />
          {!previousVersion && <p className="muted-line">这是该线路的首个配置版本。</p>}
          {previousVersion && versionChanges.length === 0 && (
            <p className="muted-line">模型与运行参数未变化。</p>
          )}
          {versionChanges.map(([key, label]) => (
            <div className="config-diff-row" key={key}>
              <b>{label}</b>
              <span>{configValue(key, previousVersion[key])}</span>
              <ArrowRight size={12} />
              <span>{configValue(key, selectedVersion[key])}</span>
            </div>
          ))}
        </section>
      )}
      <section className="content-card">
        <CardHeading title="配置原则" />
        <p className="inspector-copy">
          <ShieldCheck size={18} />
          草稿必须通过真实 API 调用测试，才能发布给新任务使用。
        </p>
        <p className="inspector-copy">
          <Clock size={18} />
          新版本不会改变已经启动任务的模型快照。
        </p>
      </section>
    </aside>
  );
}
