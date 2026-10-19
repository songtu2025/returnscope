import { formatTime } from "../../lib/presentation";
import { TaskRecycleRowActions } from "./TaskRecycleRowActions";

/** @param {{items: import("./taskRecycleContracts").RecycledListing[], selected: string[], disabled: boolean, onSelect: (ids: string[]) => void, onTask: (item: import("./taskRecycleContracts").RecycledListing) => void, onRestore: (item: import("./taskRecycleContracts").RecycledListing) => void, onPurge: (item: import("./taskRecycleContracts").RecycledListing) => void}} props */
export function TaskRecycleTable({
  items,
  selected,
  disabled,
  onSelect,
  onTask,
  onRestore,
  onPurge,
}) {
  return (
    <div className="recycle-table-wrap">
      <table className="recycle-table">
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                aria-label={`选择当前页全部 ${items.length} 条记录`}
                disabled={disabled || !items.length}
                checked={Boolean(items.length) && selected.length === items.length}
                ref={(node) => {
                  if (node)
                    node.indeterminate =
                      selected.length > 0 && selected.length < items.length;
                }}
                onChange={(event) =>
                  onSelect(event.target.checked ? items.map((item) => item.id) : [])
                }
              />
            </th>
            <th>Listing / 店铺</th>
            <th>所属任务</th>
            <th>移除人</th>
            <th>移除时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <input
                  type="checkbox"
                  aria-label={`选择 ${item.scope.listing || "Listing"} · ${item.scope.store || "未提供店铺"} · ${item.task_title}`}
                  disabled={disabled}
                  checked={selected.includes(item.id)}
                  onChange={(event) =>
                    onSelect(
                      event.target.checked
                        ? [...selected, item.id]
                        : selected.filter((id) => id !== item.id),
                    )
                  }
                />
              </td>
              <td>
                <b>{item.scope.listing || "--"}</b>
                <small>{item.scope.store || "--"}</small>
              </td>
              <td>
                <button
                  className="text-button"
                  data-list-return-id={item.id}
                  disabled={disabled}
                  onClick={() => onTask(item)}
                >
                  {item.task_title}
                </button>
              </td>
              <td>{item.removed_by}</td>
              <td>{formatTime(item.deleted_at)}</td>
              <td>
                <TaskRecycleRowActions
                  item={item}
                  disabled={disabled}
                  onRestore={() => onRestore(item)}
                  onPurge={() => onPurge(item)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
