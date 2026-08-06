from __future__ import annotations

import io
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from ..novel_view_preprocess import (
    DEFAULT_MODEL_SIZE,
    composite_model_output_on_canvas,
    prepare_cutout_for_model,
)
from ..novel_view_strategy import NovelViewStrategy

if TYPE_CHECKING:
    from avroom_object_removal.ai_engines.reconstruction_3d import Reconstruction3DFacade

logger = logging.getLogger(__name__)

# Match react-front Model3DFrame framing so preview ≈ committed mesh render.
# _FRAME_PADDING mirrors MODEL_3D_FRAME_PADDING there: the render viewport covers
# the cutout's square bbox grown by this factor, and the mesh is fit so its
# projected silhouette lands at exactly the cutout's own size inside it. Scaling
# the mesh by its largest bounding-box edge instead (the old behaviour) rendered
# it at a fraction of the cutout, since the depth axis costs on-screen size
# without ever occupying any.
_FRAME_PADDING = 1.5
_CAMERA_FOV_DEG = 40.0
_CAMERA_NEAR = 0.1
_CAMERA_FAR = 1000.0
_CAMERA_START = np.array([0.0, 0.0, 7.0], dtype=np.float64)
_DEFAULT_RENDER_SIZE = 512

# Generated GLBs come back lying flat: the side the source photo saw faces the
# mesh's -Y axis, with the photo's "up" along +X. Left uncorrected, the canonical
# pose (azimuth 0, elevation 0) shows the object edge-on, so the object only ever
# looks right after the user orbits ~90 degrees, and every rotation they ask for
# is measured from a pose that never matched the photo. This maps -Y onto the
# camera axis (+Z) and +X onto screen up (+Y), so pose zero reproduces the photo.
_GLB_TO_VIEW_ROTATION = np.array(
    [
        [0.0, 0.0, -1.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)

_AMBIENT_INTENSITY = 0.6
_KEY_LIGHT_COLOR = np.array([0.60, 0.85, 0.86], dtype=np.float64)
_KEY_LIGHT_INTENSITY = 2.0
_KEY_LIGHT_POSITION = np.array([4.0, 6.0, 5.0], dtype=np.float64)
_FILL_LIGHT_COLOR = np.array([0.05, 0.51, 0.53], dtype=np.float64)
_FILL_LIGHT_INTENSITY = 0.8
_FILL_LIGHT_POSITION = np.array([-5.0, 2.0, -4.0], dtype=np.float64)
_RIM_LIGHT_COLOR = np.array([0.95, 0.83, 0.61], dtype=np.float64)
_RIM_LIGHT_INTENSITY = 0.45
_RIM_LIGHT_POSITION = np.array([0.0, -3.0, -6.0], dtype=np.float64)


class MeshRenderNovelViewError(RuntimeError):
    """Raised when mesh-based novel-view rendering fails."""


def _spherical_from_cartesian(position: np.ndarray) -> tuple[float, float, float]:
    """Return ``(azimuth_rad, polar_rad, radius)`` for a look-at-origin camera.

    Uses the same spherical convention as Three.js OrbitControls:
    - azimuth around +Y
    - polar from +Y (0 = top, π/2 = equator)
    """

    x, y, z = float(position[0]), float(position[1]), float(position[2])
    radius = math.sqrt(x * x + y * y + z * z)
    if radius < 1e-8:
        return 0.0, math.pi / 2.0, 0.0
    polar = math.acos(max(-1.0, min(1.0, y / radius)))
    azimuth = math.atan2(x, z)
    return azimuth, polar, radius


def _cartesian_from_spherical(azimuth: float, polar: float, radius: float) -> np.ndarray:
    """Inverse of :func:`_spherical_from_cartesian`."""

    sin_polar = math.sin(polar)
    return np.array(
        [
            radius * sin_polar * math.sin(azimuth),
            radius * math.cos(polar),
            radius * sin_polar * math.cos(azimuth),
        ],
        dtype=np.float64,
    )


def _orbit_camera_position(
    *,
    azimuth_deg: float,
    relative_elevation_deg: float,
    radius: float,
) -> np.ndarray:
    """Camera eye position matching ``Model3DFrame.capture()`` deltas.

    Frontend capture:
    - ``azimuthDeg = current_azimuthal - initial_azimuthal``
    - ``relativeElevationDeg = initial_polar - current_polar`` (up → positive)

    ``radius`` zooms distance: ``0`` keeps the canonical start distance;
    positive values move farther (``ZOOM_OUT``), negative closer (``ZOOM_IN``).
    """

    start_az, start_polar, start_distance = _spherical_from_cartesian(_CAMERA_START)
    target_az = start_az + math.radians(azimuth_deg)
    target_polar = start_polar - math.radians(relative_elevation_deg)
    # Keep polar in a safe open interval to avoid gimbal lock at the poles.
    target_polar = max(1e-3, min(math.pi - 1e-3, target_polar))
    distance = start_distance * (1.0 + float(radius))
    if distance <= 1e-3:
        distance = start_distance * 0.05
    return _cartesian_from_spherical(target_az, target_polar, distance)


class MeshRenderNovelViewStrategy(NovelViewStrategy):
    """Photoshop-style novel view: render a GLB mesh at the requested orbit pose.

    Unlike Zero123 (image-to-image diffusion), this strategy loads a 3D mesh and
    rasterizes it from a camera that follows the same orbit deltas the frontend
    ``Model3DFrame`` reports. ``elevation_deg`` (absolute source elevation) is
    accepted for contract parity with diffusion strategies but does not move the
    mesh camera — orbit uses ``azimuth_deg`` + ``relative_elevation_deg`` only.

    Provide ``mesh=`` (GLB path or bytes) on ``synthesize``, or inject a
    :class:`Reconstruction3DFacade` so a missing mesh can be generated from the
    cutout.
    """

    def __init__(
        self,
        *,
        reconstruction: Reconstruction3DFacade | None = None,
        render_size: int = _DEFAULT_RENDER_SIZE,
        frame_padding: float = _FRAME_PADDING,
    ) -> None:
        self._reconstruction = reconstruction
        self._render_size = max(64, int(render_size))
        self._frame_padding = max(1.0, float(frame_padding))
        logger.info(
            "MeshRenderNovelViewStrategy created (render_size=%d, frame_padding=%.2f, "
            "reconstruction=%s)",
            self._render_size,
            self._frame_padding,
            type(reconstruction).__name__ if reconstruction is not None else None,
        )

    def synthesize(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        elevation_deg: float,
        azimuth_deg: float,
        relative_elevation_deg: float = 0.0,
        radius: float = 0.0,
        seed: int = 0,
        mesh: bytes | Path | str | None = None,
    ) -> np.ndarray:
        """Render ``mesh`` at the orbit pose and composite onto the cutout canvas."""

        del seed  # Deterministic rasterization; accepted for contract parity.
        _ = elevation_deg  # Absolute source elevation unused for mesh orbit.

        from avroom_object_removal.ai_engines.reconstruction_3d.reconstruction_image_input import (
            to_pil_rgba,
        )

        rgba = to_pil_rgba(image)
        prep = prepare_cutout_for_model(rgba, model_size=DEFAULT_MODEL_SIZE)

        mesh_bytes = self._resolve_mesh_bytes(mesh, image)
        logger.info(
            "Mesh render synthesize: azimuth=%.1f rel_elevation=%.1f radius=%.3f "
            "mesh_bytes=%d",
            azimuth_deg,
            relative_elevation_deg,
            radius,
            len(mesh_bytes),
        )

        camera_eye = _orbit_camera_position(
            azimuth_deg=azimuth_deg,
            relative_elevation_deg=relative_elevation_deg,
            radius=radius,
        )
        # The render viewport maps onto the cutout's square bbox grown by the frame
        # padding; the object itself must land back at its original width/height
        # inside that region, so it is fit to those fractions of the viewport.
        region_side = prep.square_size * self._frame_padding
        target_fractions = (
            (prep.crop_box[2] - prep.crop_box[0]) / region_side,
            (prep.crop_box[3] - prep.crop_box[1]) / region_side,
        )
        logger.debug(
            "Mesh render camera eye=%s canvas=%s target_fractions=%s",
            camera_eye.tolist(),
            prep.canvas_size,
            target_fractions,
        )

        try:
            rendered_rgba = self._render_glb_rgba(mesh_bytes, camera_eye, target_fractions)
        except MeshRenderNovelViewError:
            raise
        except Exception as exc:
            logger.exception("Mesh novel-view render failed")
            raise MeshRenderNovelViewError(f"Mesh novel-view render failed: {exc}") from exc

        output_bgra = composite_model_output_on_canvas(
            rendered_rgba,
            prep,
            region_scale=self._frame_padding,
        )
        logger.info(
            "Mesh render synthesize complete: shape=%s azimuth=%.1f",
            output_bgra.shape,
            azimuth_deg,
        )
        return output_bgra

    def _resolve_mesh_bytes(
        self,
        mesh: bytes | Path | str | None,
        image: bytes | np.ndarray | Image.Image | Path | str,
    ) -> bytes:
        """Return GLB bytes from ``mesh`` or by reconstructing from ``image``."""

        if mesh is not None:
            if isinstance(mesh, bytes):
                if not mesh:
                    raise MeshRenderNovelViewError("mesh bytes are empty")
                return mesh
            path = Path(mesh)
            if not path.is_file():
                raise MeshRenderNovelViewError(f"GLB mesh not found: {path}")
            data = path.read_bytes()
            if not data:
                raise MeshRenderNovelViewError(f"GLB mesh is empty: {path}")
            return data

        if self._reconstruction is None:
            raise MeshRenderNovelViewError(
                "mesh= is required for MeshRenderNovelViewStrategy when no "
                "Reconstruction3DFacade was injected for fallback generation."
            )

        logger.info("No mesh provided; generating GLB via Reconstruction3DFacade")
        from avroom_object_removal.ai_engines.reconstruction_3d import ReconstructionQuality

        glb = self._reconstruction.generate(
            image,
            quality=ReconstructionQuality.HIGH,
            output="bytes",
        )
        if not isinstance(glb, bytes) or not glb:
            raise MeshRenderNovelViewError(
                "Reconstruction3DFacade did not return non-empty GLB bytes"
            )
        return glb

    def _load_normalized_trimesh(
        self,
        mesh_bytes: bytes,
        target_fractions: tuple[float, float],
    ) -> Any:
        """Load GLB bytes, merge scene geometry, recenter, and fit it to the frame."""

        try:
            import trimesh
        except ModuleNotFoundError as exc:
            raise MeshRenderNovelViewError(
                "trimesh is required for mesh novel-view rendering. "
                "Install project dependencies: pip install -r requirements.txt"
            ) from exc

        loaded = trimesh.load(file_obj=io.BytesIO(mesh_bytes), file_type="glb", force="scene")
        if isinstance(loaded, trimesh.Scene):
            # Scene.to_geometry() replaces deprecated dump(concatenate=True).
            geometry = loaded.to_geometry()
        else:
            geometry = loaded

        if geometry is None or getattr(geometry, "is_empty", False):
            raise MeshRenderNovelViewError("GLB contains no renderable geometry")

        if not isinstance(geometry, trimesh.Trimesh):
            # dump() can return a list when concatenate fails for mixed types.
            if isinstance(geometry, list):
                meshes = [g for g in geometry if isinstance(g, trimesh.Trimesh)]
                if not meshes:
                    raise MeshRenderNovelViewError("GLB contains no Trimesh geometry")
                geometry = trimesh.util.concatenate(meshes)
            else:
                raise MeshRenderNovelViewError(
                    f"Unsupported GLB geometry type: {type(geometry)!r}"
                )

        bounds = geometry.bounds
        center = (bounds[0] + bounds[1]) * 0.5
        extents = bounds[1] - bounds[0]
        max_dim = float(np.max(extents))
        if max_dim <= 1e-8:
            raise MeshRenderNovelViewError("GLB mesh has zero extent")

        geometry = geometry.copy()
        geometry.apply_translation(-center)
        geometry.apply_transform(_GLB_TO_VIEW_ROTATION)
        # Normalize to roughly unit size first so the fit below starts from extents
        # comparable to the orbit radius, whatever scale the source GLB uses.
        geometry.apply_scale(1.0 / max_dim)

        fit_scale = self._projected_fit_scale(geometry, target_fractions)
        geometry.apply_scale(fit_scale)
        logger.debug(
            "Normalized mesh: verts=%d faces=%d max_dim=%.4f fit_scale=%.4f",
            len(geometry.vertices),
            len(geometry.faces),
            max_dim,
            fit_scale,
        )
        return geometry

    def _projected_fit_scale(
        self,
        geometry: Any,
        target_fractions: tuple[float, float],
    ) -> float:
        """Scale that makes the mesh's *projected* silhouette fill the target rect.

        Measured at the canonical start pose (never the requested orbit pose), so
        the object keeps one constant on-canvas size across every rotation, exactly
        like the frontend viewer which fits once and then only orbits.
        """

        frac_x, frac_y = target_fractions
        if frac_x <= 0.0 or frac_y <= 0.0:
            return 1.0

        view = np.linalg.inv(self._look_at_matrix(_CAMERA_START, np.zeros(3, dtype=np.float64)))
        # Real vertices, not bounding-box corners: a box drawn around a chair (or
        # any curved/concave shape) projects well outside the silhouette it
        # encloses, which would leave the object short of the rect it must fill.
        points = np.asarray(geometry.vertices, dtype=np.float64)
        if points.size == 0:
            return 1.0
        in_camera = points @ view[:3, :3].T + view[:3, 3]

        # OpenGL camera looks down -Z, so the origin sits at z = -distance and a
        # vertex leaning toward the camera has a larger (less negative) z.
        distance = float(np.linalg.norm(_CAMERA_START))
        toward_camera = in_camera[:, 2] + distance

        # Each vertex's projected size depends on its own depth, which depends on
        # the scale being solved for. Converge by repeatedly measuring the current
        # projection and dividing out how far it overshoots the target rect.
        tan_half_fov = math.tan(math.radians(_CAMERA_FOV_DEG) / 2.0)
        scale = 1.0
        for _ in range(8):
            depth = np.maximum(distance - scale * toward_camera, distance * 0.05)
            projected = np.abs(scale * in_camera[:, :2]) / (depth[:, None] * tan_half_fov)
            overshoot = max(
                float(np.max(projected[:, 0])) / frac_x,
                float(np.max(projected[:, 1])) / frac_y,
            )
            if overshoot <= 1e-8:
                return scale
            scale /= overshoot
        return scale

    def _render_glb_rgba(
        self,
        mesh_bytes: bytes,
        camera_eye: np.ndarray,
        target_fractions: tuple[float, float],
    ) -> Image.Image:
        """Rasterize the normalized GLB to an RGBA PIL image via pyrender."""

        try:
            import pyrender
        except ModuleNotFoundError as exc:
            raise MeshRenderNovelViewError(
                "pyrender (and PyOpenGL) are required for mesh novel-view rendering. "
                "Install project dependencies: pip install -r requirements.txt"
            ) from exc

        geometry = self._load_normalized_trimesh(mesh_bytes, target_fractions)

        try:
            mesh = pyrender.Mesh.from_trimesh(geometry, smooth=True)
        except Exception as exc:
            raise MeshRenderNovelViewError(
                f"Failed to convert trimesh to pyrender mesh: {exc}"
            ) from exc

        scene = pyrender.Scene(
            bg_color=np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            ambient_light=np.array(
                [_AMBIENT_INTENSITY, _AMBIENT_INTENSITY, _AMBIENT_INTENSITY],
                dtype=np.float32,
            ),
        )
        scene.add(mesh)

        camera = pyrender.PerspectiveCamera(
            yfov=math.radians(_CAMERA_FOV_DEG),
            znear=_CAMERA_NEAR,
            zfar=_CAMERA_FAR,
            aspectRatio=1.0,
        )
        camera_pose = self._look_at_matrix(camera_eye, target=np.zeros(3, dtype=np.float64))
        scene.add(camera, pose=camera_pose)

        scene.add(
            pyrender.DirectionalLight(
                color=_KEY_LIGHT_COLOR.astype(np.float32),
                intensity=_KEY_LIGHT_INTENSITY,
            ),
            pose=self._look_at_matrix(_KEY_LIGHT_POSITION, target=np.zeros(3)),
        )
        scene.add(
            pyrender.DirectionalLight(
                color=_FILL_LIGHT_COLOR.astype(np.float32),
                intensity=_FILL_LIGHT_INTENSITY,
            ),
            pose=self._look_at_matrix(_FILL_LIGHT_POSITION, target=np.zeros(3)),
        )
        scene.add(
            pyrender.DirectionalLight(
                color=_RIM_LIGHT_COLOR.astype(np.float32),
                intensity=_RIM_LIGHT_INTENSITY,
            ),
            pose=self._look_at_matrix(_RIM_LIGHT_POSITION, target=np.zeros(3)),
        )

        # pyrender needs a writable OpenGL context. Prefer OSMesa/EGL when set;
        # otherwise use the default platform (works on Windows with a GPU).
        renderer: Any | None = None
        try:
            renderer = pyrender.OffscreenRenderer(
                viewport_width=self._render_size,
                viewport_height=self._render_size,
            )
            color, _depth = renderer.render(
                scene,
                flags=pyrender.RenderFlags.RGBA,
            )
        except Exception as exc:
            raise MeshRenderNovelViewError(
                "Offscreen OpenGL render failed. Mesh novel-view requires a working "
                "pyrender/PyOpenGL context (GPU display, or PYOPENGL_PLATFORM=osmesa/egl "
                f"on headless hosts). Underlying error: {exc}"
            ) from exc
        finally:
            if renderer is not None:
                renderer.delete()

        if color.ndim != 3 or color.shape[2] < 4:
            raise MeshRenderNovelViewError(
                f"Unexpected pyrender output shape: {getattr(color, 'shape', None)}"
            )

        rgba = color[:, :, :4].astype(np.uint8)
        return Image.fromarray(rgba, mode="RGBA")

    @staticmethod
    def _look_at_matrix(
        eye: np.ndarray,
        target: np.ndarray,
        up: np.ndarray | None = None,
    ) -> np.ndarray:
        """Build a 4×4 camera-to-world matrix for pyrender (OpenGL camera frame)."""

        eye = np.asarray(eye, dtype=np.float64).reshape(3)
        target = np.asarray(target, dtype=np.float64).reshape(3)
        up_vec = (
            np.asarray(up, dtype=np.float64).reshape(3)
            if up is not None
            else np.array([0.0, 1.0, 0.0], dtype=np.float64)
        )

        forward = target - eye
        forward_norm = np.linalg.norm(forward)
        if forward_norm < 1e-8:
            forward = np.array([0.0, 0.0, -1.0], dtype=np.float64)
        else:
            forward = forward / forward_norm

        # OpenGL camera looks down -Z; pyrender camera pose uses camera-to-world
        # with +Z pointing backward from the view direction.
        z_axis = -forward
        x_axis = np.cross(up_vec, z_axis)
        x_norm = np.linalg.norm(x_axis)
        if x_norm < 1e-8:
            # Eye is parallel to up — pick an alternate up.
            alt_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            x_axis = np.cross(alt_up, z_axis)
            x_norm = np.linalg.norm(x_axis)
        x_axis = x_axis / x_norm
        y_axis = np.cross(z_axis, x_axis)

        pose = np.eye(4, dtype=np.float64)
        pose[:3, 0] = x_axis
        pose[:3, 1] = y_axis
        pose[:3, 2] = z_axis
        pose[:3, 3] = eye
        return pose
