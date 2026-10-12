import { useLayoutEffect, useState } from "react";

/** 后台照常读取，用户操作期间保留当前展示；显式切换对象时不沿用旧对象。
 * @template Value
 * @param {Value} value
 * @param {boolean} protectedOperation
 * @param {string} identity
 * @returns {Value}
 */
export function useProtectedData(value, protectedOperation, identity) {
  const [displayed, setDisplayed] = useState({ value, identity });
  useLayoutEffect(() => {
    setDisplayed((current) => {
      if (current.identity === identity && protectedOperation && current.value != null)
        return current;
      if (current.identity === identity && current.value === value) return current;
      return { value, identity };
    });
  }, [identity, protectedOperation, value]);
  return displayed.identity === identity ? displayed.value : value;
}
