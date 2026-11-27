import { Component, type ReactNode } from "react";
import { reportError } from "./report";

/** One pane's own error boundary: it breaks alone and tells the server. */
export class Boundary extends Component<
  { pane: string; fallback: ReactNode; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    reportError(error, this.props.pane);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
