import { lazy, Suspense } from "react";

const EChartsContainer = lazy(() =>
  import("./echarts-container").then((module) => ({ default: module.EChartsContainer })),
);

type Props = {
  option: Parameters<typeof EChartsContainer>[0]["option"];
  height?: number;
};

export function LazyEChartsContainer({ option, height = 320 }: Props) {
  return (
    <Suspense fallback={<div className="chart-loading-placeholder" />}>
      <EChartsContainer option={option} height={height} />
    </Suspense>
  );
}
