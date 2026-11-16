import "@ant-design/v5-patch-for-react-19";
import "antd/dist/reset.css";
import "./globals.css";
import "./mobile.css";
import "./ui-refresh.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider } from "antd";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";

function RootProviders() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            staleTime: 60_000,
            gcTime: 10 * 60_000,
            refetchOnWindowFocus: false,
            refetchOnReconnect: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        theme={{
          token: {
            colorPrimary: "#245bdb",
            colorInfo: "#245bdb",
            colorSuccess: "#16a34a",
            colorWarning: "#d97706",
            colorError: "#dc2626",
            colorBgLayout: "#f4f6f8",
            colorText: "#1f2937",
            colorBorder: "#d9e0e8",
            borderRadius: 5,
            fontFamily:
              '"Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif',
          },
          components: {
            Layout: {
              headerBg: "#ffffff",
              siderBg: "#ffffff",
            },
            Menu: { itemBorderRadius: 5 },
            Table: {
              headerBg: "#f8fafc",
              headerColor: "#475467",
              borderColor: "#eaecf0",
              rowHoverBg: "#f8faff",
            },
            Card: { borderRadiusLG: 8 },
          },
        }}
      >
        <AntApp>
          <App />
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <RootProviders />
    </BrowserRouter>
  </StrictMode>,
);

