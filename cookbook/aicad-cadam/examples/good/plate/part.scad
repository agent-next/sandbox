// Adapter plate, all dimensions mm.
// Spec: plate 80 (x) x 60 (y) x 8 (thick), origin at a corner,
//       center bore OD 20 through at (40, 30),
//       6 bolt holes OD 6 through on bolt circle R24 about (40, 30),
//       at 0, 60, ... 300 degrees CCW from +x.
$fn = 128;

plate_l = 80;
plate_w = 60;
plate_t = 8;
bore_d  = 20;
bolt_d  = 6;
bc_r    = 24;
n_bolts = 6;

module bolt_holes() {
    for (i = [0 : n_bolts - 1])
        translate([plate_l / 2 + bc_r * cos(i * 360 / n_bolts),
                   plate_w / 2 + bc_r * sin(i * 360 / n_bolts),
                   -1])
            cylinder(h = plate_t + 2, d = bolt_d);
}

difference() {
    cube([plate_l, plate_w, plate_t]);
    translate([plate_l / 2, plate_w / 2, -1])
        cylinder(h = plate_t + 2, d = bore_d);
    bolt_holes();
}
