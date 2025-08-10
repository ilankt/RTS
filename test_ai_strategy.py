#!/usr/bin/env python3
"""Test script to verify AI early game strategy"""

import sys
import time
from core.game import Game
from utils.debug_logger import debug_log

def test_ai_early_game():
    """Test that AI follows the early game build order: farm -> workers -> barracks"""
    print("Testing AI early game strategy...")
    print("Expected order: 1) Build farm, 2) Train workers to 5, 3) Build barracks")
    print("-" * 60)
    
    # Initialize game
    game = Game()
    
    # Let the game run for a bit to see AI decisions
    start_time = time.time()
    max_duration = 120  # 2 minutes max
    
    last_log_time = 0
    log_interval = 5  # Log every 5 seconds
    
    # Track milestones
    milestones = {
        "first_farm": False,
        "five_workers": False,
        "first_barracks": False
    }
    
    while time.time() - start_time < max_duration:
        # Update game
        delta_time = 0.016  # 60 FPS
        game.update(delta_time)
        
        # Check AI player (assuming player 2 is AI)
        ai_player = None
        for player in game.players:
            if hasattr(player, 'ai_type') and player.ai_type == "modular":
                ai_player = player
                break
                
        if not ai_player:
            print("ERROR: No AI player found!")
            break
            
        # Count AI assets
        ai_units = [u for u in game.units if u.player == ai_player]
        ai_workers = [u for u in ai_units if u.name == "worker"]
        ai_buildings = [b for b in game.buildings if b.player == ai_player]
        ai_farms = [b for b in ai_buildings if b.name == "farm"]
        ai_barracks = [b for b in ai_buildings if b.name == "barracks"]
        ai_construction = [s for s in game.construction_sites if s.player == ai_player]
        
        # Check milestones
        if (ai_farms or any(s.building_name == "farm" for s in ai_construction)) and not milestones["first_farm"]:
            milestones["first_farm"] = True
            print(f"[{time.time() - start_time:.1f}s] ✓ First farm built/started!")
            
        if len(ai_workers) >= 5 and not milestones["five_workers"]:
            milestones["five_workers"] = True
            print(f"[{time.time() - start_time:.1f}s] ✓ Reached 5 workers!")
            
        if (ai_barracks or any(s.building_name == "barracks" for s in ai_construction)) and not milestones["first_barracks"]:
            milestones["first_barracks"] = True
            print(f"[{time.time() - start_time:.1f}s] ✓ First barracks built/started!")
            
        # Periodic status log
        if time.time() - last_log_time > log_interval:
            last_log_time = time.time()
            resources = {k: int(v) for k, v in ai_player.resources.items()}
            print(f"[{time.time() - start_time:.1f}s] Workers: {len(ai_workers)}, Farms: {len(ai_farms)}, "
                  f"Barracks: {len(ai_barracks)}, Resources: {resources}")
            
            # Show what's being built
            if ai_construction:
                for site in ai_construction:
                    print(f"  - Building: {site.building_name} (progress: {site.construction_progress:.0%})")
                    
        # Check if all milestones achieved
        if all(milestones.values()):
            print(f"\n✅ SUCCESS! AI completed early game build order in {time.time() - start_time:.1f} seconds")
            break
            
        # Small delay to not overwhelm CPU
        time.sleep(0.01)
        
    # Final report
    print("\n" + "=" * 60)
    print("FINAL REPORT:")
    for milestone, achieved in milestones.items():
        status = "✓" if achieved else "✗"
        print(f"  {status} {milestone.replace('_', ' ').title()}")
        
    if not all(milestones.values()):
        print(f"\n❌ FAILED: AI did not complete build order in {max_duration} seconds")
    
if __name__ == "__main__":
    test_ai_early_game()