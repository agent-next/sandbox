// L-bracket, all dimensions mm.
// Spec: base 60 (x) x 40 (y) x 6, upright x in [54, 60] rising to z=46,
//       R6 concave fillet along the inner edge at (x=54, z=6),
//       R4 convex fillet along the outer top edge at (x=60, z=46),
//       both full depth (y = 40).
$fn = 128;

base_l    = 60;
base_w    = 40;
base_t    = 6;
upright_t = 6;
upright_h = 40;   // above the base: z from 6 to 46
fillet_r  = 6;
edge_r    = 4;

module concave_fillet() {
    // fills the inner corner between the base top (z=6) and the upright
    // left face (x=54): square [48..54] x [6..12] minus a quarter cylinder
    // of R6 centred on (x=48, z=12), extruded the full depth.
    translate([base_l - upright_t - fillet_r, 0, base_t + fillet_r])
        difference() {
            translate([0, 0, -fillet_r])
                cube([fillet_r, base_w, fillet_r]);
            rotate([-90, 0, 0]) cylinder(h = base_w, r = fillet_r);
        }
}

module convex_fillet_cut() {
    // rounds the outer corner at (x=60, z=46): removes square
    // [56..60] x [42..46] minus a quarter cylinder of R4 centred (56, 42).
    translate([base_l - edge_r, 0, base_t + upright_h - edge_r])
        difference() {
            cube([edge_r, base_w, edge_r]);
            rotate([-90, 0, 0]) cylinder(h = base_w, r = edge_r);
        }
}

difference() {
    union() {
        cube([base_l, base_w, base_t]);
        translate([base_l - upright_t, 0, base_t])
            cube([upright_t, base_w, upright_h]);
        concave_fillet();
    }
    convex_fillet_cut();
}
