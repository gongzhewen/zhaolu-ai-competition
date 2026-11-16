import { Button, Space, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";

import { apiFetch, clearToken, getToken } from "@/lib/api/client";

type CurrentUser = {
  username: string;
  display_name: string | null;
  display_role: string;
  roles: string[];
  permissions: string[];
};

const routeTitles: Record<string, string> = {
  "/dashboard": "招生工作台",
  "/admissions/overview": "招生驾驶舱",
  "/source/overview": "生源分析",
  "/data/import": "数据导入",
  "/data/dbf": "DBF 原始数据导入",
  "/data/quality": "数据质量",
  "/data/major-aliases": "专业名称修正",
  "/ai/assistant": "AI 招录助手",
  "/ai/insights": "AI 数据洞察",
  "/analytics/anomalies": "AI 异常检测",
  "/analytics/simulation": "计划策略沙盘",
  "/reports": "报告中心",
  "/forecast/overview": "预测与预警",
  "/system/users": "用户管理",
  "/system/roles": "角色权限",
  "/system/students": "学生信息管理",
  "/system/audit": "审计日志",
};

export function TopBar() {
  const navigate = useNavigate();
  const pathname = useLocation().pathname;
  const { data: currentUser } = useQuery({
    queryKey: ["current-user"],
    queryFn: () => apiFetch<CurrentUser>("/auth/me"),
    enabled: Boolean(getToken()),
    staleTime: 5 * 60_000,
  });

  function handleLogout(): void {
    clearToken();
    navigate("/login");
  }

  const userName = currentUser?.display_name || currentUser?.username || "系统用户";
  const roleName = currentUser?.display_role || "系统用户";

  return (
    <header className="app-header">
      <div className="app-header-context">
        <div className="app-header-title">
          <Typography.Text strong>{routeTitles[pathname] ?? "招录智策"}</Typography.Text>
        </div>
      </div>
      <Space>
        <div className="app-user-info">
          <Typography.Text strong>{userName}</Typography.Text>
          <small>{roleName}</small>
        </div>
        <Button onClick={handleLogout}>退出</Button>
      </Space>
    </header>
  );
}


