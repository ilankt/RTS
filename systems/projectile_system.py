import pygame
import math
import random
from typing import List, Tuple


class Projectile:
    """Base class for all projectiles"""
    def __init__(self, start_x: float, start_y: float, target_x: float, target_y: float, 
                 speed: float, damage: int, owner, color: Tuple[int, int, int] = (255, 255, 0)):
        self.x = start_x
        self.y = start_y
        self.target_x = target_x
        self.target_y = target_y
        self.speed = speed
        self.damage = damage
        self.owner = owner
        self.color = color
        self.alive = True
        
        # Calculate direction
        dx = target_x - start_x
        dy = target_y - start_y
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance > 0:
            self.velocity_x = (dx / distance) * speed
            self.velocity_y = (dy / distance) * speed
        else:
            self.velocity_x = 0
            self.velocity_y = 0
            
        # Trail effect
        self.trail = []
        self.max_trail_length = 5
        
    def update(self, delta_time: float) -> None:
        """Update projectile position"""
        if not self.alive:
            return
            
        # Store position for trail
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.max_trail_length:
            self.trail.pop(0)
            
        # Move projectile
        self.x += self.velocity_x * delta_time
        self.y += self.velocity_y * delta_time
        
        # Check if reached target
        distance_to_target = math.sqrt((self.x - self.target_x)**2 + (self.y - self.target_y)**2)
        if distance_to_target < 5:  # Close enough to target
            self.alive = False
            
    def draw(self, surface: pygame.Surface, camera) -> None:
        """Draw the projectile"""
        if not self.alive:
            return
            
        # Draw trail
        for i, (trail_x, trail_y) in enumerate(self.trail):
            screen_x = (trail_x * camera.zoom) + camera.x
            screen_y = (trail_y * camera.zoom) + camera.y
            color = tuple(int(c * (i / len(self.trail))) for c in self.color) if self.trail else self.color
            pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), 2)
            
        # Draw projectile
        screen_x = (self.x * camera.zoom) + camera.x
        screen_y = (self.y * camera.zoom) + camera.y
        pygame.draw.circle(surface, self.color, (int(screen_x), int(screen_y)), 3)


class Arrow(Projectile):
    """Arrow projectile for archers"""
    def __init__(self, start_x: float, start_y: float, target_x: float, target_y: float, 
                 speed: float, damage: int, owner):
        super().__init__(start_x, start_y, target_x, target_y, speed, damage, owner, (139, 69, 19))  # Brown
        self.max_trail_length = 3
        
    def draw(self, surface: pygame.Surface, camera) -> None:
        """Draw arrow as a line"""
        if not self.alive:
            return
            
        screen_x = (self.x * camera.zoom) + camera.x
        screen_y = (self.y * camera.zoom) + camera.y
        
        # Calculate arrow direction
        angle = math.atan2(self.velocity_y, self.velocity_x)
        
        # Arrow length
        arrow_length = 10
        
        # Calculate arrow endpoints
        end_x = screen_x - math.cos(angle) * arrow_length
        end_y = screen_y - math.sin(angle) * arrow_length
        
        # Draw arrow shaft
        pygame.draw.line(surface, self.color, (int(screen_x), int(screen_y)), 
                        (int(end_x), int(end_y)), 2)
        
        # Draw arrowhead
        arrowhead_size = 4
        angle1 = angle + 2.5
        angle2 = angle - 2.5
        
        point1_x = screen_x - math.cos(angle1) * arrowhead_size
        point1_y = screen_y - math.sin(angle1) * arrowhead_size
        
        point2_x = screen_x - math.cos(angle2) * arrowhead_size
        point2_y = screen_y - math.sin(angle2) * arrowhead_size
        
        pygame.draw.polygon(surface, self.color, [
            (int(screen_x), int(screen_y)),
            (int(point1_x), int(point1_y)),
            (int(point2_x), int(point2_y))
        ])


class CannonBall(Projectile):
    """Cannon ball projectile for siege units/watchtowers"""
    def __init__(self, start_x: float, start_y: float, target_x: float, target_y: float, 
                 speed: float, damage: int, owner):
        super().__init__(start_x, start_y, target_x, target_y, speed, damage, owner, (64, 64, 64))  # Dark gray
        self.max_trail_length = 8
        self.size = 5
        
    def draw(self, surface: pygame.Surface, camera) -> None:
        """Draw cannonball with shadow effect"""
        if not self.alive:
            return
            
        # Draw trail with decreasing size
        for i, (trail_x, trail_y) in enumerate(self.trail):
            screen_x = (trail_x * camera.zoom) + camera.x
            screen_y = (trail_y * camera.zoom) + camera.y
            size = int(self.size * (i / len(self.trail))) if self.trail else self.size
            color = tuple(int(c * (i / len(self.trail))) for c in self.color) if self.trail else self.color
            if size > 0:
                pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), size)
        
        # Draw main projectile
        screen_x = (self.x * camera.zoom) + camera.x
        screen_y = (self.y * camera.zoom) + camera.y
        
        # Shadow
        pygame.draw.circle(surface, (32, 32, 32), (int(screen_x + 2), int(screen_y + 2)), self.size)
        # Main ball
        pygame.draw.circle(surface, self.color, (int(screen_x), int(screen_y)), self.size)
        # Highlight
        pygame.draw.circle(surface, (128, 128, 128), (int(screen_x - 1), int(screen_y - 1)), 2)


