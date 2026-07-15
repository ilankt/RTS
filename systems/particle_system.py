"""Simple particle effects system for visual polish."""
import random
import math


class Particle:
    """A single particle with position, velocity, lifetime, and color."""

    def __init__(self, x, y, vx, vy, lifetime, color, size=3):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.color = color
        self.size = size
        self.alive = True

    def update(self, delta_time):
        """Update particle position and lifetime."""
        self.x += self.vx * delta_time
        self.y += self.vy * delta_time
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

    def update(self, delta_time):
        """Update all particles."""
        for p in self.particles:
            p.update(delta_time)
        self.particles = [p for p in self.particles if p.alive]

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

            # Fade out based on remaining life
            alpha = int(255 * (p.lifetime / p.max_lifetime))
            color = (*p.color, alpha)

            size = int(p.size * camera.zoom)
            if size < 1:
                size = 1

            # Create a small surface for the particle
            particle_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(particle_surf, color, (size, size), size)

            surface.blit(particle_surf, (int(screen_x) - size, int(screen_y) - size))

    def _burst(self, x, y, count, colors, speed_range, lifetime_range, size_range,
               vy_bias=0.0):
        rng = self._rng
        for _ in range(count):
            angle = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(*speed_range)
            vx = math.cos(angle) * speed
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
