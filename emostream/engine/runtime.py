"""Pretrained components EmoStream builds on, loaded once per process.

The renderer is LivePortrait (appearance extractor, motion extractor, warping
network, SPADE decoder, stitching network) in the packaging released with
antgroup/ditto-talkinghead (Apache-2.0), together with Ditto's streaming HuBERT
encoder and its motion-diffusion model, which serves as the pretrained
audio-to-motion baseline. All weights are frozen.

This module needs the Ditto repository on ``sys.path`` (``DITTO_REPO``) and its
checkpoints; it is imported only inside GPU workers.
"""
from __future__ import annotations

import copy
import os
import sys
from dataclasses import dataclass

import numpy as np

from .retarget import LIP_OPEN_THRESHOLD, build_lip_retargeter, lip_close_offset, lip_open_ratio, lip_target_for

DITTO_REPO = os.environ.get("DITTO_REPO", "/opt/ditto")


@dataclass
class Avatar:
    """A registered portrait: everything the renderer needs, computed once."""

    source_info: dict
    x_s_info: dict            # source motion (pose, expression, canonical keypoints)
    f_s: "object"             # appearance feature volume, torch tensor on the GPU, (1, 32, 16, 64, 64)
    image_rgb: np.ndarray     # original image, HxWx3 uint8
    crop_rgb: np.ndarray      # 512x512 face crop the renderer works on
    M_c2o: np.ndarray         # crop -> original affine transform


