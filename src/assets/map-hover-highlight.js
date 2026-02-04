// assets/map-hover-glow.js
(function () {
  const GRAPH_ID = "map-graph";

  // base + glow styles (tweak to taste)
  const BASE_STYLE = { "line.width": 3, "opacity": 1.0 };
  const GLOW_STYLE = { "line.width": 10, "opacity": 0.6 };

  function findPlotlyNode(container) {
    if (!container) return null;
    if (typeof container.on === "function") return container;

    const jsPlot = container.querySelector(".js-plotly-plot");
    if (jsPlot && typeof jsPlot.on === "function") return jsPlot;

    // fallback: sometimes Plotly binds deeper
    const any = container.querySelectorAll && container.querySelectorAll("*");
    if (any) {
      for (let i = 0; i < any.length; i++) {
        if (typeof any[i].on === "function") return any[i];
      }
    }
    return null;
  }

  function attach(plotlyNode) {
    if (!plotlyNode || plotlyNode._glowClickAttached) return;
    plotlyNode._glowClickAttached = true;

    let hoveredTrace = null; // hover highlight (only when not locked)
    let lockedTrace = null;  // click-locked highlight

    function applyBase(traceIndex) {
      if (traceIndex === null || traceIndex === undefined) return;
      Plotly.restyle(plotlyNode, BASE_STYLE, [traceIndex]).catch(() => {});
    }

    function applyGlow(traceIndex) {
      if (traceIndex === null || traceIndex === undefined) return;
      Plotly.restyle(plotlyNode, GLOW_STYLE, [traceIndex]).catch(() => {});
    }

    function clearHoverIfNotLocked() {
      if (hoveredTrace !== null && hoveredTrace !== lockedTrace) {
        applyBase(hoveredTrace);
      }
      hoveredTrace = null;
    }

    // Hover glow (only if nothing is locked)
    plotlyNode.on("plotly_hover", function (ev) {
      if (lockedTrace !== null) return; // lock overrides hover
      if (!ev || !ev.points || !ev.points.length) return;

      const traceIndex = ev.points[0].curveNumber;
      if (traceIndex === hoveredTrace) return;

      // reset previous hover
      clearHoverIfNotLocked();

      applyGlow(traceIndex);
      hoveredTrace = traceIndex;
    });

    plotlyNode.on("plotly_unhover", function () {
      if (lockedTrace !== null) return;
      clearHoverIfNotLocked();
    });

    // Click to lock glow
    plotlyNode.on("plotly_click", function (ev) {
      if (!ev || !ev.points || !ev.points.length) return;

      const traceIndex = ev.points[0].curveNumber;
      console.log("[map] clicked trace:", traceIndex);

      // If clicking the already-locked trace -> unlock (toggle off)
      if (lockedTrace === traceIndex) {
        applyBase(lockedTrace);
        lockedTrace = null;
        return;
      }

      // Switching lock to a different trace:
      // reset old locked trace
      if (lockedTrace !== null) {
        applyBase(lockedTrace);
      }

      // also clear any hover highlight (since lock will take over)
      if (hoveredTrace !== null && hoveredTrace !== traceIndex) {
        applyBase(hoveredTrace);
      }
      hoveredTrace = null;

      // apply lock
      lockedTrace = traceIndex;
      applyGlow(lockedTrace);
    });

    // Click anywhere off-trace clears the lock
    // plotly_click fires only on trace hits, so use plotly_clickannotation? no.
    // Instead, listen for regular DOM clicks and clear if target isn't a point.
    document.addEventListener("click", function (e) {
      if (lockedTrace === null) return;

      const container = document.getElementById(GRAPH_ID);
      if (!container) return;

      // If click happened inside the graph, but not on a trace, clear.
      // Plotly sets a flag on plotlyNode when click hits a point? Not reliably.
      // We'll approximate: if click is inside graph AND NOT on svg path/point layers, clear.
      const clickedInside = container.contains(e.target);
      if (!clickedInside) return;

      // If the click target is within Plotly hover/click layers, we assume plotly_click handled it.
      const cls = (e.target && e.target.classList) ? Array.from(e.target.classList) : [];
      const isPlotlyPointish =
        cls.includes("point") || cls.includes("points") || cls.includes("scatterlayer") ||
        cls.includes("traces") || cls.includes("trace") || cls.includes("cursor") ||
        (e.target && e.target.tagName && ["PATH", "CIRCLE"].includes(e.target.tagName));

      if (!isPlotlyPointish) {
        applyBase(lockedTrace);
        lockedTrace = null;
      }
    }, true);
  }

  function tryAttach() {
    const container = document.getElementById(GRAPH_ID);
    const node = findPlotlyNode(container);
    if (node) {
      attach(node);
      return true;
    }
    return false;
  }

  function waitAndAttach() {
    const start = Date.now();
    const poll = setInterval(() => {
      if (tryAttach() || Date.now() - start > 8000) clearInterval(poll);
    }, 250);
  }

  document.addEventListener("plotly_afterplot", tryAttach);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", waitAndAttach);
  } else {
    waitAndAttach();
  }
})();
