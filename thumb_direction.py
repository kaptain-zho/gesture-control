"""Resolve thumb poses in the already mirrored preview's coordinates."""
import math


def resolve_gesture(name, score, landmarks, width=640, height=480):
    if len(landmarks) != 21:
        return (None, 0.0) if name in ('Thumb_Up', 'Thumb_Down') else (name, score)
    p = [(v.x * width, v.y * height) for v in landmarks]
    def distance(a, b):
        return math.dist(p[a], p[b])
    palm = max(distance(5, 17), distance(0, 9) * .65)
    if palm < 5:
        return None, 0.0
    dx, dy = p[4][0] - p[2][0], p[4][1] - p[2][1]
    length = math.hypot(dx, dy)
    # A thumb must extend beyond its knuckle and the curled fingers. This
    # prevents a sideways fist from being interpreted as a track change.
    straightness = length / max(distance(2, 3) + distance(3, 4), 1e-6)
    curled = all(distance(tip, 0) < distance(pip, 0) * 1.15
                 for pip, tip in [(6, 8), (10, 12), (14, 16), (18, 20)])
    thumb_shape = curled and length > palm * .65 and straightness > .9 and distance(4, 5) > palm * .6
    model_thumb = name in ('Thumb_Up', 'Thumb_Down')
    if not thumb_shape and not model_thumb:
        return name, score
    if length < palm * .4:
        return None, 0.0
    horizontal = abs(dx) / max(length, 1e-6)
    vertical = abs(dy) / max(length, 1e-6)
    if horizontal >= .85:
        direction = 'Thumb_Right' if dx > 0 else 'Thumb_Left'
    elif vertical >= .85:
        direction = 'Thumb_Up' if dy < 0 else 'Thumb_Down'
    else:
        # Dead zone between directions avoids switching while turning the hand.
        return None, 0.0
    if model_thumb:
        return direction, score
    # A geometry fit score, not a model probability or measured accuracy.
    fit = min(straightness, max(horizontal, vertical), min(1, length / palm))
    return direction, fit
