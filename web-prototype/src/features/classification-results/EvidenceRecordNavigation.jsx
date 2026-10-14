/** @typedef {ReturnType<typeof import("./useEvidenceNavigation").useEvidenceNavigation>} Navigation */
/** @param {{navigation: Navigation, saving: boolean, onMove: (direction: number) => void}} props */
export function EvidenceRecordNavigation({ navigation, saving, onMove }) {
  const disabled = saving || navigation.busy || navigation.locked;
  return (
    <section
      className="drawer-section evidence-record-navigation"
      aria-label="连续查看反馈"
    >
      <div>
        <button
          className="secondary-button"
          disabled={disabled || navigation.position === 0}
          onClick={() => onMove(-1)}
        >
          上一条
        </button>
        <span role="status">
          {navigation.busy
            ? "正在读取反馈…"
            : `第 ${navigation.position + 1} / ${navigation.total} 条`}
        </span>
        <button
          className="secondary-button"
          disabled={disabled || navigation.position + 1 >= navigation.total}
          onClick={() => onMove(1)}
        >
          下一条
        </button>
      </div>
      {navigation.error && (
        <p role="alert">
          {navigation.error}
          <button
            className="text-button"
            disabled={navigation.busy}
            onClick={() => void navigation.retry()}
          >
            重试读取
          </button>
        </p>
      )}
    </section>
  );
}
