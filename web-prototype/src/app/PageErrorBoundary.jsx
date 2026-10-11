import { Component } from "react";
import { WarningCircle } from "@phosphor-icons/react";
import { EmptyState } from "../components/SharedUi";

/** @extends {Component<{children: import("react").ReactNode}, {failed: boolean, resourceFailed: boolean}>} */
export class PageErrorBoundary extends Component {
  state = { failed: false, resourceFailed: false };

  // React 的错误边界需通过类组件承接渲染及懒加载异常。
  /** @param {unknown} error */
  static getDerivedStateFromError(error) {
    const message = error instanceof Error ? error.message : "";
    return {
      failed: true,
      resourceFailed:
        /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(
          message,
        ),
    };
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <div className="standard-page" role="alert">
        <EmptyState
          icon={WarningCircle}
          title={this.state.resourceFailed ? "页面资源加载失败" : "页面加载失败"}
          description={
            this.state.resourceFailed
              ? "请检查网络，或刷新获取最新页面。"
              : "请刷新页面后重试。"
          }
          action={
            <button
              type="button"
              className="primary-button"
              onClick={() => window.location.reload()}
            >
              刷新页面
            </button>
          }
        />
      </div>
    );
  }
}
