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
    
    def spawn_attack_particles(self, x, y, count=3):
        """Spawn particles for an attack hit."""
        colors = [(255, 200, 50), (255, 150, 30), (255, 100, 20), (255, 255, 100)]
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(30, 80)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            lifetime = random.uniform(0.2, 0.5)
            color = random.choice(colors)
            size = random.uniform(2, 4)
            self.particles.append(Particle(x, y, vx, vy, lifetime, color, size))
    
    def spawn_death_particles(self, x, y, count=8):
        """Spawn a burst of particles for a unit/building death."""
        colors = [(255, 100, 50), (200, 200, 100), (150, 150, 150), (100, 80, 60)]
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(40, 120)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            lifetime = random.uniform(0.4, 1.0)
            color = random.choice(colors)
            size = random.uniform(3, 6)
            self.particles.append(Particle(x, y, vx, vy, lifetime, color, size))
    
    def spawn_build_particles(self, x, y, count=5):
        """Spawn particles for building completion."""
        colors = [(200, 200, 200), (180, 180, 150), (220, 220, 220), (255, 255, 200)]
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(20, 50)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed - 20  # Bias upward
            lifetime = random.uniform(0.3, 0.7)
            color = random.choice(colors)
            size = random.uniform(2, 5)
            self.particles.append(Particle(x, y, vx, vy, lifetime, color, size))
    
    def spawn_gather_particles(self, x, y, count=2):
        """Spawn small particles for resource gathering."""
        colors = [(120, 180, 80), (100, 160, 60), (80, 140, 40)]
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(10, 30)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            lifetime = random.uniform(0.2, 0.4)
            color = random.choice(colors)
            size = random.uniform(1, 3)
            self.particles.append(Particle(x, y, vx, vy, lifetime, color, size))
