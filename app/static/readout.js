/* Chart value readout.
 *
 * A monitoring console where you cannot read a month's value off a line is a
 * picture of a console. This attaches a crosshair and a value panel to every
 * chart that shipped one, using only the sample geometry already serialised
 * into `data-readout` by app/charts.py. No library, no network, no layout
 * thrash: the SVG is untouched except for one line's x coordinate.
 *
 * Progressive enhancement is the whole design. If this file never loads the
 * charts are exactly what they were: static, labelled, readable SVG.
 */
(function () {
  "use strict";

  var charts = document.querySelectorAll(".chart[data-readout]");
  if (!charts.length) return;

  function fmt(value, places) {
    return value.toLocaleString(undefined, {
      minimumFractionDigits: places,
      maximumFractionDigits: places,
    });
  }

  function attach(root) {
    var data;
    try {
      data = JSON.parse(root.getAttribute("data-readout"));
    } catch (err) {
      return; // Malformed payload: leave the static chart alone.
    }
    if (!data.x || data.x.length < 2) return;

    var svg = root.querySelector("svg");
    var group = root.querySelector(".ro");
    var line = root.querySelector(".ro-x");
    var hit = root.querySelector(".ro-hit");
    var panel = root.querySelector(".ro-panel");
    if (!svg || !group || !line || !hit || !panel) return;

    // Marker dots, one per series, created once.
    var dots = data.series.map(function (s) {
      var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("r", "4");
      c.setAttribute("fill", s.color);
      c.setAttribute("stroke", "var(--bg)");
      c.setAttribute("stroke-width", "1.5");
      group.appendChild(c);
      return c;
    });

    var index = -1;

    function show(i) {
      if (i === index || i < 0 || i >= data.x.length) return;
      index = i;
      var x = data.x[i];
      line.setAttribute("x1", x);
      line.setAttribute("x2", x);
      var rows = "";
      data.series.forEach(function (s, k) {
        var y = s.y[i];
        if (y === undefined || y === null) {
          dots[k].setAttribute("display", "none");
          return;
        }
        dots[k].removeAttribute("display");
        dots[k].setAttribute("cx", x);
        dots[k].setAttribute("cy", y);
        rows +=
          '<span><i style="background:' + s.color + '"></i>' +
          '<b>' + fmt(s.v[i], data.yp) + "</b>" + s.name + "</span>";
      });
      group.style.display = "";
      panel.innerHTML =
        '<span class="ro-at">' + fmt(data.xv[i], data.xp) + "</span>" + rows;
      panel.hidden = false;
      // Announced once per move, politely, so a screen reader user gets the
      // same information a sighted user gets from the crosshair.
      root.setAttribute(
        "aria-describedby",
        panel.id || (panel.id = "ro-" + Math.abs(data.x[0] * 1000 | 0) + "-" + data.x.length)
      );
    }

    function hide() {
      index = -1;
      group.style.display = "none";
      panel.hidden = true;
    }

    function nearest(clientX) {
      var box = svg.getBoundingClientRect();
      // The SVG scales; map the pointer back into viewBox units.
      var vb = svg.viewBox.baseVal;
      var local = ((clientX - box.left) / box.width) * (vb.width || box.width);
      var best = 0;
      var bestDist = Infinity;
      for (var i = 0; i < data.x.length; i++) {
        var d = Math.abs(data.x[i] - local);
        if (d < bestDist) {
          bestDist = d;
          best = i;
        }
      }
      return best;
    }

    hit.addEventListener("pointermove", function (e) {
      show(nearest(e.clientX));
    });
    hit.addEventListener("pointerleave", hide);
    root.addEventListener("blur", hide);
    root.addEventListener("focus", function () {
      show(index < 0 ? data.x.length - 1 : index);
    });
    root.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        var start = index < 0 ? data.x.length - 1 : index;
        show(Math.min(data.x.length - 1, Math.max(0, start + (e.key === "ArrowRight" ? 1 : -1))));
      } else if (e.key === "Home") {
        e.preventDefault();
        show(0);
      } else if (e.key === "End") {
        e.preventDefault();
        show(data.x.length - 1);
      } else if (e.key === "Escape") {
        hide();
      }
    });

    root.classList.add("has-readout");
  }

  Array.prototype.forEach.call(charts, attach);
})();
