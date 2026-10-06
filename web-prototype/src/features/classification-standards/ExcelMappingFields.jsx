/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardExcelColumns} ClassificationStandardExcelColumns */
/** @typedef {{columns: Required<ClassificationStandardExcelColumns>, headers?: string[], updateColumns: (columns: Required<ClassificationStandardExcelColumns>) => void}} ColumnFieldsProps */
/** @param {ColumnFieldsProps & {column: string, index: number}} props */
function HierarchyColumn({ column, index, columns, headers, updateColumns }) {
  return (
    <label>
      第 {index + 1} 级
      <select
        aria-label={`第 ${index + 1} 级来源列`}
        value={column}
        onChange={(event) =>
          updateColumns({
            ...columns,
            hierarchy_columns: columns.hierarchy_columns.map((value, position) =>
              position === index ? event.target.value : value,
            ),
          })
        }
      >
        <option value="">请选择列</option>
        {(headers ?? []).map((header) => (
          <option key={header}>{header}</option>
        ))}
      </select>
      <button
        type="button"
        className="secondary-button compact-button"
        onClick={() =>
          updateColumns({
            ...columns,
            hierarchy_columns: columns.hierarchy_columns.filter(
              (_value, position) => position !== index,
            ),
          })
        }
      >
        移除此级
      </button>
    </label>
  );
}
/** @param {ColumnFieldsProps & {field: "source_label_column" | "sentiment_column", label: string}} props */
function OptionalColumn({ field, label, columns, headers, updateColumns }) {
  return (
    <label>
      {label}
      <select
        aria-label={label}
        value={columns[field]}
        onChange={(event) =>
          updateColumns({
            ...columns,
            [field]: event.target.value,
          })
        }
      >
        <option value="">不指定</option>
        {(headers ?? []).map((header) => (
          <option key={header}>{header}</option>
        ))}
      </select>
    </label>
  );
}
/** @type {["source_label_column" | "sentiment_column", string][]} */
const OPTIONAL_COLUMN_FIELDS = [
  ["source_label_column", "原始说法列"],
  ["sentiment_column", "评价方向列"],
];
/** @param {ColumnFieldsProps} props */
function MappedColumns({ columns, headers, updateColumns }) {
  return (
    <>
      {columns.hierarchy_columns.map((column, index) => (
        <HierarchyColumn
          key={index}
          column={column}
          index={index}
          columns={columns}
          headers={headers}
          updateColumns={updateColumns}
        />
      ))}
      <button
        type="button"
        className="secondary-button"
        onClick={() =>
          updateColumns({
            ...columns,
            hierarchy_columns: [...columns.hierarchy_columns, ""],
          })
        }
      >
        增加层级列
      </button>
      {OPTIONAL_COLUMN_FIELDS.map(([field, label]) => (
        <OptionalColumn
          key={field}
          field={field}
          label={label}
          columns={columns}
          headers={headers}
          updateColumns={updateColumns}
        />
      ))}
    </>
  );
}
/** @param {{sheet: string, sheets: string[], onSheetChange: (sheet: string) => void}} props */
function WorksheetField({ sheet, sheets, onSheetChange }) {
  return (
    <label>
      工作表
      <select
        aria-label="标签框架工作表"
        value={sheet}
        onChange={(event) => onSheetChange(event.target.value)}
      >
        <option value="">请选择工作表</option>
        {sheets.map((sheet) => (
          <option key={sheet} value={sheet}>
            {sheet}
          </option>
        ))}
      </select>
    </label>
  );
}
/** @param {ColumnFieldsProps & {sheet: string, sheets: string[], onSheetChange: (sheet: string) => void, onPreview: () => void}} props */
export function ExcelMappingFields({
  sheet,
  sheets,
  columns,
  headers,
  updateColumns,
  onSheetChange,
  onPreview,
}) {
  return (
    <>
      <WorksheetField sheet={sheet} sheets={sheets} onSheetChange={onSheetChange} />
      {sheet && (
        <>
          <MappedColumns
            columns={columns}
            headers={headers}
            updateColumns={updateColumns}
          />
          <button
            type="button"
            className="secondary-button"
            disabled={
              columns.hierarchy_columns.length < 2 ||
              columns.hierarchy_columns.some((value) => !value)
            }
            onClick={onPreview}
          >
            生成预览
          </button>
        </>
      )}
    </>
  );
}
