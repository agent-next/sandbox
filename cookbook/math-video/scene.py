"""Why the quadratic formula is true, told as a picture.

x² + bx is a square of side x with two rectangles of b/2 by x; one small corner,
(b/2)², is missing. Fill the corner on both sides and the left side closes into
(x + b/2)² — a square root and a subtraction later, the quadratic formula stands.
The same picture solves a x² + b x + c = 0, and the film ends by checking
x² + 6x + 5 = 0 on its parabola. Each quantity keeps its colour from the picture
into the algebra: x² blue, bx teal, the corner yellow.

Narrated with an ElevenLabs voice through fal (`FAL_KEY` in the environment).
Without the key the film renders silent with the same subtitles and pacing.
"""

import os

import numpy as np

import manimgx as m

EQ = np.array([3.35, 1.7, 0.0])  # the equations' anchor while the picture shows
TOP = np.array([1.6, 2.75, 0.0])  # the worked example's anchor, above the axes
SIZE = 48  # the equations' font size

X2, BX, CORNER = m.BLUE, m.TEAL, m.YELLOW  # the colours of the quantities
COLORS = {"x2": X2, "bx": BX, "b6": BX, "sq": CORNER, "sq2": CORNER}

X, H = 2.4, 1.0  # the picture's side x and width b/2, in scene units
P0 = np.array([-5.9, -3.05, 0.0])  # the big square's lower-left corner

Terms = list[tuple[str, str]]  # (key, LaTeX): a key names a term across steps

E0: Terms = [("x2", "x^2"), ("p1", "+"), ("bx", "b\\,x"),
             ("eq", "="), ("c", "c")]  # fmt: skip
E1: Terms = [("x2", "x^2"), ("p1", "+"), ("bx", "b\\,x"), ("p3", "+"),
             ("sq", r"( \frac{b}{2} )^2"), ("eq", "="), ("c", "c"),
             ("p4", "+"), ("sq2", r"( \frac{b}{2} )^2")]  # fmt: skip
E2: Terms = [("lhs", r"( x + \frac{b}{2} )^2"), ("eq", "="), ("c", "c"),
             ("p4", "+"), ("sq2", r"( \frac{b}{2} )^2")]  # fmt: skip
E3: Terms = [("lhs", r"x + \frac{b}{2}"), ("eq", "="),
             ("rhs", r"\pm \sqrt{c + ( \frac{b}{2} )^2}")]  # fmt: skip
E4: Terms = [("x", "x"), ("eq", "="),
             ("rhs", r"-\frac{b}{2} \pm \sqrt{c + ( \frac{b}{2} )^2}")]  # fmt: skip

G0: Terms = [("ax2", "a x^2"), ("p1", "+"), ("bx", "b x"), ("p2", "+"),
             ("c", "c"), ("eq", "="), ("z", "0")]  # fmt: skip
G1: Terms = [("x2", "x^2"), ("p1", "+"), ("bx", r"\frac{b}{a} x"),
             ("p2", "+"), ("c", r"\frac{c}{a}"), ("eq", "="), ("z", "0")]  # fmt: skip
G2: Terms = [("x2", "x^2"), ("p1", "+"), ("bx", r"\frac{b}{a} x"),
             ("eq", "="), ("c", r"-\frac{c}{a}")]  # fmt: skip
G3: Terms = [("lhs", r"( x + \frac{b}{2a} )^2"), ("eq", "="),
             ("rhs", r"( \frac{b}{2a} )^2 - \frac{c}{a}")]  # fmt: skip
G4: Terms = [("lhs", r"( x + \frac{b}{2a} )^2"), ("eq", "="),
             ("rhs", r"\frac{b^2 - 4ac}{4a^2}")]  # fmt: skip
# a space before the frac's closing brace: "\sqrt{…}}" would read as the end of
# the "{{ … }}" group and leave the frac without a denominator
G5: Terms = [("lhs", r"x + \frac{b}{2a}"), ("eq", "="),
             ("rhs", r"\pm \frac{\sqrt{b^2 - 4ac} }{2a}")]  # fmt: skip
G6: Terms = [("x", "x"), ("eq", "="),
             ("sol", r"\frac{-b \pm \sqrt{b^2 - 4ac} }{2a}")]  # fmt: skip

W0: Terms = [("x2", "x^2"), ("p1", "+"), ("b6", "6x"), ("p2", "+"),
             ("c5", "5"), ("eq", "="), ("z", "0")]  # fmt: skip
