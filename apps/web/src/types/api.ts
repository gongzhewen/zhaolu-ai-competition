export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
  trace_id?: string;
};

export type DimensionItem = {
  id: number;
  [key: string]: string | number | null;
};

