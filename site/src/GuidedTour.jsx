import React, { useEffect, useRef, useState } from "react";
import { BASE } from "./data.js";
import {
  DEFAULT_TOUR,
  shouldOfferTour,
  recordTour,
  restoreTourView,
} from "./tourLogic.js";

const storage = () => {
  try {
    return localStorage;
  } catch {
    return null;
  }
};
export default function GuidedTour({ manifest, state, update, request = 0 }) {
  const [step, setStep] = useState(null),
    [highlight, setHighlight] = useState(false);
  const original = useRef(null),
    panel = useRef(null),
    offered = useRef(false),
    lastRequest = useRef(0),
    latest = useRef(state);
  latest.current = state;
  const steps = manifest?.atlas?.tour?.steps || DEFAULT_TOUR;
  const start = () => {
    original.current = { tab: latest.current.tab, tool: latest.current.tool };
    setStep(0);
    recordTour(storage(), BASE, "offered");
  };
  useEffect(() => {
    if (!manifest || offered.current) return;
    offered.current = true;
    if (shouldOfferTour(storage(), BASE)) start();
  }, [manifest]);
  useEffect(() => {
    if (request && request !== lastRequest.current) {
      lastRequest.current = request;
      start();
    }
  }, [request]);
  const finish = (status) => {
    recordTour(storage(), BASE, status);
    setStep(null);
    if (original.current) update(restoreTourView(original.current));
    requestAnimationFrame(() =>
      document.querySelector("[data-tour-replay]")?.focus(),
    );
  };
  useEffect(() => {
    if (step === null) return;
    const item = steps[step];
    if (item.tab) update({ tab: item.tab, tool: item.tool });
    let target = null,
      observer;
    const apply = () => {
      const found = document.querySelector(item.target);
      if (found === target) return;
      target?.removeAttribute("data-tour-highlight");
      target = found;
      setHighlight(!!target);
      if (target) {
        target.setAttribute("data-tour-highlight", "true");
        const r = target.getBoundingClientRect(),
          bottom = innerHeight - (panel.current?.offsetHeight || 280) - 24;
        if (step > 0 && (r.top < 28 || r.bottom > bottom)) {
          target.scrollIntoView({ block: "start", behavior: "instant" });
          window.scrollBy(0, -28);
        }
      }
    };
    apply();
    observer = new MutationObserver(apply);
    observer.observe(document.getElementById("main") || document.body, {
      childList: true,
      subtree: true,
    });
    panel.current?.focus({ preventScroll: true });
    return () => {
      observer.disconnect();
      target?.removeAttribute("data-tour-highlight");
    };
  }, [step]);
  if (step === null) return null;
  const item = steps[step];
  return (
    <aside
      className="guided-tour"
      role="dialog"
      aria-modal="false"
      aria-labelledby="tour-title"
      aria-describedby="tour-copy"
      tabIndex="-1"
      ref={panel}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          finish("skipped");
        }
      }}
    >
      <div className="tour-top">
        <span>
          Quick guide · {step + 1} of {steps.length}
        </span>
        <button
          onClick={() => finish("skipped")}
          aria-label="Close guided tour"
        >
          Skip guide
        </button>
      </div>
      <h2 id="tour-title">{item.title}</h2>
      <p id="tour-copy">{item.text}</p>
      {!highlight && step > 0 && (
        <p className="fine" role="status">
          The workspace is loading. You can continue or explore the controls.
        </p>
      )}
      <p className="fine">
        You can use the page while this guide is open. Replay it with “Guide”.
      </p>
      <div className="tour-actions">
        <button disabled={step === 0} onClick={() => setStep((i) => i - 1)}>
          Back
        </button>
        <button
          onClick={() =>
            step === steps.length - 1
              ? finish("completed")
              : setStep((i) => i + 1)
          }
        >
          {step === steps.length - 1 ? "Finish guide" : "Next"}
        </button>
        {step === steps.length - 1 && (
          <button
            onClick={() => {
              recordTour(storage(), BASE, "completed");
              setStep(null);
              update({ tab: "graph", tool: "fulltext" });
            }}
          >
            Open download checklist
          </button>
        )}
      </div>
    </aside>
  );
}
