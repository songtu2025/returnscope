/** @typedef {import("./mysqlReturnContracts").MysqlSchema} MysqlSchema */
/** @typedef {import("./mysqlReturnContracts").MysqlReturnFormState} MysqlReturnFormState */
/** @typedef {import("./mysqlReturnContracts").MysqlPreview} MysqlPreview */

/** @param {MysqlSchema | undefined} schema @param {MysqlReturnFormState} form @param {boolean} loading @param {MysqlPreview | null} preview */
export function mysqlImportReadiness(schema, form, loading, preview) {
  const mappingReady = mappingIsReady(schema, form);
  const invalidDateRange = Boolean(
    form.date_from && form.date_to && form.date_from > form.date_to,
  );

  const canPrepare = Boolean(
    !loading &&
    mappingReady &&
    !invalidDateRange &&
    preview?.row_count &&
    !preview.over_limit &&
    !preview.missing_store_rows,
  );

  return { mappingReady, invalidDateRange, canPrepare };
}

/** @param {MysqlSchema | undefined} schema @param {MysqlReturnFormState} form */
function mappingIsReady(schema, form) {
  return Boolean(
    schema?.configured &&
    schema.fields.every((field) => !field.required || form.mapping[field.name]) &&
    (form.mapping["店铺/站点"] || form.default_store.trim()),
  );
}
