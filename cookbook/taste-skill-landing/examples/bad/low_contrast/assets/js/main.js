/* Kestrel: the live thing (wind math) + section entrances.
   Transform/opacity only; every move has a reduced-motion fallback (CSS). */
(function () {
  "use strict";

  var form = document.getElementById("wind-form");
  var out = document.getElementById("wind-result");
  var STATIONARY_MINUTES = 100; // 40 km at 24 km/h, still air

  // Same loop, two ways round. The long leg carries the wind one way only.
  function windMinutes(speed, dir) {
    // Tailwind fractions per leg, by compass origin of the wind.
    // Loop: 16 km crosswind legs, 12 km into/out-of the wind, 12 km diagonal.
    var leg1 = { E: 0.0, NE: 0.5, N: 0.87, SE: -0.5, S: -0.87, SW: -0.5, W: 0.0, NW: 0.5 };
    var leg2 = { E: 1.0, NE: 0.5, N: 0.0, SE: 0.5, S: 0.0, SW: -0.5, W: -1.0, NW: -0.5 };
    var leg3 = { E: 0.0, NE: -0.5, N: -0.87, SE: 0.5, S: 0.87, SW: 0.5, W: 0.0, NW: -0.5 };
    var legs = [[16, leg1[dir]], [12, leg2[dir]], [12, leg3[dir]]];
    var best = 0, worst = 0, rider = 24;
    for (var i = 0; i < 2; i++) { // two ways round
      var t = 0;
      for (var j = 0; j < legs.length; j++) {
        var leg = legs[(j + i) % legs.length];
        var ground = rider + (i === 0 ? 1 : -1) * leg[1] * speed;
        if (ground < 6) { ground = 6; }
        t += leg[0] / ground * 60;
      }
      if (i === 0) { best = t; } else { worst = t; }
    }
    var diff = worst - best;
    return { best: t0(best), diff: diff };
  }

  function t0(m) { return m; }

  function fmt(m) { return Math.round(m); }

  function render() {
    if (!form || !out) { return; }
    var speed = parseInt(form["wind-speed"].value, 10);
    var dir = form["wind-dir"].value;
    if (!speed && speed !== 0 || !dir) { return; }
    var r = windMinutes(speed, dir);
    out.textContent = "At " + speed + " km/h from the " + dirName(dir) +
      ", the 40 km loop flips to " + fmt(r.best) + " minutes one way round, " +
      fmt(r.best + r.diff) + " the other — the wind saves you " + fmt(r.diff) +
      " minutes if you ride it the right way.";
  }

  function dirName(d) {
    return { E: "east", NE: "north-east", N: "north", SE: "south-east",
             S: "south", SW: "south-west", W: "west", NW: "north-west" }[d];
  }

  if (form) {
    form.addEventListener("input", render);
    render();
  }

  // Entrances: heading, then text, then picture, staggered 60–90 ms.
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add("revealed");
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.16 });
    document.querySelectorAll("section, footer").forEach(function (s) {
      var kids = s.querySelectorAll(":scope > * > *");
      // tag the first three content elements of each section for stagger
      var count = 0;
      kids.forEach(function (k) {
        if (count < 3 && k.tagName) {
          k.classList.add("reveal");
          k.classList.add("d" + count);
          io.observe(k);
          count++;
        }
      });
    });
  }
})();
