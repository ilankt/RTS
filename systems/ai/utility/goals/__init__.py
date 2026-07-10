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
    BuildBlacksmithGoal,
    BuildSiegeWorkshopGoal,
    BuildWatchtowerGoal,
    BuildWallGoal,
    TrainWarriorGoal,
    TrainArcherGoal,
    TrainSpearmanGoal,
    TrainCavalryGoal,
    TrainRamGoal,
    ResearchImprovedToolsGoal,
    ResearchForgedBladesGoal,
    ResearchFletchingGoal,
    ResearchPaddedArmorGoal,
    ResearchReinforcedFramesGoal,
    ResearchSiegeEngineeringGoal,
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
    BuildBlacksmithGoal,
    BuildSiegeWorkshopGoal,
    BuildWatchtowerGoal,
    BuildWallGoal,
    TrainWarriorGoal,
    TrainArcherGoal,
    TrainSpearmanGoal,
    TrainCavalryGoal,
    TrainRamGoal,
    ResearchImprovedToolsGoal,
    ResearchForgedBladesGoal,
    ResearchFletchingGoal,
    ResearchPaddedArmorGoal,
    ResearchReinforcedFramesGoal,
    ResearchSiegeEngineeringGoal,
    # Economy
    TrainWorkerGoal,
    BuildHouseGoal,
    BuildFarmGoal,
    BuildLumbermillGoal,
    BuildMineGoal,
    BuildQuarryGoal,
]
