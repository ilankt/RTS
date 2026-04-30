from .economy import (
    TrainWorkerGoal,
    BuildFarmGoal,
    BuildHouseGoal,
    BuildLumbermillGoal,
    BuildMineGoal,
    BuildQuarryGoal,
)
from .military import (
    BuildBarracksGoal,
    BuildStableGoal,
    TrainWarriorGoal,
    TrainArcherGoal,
    TrainSpearmanGoal,
    TrainCavalryGoal,
)
from .tactical import (
    DefendBaseGoal,
    AttackGoal,
    ScoutGoal,
)


ALL_GOALS = [
    # Tactical first — DefendBase has the highest possible scores
    DefendBaseGoal,
    AttackGoal,
    ScoutGoal,
    # Military structures and training
    BuildBarracksGoal,
    BuildStableGoal,
    TrainWarriorGoal,
    TrainArcherGoal,
    TrainSpearmanGoal,
    TrainCavalryGoal,
    # Economy
    TrainWorkerGoal,
    BuildHouseGoal,
    BuildFarmGoal,
    BuildLumbermillGoal,
    BuildMineGoal,
    BuildQuarryGoal,
]
