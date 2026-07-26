"""Simple particle effects system for visual polish."""
import random
import math


class Particle:
    """A single particle with position, velocity, lifetime, and color.

    `soft`/`growth`/`drag`/`alpha` exist for smoke (§11.3). A hard-edged disc
    at full alpha reads as a BUBBLE, not a puff — smoke needs a soft edge, it
    has to swell as it rises, and it has to stay translucent. Sparks and dust
    keep the crisp default.
    """

    def __init__(self, x, y, vx, vy, lifetime, color, size=3,
                 growth=0.0, drag=0.0, alpha=255, soft=False):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.color = color
        self.size = size
        self.growth = growth
        self.drag = drag
        self.alpha = alpha
        self.soft = soft
        self.alive = True

    def update(self, delta_time):
        """Update particle position, size and lifetime."""
        self.x += self.vx * delta_time
        self.y += self.vy * delta_time
        if self.drag:
            damping = max(0.0, 1.0 - self.drag * delta_time)
            self.vx *= damping
            self.vy *= damping
        if self.growth:
            self.size += self.growth * delta_time
        self.lifetime -= delta_time
        if self.lifetime <= 0:
            self.alive = False


class ParticleSystem:
    """Manages and renders particle effects."""

    def __init__(self, game):
        self.game = game
        self.particles = []
        # Own RNG: particle bursts must not consume the seeded global random
        # stream the map gen / AI / balance sims depend on.
        self._rng = random.Random(9137)
        self._disc_cache = {}   # (radius, colour) -> soft puff surface

    def update(self, delta_time):
        """Update all particles."""
        for p in self.particles:
            p.update(delta_time)
        self.particles = [p for p in self.particles if p.alive]

    # Soft puffs are cached per (radius, colour). Radii are quantised so a
    # growing plume reuses a handful of surfaces instead of building one per
    # particle per frame.
    _SOFT_RADIUS_STEP = 2
    _SOFT_CACHE_MAX = 256

    def _soft_disc(self, radius, color):
        """A radial-gradient disc: opaque core fading to nothing at the rim."""
        import pygame

        key = (radius, color)
        disc = self._disc_cache.get(key)
        if disc is not None:
            return disc
        if len(self._disc_cache) > self._SOFT_CACHE_MAX:
            self._disc_cache.clear()
        size = radius * 2
        disc = pygame.Surface((size, size), pygame.SRCALPHA)
        # Outside in: pygame.draw writes pixels directly (no blending), so
        # each smaller ring simply overwrites with a stronger alpha.
        for r in range(radius, 0, -1):
            # ^1.15 rather than a steeper curve: at ^1.5 only a small core
            # carried any alpha and the plume was nearly invisible in game.
            edge = 1.0 - r / radius
            pygame.draw.circle(disc, (*color, int(255 * edge ** 1.15)),
                               (radius, radius), r)
        self._disc_cache[key] = disc
        return disc

    def draw(self, surface, camera):
        """Draw all particles on the map surface."""
        import pygame

        for p in self.particles:
            screen_x = (p.x * camera.zoom) + camera.x
            screen_y = (p.y * camera.zoom) + camera.y

            # Skip off-screen particles
            if (screen_x < -20 or screen_x > surface.get_width() + 20 or
                screen_y < -20 or screen_y > surface.get_height() + 20):
                continue

            life = p.lifetime / p.max_lifetime
            size = int(p.size * camera.zoom)
            if size < 1:
                size = 1

            if p.soft:
                # Fade IN briefly too, or a puff pops into being at full size
                age = p.max_lifetime - p.lifetime
                fade = min(1.0, age / 0.3) * life
                radius = max(2, (size // self._SOFT_RADIUS_STEP)
                             * self._SOFT_RADIUS_STEP)
                disc = self._soft_disc(radius, p.color)
                disc.set_alpha(int(p.alpha * fade))
                surface.blit(disc, (int(screen_x) - radius,
                                    int(screen_y) - radius))
                continue

            color = (*p.color, int(p.alpha * life))
            particle_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(particle_surf, color, (size, size), size)
            surface.blit(particle_surf, (int(screen_x) - size, int(screen_y) - size))

    def _burst(self, x, y, count, colors, speed_range, lifetime_range, size_range,
               vy_bias=0.0, vx_bias=0.0):
        rng = self._rng
        for _ in range(count):
            angle = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(*speed_range)
            vx = math.cos(angle) * speed + vx_bias
            vy = math.sin(angle) * speed + vy_bias
            lifetime = rng.uniform(*lifetime_range)
            color = rng.choice(colors)
            size = rng.uniform(*size_range)
            self.particles.append(Particle(x, y, vx, vy, lifetime, color, size))

    def spawn_attack_particles(self, x, y, count=3):
        """Spawn particles for an attack hit."""
        self._burst(x, y, count,
                    [(255, 200, 50), (255, 150, 30), (255, 100, 20), (255, 255, 100)],
                    (30, 80), (0.2, 0.5), (2, 4))

    def spawn_death_particles(self, x, y, count=8):
        """Spawn a burst of particles for a unit/building death."""
        self._burst(x, y, count,
                    [(255, 100, 50), (200, 200, 100), (150, 150, 150), (100, 80, 60)],
                    (40, 120), (0.4, 1.0), (3, 6))

    def spawn_build_particles(self, x, y, count=5):
        """Spawn particles for building construction/completion."""
        self._burst(x, y, count,
                    [(200, 200, 200), (180, 180, 150), (220, 220, 220), (255, 255, 200)],
                    (20, 50), (0.3, 0.7), (2, 5), vy_bias=-20)

    def spawn_gather_particles(self, x, y, count=2):
        """Spawn small particles for resource gathering."""
        self._burst(x, y, count,
                    [(120, 180, 80), (100, 160, 60), (80, 140, 40)],
                    (10, 30), (0.2, 0.4), (1, 3))

    # ---- §8.5 VFX/juice presets ------------------------------------- #

    def spawn_move_dust(self, x, y, count=2):
        """Small dusty puffs at a fast mover's feet."""
        self._burst(x, y, count,
                    [(150, 130, 100), (170, 150, 120), (130, 115, 90)],
                    (5, 20), (0.25, 0.5), (1, 3), vy_bias=-8)

    def spawn_muzzle_flash(self, x, y, count=3):
        """Brief bright flash where a projectile leaves the attacker."""
        self._burst(x, y, count,
                    [(255, 255, 200), (255, 230, 140), (255, 255, 255)],
                    (15, 45), (0.08, 0.18), (2, 4))

    def spawn_impact_flash(self, x, y, count=4):
        """Punchier flash where a projectile lands."""
        self._burst(x, y, count,
                    [(255, 220, 120), (255, 170, 60), (255, 255, 220)],
                    (40, 110), (0.12, 0.28), (2, 5))

    def spawn_fountain_sparkles(self, x, y, count=2):
        """Blue healing motes drifting up from a fountain (§8.9)."""
        self._burst(x, y, count,
                    [(120, 200, 255), (170, 225, 255), (90, 160, 240)],
                    (8, 25), (0.5, 1.0), (1, 3), vy_bias=-22)

    # ---- §11.3 ambient smoke ----------------------------------------- #
    # Both lean on `wind_x`, the same wind vector that drives tree sway and
    # cloud drift, so smoke agrees with the rest of the world instead of
    # rising in its own private calm.

    def _smoke(self, x, y, count, colors, rise, lifetime, size, growth,
               alpha, wind_x):
        """Shared smoke emitter. Deliberately NOT `_burst`: a burst throws
        particles out radially, which is what made the first version look like
        blown bubbles. Smoke leaves from one spot, rises, swells and thins."""
        rng = self._rng
        for _ in range(count):
            self.particles.append(Particle(
                x + rng.uniform(-2.5, 2.5),
                y + rng.uniform(-2.0, 2.0),
                wind_x * rng.uniform(0.55, 1.15) + rng.uniform(-5.0, 5.0),
                rng.uniform(*rise),
                rng.uniform(*lifetime),
                rng.choice(colors),
                size=rng.uniform(*size),
                growth=rng.uniform(*growth),
                drag=0.35,          # the rise slows as the puff spreads
                alpha=alpha,
                soft=True))

    def spawn_chimney_smoke(self, x, y, count=1, wind_x=0.0):
        """Lazy hearth smoke from an inhabited building. Slow, pale and
        long-lived — it should read as a wisp, never as damage."""
        self._smoke(x, y, count,
                    [(206, 206, 211), (188, 190, 196), (216, 216, 220)],
                    rise=(-21, -13), lifetime=(2.4, 3.6), size=(3.5, 5.0),
                    growth=(5.0, 8.5), alpha=132, wind_x=wind_x)

    def spawn_damage_smoke(self, x, y, count=1, wind_x=0.0):
        """Dark smoke from a badly hurt building. Dual purpose: atmosphere,
        and readability — a burning building is legible at a glance without
        parsing its health bar."""
        self._smoke(x, y, count,
                    [(74, 70, 66), (96, 91, 86), (54, 51, 49), (118, 110, 104)],
                    rise=(-30, -19), lifetime=(1.8, 2.8), size=(4.0, 6.0),
                    growth=(9.0, 14.0), alpha=198, wind_x=wind_x)
