import {
  BarChartOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  RobotOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Layout, Menu } from "antd";
import type { MenuProps } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import { apiFetch, getToken } from "@/lib/api/client";

type CurrentUser = {
  username: string;
  roles: string[];
  permissions: string[];
};

type NavigationItem = {
  key: string;
  label: React.ReactNode;
};

const navigationGroups = ["admissions", "data", "ai", "system"];

function findActiveGroup(pathname: string): string | undefined {
  if (pathname.startsWith("/admissions") || pathname.startsWith("/source")) {
    return "admissions";
  }
  if (pathname.startsWith("/data")) {
    return "data";
  }
  if (
    pathname.startsWith("/ai") ||
    pathname.startsWith("/analytics") ||
    pathname.startsWith("/reports") ||
    pathname.startsWith("/forecast")
  ) {
    return "ai";
  }
  if (pathname.startsWith("/system")) {
    return "system";
  }
  return undefined;
}

function linkItem(path: string, label: string): NavigationItem {
  return { key: path, label: <Link to={path}>{label}</Link> };
}

export function Sidebar() {
  const pathname = useLocation().pathname;
  const [collapsed, setCollapsed] = useState(false);
  const [openKeys, setOpenKeys] = useState<string[]>(navigationGroups);
  const { data: currentUser } = useQuery({
    queryKey: ["current-user"],
    queryFn: () => apiFetch<CurrentUser>("/auth/me"),
    enabled: Boolean(getToken()),
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    const activeGroup = findActiveGroup(pathname);
    if (!activeGroup) {
      return;
    }
    setOpenKeys((current) => (
      current.includes(activeGroup) ? current : [...current, activeGroup]
    ));
  }, [pathname]);

  const isSuperAdmin = currentUser?.roles?.some((role) => role === "SUPER_ADMIN") ?? false;
  const canManagePlans = currentUser?.permissions?.includes("admissions:plan:manage") ?? false;
  const canManageAliases = currentUser?.permissions?.includes("data:quality:manage") ?? false;

  const admissionItems = [
    linkItem("/admissions/overview", "招生驾驶舱"),
    linkItem("/source/overview", "生源分析"),
    ...(canManagePlans ? [linkItem("/admissions/plans", "招生计划填报")] : []),
  ];
  const dataItems = [
    linkItem("/data/import", "数据导入"),
    linkItem("/data/dbf", "DBF 原始导入"),
    linkItem("/data/quality", "数据质量"),
    ...(canManageAliases ? [linkItem("/data/major-aliases", "专业名称修正")] : []),
  ];
  const aiItems = [
    linkItem("/ai/assistant", "AI 招录助手"),
    linkItem("/ai/insights", "AI 数据洞察"),
    linkItem("/analytics/anomalies", "AI 异常检测"),
    linkItem("/analytics/simulation", "计划策略沙盘"),
    linkItem("/reports", "AI 报告中心"),
    linkItem("/forecast/overview", "预测与预警"),
  ];
  const systemItems = [
    linkItem("/system/users", "用户管理"),
    linkItem("/system/roles", "角色权限"),
    ...(isSuperAdmin ? [linkItem("/system/students", "学生信息管理")] : []),
    linkItem("/system/audit", "审计日志"),
  ];

  const items: MenuProps["items"] = [
    {
      key: "/dashboard",
      icon: <DashboardOutlined />,
      label: <Link to="/dashboard">工作台</Link>,
    },
    {
      key: "admissions",
      icon: <BarChartOutlined />,
      label: "招生分析",
      children: admissionItems,
    },
    {
      key: "data",
      icon: <DatabaseOutlined />,
      label: "数据资产",
      children: dataItems,
    },
    {
      key: "ai",
      icon: <RobotOutlined />,
      label: "AI 决策",
      children: aiItems,
    },
    {
      key: "system",
      icon: <SettingOutlined />,
      label: "系统管理",
      children: systemItems,
    },
  ];

  return (
    <Layout.Sider
      width={232}
      collapsedWidth={64}
      breakpoint="lg"
      collapsed={collapsed}
      onCollapse={(value) => setCollapsed(value)}
      className="app-sidebar"
      theme="light"
    >
      <div className="app-brand">
        <span className="app-brand-text">
          <strong>招录智策</strong>
        </span>
      </div>
      <Menu
        theme="light"
        mode="inline"
        selectedKeys={[pathname]}
        openKeys={collapsed ? [] : openKeys}
        onOpenChange={(keys) => setOpenKeys(keys)}
        items={items}
        style={{ background: "transparent" }}
      />
    </Layout.Sider>
  );
}



