"""Granular column collapse onto a rigid peg (Genesis, CPU backend).

A box of MPM elasto-plastic particles (sand modelled with a von Mises yield
surface) is held at rest in *zero* gravity, then gravity is switched on at
t = 0. The column free-falls onto a rigid box standing on the floor,
collapses around it and settles into a heap. The judge builds the scene
from this spec, runs it twice for a determinism check, and grades the
simulator state (no pixels).

The scene constants below are the known-good reference. Everything the
judge knows about the intended physics comes from this dict.
"""

SCENARIO = {
    # physics
    "gravity": -9.81,          # m/s^2, switched on at t = 0 (down is -z)
    "dt": 1e-3,                # s per scene.step() frame (4 substeps -> 2.5e-4 substep dt)
    "substeps": 4,
    "steps": 1200,             # frames; total simulated time 1.2 s
    "seed": 42,

    # MPM discretisation
    "particle_size": 0.0125,   # m
    "grid_density": 48,
    "domain_lower": [-0.4, -0.4, -0.05],
    "domain_upper": [1.2, 1.2, 1.1],

    # column of sand: bottom face centred at column_pos, sizes in m
    "column_size": [0.12, 0.12, 0.20],
    "column_pos": [0.40, 0.40, 0.51],

    # sand material (von Mises elasto-plastic)
    "E": 1.0e5,                # Young's modulus, Pa
    "nu": 0.25,                # Poisson ratio
    "rho": 1200.0,             # density, kg/m^3
    "yield_stress": 2.0e3,     # von Mises yield stress, Pa

    # rigid peg on the floor
    "obstacle_size": [0.16, 0.16, 0.12],
    "obstacle_pos": [0.40, 0.40, 0.06],
    "friction": 0.5,
}
