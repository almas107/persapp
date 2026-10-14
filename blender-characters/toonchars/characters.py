"""The six characters from the reference lineup."""


def srgb(h):
    """'#rrggbb' -> linear RGB tuple (Blender colours are scene linear)."""
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


FEMALE = dict(shoulders=0.9, waist=0.86, hips=1.04, girth=0.96, arm_girth=0.88, leg_girth=0.94, neck_r=0.03)
MALE = dict(shoulders=1.04, waist=0.98, hips=0.92, girth=1.0, arm_girth=1.0, leg_girth=0.96, neck_r=0.035)


def face_defaults(hh, eye_w=0.25, eye_h=0.27, **kw):
    """Face layout as fractions of head height -> metres relative to head centre."""
    F = dict(
        eye_x=hh * 0.165, eye_z=-hh * 0.12, eye_w=hh * 0.085 * eye_w / 0.25, eye_h=hh * 0.095 * eye_h / 0.27,
        eye_tilt=6, iris=1.0, lash=0.0075, brow_gap=0.013, brow_t=0.0042, brow_arch=0.004,
        mouth_z=-hh * 0.36, mouth_w=0.016, nose_z=-hh * 0.245, blush=0.0, blush_on=True,
    )
    F.update(kw)
    return F


CHARACTERS = [
    dict(
        name="Rebel", title="REBEL - Leader",
        P=dict(height=1.66, head_h=0.275, shoulder_x=0.15, hip_x=0.082, arm_angle=44, jaw=0.52, head_wide=0.39),
        B=dict(FEMALE, shoulders=0.97, waist=0.9, hips=0.98, bust=0.35),
        skin=srgb("#f3d2b6"), skin_shadow=srgb("#d39a8a"),
        F=face_defaults(0.275, eye_w=0.27, eye_h=0.21, eye_tilt=11, lid=0.86, lash=0.006, brow_t=0.0045,
                        brow_tilt=0.004, mouth_smile=0.25, mouth_asym=0.45, blush=0.0),
        eye=srgb("#5f7f2e"), eye_dark=srgb("#2f4416"),
        hair=dict(style="ponytail_rebel", color=srgb("#2f5236"), shadow=srgb("#1a2c20"), length=0.46,
                  tie=srgb("#151515")),
        brow=srgb("#1f3324"),
        outfit=dict(
            skin_torso=[], skin_arms=0.18, skin_legs=None,
            torso=[dict(z0=("hips", 0.0), z1="neck", color=srgb("#f1f0ea"), shadow=srgb("#b9b6c6"), inflate=0.004,
                        bust=0.35, name="tank"),
                   dict(z0=("hips", -0.02), z1="neck", color=srgb("#202024"), shadow=srgb("#101016"),
                        inflate=0.016, gap=78, name="vest", collar=True, hood=True)],
            sleeves=[dict(t1=0.16, color=srgb("#202024"), inflate=0.012, name="vest")],
            pants=dict(color=srgb("#2e4b3c"), shadow=srgb("#1a2a26"), inflate=0.012, flare=0.03, t1=1.0,
                       name="pants", belt=srgb("#18181a")),
            shoes=dict(color=srgb("#1e1e22"), sole=srgb("#d8d4cc")),
        ),
        acc=["cross_necklace", "wallet_chain"],
        pose="rebel",
    ),
    dict(
        name="Racer", title="RACER - Co-Leader",
        P=dict(height=1.55, head_h=0.285, shoulder_x=0.145, hip_x=0.08, arm_angle=44, jaw=0.55, head_wide=0.41),
        B=dict(FEMALE, bust=0.5),
        skin=srgb("#f7dcca"), skin_shadow=srgb("#dc9f94"),
        F=face_defaults(0.285, eye_w=0.27, eye_h=0.30, eye_tilt=3, lid=1.0, iris=1.05, blush=0.9,
                        mouth_open=0.22, bandage=(-0.052, -0.072, 18)),
        eye=srgb("#a33a33"), eye_dark=srgb("#5a1518"),
        hair=dict(style="twintails", color=srgb("#f4a3bd"), shadow=srgb("#cf6f92"), tie=srgb("#e23c4a")),
        brow=srgb("#c46482"),
        outfit=dict(
            skin_torso=[(("waist", -0.075), ("chest", -0.02))], skin_arms=None, skin_legs=(0.30, 0.66),
            torso=[dict(z0=("chest", -0.035), z1="neck", color=srgb("#c8262d"), shadow=srgb("#7d1f3a"),
                        inflate=0.004, bust=0.5, name="crop", cap0=None),
                   dict(z0=("waist", -0.035), z1="neck", color=srgb("#1f2b4d"), shadow=srgb("#121733"),
                        inflate=0.02, gap=70, name="jacket", collar=True, flare=0.012)],
            sleeves=[dict(t1=0.97, color=srgb("#1f2b4d"), inflate=0.016, name="jacket", cuff=srgb("#c8262d"))],
            pants=dict(color=srgb("#232327"), shadow=srgb("#121216"), inflate=0.008, t1=0.30, name="shorts",
                       stripe=srgb("#c8262d"), top=("waist", -0.06)),
            socks=dict(color=srgb("#1c1c20"), t0=0.62),
            shoes=dict(color=srgb("#2a2a30"), sole=srgb("#f0f0f0")),
            patches=True,
        ),
        acc=[],
        pose="racer",
    ),
    dict(
        name="Collector", title="COLLECTOR",
        P=dict(height=1.5, head_h=0.275, shoulder_x=0.15, hip_x=0.082, arm_angle=46, jaw=0.45, head_wide=0.41,
               chin_forward=0.015),
        B=dict(MALE),
        skin=srgb("#6b4330"), skin_shadow=srgb("#4a2a24"),
        F=face_defaults(0.275, eye_w=0.24, eye_h=0.20, eye_tilt=1, lid=0.66, lower=0.08, lash=0.0045,
                        brow_t=0.0038, mouth_smile=-0.15, blush_on=False, iris=0.95),
        eye=srgb("#3d2619"), eye_dark=srgb("#1d110b"),
        hair=dict(style="buzz", color=srgb("#1d1716"), shadow=srgb("#0f0b0b")),
        brow=srgb("#1d1716"),
        outfit=dict(
            skin_torso=[], skin_arms=None, skin_legs=None,
            torso=[dict(z0=("crotch", 0.04), z1="neck", color=srgb("#f5f5f2"), shadow=srgb("#b9bccc"),
                        inflate=0.004, name="shirt"),
                   dict(z0=("hips", 0.01), z1="neck", color=srgb("#f2a9bb"), shadow=srgb("#c5768f"),
                        inflate=0.014, name="sweater", vneck=True, hem=srgb("#e597aa"))],
            sleeves=[dict(t1=0.99, color=srgb("#f5f5f2"), inflate=0.006, name="shirt"),
                     dict(t1=0.93, color=srgb("#f2a9bb"), inflate=0.013, name="sweater", cuff=srgb("#e597aa"))],
            pants=dict(color=srgb("#1f2436"), shadow=srgb("#11141f"), inflate=0.012, flare=0.01, t1=1.0,
                       name="pants"),
            shoes=dict(color=srgb("#2c2420"), sole=srgb("#1a1614")),
            shirt_collar=srgb("#f5f5f2"),
        ),
        acc=[],
        props=["console"],
        pose="collector",
    ),
    dict(
        name="NatureSpirit", title="NATURE SPIRIT",
        P=dict(height=1.63, head_h=0.275, shoulder_x=0.146, hip_x=0.082, arm_angle=40, jaw=0.52, head_wide=0.4),
        B=dict(FEMALE, bust=0.6),
        skin=srgb("#a8704e"), skin_shadow=srgb("#7a4a3e"),
        F=face_defaults(0.275, eye_w=0.26, eye_h=0.25, eye_tilt=4, lid=0.88, lower=0.1, mouth_smile=0.55,
                        blush=0.55),
        eye=srgb("#3e2418"), eye_dark=srgb("#1e100a"),
        hair=dict(style="long_parted", color=srgb("#1f1b1c"), shadow=srgb("#0e0b0d")),
        brow=srgb("#1a1414"),
        outfit=dict(
            skin_torso=[], skin_arms=None, skin_legs=(0.64, 0.98),
            torso=[dict(z0=("hips", -0.05), z1="neck", color=srgb("#2f8a52"), shadow=srgb("#1b5040"),
                        inflate=0.016, bust=0.6, name="sweater", hem=srgb("#287a47"), crew=True)],
            sleeves=[dict(t1=0.96, color=srgb("#2f8a52"), inflate=0.016, name="sweater", cuff=srgb("#287a47"))],
            skirt=dict(color=srgb("#b39272"), shadow=srgb("#7f6253"), top=("waist", -0.02), length=0.66),
            shoes=dict(color=srgb("#6b4a33"), sole=srgb("#3b2a20"), height=0.04),
        ),
        acc=["earrings", "leaves"],
        pose="nature",
    ),
    dict(
        name="Scholar", title="SCHOLAR - Archivist",
        P=dict(height=1.57, head_h=0.278, shoulder_x=0.145, hip_x=0.08, arm_angle=44, jaw=0.55, head_wide=0.4),
        B=dict(FEMALE, bust=0.4),
        skin=srgb("#f5dcc8"), skin_shadow=srgb("#d7a094"),
        F=face_defaults(0.278, eye_w=0.25, eye_h=0.25, eye_tilt=5, lid=0.9, mouth_smile=0.45, blush=0.3,
                        iris=0.95),
        eye=srgb("#3f8088"), eye_dark=srgb("#1d4146"),
        hair=dict(style="ponytail_neat", color=srgb("#1e2c31"), shadow=srgb("#0f171b"), length=0.3,
                  tie=srgb("#101010")),
        brow=srgb("#18232a"),
        outfit=dict(
            skin_torso=[], skin_arms=None, skin_legs=None,
            torso=[dict(z0=("hips", -0.03), z1="neck", color=srgb("#232328"), shadow=srgb("#121218"),
                        inflate=0.014, bust=0.4, name="jacket", high_collar=True, buttons=srgb("#c7a24a"))],
            sleeves=[dict(t1=0.97, color=srgb("#232328"), inflate=0.014, name="jacket")],
            pants=dict(color=srgb("#c7b08e"), shadow=srgb("#937d6f"), inflate=0.012, flare=0.012, t1=1.0,
                       name="pants"),
            shoes=dict(color=srgb("#3a2a22"), sole=srgb("#1d1612")),
        ),
        acc=["glasses"],
        props=["camera"],
        pose="scholar",
    ),
    dict(
        name="Trickster", title="TRICKSTER",
        P=dict(height=1.62, head_h=0.278, shoulder_x=0.152, hip_x=0.082, arm_angle=46, jaw=0.48, head_wide=0.4),
        B=dict(MALE, shoulders=0.98, girth=0.95, arm_girth=0.92),
        skin=srgb("#f2dccb"), skin_shadow=srgb("#cf9c96"),
        F=face_defaults(0.278, eye_w=0.25, eye_h=0.24, eye_tilt=2, lid=0.58, lower=0.12, eye_bags=True,
                        mouth_smile=0.1, mouth_asym=0.0, blush_on=False, iris=0.9,
                        freckles=[(sx * x, z) for sx in (1, -1) for (x, z) in
                                  ((0.032, -0.062), (0.040, -0.068), (0.048, -0.061), (0.037, -0.074),
                                   (0.052, -0.071), (0.027, -0.07))]),
        eye=srgb("#b3232c"), eye_dark=srgb("#5e0f15"),
        hair=dict(style="messy", color=srgb("#ece7df"), shadow=srgb("#b5b0c4")),
        brow=srgb("#c9c3bb"),
        outfit=dict(
            skin_torso=[], skin_arms=None, skin_legs=None,
            torso=[dict(z0=("hips", -0.02), z1="neck", color=srgb("#3b3b3d"), shadow=srgb("#232329"),
                        inflate=0.006, name="tee", crew=True),
                   dict(z0=("hips", -0.06), z1="neck", color=srgb("#c9302c"), shadow=srgb("#7d1d2c"),
                        inflate=0.024, gap=62, name="jacket", collar=True, flare=0.02, yoke=srgb("#8e1f22"),
                        letter="M")],
            sleeves=[dict(t1=0.3, color=srgb("#3b3b3d"), inflate=0.007, name="tee"),
                     dict(t1=0.95, color=srgb("#c9302c"), inflate=0.022, name="jacket", cuff=srgb("#d9d4cc"),
                          flare=0.006)],
            pants=dict(color=srgb("#93aac6"), shadow=srgb("#5d6c94"), inflate=0.014, flare=0.02, t1=1.0,
                       name="jeans"),
            shoes=dict(color=srgb("#e6e2da"), sole=srgb("#b8b2a8"), laces=srgb("#c9302c")),
        ),
        acc=["lock_key_necklace"],
        pose="trickster",
    ),
]