class Runtime:
    """Holds the frozen networks. One instance can serve many sessions sequentially."""

    def __init__(self, checkpoints: str, device: str = "cuda", tensorrt: bool = False):
        """``tensorrt=True`` swaps the warping network, the decoder and the speech encoder
        for Ditto's published TensorRT engines (Ampere-or-newer GPUs, TensorRT 8.6)."""
        if DITTO_REPO not in sys.path:
            sys.path.insert(0, DITTO_REPO)
        import torch
        from stream_pipeline_online import StreamSDK  # builds components, starts no threads

        self.torch = torch
        self.device = device
        self.tensorrt = tensorrt
        cfg = f"{checkpoints}/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl"
        replace = {}
        if tensorrt:
            trt = f"{checkpoints}/ditto_trt_Ampere_Plus"
            replace = {"base_cfg": {
                "warp_network_cfg": {"model_path": f"{trt}/warp_network_fp16.engine", "device": device},
                "decoder_cfg": {"model_path": f"{trt}/decoder_fp16.engine", "device": device},
                "hubert_cfg": {"model_path": f"{trt}/hubert_fp32.engine", "device": device},
            }}
        self.sdk = StreamSDK(cfg, f"{checkpoints}/ditto_pytorch", **replace)
        self.defaults = self.sdk.default_kwargs
        # Optional LivePortrait lip-retargeting network (closes an open-mouthed portrait).
        lip_ckpt = os.path.join(os.path.dirname(checkpoints.rstrip("/")), "liveportrait",
                                "stitching_retargeting_module.pth")
        self.lip_net = build_lip_retargeter(lip_ckpt, device) if os.path.exists(lip_ckpt) else None
        if not tensorrt:
            self.warp = self.sdk.warp_f3d.warp_net.model
            self.decoder = self.sdk.decode_f3d.decoder.model
            self.warp.eval()
            self.decoder.eval()

    # ---- portrait -----------------------------------------------------------------
    def register(self, image_path: str, max_dim: int = 1920, close_open_mouth: bool = True,
                 lip_target: float | None = None, lip_strength: float = 1.0) -> Avatar:
        """Registers a portrait. If its mouth is open and ``close_open_mouth`` is set, the
        lip-closing keypoint offset is computed once and applied to every rendered frame,
        so that the avatar rests with a closed mouth."""
        import cv2
        from core.atomic_components.loader import load_source_frames
        from core.atomic_components.motion_stitch import transform_keypoint

        d = self.defaults
        rgb_list, is_image = load_source_frames(image_path, max_dim=max_dim, n_frames=1)
        img = rgb_list[0]
        one = self.sdk.avatar_registrar.source2info(
            img, None, crop_scale=d.get("crop_scale", 2.3), crop_vx_ratio=d.get("crop_vx_ratio", 0),
            crop_vy_ratio=d.get("crop_vy_ratio", -0.125), crop_flag_do_rot=d.get("crop_flag_do_rot", True))
        info = {"x_s_info_lst": [one["x_s_info"]], "f_s_lst": [one["f_s"]], "M_c2o_lst": [one["M_c2o"]],
                "eye_open_lst": [one["eye_open"]], "eye_ball_lst": [one["eye_ball"]],
                "sc": one["x_s_info"]["kp"].flatten(), "is_image_flag": True, "img_rgb_lst": [img]}
        M = one["M_c2o"]
        crop = cv2.warpAffine(img, np.linalg.inv(M)[:2], (512, 512), flags=cv2.INTER_LINEAR)
        f_s = one["f_s"] if self.tensorrt else self.torch.from_numpy(one["f_s"]).to(self.device)
        avatar = Avatar(source_info=info, x_s_info=one["x_s_info"], f_s=f_s, image_rgb=img, crop_rgb=crop, M_c2o=M)
        avatar.lip_ratio = lip_open_ratio(one["lmk203"])
        avatar.mouth_open = avatar.lip_ratio >= LIP_OPEN_THRESHOLD
        avatar.lip_delta = None
        if close_open_mouth and avatar.mouth_open and self.lip_net is not None:
            avatar.lip_delta = lip_close_offset(self.lip_net, transform_keypoint(one["x_s_info"]), avatar.lip_ratio,
                                                self.device, strength=lip_strength,
                                                target=lip_target_for(avatar.lip_ratio) if lip_target is None else lip_target)
        return avatar

    # ---- rendering ----------------------------------------------------------------
    def new_stitcher(self, avatar: Avatar):
        """A per-session MotionStitch (it keeps the rest pose and the blink schedule)."""
        d = self.defaults
        ms = copy.copy(self.sdk.motion_stitch)
        ms.setup(
            N_d=-1, use_d_keys=d.get("use_d_keys"), relative_d=d.get("relative_d", True),
            drive_eye=d.get("drive_eye"), delta_eye_arr=d.get("delta_eye_arr"),
            delta_eye_open_n=d.get("delta_eye_open_n", 0), fade_out_keys=d.get("fade_out_keys", ("exp",)),
            fade_type="", flag_stitching=d.get("flag_stitching", True), is_image_flag=True,
            x_s_info=avatar.x_s_info, d0=None, ch_info=d.get("ch_info"),
            overall_ctrl_info=dict(d.get("overall_ctrl_info", {})),
        )
        return ms

    def source_degrees(self, avatar: Avatar) -> np.ndarray:
        """Source head rotation (pitch, yaw, roll) in degrees."""
        from core.atomic_components.motion_stitch import bin66_to_degree

        return np.array([float(np.asarray(bin66_to_degree(avatar.x_s_info[k])).reshape(-1)[0])
                         for k in ("pitch", "yaw", "roll")], dtype=np.float32)

    def keypoints_full_face(self, avatar: Avatar, x_d_info: dict):
        """Driving keypoints from a complete motion dict, using *all* expression
        coordinates. (Ditto's own stitcher keeps only lip and eye keypoints from the
        driving expression and copies the rest from the source, which hides brow and
        cheek movement.) The stitching network still corrects the composition."""
        from core.atomic_components.motion_stitch import transform_keypoint

        if getattr(avatar, "_x_s_kp", None) is None:
            avatar._x_s_kp = transform_keypoint(avatar.x_s_info)
        x_d = transform_keypoint(x_d_info)
        x_d = self.sdk.motion_stitch.stitch_net(avatar._x_s_kp, x_d)
        if getattr(avatar, "lip_delta", None) is not None:
            x_d = x_d + avatar.lip_delta      # close the portrait's open mouth before animating
        return avatar._x_s_kp, x_d

    def blink_template(self):
        """Ditto's 15-frame eye-closure expression template, or None."""
        return self.defaults.get("delta_eye_arr")

    def render_keypoints(self, avatar: Avatar, x_s: np.ndarray, x_d: np.ndarray, size: int = 512) -> np.ndarray:
        """Warps the cached appearance volume and decodes one frame. Tensors stay on
        the GPU between the two networks; returns HxWx3 uint8 RGB."""
        if self.tensorrt:
            import cv2

            img = self.sdk.decode_f3d(self.sdk.warp_f3d(avatar.f_s, x_s.astype(np.float32), x_d.astype(np.float32)))
            img = np.clip(img + 0.5, 0, 255).astype(np.uint8)
            return img if size == img.shape[0] else cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
        torch = self.torch
        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.float16):
            xs = torch.from_numpy(x_s).to(self.device)
            xd = torch.from_numpy(x_d).to(self.device)
            feat = self.warp(avatar.f_s, xs, xd)
            img = self.decoder(feat)
        img = img.float().clamp_(0, 1)
        if size != img.shape[-1]:
            img = torch.nn.functional.interpolate(img, size=(size, size), mode="area")
        return (img[0].permute(1, 2, 0) * 255.0 + 0.5).to(torch.uint8).cpu().numpy()

    def paste_back(self, avatar: Avatar, crop_frame_512: np.ndarray) -> np.ndarray:
        """Composites a rendered 512 crop back into the original portrait."""
        return self.sdk.putback(avatar.image_rgb, crop_frame_512.astype(np.float32), avatar.M_c2o)

    def gpu_memory(self) -> dict:
        t = self.torch
        return {"torch_alloc_gib": round(t.cuda.max_memory_allocated() / 2**30, 3),
                "torch_reserved_gib": round(t.cuda.max_memory_reserved() / 2**30, 3)}
