// Adapter plate top view, for DXF export. Mirrors part.scad dimensions.
// Spec: outline 80 x 60, bore OD 20 at (40, 30),
//       6 bolt holes OD 6 on bolt circle R24 at 60 degree spacing.
// OpenSCAD's DXF export needs a projection() at the root.
$fn = 128;

plate_l = 80;
plate_w = 60;
plate_t = 8;
bore_d  = 20;
bolt_d  = 6;
bc_r    = 24;
n_bolts = 6;

module plate_3d() {
    difference() {
        cube([plate_l, plate_w, plate_t]);
        translate([plate_l / 2, plate_w / 2, -1])
            cylinder(h = plate_t + 2, d = bore_d);
        for (i = [0 : n_bolts - 1])
            translate([plate_l / 2 + bc_r * cos(i * 360 / n_bolts),
                       plate_w / 2 + bc_r * sin(i * 360 / n_bolts),
                       -1])
                cylinder(h = plate_t + 2, d = bolt_d);
    }
}

projection(cut = true) translate([0, 0, -plate_t / 2]) plate_3d();