W1: Terms = [("x", "x"), ("eq", "="),
             ("sol", r"\frac{-6 \pm \sqrt{36 - 20} }{2}")]  # fmt: skip
W2: Terms = [("x", "x"), ("eq", "="), ("sol", r"\frac{-6 \pm 4}{2}")]  # fmt: skip
W3: Terms = [("r1", "x = -1"), ("or", r"\quad \text{or} \quad"),
             ("r2", "x = -5")]  # fmt: skip


class Equation(m.MathTex):
    """An equation whose terms are named, so a step can say which becomes which."""

    def __init__(self, terms: Terms, font_size: float = SIZE) -> None:
        super().__init__(
            " ".join("{{ " + tex + " }}" for _, tex in terms), font_size=font_size
        )
        assert len(self.submobjects) == len(terms)
        self.parts = {
            key: part for (key, _), part in zip(terms, self.submobjects, strict=True)
        }
        for key, color in COLORS.items():
            if key in self.parts:
                self.parts[key].set_color(color)


def box(x0: float, y0: float, w: float, h: float, color: m.ManimColor) -> m.Rectangle:
    rect = m.Rectangle(
        width=w, height=h, fill_color=color, fill_opacity=0.7,
        stroke_color=m.WHITE, stroke_width=2.5,
    )  # fmt: skip
    return rect.move_to([x0 + w / 2, y0 + h / 2, 0])


def _silent(text: str) -> m.Speech:
    """A voice that says nothing: paced silence, with the line's words timed, so
    the film keeps its rhythm and writes the same subtitles without FAL_KEY."""
    tokens = text.split()
    rate = 44_100
    lead, per_word, tail = 0.35, 0.42, 0.30
    samples = np.zeros(int(rate * (lead + per_word * len(tokens) + tail)), np.float32)
    words = tuple(
        m.voices.Word(word, lead + i * per_word, lead + (i + 0.8) * per_word)
        for i, word in enumerate(tokens)
    )
    return m.Speech(samples, text=text, words=words, rate=rate)


_ELEVEN = m.voices.Fal(
    "fal-ai/elevenlabs/tts/eleven-v3", voice="Rachel", stability=0.6
)


def _narrate(text: str) -> m.Speech:
    """The film's voice: fal's ElevenLabs when FAL_KEY is set, silence else."""
    return _ELEVEN(text) if os.environ.get("FAL_KEY") else _silent(text)


