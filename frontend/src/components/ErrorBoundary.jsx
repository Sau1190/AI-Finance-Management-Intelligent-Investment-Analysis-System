import { Component } from "react";
import { CRASH_MESSAGE, CRASH_TITLE, crashLogLine } from "../lib/crash.js";

// Stops one broken page from blanking the whole dashboard. Shows a fixed,
// generic message (never the error text) and a retry button.
export default class ErrorBoundary extends Component {
  state = { crashed: false };

  static getDerivedStateFromError() {
    return { crashed: true };
  }

  componentDidCatch(error) {
    console.error(crashLogLine(error)); // type only, never the message or stack
  }

  render() {
    if (!this.state.crashed) return this.props.children;
    return (
      <div className="state error" role="alert" data-state="crash" data-testid="crash-box">
        <strong>{CRASH_TITLE}.</strong> {CRASH_MESSAGE}
        <button type="button" className="btn small" onClick={() => this.setState({ crashed: false })}>Try again</button>
      </div>
    );
  }
}
