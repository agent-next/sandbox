// Flanged bushing, all dimensions mm.
// Spec: body OD 30 x 25 long, flange OD 50 x 5 thick at z=25,
//       bore OD 12 through, axis at (0,0) along z.
$fn = 128;

bore_d   = 12;
body_d   = 30;
flange_d = 50;
body_h   = 25;
flange_h = 5;
total_h  = body_h + flange_h;

difference() {
    union() {
        cylinder(h = body_h, d = body_d);
        translate([0, 0, body_h]) cylinder(h = flange_h, d = flange_d);
    }
    // bore through everything
    translate([0, 0, -1]) cylinder(h = total_h + 2, d = bore_d);
}
