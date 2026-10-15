# Model provenance

`go1_meshless.xml` derives from the Unitree Go1 in
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/d7b481bac63d3d600ab404ee74f7474c5efe8a67/unitree_go1),
commit `d7b481bac63d3d600ab404ee74f7474c5efe8a67`.
The directory's licence is **BSD 3-Clause**, retained verbatim in `LICENSE`.

This demo removes visual meshes and cameras, retains the primitive
geometry and explicit inertias, permits floor contact only at the four
foot spheres, and sets a crouched home pose at 0.27 m. Those contact
and home-pose changes are intentional simplifications, not a claim
that all upstream dynamics remain unchanged. Position actuators retain
the upstream gains, joint ranges and torque limits.

Rendering adds only materials, textures and lights to a copy. It verifies
that body inertias, geometry, contact parameters and actuators are unchanged.
