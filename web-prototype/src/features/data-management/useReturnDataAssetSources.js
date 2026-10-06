import useSWR from "swr";
import { dataApi } from "../../shared/api/dataApi";
import { serverStateKeys } from "../../shared/serverState";
import { canonicalSources, mergeSourceDetails } from "./returnDataAssetPresentation";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetSource} DatasetSource */

export function useReturnSources() {
  return useSWR(serverStateKeys.returnSources, async () =>
    canonicalSources(await dataApi.managedDatasets("returns")),
  );
}

/** @param {DatasetSource | undefined} expandedSource */
export function useReturnSourceDetails(expandedSource) {
  return useSWR(
    expandedSource
      ? serverStateKeys.returnSourceDetails(
          expandedSource.id,
          expandedSource.member_ids,
        )
      : null,
    async () => {
      if (!expandedSource) return null;
      const members = await Promise.all(
        expandedSource.member_ids.map((id) =>
          dataApi.dataset(id, { include: "versions,imports" }),
        ),
      );
      return mergeSourceDetails(expandedSource, members);
    },
  );
}
