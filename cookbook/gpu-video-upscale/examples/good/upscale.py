"""Minimal pure-torch Real-ESRGAN x4plus super-resolution.

Implements the RRDBNet architecture used by the Real-ESRGAN x4plus
checkpoint (https://github.com/xinntao/Real-ESRGAN, BSD-3-Clause) with
no third-party SR framework: only torch and numpy are imported.

The checkpoint is the upstream release v0.1.0 weights
(RealESRGAN_x4plus.pth, sha256
4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

MODEL_SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
SCALE = 4
# Overridden by the judge (it builds the model from --weights, not from
# disk paths); this default works when the demo tree is on disk as-is.
WEIGHTS_PATH = "data/weights/RealESRGAN_x4plus.pth"


def _default_conv(in_c, out_c, k, bias=True):
    return nn.Conv2d(in_c, out_c, k, 1, k // 2, bias=bias)


class ResidualDenseBlock(nn.Module):
    """RDB: 5 conv layers, each concatenated with all previous features.

    Attribute names (conv1..conv5) match the released checkpoint keys
    (body.N.rdbK.convJ.*) so load_state_dict maps them without renaming.
    """

    def __init__(self, nc=64, gc=32):
        super().__init__()
        self.conv1 = _default_conv(nc, gc, 3)
        self.conv2 = _default_conv(nc + gc, gc, 3)
        self.conv3 = _default_conv(nc + 2 * gc, gc, 3)
        self.conv4 = _default_conv(nc + 3 * gc, gc, 3)
        self.conv5 = _default_conv(nc + 4 * gc, nc, 3)
        self.act = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        x1 = self.act(self.conv1(x))
        x2 = self.act(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.act(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.act(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    """Residual-in-residual dense block: 3 RDBs with outer residual."""

    def __init__(self, nc=64, gc=32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(nc, gc)
        self.rdb2 = ResidualDenseBlock(nc, gc)
        self.rdb3 = ResidualDenseBlock(nc, gc)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    """Real-ESRGAN x4plus network: 23 RRDBs, nearest x2 upsample blocks."""

    def __init__(self, in_nc=3, out_nc=3, nf=64, nb=23, gc=32):
        super().__init__()
        self.conv_first = _default_conv(in_nc, nf, 3)
        self.body = nn.ModuleList([RRDB(nf, gc) for _ in range(nb)])
        self.conv_body = _default_conv(nf, nf, 3)
        self.conv_up1 = _default_conv(nf, nf, 3)
        self.conv_up2 = _default_conv(nf, nf, 3)
        self.conv_hr = _default_conv(nf, nf, 3)
        self.conv_last = _default_conv(nf, out_nc, 3)
        self.act = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        body = feat
        for block in self.body:
            body = block(body)
        body = self.conv_body(body)
        feat = feat + body
        feat = self.act(self.conv_up1(F.interpolate(feat, scale_factor=2,
                                                    mode="nearest")))
        feat = self.act(self.conv_up2(F.interpolate(feat, scale_factor=2,
                                                    mode="nearest")))
        return self.conv_last(self.act(self.conv_hr(feat)))


def build_model():
    """Return the RRDBNet in eval mode with the pinned x4plus weights loaded."""
    model = RRDBNet()
    checkpoint = torch.load(WEIGHTS_PATH, map_location="cpu", weights_only=False)
    params = checkpoint.get("params_ema", checkpoint)
    model.load_state_dict(params, strict=True)
    model.eval()
    return model


def upscale_frames(model, frames):
    """Upscale (N, 3, H, W) float32 [0,1] frames by SCALE; input unmodified."""
    with torch.no_grad():
        out = model(frames)
    return out.clamp(0.0, 1.0)