class CompletingTheSquare(m.Scene):
    voice = _narrate

    def morph(
        self,
        before: Equation,
        after: Equation,
        come_from: dict[str, m.Mobject] | None = None,
    ) -> m.Animation:
        """An animation turning one named equation into the next. Terms keep their
        places when they keep their key; or, given `come_from`, a term it names is
        drawn out of a copy of that mobject."""
        if come_from is None:
            return m.TransformMatchingShapes(before, after)
        self.remove(before)
        self.add(*before.submobjects)
        moves: list[m.Animation] = []
        for key, part in after.parts.items():
            if key in come_from:
                moves.append(m.FadeTransform(come_from[key].copy(), part))
            elif key in before.parts:
                moves.append(m.ReplacementTransform(before.parts[key], part))
            else:
                moves.append(m.FadeIn(part, shift=0.25 * m.DOWN))
        moves += [
            m.FadeOut(part)
            for key, part in before.parts.items()
            if key not in after.parts
        ]
        return m.AnimationGroup(*moves)

    def construct(self) -> None:
        title = m.Text("Why the quadratic formula is true", font_size=46)
        title.to_edge(m.UP, buff=0.45)

        e0 = Equation(E0).move_to(EQ)
        e1 = Equation(E1).move_to(EQ)
        e2 = Equation(E2).move_to(EQ)
        e3 = Equation(E3).move_to(EQ)
        e4 = Equation(E4).move_to(EQ)

        # the picture: x² + bx as a square and two rectangles
        square = box(P0[0], P0[1] + H, X, X, X2)
        rect_r = box(P0[0] + X, P0[1] + H, H, X, BX)
        rect_b = box(P0[0], P0[1], X, H, BX)
        corner = box(P0[0] + X, P0[1], H, H, CORNER)
        big_center = P0 + np.array([(X + H) / 2, (X + H) / 2, 0.0])

        x_top = m.MathTex("x", font_size=40).move_to(
            [P0[0] + X / 2, P0[1] + H + X + 0.6, 0]
        )
        x_left = m.MathTex("x", font_size=40).move_to(
            [P0[0] - 0.32, P0[1] + H + X / 2, 0]
        )
        h_top = m.MathTex(r"\frac{b}{2}", font_size=34, color=CORNER).move_to(
            [P0[0] + X + H / 2, P0[1] + H + X + 0.62, 0]
        )
        h_left = m.MathTex(r"\frac{b}{2}", font_size=34, color=CORNER).move_to(
            [P0[0] - 0.42, P0[1] + H / 2, 0]
        )
        sq_lab = m.MathTex("x^2", font_size=44).move_to(square)
        rt_lab = m.MathTex(r"{{\frac{b}{2}}}{{x}}", font_size=30).move_to(rect_r)
        rb_lab = m.MathTex(r"{{\frac{b}{2}}}{{x}}", font_size=30).move_to(rect_b)
        for lab in (rt_lab, rb_lab):
            lab[0].set_color(CORNER)
        c_lab = m.MathTex(r"( \frac{b}{2} )^2", font_size=24, color=CORNER)
        c_lab.move_to(corner)

        dashed = m.DashedVMobject(
            m.Rectangle(width=H, height=H, stroke_color=CORNER, stroke_width=3)
            .move_to(corner),
            num_dashes=12,
        )
        ghost = m.DashedVMobject(
            m.Rectangle(width=X + H, height=X + H, stroke_color=m.WHITE,
                        stroke_width=3).move_to(big_center),
            num_dashes=24,
        )
        whole = m.Rectangle(
            width=X + H, height=X + H, stroke_color=m.WHITE, stroke_width=5
        ).move_to(big_center)
        brace = m.Brace(whole, m.RIGHT, buff=0.15)
        brace_lab = m.MathTex(r"x + \frac{b}{2}", font_size=38)
        brace_lab.next_to(brace, m.RIGHT, buff=0.15)

        self.say(
            "[Why is the quadratic formula] true? A square, completed.",
            m.Write(title),
        )
        self.wait(0.3)
        self.say(
            "Take [x squared plus b x, and set it equal to c].",
            m.Write(e0),
        )
        self.wait(0.2)
        self.say(
            "[x squared is a square] of side x, and [b x is two rectangles], "
            "each b over two by x.",
            m.AnimationGroup(
                m.TransformFromCopy(e0.parts["x2"], square),
                m.FadeIn(m.VGroup(x_top, x_left, sq_lab)),
            ),
            m.AnimationGroup(
                m.TransformFromCopy(e0.parts["bx"], rect_r),
                m.TransformFromCopy(e0.parts["bx"], rect_b),
                m.FadeIn(m.VGroup(h_top, h_left, rt_lab, rb_lab)),
            ),
        )
        self.say(
            "It almost makes [one bigger square] — only [this corner] is "
            "missing: b over two, squared.",
            m.Create(ghost),
            m.AnimationGroup(m.Create(dashed), m.FadeIn(c_lab)),
        )
        self.say(
            "[Add that corner to both sides.]",
            m.AnimationGroup(
                m.FadeOut(dashed),
                m.FadeOut(c_lab),  # the filled corner would cover it; e1 says it now
                m.FadeIn(corner),
                self.morph(e0, e1, come_from={"sq": corner, "sq2": corner}),
            ),
        )
        self.say(
            "Now the pieces are [one square] of side [x plus b over two].",
            m.AnimationGroup(
                m.FadeOut(ghost),
                m.Create(whole),
                m.GrowFromCenter(brace),
                m.Write(brace_lab),
            ),
            self.morph(e1, e2, come_from={"lhs": brace_lab}),
        )
        self.say(
            "[Take the square root], then [subtract b over two].",
            self.morph(e2, e3),
            self.morph(e3, e4),
        )
        self.wait(0.4)

        picture = m.VGroup(
            square, rect_r, rect_b, corner, whole, brace, brace_lab,
            x_top, x_left, h_top, h_left, sq_lab, rt_lab, rb_lab, c_lab,
        )
        g0 = Equation(G0).move_to(EQ)
        g1 = Equation(G1).move_to(EQ)
        g2 = Equation(G2).move_to(EQ)
        g3 = Equation(G3).move_to(EQ)
        g4 = Equation(G4).move_to(EQ)
        g5 = Equation(G5).move_to(EQ)
        g6 = Equation(G6, font_size=56).move_to(EQ)

        self.say(
            "The same square [solves every quadratic].",
            m.AnimationGroup(m.FadeOut(picture), self.morph(e4, g0)),
        )
        self.say(
            "[Divide by a], and [move c over a] across.",
            self.morph(g0, g1),
            self.morph(g1, g2),
        )
        self.say(
            "[Complete the square], [gather the right side], [take the root], "
            "and [subtract b over two a].",
            self.morph(g2, g3),
            self.morph(g3, g4),
            self.morph(g4, g5),
            self.morph(g5, g6),
        )
        frame = m.SurroundingRectangle(g6, color=m.YELLOW, buff=0.4, stroke_width=5)
        self.say("[The quadratic formula.]", m.Create(frame))
        self.wait(0.6)

        w0 = Equation(W0, font_size=50).move_to(TOP)
        w1 = Equation(W1, font_size=50).move_to(TOP)
        w2 = Equation(W2, font_size=50).move_to(TOP)
        w3 = Equation(W3, font_size=54).move_to(TOP)

        self.say(
            "Try it on [x squared plus six x plus five equals zero].",
            m.AnimationGroup(
                m.FadeOut(frame), m.FadeOut(title), self.morph(g6, w0)
            ),
        )
        self.say(
            "The formula gives [minus six, plus or minus the root of "
            "thirty-six minus twenty, over two].",
            self.morph(w0, w1),
        )
        self.say(
            "[The root of sixteen is four]: minus six, plus or minus four, "
            "over two — [minus one, or minus five].",
            self.morph(w1, w2),
            self.morph(w2, w3),
        )

        # check the roots on the parabola
        axes = m.Axes(
            x_range=[-6.5, 0.5, 1],
            y_range=[-4.5, 9.5, 1],  # deep enough that the vertex stays on screen
            x_length=9,
            y_length=5.6,
            tips=False,
            axis_config={"stroke_width": 2.5, "color": m.GREY_B},
        ).move_to([-0.4, -0.85, 0])
        names = axes.get_axis_labels("x", "y")
        curve = axes.plot(
            lambda x: x * x + 6 * x + 5, x_range=[-6.4, 0.4], color=X2,
            stroke_width=5,
        )
        curve_lab = m.MathTex("y = x^2 + 6x + 5", font_size=40, color=X2)
        curve_lab.move_to([0.0, -1.5, 0])  # inside the parabola's cup
        dot5 = m.Dot(axes.c2p(-5, 0), color=CORNER, radius=0.11)
        dot1 = m.Dot(axes.c2p(-1, 0), color=CORNER, radius=0.11)
        lab5 = m.MathTex("-5", font_size=44, color=CORNER)
        lab5.next_to(dot5, m.DOWN + m.LEFT, buff=0.28)  # the curve dives right
        lab1 = m.MathTex("-1", font_size=44, color=CORNER)
        lab1.next_to(dot1, m.DOWN + m.RIGHT, buff=0.28)  # and climbs left

        self.say(
            "And [check it on the parabola]: [y equals x squared plus six x "
            "plus five].",
            m.AnimationGroup(m.Create(axes), m.Write(names)),
            m.AnimationGroup(m.Create(curve), m.Write(curve_lab)),
        )
        self.say(
            "It crosses the x-axis at [minus five] and [minus one].",
            m.AnimationGroup(m.GrowFromCenter(dot5), m.Write(lab5)),
            m.AnimationGroup(m.GrowFromCenter(dot1), m.Write(lab1)),
        )
        self.wait(0.6)

        finale = m.MathTex(
            r"x = \frac{-b \pm \sqrt{b^2 - 4ac} }{2a}", font_size=76
        )
        last_frame = m.SurroundingRectangle(
            finale, color=m.YELLOW, buff=0.45, stroke_width=6
        )
        graph = m.VGroup(axes, names, curve, curve_lab, dot5, lab5, dot1, lab1)
        self.say(
            "That is why it is true: [the formula is a picture] — "
            "[a square, completed].",
            m.AnimationGroup(
                m.FadeOut(graph), m.FadeOut(w3), m.FadeIn(finale)
            ),
            m.Create(last_frame),
        )
        self.wait(1.5)


if __name__ == "__main__":
    CompletingTheSquare().render("completing_the_square.mp4")
