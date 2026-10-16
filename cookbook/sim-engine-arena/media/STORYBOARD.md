# sim-engine-arena demo storyboard

The video is real MuJoCo offscreen footage of the trajectories the judge
graded, composed in Remotion. There is no slide, no plot still and no
Ken-Burns: every frame before the end card is a moving 3D render with a
HUD on top.

Renderer: `remotion` 4.0.531 + `@remotion/cli` 4.0.531 (npm, published
2026-09-30, 15 days before the 2026-10-15 cut). Headless, Node >= 22.
ffmpeg only encodes the clips (`media/clips/*.mp4`, recorded by
`media/clips.py`) and the final web master; it never builds a frame.

Canvas: 1920x1080, 30 fps. 29.5 s of moving footage + a 2.5 s static end
card = 32.0 s total (960 frames).

Composition source: `media/video/src/`. `make_media.sh` copies the run's
clips and `clips/numbers.json` into `media/video/public/`, renders the
composition to a lossless PNG sequence, then encodes.

Every number below comes from this run's `media/data/grade.json`
(produced by `media/collect.py`, seed 0), `media/data/selftest.txt`, or
the RECEIPT.md "Fresh-sandbox run 2" block, and reaches the video only
through `clips/numbers.json`.

| slot | time | what fills the frame | source | caption / HUD |
|---|---|---|---|---|
| hook | 0-2 s | the finished result, moving: the graded pendulum at real time, camera orbiting 60->105 deg, bob and rod clearly in motion | `clips/01_hook.mp4` (graded samples of `traj_pendulum.csv`, sim 0-2 s, 1.00x) | kinetic headline "GRADED MOTION, RE-RENDERED"; HUD "SCENES PASS / oracle gates 4/4 / self-test kills 8/8 / judge intact yes" |
| input -> output | 2-12 s | four beats, 2.5 s each, hard cuts, one camera orbit per scene: drop, 35 deg slide, 20 deg stick, pendulum. Each cut restarts the new scene's orbit at its first graded sample | `clips/02_drop.mp4` (1.67x slow), `clips/03_slide.mp4` (2.50x slow), `clips/04_stick.mp4` (2.50x slow), `clips/05_pendulum.mp4` (1.00x) | scene title + the spec sentence as `input:`, the measured value counting up, `oracle <x> <err>% PASS`, and the clip's own slow-motion factor |
| escalate | 12-17 s | 2x2 grid of all four scenes playing at once, each tile orbiting independently inside its own tile; motion in every tile | `clips/06_quad.mp4` (6.00x slow, four tiles) | "4 SCENES - 1 SPEC - SEED 0"; each tile keeps its scene label; "13,504 graded samples replayed" |
| escalate: the agent run | 17-21 s | the recorded fresh-sandbox run, replayed 17.2x: create/clone/setup/selftest/grade/kill rows land at the frames their real cumulative seconds map to, over the graded pendulum still playing at 1x | `clips/05_pendulum.mp4` footage + `RECEIPT.md` run 2 (69 s -> 4 s) | "THE AGENT RUN, 17.2x", one row per stage with its real seconds, "RUN CLOCK 69 s", progress bar |
| escalate: close-ups | 21-23 s | hard cut between two half-length close-ups: the 0.8 m sliding box tracked by its own graded x, then a push-in on the pendulum bob | `clips/08_closeup.mp4` (0.67x: 2 s on screen covers 3 s of graded sim) | "camera tracks the graded state - 0.8 m slide" |
| proof | 23-29.5 s | the PASS badge and the four gate rows sliding in one by one over the still-playing pendulum orbit; the kill rate lands last | `clips/09_proof.mp4` (1.00x) + overlays from `data/grade.json`, `data/selftest.txt` | PASS badge; "ALL GATES / seed 0 / judge intact"; one row per scene with its value, oracle and the judge's own error; "self-test mutants killed 8/8 = 100 %" |
| end card | 29.5-32 s | static card, no motion, no footage | Remotion only | `python3 run.py` |

Numbers on screen (all from `data/grade.json`, seed 0, and the RECEIPT's
own printed error percentages):

- drop: `t_contact 0.4406 s (+0.11 %)` vs oracle 0.4401 s
- incline_slide: `a 1.6082 m/s2 (+0.04 %)` vs oracle 1.6088 m/s2
- incline_stick: `travel 1.8 mm` vs oracle: none, threshold < 20 mm
- pendulum: `T 2.0073 s (+0.00 %)` vs oracle 2.0073 s
- self-test kill rate `8/8 = 100 %` (`data/selftest.txt`)
- agent run: `69 s` of real sandbox work in 4 s of screen time = 17.2x

Speed labels: the drop (1.67x) and the inclines (2.50x) and the quad grid
(6.00x per tile) are played back slower than their graded simulation so
contact and the 0.8 m slide stay legible; each such beat is stamped with
its factor. The pendulum and the close-up slot's second half are real
time; the close-up slot as a whole covers 3 s of graded sim in 2 s
(0.67x) and is stamped. The agent-run slot compresses a recorded 69 s
timeline into 4 s and is stamped `17.2x`.

Caption sizes: every on-screen size is >= 60 px, i.e. >= 43.8 px of
DejaVu capital height at 1080 (4.1 % of frame height, above the 4 %
standard). Scene titles 76 px, HUD values 92 px, the headline 128 px, the
PASS badge 80-114 px, the end card 150 px.

Judge: `cookbook/sim-engine-arena/media/REVIEW.md` and `REVIEW.json`
record the two blind panel verdicts for this cut.
