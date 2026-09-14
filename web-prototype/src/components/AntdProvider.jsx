import ConfigProvider from "antd/es/config-provider";
import zhCN from "antd/es/locale/zh_CN";

const antdTheme = {
  token: {
    colorPrimary: "#12765b",
    colorInfo: "#12765b",
    colorText: "#20332c",
    colorTextSecondary: "#66736e",
    colorBorder: "#d7e0db",
    colorBgContainer: "#ffffff",
    borderRadius: 8,
    controlHeight: 36,
    controlHeightSM: 32,
    fontFamily:
      'Inter, "Noto Sans SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif',
  },
};

export function AntdProvider({ children }) {
  return (
    <ConfigProvider button={{ autoInsertSpace: false }} locale={zhCN} theme={antdTheme}>
      {children}
    </ConfigProvider>
  );
}
