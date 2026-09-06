"""Assert css3dTransform string helper stays stable."""

from __future__ import annotations

# Mirror of react-front/src/utils/css3dTransform.ts — keep in sync for the
# string contract tests care about. Browser DOMMatrix tests live elsewhere.


def css3d_transform(
    *,
    rotate_x_deg: float,
    rotate_y_deg: float,
    rotate_z_deg: float,
    perspective_px: float,
    scale: float = 1.0,
) -> str:
    parts = [
        f"perspective({perspective_px}px)",
        f"rotateX({rotate_x_deg}deg)",
        f"rotateY({rotate_y_deg}deg)",
        f"rotateZ({rotate_z_deg}deg)",
    ]
    if scale != 1:
        parts.append(f"scale({scale})")
    return " ".join(parts)


def test_css3d_transform_identity_order() -> None:
    assert (
        css3d_transform(
            rotate_x_deg=0,
            rotate_y_deg=0,
            rotate_z_deg=0,
            perspective_px=800,
        )
        == "perspective(800px) rotateX(0deg) rotateY(0deg) rotateZ(0deg)"
    )


def test_css3d_transform_includes_scale_when_not_one() -> None:
    out = css3d_transform(
        rotate_x_deg=10,
        rotate_y_deg=-20,
        rotate_z_deg=5,
        perspective_px=600,
        scale=1.25,
    )
    assert out == (
        "perspective(600px) rotateX(10deg) rotateY(-20deg) rotateZ(5deg) scale(1.25)"
    )
