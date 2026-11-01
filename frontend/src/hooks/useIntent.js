import { useEffect, useRef } from "react";
import { useApp } from "../context.js";

// Lets a suggested action (composer chip / overview card) start a workflow on the page it opens.
// The start is deferred one tick so the page's own "load the latest saved result" call goes
// first and the workflow's call is the newest one — also under React StrictMode's double effects.
// `claimIntent` hands the request out exactly once.
export function useIntent(key, fn) {
  const { intentNonce, claimIntent } = useApp();
  const latest = useRef(fn);
  latest.current = fn;
  useEffect(() => {
    if (!intentNonce) return undefined;
    const t = setTimeout(() => { if (claimIntent(key)) latest.current(); }, 0);
    return () => clearTimeout(t);
  }, [intentNonce, claimIntent, key]);
}
