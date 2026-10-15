/* Kestrel: the live thing (wind math) + section entrances.
   Transform/opacity only; every move has a reduced-motion fallback (CSS). */
(function () {
  "use strict";

  var form = document.getElementById("wind-form");
  var out = document.getElementById("wind-result");

  // The wind model, stated plainly:
  //   - the rider's still-air cruise speed is 24 km/h;
  //   - the loop is 40 km: 16 km across the wind, 12 km straight into or
  //     with it, 12 km diagonal;
  //   - a tailwind adds up to half its speed to the rider (drafting,
  //     bearing, rolling resistance all eat the rest); a headwind takes
  //     its full speed off the rider's air speed (air drag is quadratic,
  //     so a headwind hurts more than a tailwind helps);
  //   - alignment in [-1, 1] is the cosine between the rider's heading
  //     and the direction the wind blows TO (tailwind positive);
  //   - ground speed = still-air speed + (alignment >= 0 ? 0.5 : 1.0)
  //     * alignment * wind speed, floored at 8 km/h so the rider always
  //     makes progress;
  //   - riding the same loop the other way round flips every alignment's
  //     sign but leaves the still-air time of 100 minutes unchanged.
  // Time per leg = distance / ground speed, in minutes. The saving is
  // slow-direction minus fast-direction, so it is never negative and
  // never exceeds the still-air time.
  function windMinutes(speed, dir) {
    // Alignment per leg for the anticlockwise direction, by compass
    // origin of the wind (E wind blows TO the west, and so on). For the
    // opposite origin each sign flips, so opposite winds mirror each other.
    var leg1 = { E: 0.0, NE: 0.5, N: 0.87, NW: 0.5, W: 0.0, SW: -0.5, S: -0.87, SE: -0.5 };
    var leg2 = { E: 1.0, NE: 0.5, N: 0.0, NW: -0.5, W: -1.0, SW: -0.5, S: 0.0, SE: 0.5 };
    var leg3 = { E: 0.0, NE: -0.5, N: -0.87, NW: -0.5, W: 0.0, SW: 0.5, S: 0.87, SE: 0.5 };
    var legs = [[16, leg1[dir]], [12, leg2[dir]], [12, leg3[dir]]];
    var rider = 24;
    var times = [0, 0];
    for (var way = 0; way < 2; way++) { // the same legs, both ways round
      var sign = way === 0 ? 1 : -1;
      for (var j = 0; j < legs.length; j++) {
        var a = sign * legs[j][1];
        var effect = a >= 0 ? 0.5 * a : a; // tailwind helps half, headwind costs full
        var ground = rider + effect * speed;
        if (ground < 8) { ground = 8; }
        times[way] += legs[j][0] / ground * 60;
      }
    }
    var best = Math.min(times[0], times[1]);
    var worst = Math.max(times[0], times[1]);
    return { best: best, diff: worst - best };
  }

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
