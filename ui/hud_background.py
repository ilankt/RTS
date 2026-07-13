"""9-slice HUD panel frames (§ visual polish).

A framed panel image (ornate stone/wood border around a flat centre) is drawn
via 9-slice so the border stays crisp at ANY target size: the four corners are
uniform-scaled, the four edges stretch along one axis only, and the centre
stretches to fill. That avoids the "squashed frame" you get from scaling the
whole image to a very different aspect ratio.

Near-black margins are trimmed on load (the source art is padded with black),
so panels never show a black border. Everything is cached per target size.

- render(w, h)         -> full framed panel (border + filled stone centre)
- render_border(w, h)  -> border only, transparent centre (for framing the map)
- content_rect(w, h)   -> the inner rectangle inside the border, so callers can
                          inset their content and it sits WITHIN the frame.
"""
import os

import pygame


class NineSliceFrame:
    def __init__(self, path, src_inset, dst_inset):
        # src_inset / dst_inset are (left, top, right, bottom) in pixels.
        # src = how much of the source edge is the ornate border (post-trim);
        # dst = how thick that border is drawn in the target.
        self.src_inset = src_inset
        self.dst_inset = dst_inset
        self.image = None
        self._cache = {}
        self._border_cache = {}
        try:
            if os.path.exists(path):
                self.image = self._trim_black(pygame.image.load(path).convert_alpha())
        except pygame.error:
            self.image = None

    @staticmethod
    def _trim_black(surf):
        """Crop the uniform near-black padding around the frame art."""
        try:
            import numpy as np
            arr = pygame.surfarray.array3d(surf)  # (w, h, 3)
            bright = arr.max(axis=2)
            cols = np.where(bright.max(axis=1) >= 16)[0]
            rows = np.where(bright.max(axis=0) >= 16)[0]
            if len(cols) == 0 or len(rows) == 0:
                return surf
            l, r, t, b = int(cols[0]), int(cols[-1]), int(rows[0]), int(rows[-1])
            return surf.subsurface(pygame.Rect(l, t, r - l + 1, b - t + 1)).copy()
        except Exception:
            return surf

    def _slice(self, tw, th, border_only, dst_inset=None):
        sl, st, sr, sb = self.src_inset
        dl, dt, dr, db = dst_inset or self.dst_inset
        dl = min(dl, tw // 2); dr = min(dr, tw // 2)
        dt = min(dt, th // 2); db = min(db, th // 2)
        sw, sh = self.image.get_size()
        xs = [0, sl, sw - sr, sw]
        ys = [0, st, sh - sb, sh]
        xd = [0, dl, tw - dr, tw]
        yd = [0, dt, th - db, th]
        dst = pygame.Surface((tw, th), pygame.SRCALPHA)
        for i in range(3):
            for j in range(3):
                if border_only and i == 1 and j == 1:
                    continue  # leave the centre transparent
                sw_, sh_ = xs[i + 1] - xs[i], ys[j + 1] - ys[j]
                dw_, dh_ = xd[i + 1] - xd[i], yd[j + 1] - yd[j]
                if sw_ <= 0 or sh_ <= 0 or dw_ <= 0 or dh_ <= 0:
                    continue
                piece = self.image.subsurface(pygame.Rect(xs[i], ys[j], sw_, sh_))
                piece = pygame.transform.smoothscale(piece, (dw_, dh_))
                dst.blit(piece, (xd[i], yd[j]))
        return dst

    def _cached(self, cache, width, height, border_only, dst_inset=None):
        if self.image is None or width <= 0 or height <= 0:
            return None
        key = (width, height, dst_inset)
        surf = cache.get(key)
        if surf is None:
            if len(cache) > 8:
                cache.clear()
            surf = self._slice(width, height, border_only, dst_inset)
            cache[key] = surf
        return surf

    def render(self, width, height):
        return self._cached(self._cache, width, height, False)

    def render_border(self, width, height, dst_inset=None):
        """Border only (transparent centre). dst_inset overrides the border
        thickness for this call (e.g. a thinner frame on the small minimap)."""
        return self._cached(self._border_cache, width, height, True, dst_inset)

    def content_rect(self, width, height):
        """Inner rectangle inside the drawn border."""
        dl, dt, dr, db = self.dst_inset
        dl = min(dl, width // 2); dr = min(dr, width // 2)
        dt = min(dt, height // 2); db = min(db, height // 2)
        return pygame.Rect(dl, dt, width - dl - dr, height - dt - db)
