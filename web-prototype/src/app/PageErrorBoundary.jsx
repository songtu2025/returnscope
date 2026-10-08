import { Component } from "react";
import { WarningCircle } from "@phosphor-icons/react";
import { EmptyState } from "../components/SharedUi";

/** @extends {Component<{children: import("react").ReactNode}, {failed: boolean}>} */
export class PageErrorBoundary extends Component {
  state = { failed: false };

  // React 的错误边界需通过类组件承接渲染及懒加载异常。
  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <div className="standard-page" role="alert">
        <EmptyState
          icon={WarningCircle}
          title="页面加载失败"
          description="请刷新页面后重试。"
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