class MagicBolt(Projectile):
    """Magic projectile with particle effects"""
    def __init__(self, start_x: float, start_y: float, target_x: float, target_y: float, 
                 speed: float, damage: int, owner, color: Tuple[int, int, int] = (128, 0, 255)):
        super().__init__(start_x, start_y, target_x, target_y, speed, damage, owner, color)
        self.particles = []
        self.max_trail_length = 10
        
    def update(self, delta_time: float) -> None:
        """Update with particle generation"""
        super().update(delta_time)
        
        # Generate particles
        if self.alive and random.random() < 0.8:
            particle = {
                'x': self.x + random.uniform(-3, 3),
                'y': self.y + random.uniform(-3, 3),
                'vx': random.uniform(-20, 20),
                'vy': random.uniform(-20, 20),
                'life': 1.0
            }
            self.particles.append(particle)
            
        # Update particles
        for particle in self.particles[:]:
            particle['x'] += particle['vx'] * delta_time
            particle['y'] += particle['vy'] * delta_time
            particle['life'] -= delta_time * 2
            
            if particle['life'] <= 0:
                self.particles.remove(particle)
                
    def draw(self, surface: pygame.Surface, camera) -> None:
        """Draw magic bolt with particles"""
        if not self.alive and not self.particles:
            return
            
        # Draw particles
        for particle in self.particles:
            screen_x = (particle['x'] * camera.zoom) + camera.x
            screen_y = (particle['y'] * camera.zoom) + camera.y
            size = int(3 * particle['life'])
            if size > 0:
                color = tuple(int(c * particle['life']) for c in self.color)
                pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), size)
                
        if self.alive:
            # Draw glowing core
            screen_x = (self.x * camera.zoom) + camera.x
            screen_y = (self.y * camera.zoom) + camera.y
            
            # Outer glow
            for i in range(3, 0, -1):
                alpha = 64 // i
                color = tuple(min(255, c + alpha) for c in self.color)
                pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), 3 + i * 2, 1)
                
            # Inner core
            pygame.draw.circle(surface, (255, 255, 255), (int(screen_x), int(screen_y)), 3)
            pygame.draw.circle(surface, self.color, (int(screen_x), int(screen_y)), 2)


class ProjectileSystem:
    """Manages all projectiles in the game"""
    def __init__(self, game):
        self.game = game
        self.projectiles: List[Projectile] = []
        
    def create_projectile(self, attacker, target, damage: int) -> None:
        """Create a projectile based on attacker type"""
        # Get attacker position (could be unit or building)
        start_x = attacker.x
        start_y = attacker.y
        
        # Get target position
        target_x = target.x
        target_y = target.y
        
        # Determine projectile type based on attacker
        projectile = None
        
        if hasattr(attacker, 'name'):
            if attacker.name == "archer":
                # Arrows are fast
                projectile = Arrow(start_x, start_y, target_x, target_y, 300, damage, attacker)
            elif attacker.name == "watchtower":
                # Cannonballs are slower but impactful
                projectile = CannonBall(start_x, start_y, target_x, target_y, 200, damage, attacker)
            elif attacker.name in ("warrior", "spearman", "cavalry", "ram"):
                # Melee and ram attacks don't use projectiles.
                return
            else:
                # Default projectile
                projectile = Projectile(start_x, start_y, target_x, target_y, 250, damage, attacker)
                
        if projectile:
            self.projectiles.append(projectile)
            
    def update(self, delta_time: float) -> None:
        """Update all projectiles, then drop dead ones in a single pass"""
        any_dead = False
        for projectile in self.projectiles:
            projectile.update(delta_time)
            if not projectile.alive:
                any_dead = True
        if any_dead:
            self.projectiles = [p for p in self.projectiles if p.alive]
                
    def draw(self, surface: pygame.Surface, camera) -> None:
        """Draw all projectiles"""
        for projectile in self.projectiles:
            projectile.draw(surface, camera)
            
    def clear(self) -> None:
        """Clear all projectiles"""
        self.projectiles.clear()
